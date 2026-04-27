"""Detects temporal intent + resolves anchor date."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from app.services.llm import chat_complete


@dataclass
class TemporalIntent:
    mode: str = "local"  # local | global
    date_range: tuple[date, date] | None = None
    anchor_date: date | None = None
    target_entities: list[str] = field(default_factory=list)


_DATE_PAT = re.compile(r"\b(20\d{2}|19\d{2})\b")
_GLOBAL_HINTS = ("synthèse", "synthese", "vue d'ensemble", "thématique", "thematique",
                 "panorama", "résumé", "resume", "tendances")


async def detect(query: str, kb_max_date: date | None = None) -> TemporalIntent:
    today = datetime.now(timezone.utc).date()
    out = TemporalIntent(anchor_date=kb_max_date or today)

    # Cheap heuristic first
    years = _DATE_PAT.findall(query)
    if len(years) >= 2:
        a, b = sorted(int(y) for y in years[:2])
        out.date_range = (date(a, 1, 1), date(b, 12, 31))
    elif len(years) == 1:
        y = int(years[0])
        out.date_range = (date(y, 1, 1), date(y, 12, 31))

    if any(h in query.lower() for h in _GLOBAL_HINTS):
        out.mode = "global"

    if not settings.openai_api_key:
        return out

    # LLM refinement
    sys = (
        "Tu analyses une requête utilisateur sur une base de connaissance temporelle. "
        "Réponds en JSON STRICT avec : "
        '{"mode":"local|global","date_range":[YYYY-MM-DD,YYYY-MM-DD]|null,'
        '"anchor_date":"YYYY-MM-DD"|null,"target_entities":[string]}.'
        " Si la requête mentionne 'dernier' / 'récent' utilise anchor_date = aujourd'hui."
        " Si la requête est thématique large, mode = 'global'."
    )
    res = await chat_complete(
        system=sys,
        messages=[{"role": "user", "content": query}],
        model=settings.openai_model_routing,
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    try:
        data = json.loads(res["text"]) if res["text"] else {}
    except json.JSONDecodeError:
        return out

    if data.get("mode") in ("local", "global"):
        out.mode = data["mode"]
    dr = data.get("date_range")
    if isinstance(dr, list) and len(dr) == 2:
        try:
            out.date_range = (date.fromisoformat(dr[0]), date.fromisoformat(dr[1]))
        except (ValueError, TypeError):
            pass
    if data.get("anchor_date"):
        try:
            out.anchor_date = date.fromisoformat(data["anchor_date"])
        except (ValueError, TypeError):
            pass
    out.target_entities = [s for s in data.get("target_entities", []) if isinstance(s, str)]
    return out
