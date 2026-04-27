import uuid

from app.ingestion.resolver import _normalize, stable_entity_id


def test_normalize_strips_diacritics_and_case():
    assert _normalize("Saint-Étienne") == "saint-etienne"
    assert _normalize("  CONSEIL    Municipal  ") == "conseil municipal"


def test_stable_entity_id_is_deterministic():
    kb = uuid.UUID("00000000-0000-0000-0000-000000000001")
    a = stable_entity_id(kb, "Person", "Jean Dupont")
    b = stable_entity_id(kb, "Person", "  jean  dupont  ")
    assert a == b


def test_stable_entity_id_differs_per_type():
    kb = uuid.UUID("00000000-0000-0000-0000-000000000001")
    a = stable_entity_id(kb, "Person", "Mairie de X")
    b = stable_entity_id(kb, "Organization", "Mairie de X")
    assert a != b
