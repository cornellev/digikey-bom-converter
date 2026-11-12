"""Elec's standardized components: parts the team buys in bulk and keeps in the ELL, so BOM lines using them are
pulled from ELL stock instead of ordered.

The list is the "Standardized Components" Google Sheet linked from Confluence (PCB Ordering & Requirements). It is
read with the `bom-sheet-reader` service account, which can see only that sheet. Key file: GOOGLE_SA_FILE, else
Render's secret file /etc/secrets/google-sa.json, else backend/.runtime/google-sa.json (local dev).
"""

import csv
import io
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests

DEFAULT_SHEET_ID = '1Cu6EPDHoVM6xf87pxzi4HhAb9UjkhsmBFUes17s5fYU'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/{}/edit'
KEY_PATHS = [Path('/etc/secrets/google-sa.json'), Path(__file__).resolve().parent / '.runtime' / 'google-sa.json']
TTL_S = 3600
# Sheet entries this short are not matched by prefix ("LMR38020" matches "LMR38020SDDAR", but "RC06" matches nothing).
MIN_PREFIX_LEN = 6

_lock = threading.Lock()
_state: dict[str, Any] = {'parts': None, 'loaded_at': 0.0, 'error': None}


def normalize(mpn: str) -> str:
    return re.sub(r'\s+', '', (mpn or '')).upper()


def parse_sheet(text: str) -> list[dict[str, str]]:
    """Part rows from the sheet's CSV export.

    The first column holds the part number; section headings ("RESISTORS", "CEVPico") and stray notes ("25 8mms")
    have nothing in the other columns, so rows need a part number plus a note or package to count.
    """
    rows = list(csv.reader(io.StringIO(text)))
    parts = []
    for row in rows[1:]:
        cells = [c.strip() for c in row] + ['', '', '']
        mpn, note, package = cells[0], cells[1], cells[2]
        if mpn and (note or package):
            parts.append({'mpn': mpn, 'note': note, 'package': package, 'source': 'sheet'})
    return parts


def parse_manual(text: str) -> list[dict[str, str]]:
    """Entries typed or pasted by the user, one per line: MPNs, DigiKey part numbers or DigiKey links (resolved to
    MPNs by bom_service.resolve_manual_entries). Not split on commas: some MPNs contain one ("PMEG2010ER,115")."""
    lines = [line.strip() for line in (text or '').splitlines()]
    return [{'mpn': line, 'note': '', 'package': '', 'source': 'manual'} for line in lines if line]


def match(candidates: list[str], parts: list[dict[str, str]]) -> Optional[dict[str, str]]:
    """The standard part a BOM line uses, if any: exact part number, or a full part number that starts with a
    (partial) sheet entry such as "LMR38020"."""
    wanted = [normalize(c) for c in candidates if c]
    for part in parts:
        if normalize(part['mpn']) in wanted:
            return part
    for part in parts:
        key = normalize(part['mpn'])
        if len(key) >= MIN_PREFIX_LEN and any(w.startswith(key) for w in wanted):
            return part
    return None


def _key_path() -> Optional[Path]:
    env = os.getenv('GOOGLE_SA_FILE')
    for path in ([Path(env)] if env else []) + KEY_PATHS:
        if path.is_file():
            return path
    return None


def _fetch(sheet_id: str) -> list[dict[str, str]]:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    key = _key_path()
    if not key:
        raise RuntimeError('no Google service account key configured')
    creds = service_account.Credentials.from_service_account_file(
        str(key), scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    creds.refresh(Request())
    response = requests.get(
        f'https://www.googleapis.com/drive/v3/files/{sheet_id}/export',
        params={'mimeType': 'text/csv'},
        headers={'Authorization': f'Bearer {creds.token}'},
        timeout=20,
    )
    if response.status_code == 404:
        raise RuntimeError('sheet not shared with the bom-sheet-reader service account')
    response.raise_for_status()
    return parse_sheet(response.content.decode('utf-8-sig'))


def load() -> dict[str, Any]:
    """The standard parts list, refreshed hourly. If a refresh fails the last good copy is kept; if there never was
    one, the list is empty and `error` says why (lines are then simply looked up on DigiKey as before)."""
    sheet_id = os.getenv('STANDARD_PARTS_SHEET_ID', DEFAULT_SHEET_ID)
    with _lock:
        if _state['parts'] is None or time.time() - _state['loaded_at'] > TTL_S:
            try:
                _state.update(parts=_fetch(sheet_id), loaded_at=time.time(), error=None)
            except Exception as exc:
                _state['error'] = str(exc)[:200]
                _state['loaded_at'] = time.time() - TTL_S + 300  # retry in 5 min, not on every request
                if _state['parts'] is None:
                    _state['parts'] = []
        return {
            'parts': _state['parts'],
            'error': _state['error'],
            'url': SHEET_URL.format(sheet_id),
        }
