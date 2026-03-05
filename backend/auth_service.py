"""DigiKey client-credentials token helpers."""

import os
import time
from typing import Any

import requests

from storage import load_tokens, save_tokens

TOKEN_URLS = {
    'prod': 'https://api.digikey.com/v1/oauth2/token',
    'sandbox': 'https://sandbox-api.digikey.com/v1/oauth2/token',
}


def _env_name() -> str:
    env = os.getenv('DIGIKEY_ENVIRONMENT', 'prod').strip().lower()
    return env if env in TOKEN_URLS else 'prod'

def get_client_id() -> str:
    return os.getenv('DIGIKEY_CLIENT_ID', '').strip()

def _client_secret() -> str:
    return os.getenv('DIGIKEY_CLIENT_SECRET', '').strip()

def _scope() -> str:
    return os.getenv('DIGIKEY_SCOPE', 'productsearch').strip()

def _require_client_config() -> None:
    if not get_client_id() or not _client_secret():
        raise RuntimeError('Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET.')

def _normalize_token_payload(raw: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(raw.get('expires_in') or 0)
    expires_at = int(time.time()) + max(0, expires_in - 60)
    return {
        'access_token': (raw.get('access_token') or '').strip(),
        'expires_at': expires_at,
    }

def get_auth_status() -> dict[str, Any]:
    configured = bool(get_client_id() and _client_secret())
    return {
        'configured': configured,
        'has_refresh_token': configured,
    }

def fetch_client_credentials_token() -> dict[str, Any]:
    _require_client_config()
    data = {
        'client_id': get_client_id(),
        'client_secret': _client_secret(),
        'grant_type': 'client_credentials',
        'scope': _scope(),
    }
    response = requests.post(TOKEN_URLS[_env_name()], data=data, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(
            f'Client credentials token fetch failed ({response.status_code}): {response.text}'
        )
    payload = _normalize_token_payload(response.json())
    save_tokens(payload)
    return payload

def ensure_valid_access_token() -> str:
    _require_client_config()
    tokens = load_tokens()
    access_token = (tokens.get('access_token') or '').strip()
    expires_at = int(tokens.get('expires_at') or 0)
    if access_token and expires_at > int(time.time()):
        return access_token
    refreshed = fetch_client_credentials_token()
    return (refreshed.get('access_token') or '').strip()
