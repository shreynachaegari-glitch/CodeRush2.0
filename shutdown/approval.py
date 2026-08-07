"""Human-approval gates: pause-with-full-context, checkpointed, resumable.

Only two action types ever hit this gate: publish_verdict and promote_strategy.
Everything else in the system runs autonomously. A third case -- a proposed
strategy trying to expand its own permissions or reach an unapproved network --
never reaches this module at all: it's auto-rejected by the policy check in
strategy.py before an approval row would even be created.
"""

from __future__ import annotations

from .db import Store, dumps, new_id, now


class ApprovalGate:
    def __init__(self, store: Store):
        self.store = store

    def request(self, *, run_id: str, action_type: str, context: dict, ticket_id: str | None = None) -> str:
        assert action_type in ("publish_verdict", "promote_strategy")
        approval_id = new_id()
        self.store.insert(
            "approvals",
            {
                "approval_id": approval_id,
                "run_id": run_id,
                "ticket_id": ticket_id,
                "action_type": action_type,
                "context_snapshot": dumps(context),
                "status": "pending",
                "requested_at": now(),
                "resolved_at": None,
                "resolved_by": None,
            },
        )
        return approval_id

    def pending(self) -> list:
        return self.store.read("SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at")

    def resolve(self, approval_id: str, *, approved: bool, resolved_by: str = "presenter") -> None:
        self.store.update(
            "approvals",
            "approval_id",
            approval_id,
            {
                "status": "approved" if approved else "rejected",
                "resolved_at": now(),
                "resolved_by": resolved_by,
            },
        )
        row = self.store.read_one("SELECT run_id FROM approvals WHERE approval_id = ?", (approval_id,))
        if row:
            run = self.store.read_one("SELECT human_interventions FROM runs WHERE run_id = ?", (row["run_id"],))
            if run is not None:
                self.store.update(
                    "runs", "run_id", row["run_id"], {"human_interventions": (run["human_interventions"] or 0) + 1}
                )

    def status(self, approval_id: str) -> str:
        row = self.store.read_one("SELECT status FROM approvals WHERE approval_id = ?", (approval_id,))
        return row["status"] if row else "unknown"
