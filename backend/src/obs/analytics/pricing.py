from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from obs.models import Usage


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


class Pricing:
    def __init__(self, models: dict[str, Price] | None = None):
        self.models = {key.lower(): value for key, value in (models or {}).items()}

    @classmethod
    def load(cls, path: Path | None) -> Pricing:
        if path is None or not path.is_file():
            return cls({})
        data = yaml.safe_load(path.read_text()) or {}
        models: dict[str, Price] = {}
        for name, raw in (data.get("models") or {}).items():
            if not isinstance(raw, dict):
                continue
            models[str(name)] = Price(
                input=float(raw.get("input", 0)),
                output=float(raw.get("output", 0)),
                cache_read=float(raw.get("cache_read", 0)),
                cache_write=float(raw.get("cache_write", 0)),
            )
        return cls(models)

    def match(self, model: str | None) -> Price | None:
        if not model:
            return None
        name = model.lower()
        for key in sorted(self.models, key=len, reverse=True):
            if name == key or name.startswith(key + "-") or name.startswith(key + "."):
                return self.models[key]
        return None

    def estimate(self, model: str | None, usage: Usage | None) -> float | None:
        if usage is None or not usage.known():
            return None
        price = self.match(model)
        if price is None:
            return None
        total = 0.0
        if usage.input_tokens is not None:
            total += usage.input_tokens * price.input / 1_000_000
        if usage.output_tokens is not None:
            total += usage.output_tokens * price.output / 1_000_000
        if usage.cache_read_tokens is not None:
            total += usage.cache_read_tokens * price.cache_read / 1_000_000
        if usage.cache_write_tokens is not None:
            total += usage.cache_write_tokens * price.cache_write / 1_000_000
        return total
