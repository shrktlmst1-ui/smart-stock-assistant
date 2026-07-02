"""Engine logging — trace inputs, calculations, and decisions per engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EngineLogEntry:
    engine: str
    inputs: dict
    calculation: str
    result: str
    reason: str


@dataclass
class EngineLogger:
    entries: list[EngineLogEntry] = field(default_factory=list)

    def log(self, engine: str, inputs: dict, calculation: str, result: str, reason: str) -> None:
        self.entries.append(EngineLogEntry(
            engine=engine,
            inputs={k: _safe(v) for k, v in inputs.items()},
            calculation=calculation,
            result=result,
            reason=reason,
        ))

    def to_dicts(self) -> list[dict]:
        return [
            {
                "engine": e.engine,
                "inputs": e.inputs,
                "calculation": e.calculation,
                "result": e.result,
                "reason": e.reason,
            }
            for e in self.entries
        ]


def _safe(v: object) -> object:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v[:5]]
    return str(v)
