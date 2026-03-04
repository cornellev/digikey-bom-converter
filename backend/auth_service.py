"""DigiKey OAuth/token helpers."""

import base64
import hashlib
import os
import secrets
import time
import urllib.parse
from typing import Any

import requests

from storage import load_tokens, save_tokens

# --- Configs/Constants ---
AUTH_URLS = {
    'prod': 'https://api.digikey.com/v1/oauth2/authorize',
    'sandbox': 'https://sandbox-api.digikey.com/v1/oauth2/authorize',
}
TOKEN_URLS = {
    'prod': 'https://api.digikey.com/v1/oauth2/token',
    'sandbox': 'https://sandbox-api.digikey.com/v1/oauth2/token',
}
REDIRECT_URI = os.getenv('DIGIKEY_REDIRECT_URI', 'https://localhost:5000/callback/').strip()


# --- PKCE Runtime State ---
_PENDING_PKCE: dict[str, str] = {}  # Mapping: (state -> code_verifier)


# --- Environment Variable Helpers ---
def _env_name() -> str:
    env = os.getenv('DIGIKEY_ENVIRONMENT', 'prod').strip().lower()
    return env if env in AUTH_URLS else 'prod'

def get_client_id() -> str:
    return os.getenv('DIGIKEY_CLIENT_ID', '').strip()

def _client_secret() -> str:
    return os.getenv('DIGIKEY_CLIENT_SECRET', '').strip()

def _scope() -> str:
    return os.getenv('DIGIKEY_SCOPE', 'productsearch offline_access').strip()

def _require_client_config() -> None:
    if not get_client_id() or not _client_secret():
        raise RuntimeError('Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET.')
    

# --- PKCE Helpers ---
def make_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:64]

def make_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')

def _make_state() -> str:
    return secrets.token_urlsafe(24)


# --- Auth Status ---
def get_auth_status() -> dict[str, bool]:
    tokens = load_tokens()
    return {
        'configured': bool(get_client_id() and _client_secret()),
        'has_refresh_token': bool((tokens.get('refresh_token') or '').strip()),
    }


# --- OAuth Start ---
def start_oauth() -> str:
    _require_client_config()

    verifier = make_code_verifier()
    challenge = make_code_challenge(verifier)
    state = _make_state()

    params = {
        'response_type': 'code',
        'client_id': get_client_id(),
        'redirect_uri': REDIRECT_URI,
        'scope': _scope(),
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    url = AUTH_URLS[_env_name()] + '?' + urllib.parse.urlencode(params)

    _PENDING_PKCE[state] = verifier
    return url


# --- Token Payload Helpers ---
def _normalize_token_payload(raw: dict[str, Any], fallback_refresh: str = '') -> dict[str, Any]:
    expires_in = int(raw.get('expires_in') or 0)
    expires_at = int(time.time()) + max(0, expires_in - 60)
    return {
        'access_token': raw.get('access_token', ''),
        'refresh_token': raw.get('refresh_token', fallback_refresh),
        'expires_at': expires_at,
    }


# --- OAuth Code Exchange ---
def exchange_code_for_tokens(code: str, verifier: str) -> dict[str, Any]:
    _require_client_config()

    data = {
        'client_id': get_client_id(),
        'client_secret': _client_secret(),
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'code_verifier': verifier,
    }

    response = requests.post(TOKEN_URLS[_env_name()], data=data, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'Token exchange failed ({response.status_code}): {response.text}')

    existing = load_tokens()
    payload = _normalize_token_payload(response.json(), fallback_refresh=existing.get('refresh_token', ''))
    save_tokens(payload)
    return payload


# --- OAuth Callback Completion ---
def complete_oauth_callback(code: str, state: str) -> dict[str, Any]:
    verifier = _PENDING_PKCE.pop(state, None)
    if not verifier:
        raise RuntimeError('Invalid or expired OAuth state.')

    tokens = exchange_code_for_tokens(code=code, verifier=verifier)
    return {
        'ok': True,
        'has_refresh_token': bool(tokens.get('refresh_token')),
    }


# --- Token Refresh ---
def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    _require_client_config()

    data = {
        'client_id': get_client_id(),
        'client_secret': _client_secret(),
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    response = requests.post(TOKEN_URLS[_env_name()], data=data, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'Refresh failed ({response.status_code}): {response.text}')

    payload = _normalize_token_payload(response.json(), fallback_refresh=refresh_token)
    save_tokens(payload)
    return payload


# --- Access Token Guard ---
def ensure_valid_access_token() -> str:
    _require_client_config()

    tokens = load_tokens()
    access_token = (tokens.get('access_token') or '').strip()
    refresh_token = (tokens.get('refresh_token') or '').strip()
    expires_at = int(tokens.get('expires_at') or 0)

    if access_token and expires_at > int(time.time()):
        return access_token

    if refresh_token:
        refreshed = refresh_access_token(refresh_token)
        return (refreshed.get('access_token') or '').strip()

    raise RuntimeError('Digi-Key authorization required. Use /auth/start first.')
