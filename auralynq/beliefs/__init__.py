"""Bi-temporal belief store — how facts evolve over valid-time and ingest-time.

A *claim* is an atomic (entity, predicate, object) assertion with provenance and
two independent time axes:

* **valid-time** (``valid_from`` / ``valid_to``) — the period the fact holds in
  the world. Sourced from a document's authored/effective date.
* **ingest-time** (``ingest_time``) — when Auralynq learned the claim
  (transaction-time). Monotonic; never rewritten.

Keeping both axes is what lets the platform answer "what did we believe, as of
when" and render a belief-revision timeline that self-corrects rather than
silently overwrites. Backs contradiction alerts and the timeline UI.
"""

from auralynq.beliefs.store import BeliefStore, Claim, get_belief_store

__all__ = ["BeliefStore", "Claim", "get_belief_store"]
