import pytest

from app.retrieval.temporal_intent import detect


@pytest.mark.asyncio
async def test_detects_year_range():
    intent = await detect("Quelle a été l'évolution du projet entre 2020 et 2024 ?")
    assert intent.date_range is not None
    a, b = intent.date_range
    assert a.year == 2020 and b.year == 2024


@pytest.mark.asyncio
async def test_detects_global_intent():
    intent = await detect("Donne-moi une synthèse des grandes thématiques du conseil")
    assert intent.mode == "global"


@pytest.mark.asyncio
async def test_local_default():
    intent = await detect("Qui est le maire ?")
    assert intent.mode == "local"
