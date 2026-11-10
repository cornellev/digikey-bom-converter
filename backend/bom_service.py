"""BOM parsing and mapping helpers."""

import math
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, Optional

import pandas as pd

from alternatives import find_alternatives, manual_replacement, product_card, suggest_for_unmatched
from auth_service import ensure_valid_access_token, get_client_id
from digikey_client import (
    V4_BASE,
    DigiKeyV4,
    build_dk_search_url,
    env_name,
    locale_currency,
    locale_language,
    locale_ship_to_country,
    locale_site,
    QuotaExceeded,
    lookup_product,
    merge_listings,
    pick_variation,
)
from storage import load_cache, save_cache

# Statuses that keep a row out of the DigiKey cart file until someone picks a replacement.
BLOCKING_STATUSES = {'out_of_stock', 'low_stock', 'moq', 'ambiguous', 'not_found', 'error'}

# Columns this tool appends. Dropped from uploads so a previously converted file can be re-run.
OUTPUT_COLUMNS = [
    'dk_mpn', 'dk_manufacturer', 'dkpn', 'dk_packaging', 'dk_qty_avail', 'dk_moq', 'dk_unit_price',
    'qty_per_board', 'order_qty', 'match_status', 'match_note', 'dk_search_url',
]

# --- BOM Column Heuristics ---
MPN_CANDIDATES = [
    'name',
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
PART_NUMBER_CANDIDATES = ['part number', 'manufacturer part number', 'manufacturer part number 1', 'mpn', 'mfr part #']
MANUFACTURER_CANDIDATES = ['manufacturer', 'manufacturer 1', 'manufacturer name', 'mfr', 'mfg']
QTY_CANDIDATES = ['qty', 'quantity', 'qty.', 'count']
DESIGNATOR_CANDIDATES = ['designator', 'designators', 'reference', 'references', 'refdes']

# Board features that appear in Altium BOMs but are not purchasable (only skipped when no part number is given).
NON_PART_RE = re.compile(r'\b(fiducial|mounting hole|logo|test pad|tooling hole)\b', re.IGNORECASE)


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


def pick_exact_col(columns: list[str], candidates: list[str], exclude: Optional[str] = None) -> Optional[str]:
    lower_map = {column.lower().strip(): column for column in columns if column != exclude}
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


# --- BOM Parse Helpers ---
def parse_uploaded_bom(payload: bytes, filename: str, sheet: Optional[str] = None) -> tuple[pd.DataFrame, Optional[str]]:
    lower_name = (filename or '').lower()
    stream = BytesIO(payload)

    if lower_name.endswith('.csv'):
        frame = pd.read_csv(stream, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        return frame, None

    if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
        if sheet:
            frame = pd.read_excel(stream, sheet_name=sheet, dtype=str, keep_default_na=False)
            return frame, sheet

        xls = pd.ExcelFile(stream)
        selected_sheet = next((s for s in xls.sheet_names if 'bom' in s.lower()), xls.sheet_names[0])
        frame = pd.read_excel(BytesIO(payload), sheet_name=selected_sheet, dtype=str, keep_default_na=False)
        return frame, selected_sheet

    raise ValueError('Unsupported file type. Use .xlsx, .xls, or .csv.')


def clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]
    frame = frame.astype(str)
    drop = [
        c for c in frame.columns
        if c in OUTPUT_COLUMNS or (c.startswith('Unnamed:') and not frame[c].str.strip().any())
    ]
    frame = frame.drop(columns=drop)
    # Drop fully blank rows (Altium exports often end with some).
    frame = frame[frame.apply(lambda r: any(str(v).strip() for v in r), axis=1)]
    return frame.reset_index(drop=True)


def parse_qty(value: Any, designators: str) -> int:
    try:
        qty = float(str(value).strip())
        if math.isfinite(qty) and qty > 0:
            return int(math.ceil(qty))
    except ValueError:
        pass
    refs = [r for r in re.split(r'[,\s]+', designators or '') if r]
    return max(1, len(refs))


def mpn_candidates(name: str, part_number: str, manufacturer: str) -> list[tuple[str, str]]:
    """Return (mpn, manufacturer hint) pairs to try, best first.

    Altium 365 exports put the MPN in `Name` and "<Manufacturer> <MPN>, <Manufacturer> <MPN>, ..." in `Part Number`.
    `Name` is sometimes a description instead (e.g. "147K 1% 0603(1608)"), so the Part Number entries are fallbacks.
    """
    name = (name or '').strip()
    segments = [seg.strip() for seg in (part_number or '').split(',') if seg.strip()]
    parsed: list[tuple[str, str]] = []
    for seg in segments:
        if name and seg.lower().endswith(name.lower()):
            parsed.append((name, seg[: -len(name)].strip()))
        else:
            head, _, tail = seg.rpartition(' ')
            parsed.append((tail, head.strip()))

    out: list[tuple[str, str]] = []
    if name:
        name_hint = next((mfr for mpn, mfr in parsed if mpn.lower() == name.lower() and mfr), '')
        out.append((name, manufacturer or name_hint))
    for mpn, mfr in parsed:
        if all(mpn.lower() != seen.lower() for seen, _ in out):
            out.append((mpn, mfr or manufacturer))
    return out


def _mfr_key(name: str) -> str:
    words = re.findall(r'[a-z0-9]+', (name or '').lower())
    return words[0] if words else ''


def manufacturer_matches(hint: str, actual: str) -> bool:
    """Loose match: "Yageo Group" ~ "YAGEO", "TE Connectivity" ~ "TE Connectivity AMP Connectors"."""
    return bool(hint) and _mfr_key(hint) == _mfr_key(actual)


def resolve_product(candidates: list[tuple[str, str]], dk: DigiKeyV4) -> tuple[Optional[dict[str, Any]], str, str]:
    """Find the DigiKey product for a BOM line. Returns (product, how, note)."""
    ambiguous: Optional[tuple[str, str]] = None
    for index, (mpn, hint) in enumerate(candidates):
        details = dk.productdetails_by_mpn(mpn)
        product = details.get('Product') if not details.get('__not_found__') else None
        if not product and 'duplicate' in str(details.get('detail', '')).lower():
            product = lookup_product(dk, mpn)  # same part listed twice by DigiKey, not several manufacturers
        if product:
            return product, 'exact' if index == 0 else 'part_number_column', f'matched {mpn} from the Part Number column'
        if 'duplicate' in str(details.get('detail', '')).lower():
            ambiguous = ambiguous or (mpn, hint)
            if hint:
                product = _resolve_with_manufacturer(mpn, hint, dk)
                if product:
                    return product, 'manufacturer', f'{mpn} is made by several manufacturers; used {hint}'

    if ambiguous:
        mpn, hint = ambiguous
        why = f'none of them is "{hint}"' if hint else 'the BOM names no manufacturer'
        return None, 'ambiguous', f'{mpn} is made by several manufacturers and {why}'
    return None, 'not_found', 'no DigiKey product for ' + ' / '.join(m for m, _ in candidates)


def _resolve_with_manufacturer(mpn: str, hint: str, dk: DigiKeyV4) -> Optional[dict[str, Any]]:
    found = dk.keyword_search(mpn, limit=50)
    for product in merge_listings(found.get('Products') or []):
        manufacturer = product.get('Manufacturer') or {}
        if (product.get('ManufacturerProductNumber') or '').lower() == mpn.lower() and manufacturer_matches(
            hint, manufacturer.get('Name', '')
        ):
            return lookup_product(dk, mpn, manufacturer.get('Id')) or product
    return None


def process_line(line: dict[str, Any], need: int, dk: DigiKeyV4, with_alternatives: bool) -> dict[str, Any]:
    out: dict[str, Any] = {col: '' for col in OUTPUT_COLUMNS}
    out['qty_per_board'] = line['qty']
    out['order_qty'] = need
    out['alternatives'] = []
    out['card'] = None
    candidates = line['candidates']
    out['dk_search_url'] = build_dk_search_url(candidates[0][0]) if candidates else ''

    if not candidates:
        out['match_status'] = 'not_a_part' if line['non_part'] else 'not_found'
        out['match_note'] = 'board feature, not purchasable' if line['non_part'] else 'no part number in this row'
        return out

    try:
        product, how, note = resolve_product(candidates, dk)
        if not product:
            out['match_status'] = how
            out['match_note'] = note
            if with_alternatives:
                out['alternatives'] = suggest_for_unmatched(candidates, need, dk)
            return out

        variation, status = pick_variation(product, need)
        out['card'] = product_card(product)
        out['dk_mpn'] = product.get('ManufacturerProductNumber', '')
        out['dk_manufacturer'] = (product.get('Manufacturer') or {}).get('Name', '')
        out['dk_search_url'] = build_dk_search_url(out['dk_mpn'] or candidates[0][0])
        if variation:
            out['dkpn'] = variation['dkpn']
            out['dk_packaging'] = variation['packaging']
            out['dk_qty_avail'] = variation['stock']
            out['dk_moq'] = variation['moq']
            out['dk_unit_price'] = variation['unit_price'] if variation['unit_price'] is not None else ''
        out['match_status'] = status
        notes = [note] if how != 'exact' else []
        if status == 'marketplace':
            notes.append('sold by a DigiKey Marketplace seller, ships separately')
        elif status == 'moq':
            notes.append(f'in stock only with a minimum order of {variation["moq"]}')
        elif status in ('out_of_stock', 'low_stock'):
            lead = product.get('ManufacturerLeadWeeks')
            have = variation['stock'] if variation else 0
            notes.append(f'need {need}, DigiKey has {have}' + (f'; manufacturer lead time {lead} weeks' if lead else ''))
        out['match_note'] = '; '.join(notes)
        if with_alternatives and status in BLOCKING_STATUSES | {'marketplace'}:
            out['alternatives'] = find_alternatives(product, need, dk)
        return out
    except QuotaExceeded:
        raise  # no point continuing: every other line would fail the same way
    except Exception as exc:  # one bad line should not fail the whole BOM
        out['match_status'] = 'error'
        out['match_note'] = str(exc)[:300]
        return out


def _build_dk_client(access_token: str, cache: Optional[dict[str, Any]] = None) -> DigiKeyV4:
    return DigiKeyV4(
        client_id=get_client_id(),
        access_token=access_token,
        v4_base=V4_BASE[env_name()],
        site=locale_site(),
        language=locale_language(),
        currency=locale_currency(),
        ship_to_country=locale_ship_to_country(),
        cache=cache,
    )


def convert_uploaded_bom(
    payload: bytes,
    filename: str,
    mpn_col: Optional[str] = None,
    sheet: Optional[str] = None,
    workers: int = 4,
    boards: int = 1,
    with_alternatives: bool = True,
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]], dict[str, Any]]:
    """Convert a BOM. Returns (rows, alternatives per row, meta)."""
    frame, selected_sheet = parse_uploaded_bom(payload=payload, filename=filename, sheet=sheet)
    frame = clean_frame(frame)
    columns = list(frame.columns)

    detected_mpn_col = mpn_col or pick_mpn_col(columns)
    if not detected_mpn_col:
        raise RuntimeError('Could not detect MPN column; pass mpn_col explicitly.')
    if detected_mpn_col not in frame.columns:
        raise RuntimeError(f"Column '{detected_mpn_col}' not found. Columns: {columns}")
    pn_col = pick_exact_col(columns, PART_NUMBER_CANDIDATES, exclude=detected_mpn_col)
    mfr_col = pick_exact_col(columns, MANUFACTURER_CANDIDATES)
    qty_col = pick_exact_col(columns, QTY_CANDIDATES)
    ref_col = pick_exact_col(columns, DESIGNATOR_CANDIDATES)
    desc_col = pick_exact_col(columns, ['description'])
    boards = max(1, int(boards))

    lines = []
    for _, row in frame.iterrows():
        name = row[detected_mpn_col].strip()
        part_number = row[pn_col].strip() if pn_col else ''
        description = row[desc_col] if desc_col else ''
        non_part = not part_number and bool(NON_PART_RE.search(f'{name} {description}'))
        manufacturer = row[mfr_col].strip() if mfr_col else ''
        lines.append({
            'qty': parse_qty(row[qty_col] if qty_col else '', row[ref_col] if ref_col else ''),
            'candidates': [] if non_part else mpn_candidates(name, part_number, manufacturer),
            'non_part': non_part,
        })

    access_token = ensure_valid_access_token()
    cache = load_cache()
    dk = _build_dk_client(access_token, cache)

    max_workers = max(1, min(int(workers), 8))
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(
                lambda line: process_line(line, line['qty'] * boards, dk, with_alternatives), lines
            ))
    finally:
        save_cache(cache)  # keep what was fetched, so a re-run after the quota resets costs fewer calls

    alternatives = [r.pop('alternatives') for r in results]
    cards = [r.pop('card') for r in results]
    for col in OUTPUT_COLUMNS:
        frame[col] = [r[col] for r in results]

    statuses: dict[str, int] = {}
    for r in results:
        statuses[r['match_status']] = statuses.get(r['match_status'], 0) + 1
    rows = frame.to_dict(orient='records')
    meta = {
        'row_count': len(rows),
        'mpn_column': detected_mpn_col,
        'part_number_column': pn_col,
        'manufacturer_column': mfr_col,
        'qty_column': qty_col,
        'designator_column': ref_col,
        'sheet': selected_sheet,
        'workers': max_workers,
        'boards': boards,
        'statuses': statuses,
        'api_calls': dk.calls,
        'api_rate_remaining': dk.rate_remaining,
    }
    meta['cards'] = cards
    return rows, alternatives, meta


def lookup_replacement(query: str, need: int, original_mpn: str = '', original_manufacturer: str = '') -> dict[str, Any]:
    """Look up a replacement the user pasted for one BOM line and compare it with that line's part (if it had one)."""
    cache = load_cache()
    dk = _build_dk_client(ensure_valid_access_token(), cache)
    try:
        original = None
        if original_mpn:
            original, _, _ = resolve_product([(original_mpn, original_manufacturer)], dk)
        alt = manual_replacement(query, max(1, int(need)), dk, original)
    finally:
        save_cache(cache)
    return {**alt, 'api_calls': dk.calls, 'api_rate_remaining': dk.rate_remaining}
