"""Pure unit tests for document_state — no DB required (mock session)."""
import pytest

from app.services import document_state


class _FakeDoc:
    def __init__(self, state):
        self.state = state
        self.id = "fake"


class _FakeSession:
    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_legal_transition():
    doc = _FakeDoc("proposed")
    session = _FakeSession()
    await document_state.transition(session, doc, "approved", actor_id=None)
    assert doc.state == "approved"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_illegal_transition_raises():
    doc = _FakeDoc("rejected")
    session = _FakeSession()
    with pytest.raises(document_state.IllegalStateTransition):
        await document_state.transition(session, doc, "ingested", actor_id=None)


@pytest.mark.asyncio
async def test_terminal_deleted_blocks_further_transitions():
    doc = _FakeDoc("deleted")
    session = _FakeSession()
    with pytest.raises(document_state.IllegalStateTransition):
        await document_state.transition(session, doc, "approved", actor_id=None)
