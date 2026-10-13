from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import threading
import time
from urllib.request import urlopen

import yaml

from obs.models import Usage


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0
    tiers: tuple[tuple[int, "Price"], ...] = ()


class Pricing:
    def __init__(self, models: dict[str, Price] | None = None):
        self.models = {key.lower(): value for key, value in (models or {}).items()}
        self.cache_path: Path | None = None
        self.fetched_at = 0.0
        self.last_attempt = 0.0
        self._lock = threading.Lock()

    @classmethod
    def openrouter(cls, data_dir: Path) -> Pricing:
        pricing = cls()
        pricing.cache_path = data_dir / "openrouter-pricing.json"
        try:
            cached = json.loads(pricing.cache_path.read_text())
            pricing.models = cls._catalog(cached["catalog"])
            pricing.fetched_at = float(cached["fetched_at"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return pricing

    @staticmethod
    def _catalog(catalog: dict) -> dict[str, Price]:
        if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
            raise ValueError("Invalid OpenRouter catalog")
        def price(raw: dict) -> Price:
            def rate(key: str, default=None) -> float:
                value = float(raw.get(key, default)) * 1_000_000
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid token price")
                return value

            base = Price(rate("prompt"), rate("completion"),
                         rate("input_cache_read", raw.get("prompt")),
                         rate("input_cache_write", raw.get("prompt")))
            tiers = tuple(sorted(
                ((int(tier["min_prompt_tokens"]), price({**raw, **tier, "overrides": []}))
                 for tier in raw.get("overrides", [])), key=lambda item: item[0]))
            return Price(base.input, base.output, base.cache_read, base.cache_write, tiers)

        models = {}
        for model in catalog["data"]:
            try:
                name = model["id"].lower()
                models[name] = price(model["pricing"])
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        if not models:
            raise ValueError("OpenRouter returned no valid model pricing")
        return models

    def refresh(self) -> None:
        if self.cache_path is None:
            return
        with self._lock:
            now = time.time()
            if now - self.fetched_at < 86400 or now - self.last_attempt < 300:
                return
            self.last_attempt = now
            try:
                with urlopen("https://openrouter.ai/api/v1/models", timeout=10) as response:
                    catalog = json.load(response)
                models = self._catalog(catalog)
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"fetched_at": now, "catalog": catalog}))
                temporary.replace(self.cache_path)
                self.models = models
                self.fetched_at = now
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logging.getLogger(__name__).warning("OpenRouter pricing refresh failed; retaining cached prices: %s", exc)

    def fingerprint(self) -> str:
        return hashlib.sha256(repr(sorted(self.models.items())).encode()).hexdigest()

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
        if self.cache_path is not None:
            # Only normalize known provider names and Claude's decimal versions.
            if "/" not in name:
                provider = "anthropic" if name.startswith("claude-") else "openai" if name.startswith(("gpt-", "o1", "o3", "o4")) else None
                if provider:
                    name = f"{provider}/{name}"
            name = re.sub(r"(claude-(?:sonnet|opus|haiku)-\d+)-(\d+)(?=-|$)", r"\1.\2", name)
            if name in self.models:
                return self.models[name]
            # A dated snapshot may use the base model; never guess variants.
            name = re.sub(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$", "", name)
            return self.models.get(name)
        for key in sorted(self.models, key=len, reverse=True):
            if name == key or name.startswith(key + "-") or name.startswith(key + "."):
                return self.models[key]
        return None

    def estimate(self, model: str | None, usage: Usage | None, *, cached_input_included: bool = False) -> float | None:
        if usage is None or not usage.known():
            return None
        price = self.match(model)
        if price is None:
            return None
        prompt_tokens = (usage.input_tokens or 0) + (0 if cached_input_included else (usage.cache_read_tokens or 0) + (usage.cache_write_tokens or 0))
        for minimum, tier in price.tiers:
            if prompt_tokens >= minimum:
                price = tier
        total = 0.0
        if usage.input_tokens is not None:
            uncached = max(0, usage.input_tokens - (usage.cache_read_tokens or 0)) if cached_input_included else usage.input_tokens
            total += uncached * price.input / 1_000_000
        if usage.output_tokens is not None:
            total += usage.output_tokens * price.output / 1_000_000
        if usage.cache_read_tokens is not None:
            total += usage.cache_read_tokens * price.cache_read / 1_000_000
        if usage.cache_write_tokens is not None:
            total += usage.cache_write_tokens * price.cache_write / 1_000_000
        return total
