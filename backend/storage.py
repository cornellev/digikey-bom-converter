"""Handles persistent runtime data for OAuth tokens and MPN lookup cache."""

import json
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(__file__).resolve().parent / '.runtime'
TOKENS_PATH = RUNTIME_DIR / 'digikey_tokens.json'
CACHE_PATH = RUNTIME_DIR / 'dk_cache.json'

def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}

def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_runtime_dir()
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

def load_tokens() -> dict[str, Any]:
    return _read_json(TOKENS_PATH)

def save_tokens(tokens: dict[str, Any]) -> None:
    _write_json(TOKENS_PATH, tokens)

def load_cache() -> dict[str, Any]:
    return _read_json(CACHE_PATH)

def save_cache(cache: dict[str, Any]) -> None:
    _write_json(CACHE_PATH, cache)
