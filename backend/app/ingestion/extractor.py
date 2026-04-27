"""Entity + relation extraction with explicit temporal fields.

Uses OpenAI function calling with a strict JSON schema. In dev / no-key mode,
returns an empty extraction (still allows the rest of the pipeline to run).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from app.services.llm import chat_complete, cost_usd
from app.config import settings


@dataclass
class ExtractedEntity:
    local_id: str               # local within this chunk extraction
    type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class ExtractedRelation:
    src_local_id: str
    dst_local_id: str
    type: str
    valid_from: str | None = None
    valid_to: str | None = None
    observation_date: str | None = None
    confidence: float = 0.7


@dataclass
class ExtractionOut:
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]
    document_date: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float


SYSTEM_PROMPT = """\
Tu es un extracteur d'entités et relations TEMPORELLES pour des documents
français : comptes-rendus de conseil municipal, délibérations, arrêtés,
textes de loi, articles de presse, rapports.

Pour chaque chunk, identifie :
- entités notables : Person (élu, fonctionnaire, citoyen cité), Organization
  (mairie, conseil, entreprise), Project (projet d'urbanisme, plan, programme),
  Location (commune, lieu-dit), Document (loi, arrêté), Concept (politique
  publique, thématique).
- relations entre entités, AVEC dates lorsque possible :
  valid_from = date à partir de laquelle le fait est vrai
  valid_to   = date à partir de laquelle le fait n'est plus vrai (null si toujours valide)
  observation_date = date à laquelle le fait est constaté/déclaré dans le doc.

Si une date n'apparaît pas dans le texte mais est clairement le contexte du
document, utilise la date du document. Sinon laisse null.

Indique aussi document_date = date principale du document si tu peux la
déduire (ex. "séance du 12 mars 2023" → 2023-03-12).
"""


def _tool_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_extraction",
            "description": "Soumet l'extraction d'entités et relations temporelles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_date": {
                        "type": ["string", "null"],
                        "description": "ISO-8601 date principale du document (ex. 2023-03-12)",
                    },
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "local_id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["Person", "Organization", "Project",
                                             "Location", "Document", "Concept", "Event"],
                                },
                                "canonical_name": {"type": "string"},
                                "aliases": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["local_id", "type", "canonical_name"],
                        },
                    },
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "src_local_id": {"type": "string"},
                                "dst_local_id": {"type": "string"},
                                "type": {"type": "string"},
                                "valid_from": {"type": ["string", "null"]},
                                "valid_to": {"type": ["string", "null"]},
                                "observation_date": {"type": ["string", "null"]},
                                "confidence": {"type": "number"},
                            },
                            "required": ["src_local_id", "dst_local_id", "type"],
                        },
                    },
                },
                "required": ["entities", "relations"],
            },
        },
    }


async def extract_chunk(
    text: str, doc_title: str, doc_hint_date: date | None = None
) -> ExtractionOut:
    """Extract entities + relations from a single chunk."""
    if not settings.openai_api_key:
        return ExtractionOut([], [], None, 0, 0, 0.0)

    user = (
        f"Document: {doc_title}\n"
        f"Date probable du document: {doc_hint_date.isoformat() if doc_hint_date else 'inconnue'}\n\n"
        f"Texte du chunk :\n---\n{text}\n---\n\n"
        "Renvoie l'extraction via la fonction submit_extraction."
    )
    res = await chat_complete(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        model=settings.openai_model_extraction,
        tools=[_tool_schema()],
        tool_choice={"type": "function", "function": {"name": "submit_extraction"}},
        temperature=0.1,
    )
    args: dict = {}
    if res["tool_calls"]:
        try:
            args = json.loads(res["tool_calls"][0]["arguments"])
        except json.JSONDecodeError:
            args = {}

    ents = [
        ExtractedEntity(
            local_id=e["local_id"],
            type=e["type"],
            canonical_name=e["canonical_name"],
            aliases=e.get("aliases", []),
        )
        for e in args.get("entities", [])
    ]
    rels = [
        ExtractedRelation(
            src_local_id=r["src_local_id"],
            dst_local_id=r["dst_local_id"],
            type=r["type"],
            valid_from=r.get("valid_from"),
            valid_to=r.get("valid_to"),
            observation_date=r.get("observation_date"),
            confidence=r.get("confidence", 0.7),
        )
        for r in args.get("relations", [])
    ]
    return ExtractionOut(
        entities=ents,
        relations=rels,
        document_date=args.get("document_date"),
        tokens_in=res["tokens_in"],
        tokens_out=res["tokens_out"],
        cost_usd=cost_usd(res["model"], res["tokens_in"], res["tokens_out"]),
    )
