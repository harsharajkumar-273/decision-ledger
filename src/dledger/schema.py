"""Generic claim schema. One small schema serves every domain
(engineering decisions, customer commitments, policies)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    ACTIVE = "active"
    VALID = "valid"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    NEEDS_REVIEW = "needs_review"
    SUPERSEDED = "superseded"


class EdgeType(str, Enum):
    DEPENDS_ON = "depends_on"      # A depends_on B: A is only valid if B holds
    SUPERSEDES = "supersedes"      # A supersedes B: A replaces B
    CONTRADICTS = "contradicts"
    JUSTIFIED_BY = "justified_by"  # claim -> evidence/source


@dataclass
class Claim:
    id: str
    text: str                      # the decision in one sentence
    subject: str                   # the component it is about, e.g. "database"
    value: str                     # what was chosen, e.g. "postgres"
    kind: str = "tech_choice"      # tech_choice | commitment | policy
    owner: Optional[str] = None
    date: Optional[str] = None     # ISO date
    source: Optional[str] = None   # message / ticket / PR reference
    reason: Optional[str] = None
    confidence: float = 0.5
    status: Status = Status.ACTIVE
    acl: Optional[list[str]] = None  # None = visible to everyone; else groups allowed to see it
    scope: Optional[str] = None     # environment/component scope, e.g. production
    condition: Optional[str] = None # contingent commitment; never silently treat as unconditional

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "Claim":
        d = dict(d)
        d["status"] = Status(d.get("status", "active"))
        return Claim(**d)


@dataclass
class Evidence:
    kind: str                      # repo | web | message
    detail: str
    supports: Optional[bool] = None  # True supports, False contradicts, None unclear
    ref: Optional[str] = None


@dataclass
class Verdict:
    claim_id: str
    status: Status
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)
    impacted: list[str] = field(default_factory=list)
