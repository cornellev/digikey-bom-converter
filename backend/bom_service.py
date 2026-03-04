"""BOM parsing and mapping helpers."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Optional

import pandas as pd

from auth_service import ensure_valid_access_token, get_client_id
from digikey_client import (
    V4_BASE,
    DigiKeyV4,
    build_dk_search_url,
    env_name,
    label_packaging,
    locale_currency,
    locale_language,
    locale_ship_to_country,
    locale_site,
    offers_from_keyword,
    offers_from_productdetails,
    prefer_cut_tape,
)
from storage import load_cache, save_cache

# --- BOM Column Heuristics ---
MPN_CANDIDATES = [
    'mpn',
    'manufacturer part number',
    'manufacturerproductnumber',
    'mfr part',
    'mfg part',
    'part number',
    'mfr part #',
    'mfg part #',
    'comment',
]

def pick_mpn_col(columns: list[str]) -> Optional[str]:
    lower_map = {column.lower().strip(): column for column in columns}
    for candidate in MPN_CANDIDATES:
        if candidate in lower_map:
            return lower_map[candidate]

    for column in columns:
        lc = column.lower().replace(' ', '')
        for candidate in MPN_CANDIDATES:
            if candidate.replace(' ', '') in lc:
                return column
    return None


# --- BOM Parse Helpers ---
def parse_uploaded_bom(payload: bytes, filename: str, sheet: Optional[str] = None) -> tuple[pd.DataFrame, Optional[str]]:
    lower_name = (filename or '').lower()
    stream = BytesIO(payload)

    if lower_name.endswith('.csv'):
        frame = pd.read_csv(stream)
        return frame, None

    if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
        if sheet:
            frame = pd.read_excel(stream, sheet_name=sheet)
            return frame, sheet

        xls = pd.ExcelFile(stream)
        selected_sheet = next((s for s in xls.sheet_names if 'bom' in s.lower()), xls.sheet_names[0])
        frame = pd.read_excel(BytesIO(payload), sheet_name=selected_sheet)
        return frame, selected_sheet

    raise ValueError('Unsupported file type. Use .xlsx, .xls, or .csv.')


# --- Mapping ---
def map_one_mpn(mpn: str, dk: DigiKeyV4) -> dict[str, Any]:
    mpn = (mpn or '').strip()
    out = {
        'dkpn': '',
        'dk_packaging': '',
        'dk_qty_avail': '',
        'dk_search_url': build_dk_search_url(mpn) if mpn else '',
    }
    if not mpn:
        return out

    try:
        details = dk.productdetails_by_mpn(mpn)
        offers = [] if details.get('__not_found__') else offers_from_productdetails(details)

        if not offers:
            keyword = dk.keyword_search(mpn, limit=5)
            offers = offers_from_keyword(keyword)

        choice = prefer_cut_tape(offers)
        if not choice:
            return out

        out['dkpn'] = choice['dkpn']
        out['dk_packaging'] = label_packaging(choice.get('packaging'))
        out['dk_qty_avail'] = choice.get('quantityAvailable', '')
        return out
    except Exception as exc:
        out['dk_packaging'] = f'ERROR: {exc}'
        return out

def _build_dk_client(access_token: str) -> DigiKeyV4:
    return DigiKeyV4(
        client_id=get_client_id(),
        access_token=access_token,
        v4_base=V4_BASE[env_name()],
        site=locale_site(),
        language=locale_language(),
        currency=locale_currency(),
        ship_to_country=locale_ship_to_country(),
    )

def convert_uploaded_bom(
    payload: bytes,
    filename: str,
    mpn_col: Optional[str] = None,
    sheet: Optional[str] = None,
    workers: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame, selected_sheet = parse_uploaded_bom(payload=payload, filename=filename, sheet=sheet)

    detected_mpn_col = mpn_col or pick_mpn_col([str(c).strip() for c in frame.columns])
    if not detected_mpn_col:
        raise RuntimeError('Could not detect MPN column; pass mpn_col explicitly.')
    if detected_mpn_col not in frame.columns:
        raise RuntimeError(f"Column '{detected_mpn_col}' not found. Columns: {list(frame.columns)}")

    access_token = ensure_valid_access_token()
    dk = _build_dk_client(access_token)

    cache = load_cache()
    mpns = frame[detected_mpn_col].astype(str).fillna('').tolist()
    unique_mpns = sorted(set([m.strip() for m in mpns if m.strip()]))
    results: dict[str, dict[str, Any]] = {}

    def lookup(mpn: str) -> dict[str, Any]:
        if mpn in cache:
            return cache[mpn]
        mapped = map_one_mpn(mpn, dk)
        if not str(mapped.get('dk_packaging', '')).startswith('ERROR:'):
            cache[mpn] = mapped
        return mapped

    max_workers = max(1, min(int(workers), 8))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(lookup, mpn): mpn for mpn in unique_mpns}
        for future in as_completed(futures):
            mpn = futures[future]
            try:
                results[mpn] = future.result()
            except Exception as exc:
                results[mpn] = {
                    'dkpn': '',
                    'dk_packaging': f'ERROR: {exc}',
                    'dk_qty_avail': '',
                    'dk_search_url': build_dk_search_url(mpn),
                }

    save_cache(cache)

    frame['dkpn'] = [results.get(m.strip(), {}).get('dkpn', '') for m in mpns]
    frame['dk_packaging'] = [results.get(m.strip(), {}).get('dk_packaging', '') for m in mpns]
    frame['dk_qty_avail'] = [results.get(m.strip(), {}).get('dk_qty_avail', '') for m in mpns]
    frame['dk_search_url'] = [results.get(m.strip(), {}).get('dk_search_url', build_dk_search_url(m)) for m in mpns]

    rows = frame.to_dict(orient='records')
    meta = {
        'row_count': len(rows),
        'mpn_column': detected_mpn_col,
        'sheet': selected_sheet,
        'workers': max_workers,
    }
    return rows, meta
