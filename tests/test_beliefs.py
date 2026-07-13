"""Bi-temporal belief store — offline unit tests (stdlib sqlite, no network)."""

from __future__ import annotations

from auralynq.beliefs import BeliefStore, get_belief_store
from auralynq.config.settings import get_settings

T1 = "2020-01-01T00:00:00+00:00"
T2 = "2021-06-01T00:00:00+00:00"
T3 = "2022-12-31T00:00:00+00:00"


def _store(tmp_path) -> BeliefStore:
    return BeliefStore(tmp_path / "beliefs.db")


def test_record_and_current(tmp_path):
    s = _store(tmp_path)
    cid = s.record_claim("Acme", "ceo", "Alice", source="doc1.pdf", valid_from=T1)
    assert cid
    got = s.get(cid)
    assert got is not None
    assert got.entity == "Acme" and got.object == "Alice"
    assert got.valid_to is None and got.superseded_by is None
    current = s.current("Acme")
    assert [c.object for c in current] == ["Alice"]
    assert s.count() == 1


def test_record_is_idempotent(tmp_path):
    s = _store(tmp_path)
    a = s.record_claim("Acme", "ceo", "Alice", source="doc1.pdf")
    b = s.record_claim("Acme", "ceo", "Alice", source="doc1.pdf")
    assert a == b
    assert s.count() == 1


def test_revise_supersedes_and_time_travels(tmp_path):
    s = _store(tmp_path)
    old = s.revise("Acme", "ceo", "Alice", source="2020.pdf", valid_from=T1)
    new = s.revise("Acme", "ceo", "Bob", source="2021.pdf", valid_from=T2)
    assert old != new

    # The prior claim is closed at the revision's valid-time and linked forward.
    old_claim = s.get(old)
    assert old_claim is not None
    assert old_claim.valid_to == T2
    assert old_claim.superseded_by == new

    # Only the new belief is current.
    assert [c.object for c in s.current("Acme")] == ["Bob"]

    # Valid-time travel: who was CEO at T1 vs T3?
    assert [c.object for c in s.as_of("Acme", T1)] == ["Alice"]
    assert [c.object for c in s.as_of("Acme", T3)] == ["Bob"]

    # History is ordered oldest-first and retains both revisions.
    hist = s.history("Acme")
    assert [c.object for c in hist] == ["Alice", "Bob"]


def test_revise_same_value_does_not_supersede(tmp_path):
    s = _store(tmp_path)
    first = s.revise("Acme", "hq", "Paris", source="a.pdf", valid_from=T1)
    again = s.revise("Acme", "hq", "Paris", source="a.pdf", valid_from=T2)
    # Identical (entity, predicate, object, source) → same id, still open.
    assert first == again
    assert s.get(first).valid_to is None
    assert [c.object for c in s.current("Acme")] == ["Paris"]


def test_as_of_bitemporal_ingest_axis(tmp_path):
    s = _store(tmp_path)
    # Recorded (ingest_time) T2 but valid from T1 — a back-dated fact.
    s.record_claim("Acme", "ceo", "Alice", source="d.pdf", valid_from=T1, ingest_time=T2)
    # As of ingest-time T1 we had not yet learned it.
    assert s.as_of("Acme", T3, ingest_time=T1) == []
    # As of ingest-time T3 we know it, and it is valid at T3.
    assert [c.object for c in s.as_of("Acme", T3, ingest_time=T3)] == ["Alice"]


def test_get_belief_store_uses_settings_path(tmp_path):
    # get_belief_store defaults to settings.beliefs_db (temp data dir via conftest).
    store = get_belief_store()
    assert store.path == get_settings().beliefs_db
    cid = store.record_claim("X", "is", "Y")
    assert store.get(cid) is not None
