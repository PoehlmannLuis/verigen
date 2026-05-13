"""Trace logging for verifiable code generation runs."""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional, Union


@dataclass
class TraceEntry:
    """A single step in the evolution trace."""
    iteration: int
    phase: str  # "initial" | "mutate"
    block_code: str
    score: float
    passed: bool
    feedback: str
    metrics: dict[str, float] = field(default_factory=dict)
    change_rationale: Optional[str] = None
    elapsed_ms: Optional[float] = None
    diff_from_previous: Optional[str] = None


class TraceLogger:
    """Collects and persists evolution traces."""

    def __init__(self):
        self.entries: list[TraceEntry] = []

    def record(self, entry: TraceEntry) -> None:
        """Record a trace entry. If there's a previous entry, compute a diff."""
        self.entries.append(entry)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(e)) for e in self.entries)

    def save(self, path: Union[str, Path]) -> None:
        with open(path, "w") as f:
            f.write(self.to_jsonl())
            if self.entries:
                f.write("\n")

    @classmethod
    def from_jsonl(cls, path: Union[str, Path]) -> "TraceLogger":
        logger = cls()
        with open(path) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    logger.entries.append(TraceEntry(**data))
        return logger

    @property
    def best_score(self) -> float:
        return max((e.score for e in self.entries if e.passed), default=0.0)

    @property
    def n_iterations(self) -> int:
        return len(self.entries)

    @property
    def n_passed(self) -> int:
        return sum(1 for e in self.entries if e.passed)
