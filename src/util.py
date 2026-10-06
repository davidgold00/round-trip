"""Shared helpers: config loading, .env loading, paths, logging, slugs."""
from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ without overwriting."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_config() -> dict:
    with open(ROOT / "config.yaml") as fh:
        return yaml.safe_load(fh)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("RT_LOGLEVEL", "INFO"))
    return logger


def today() -> str:
    return _dt.date.today().isoformat()


def slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return out or "x"


def edge_id(source: str, target: str, edge_type: str, as_of: str) -> str:
    return f"{slug(source)}__{slug(target)}__{slug(edge_type)}__{str(as_of).replace('-', '')}"


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def term_years(term_start: str | None, term_end: str | None, default: float) -> tuple[float, bool]:
    """Return (years, assumed). Falls back to the configured default."""
    try:
        if term_start and term_end:
            a = _dt.date.fromisoformat(str(term_start)[:10])
            b = _dt.date.fromisoformat(str(term_end)[:10])
            yrs = (b - a).days / 365.25
            if yrs > 0:
                return max(1.0, yrs), False
    except (ValueError, TypeError):
        pass
    return float(default), True


def fmt_usd(x: float) -> str:
    """Human dollar string. Used in generated prose; avoids em-dashes."""
    if x is None:
        return "n/a"
    a = abs(float(x))
    for cut, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= cut:
            return f"${float(x) / cut:,.1f}{suf}"
    return f"${float(x):,.0f}"
