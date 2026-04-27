"""Cypher templates for the bitemporal graph model.

Conventions:
  - (:Entity {id, kb_id, type, canonical_name, aliases})
  - (:Document {id, kb_id, title, source_date})
  - (:Entity)-[:MENTIONED_IN {observation_date, confidence, chunk_id}]->(:Document)
  - (:Entity)-[:RELATED_TO {type, valid_from, valid_to, tx_from, tx_to,
                            source_doc_id, confidence}]->(:Entity)
  - (:Document)-[:SUPERSEDES]->(:Document)
"""
from __future__ import annotations

ENSURE_CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE INDEX entity_kb IF NOT EXISTS FOR (e:Entity) ON (e.kb_id)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
    "CREATE INDEX entity_canonical IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name)",
    "CREATE INDEX document_kb IF NOT EXISTS FOR (d:Document) ON (d.kb_id)",
    "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS "
    "FOR (e:Entity) ON EACH [e.canonical_name, e.aliases]",
]


MERGE_DOCUMENT = """
MERGE (d:Document {id: $doc_id})
SET d.kb_id = $kb_id,
    d.title = $title,
    d.source_date = date($source_date)
RETURN d.id as id
"""

MERGE_SUPERSEDES = """
MATCH (new:Document {id: $new_id}), (old:Document {id: $old_id})
MERGE (new)-[:SUPERSEDES]->(old)
"""

MERGE_ENTITY = """
MERGE (e:Entity {id: $id})
ON CREATE SET e.kb_id = $kb_id,
              e.type = $type,
              e.canonical_name = $canonical_name,
              e.aliases = $aliases,
              e.created_at = datetime()
ON MATCH  SET e.aliases = apoc.coll.toSet(coalesce(e.aliases, []) + $aliases)
RETURN e.id as id
"""

# fallback (without APOC): de-dup aliases in Python before passing
MERGE_ENTITY_NOAPOC = """
MERGE (e:Entity {id: $id})
ON CREATE SET e.kb_id = $kb_id,
              e.type = $type,
              e.canonical_name = $canonical_name,
              e.aliases = $aliases,
              e.created_at = datetime()
ON MATCH  SET e.aliases = $aliases
RETURN e.id as id
"""

MERGE_MENTIONED_IN = """
MATCH (e:Entity {id: $entity_id}), (d:Document {id: $doc_id})
MERGE (e)-[r:MENTIONED_IN {chunk_id: $chunk_id}]->(d)
ON CREATE SET r.observation_date = CASE WHEN $observation_date IS NULL
                                       THEN null ELSE date($observation_date) END,
              r.confidence = $confidence
"""

MERGE_RELATED_TO = """
MATCH (a:Entity {id: $src_id}), (b:Entity {id: $dst_id})
MERGE (a)-[r:RELATED_TO {type: $type, source_doc_id: $source_doc_id}]->(b)
ON CREATE SET r.valid_from = CASE WHEN $valid_from IS NULL THEN null ELSE date($valid_from) END,
              r.valid_to   = CASE WHEN $valid_to   IS NULL THEN null ELSE date($valid_to)   END,
              r.tx_from    = datetime(),
              r.tx_to      = null,
              r.confidence = $confidence
"""

# When a doc is amended, contradicting older facts gets `tx_to = now()`.
CLOSE_TX_FOR_DOC_FACTS = """
MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
WHERE r.source_doc_id = $old_doc_id AND r.tx_to IS NULL
SET r.tx_to = datetime()
"""

DELETE_DOC_CASCADE = """
MATCH (d:Document {id: $doc_id})
OPTIONAL MATCH (e:Entity)-[r:RELATED_TO]-() WHERE r.source_doc_id = $doc_id
DELETE r
WITH d
OPTIONAL MATCH (d)<-[m:MENTIONED_IN]-()
DELETE m
WITH d
DETACH DELETE d
"""

CLEANUP_ORPHAN_ENTITIES = """
MATCH (e:Entity {kb_id: $kb_id})
WHERE NOT (e)-[:MENTIONED_IN]->(:Document)
  AND NOT (e)-[:RELATED_TO]-(:Entity)
DETACH DELETE e
"""


# === Retrieval queries ===

ENTITY_FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('entity_fulltext', $q)
YIELD node, score
WHERE node.kb_id = $kb_id
RETURN node.id AS id, node.type AS type, node.canonical_name AS canonical_name,
       node.aliases AS aliases, score
ORDER BY score DESC LIMIT $k
"""

ENTITY_TIMELINE = """
MATCH (e:Entity {id: $entity_id})-[r:RELATED_TO]-(other:Entity)
WHERE ($start IS NULL OR r.valid_to IS NULL OR r.valid_to >= date($start))
  AND ($end   IS NULL OR r.valid_from IS NULL OR r.valid_from <= date($end))
  AND ($include_superseded = true OR r.tx_to IS NULL)
OPTIONAL MATCH (d:Document {id: r.source_doc_id})
RETURN e.id as entity_id, other.id as related_entity_id,
       other.canonical_name as related_canonical_name,
       r.type as type, r.valid_from as valid_from, r.valid_to as valid_to,
       r.confidence as confidence,
       d.id as source_doc_id, d.title as source_doc_title, d.source_date as source_date
ORDER BY coalesce(r.valid_from, r.tx_from) DESC
LIMIT 200
"""

EXPAND_NEIGHBOURS = """
UNWIND $entity_ids AS eid
MATCH (e:Entity {id: eid})-[r:RELATED_TO]-(n:Entity)
WHERE ($start IS NULL OR r.valid_to IS NULL OR r.valid_to >= date($start))
  AND ($end   IS NULL OR r.valid_from IS NULL OR r.valid_from <= date($end))
RETURN DISTINCT n.id AS id, n.canonical_name AS canonical_name, n.type AS type
LIMIT 200
"""

ENTITIES_FOR_CHUNKS = """
UNWIND $chunk_ids AS cid
MATCH (e:Entity)-[m:MENTIONED_IN {chunk_id: cid}]->(:Document)
RETURN cid AS chunk_id, collect(DISTINCT e.id) AS entity_ids
"""
