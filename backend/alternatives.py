"""Suggest orderable replacements for BOM lines that can't be bought as-is, and judge each one against the original.

Candidates come from the DigiKey Product Information v4 API:
1. DigiKey's own substitutes (`/search/{part}/substitutions`): Direct / Upgrade / Parametric Equivalent / Similar.
2. For resistors, capacitors and inductors, a parametric search in the same category (same value, package,
   tolerance, ...), which covers niche parts DigiKey lists no substitutes for; if nothing orderable turns up, tighter
   tolerances and then one step looser.

Every candidate is then compared spec by spec with the original (`specs.compare_parts`) and gets a verdict. Only
`drop_in` candidates (same package, every listed spec equal or better) are safe to pick without a human.
"""

import re
import urllib.parse
from typing import Any, Optional

from digikey_client import DigiKeyV4, build_dk_search_url, lookup_product, merge_listings, pick_variation
from specs import compare_parts

MAX_ALTERNATIVES = 5
MIN_DROP_INS = 3
# Each checked substitute costs one productdetails call (API budget is ~1000 calls/day). Actives only have DigiKey's
# substitutes to go on, so more of them are checked.
MAX_SUBSTITUTES_CHECKED = {'passive': 3, 'active': 6}

# Top-level category -> parameters a parametric search must match exactly.
PASSIVE_SEARCH_PARAMETERS: dict[str, list[str]] = {
    'Resistors': ['Resistance', 'Package / Case', 'Tolerance'],
    'Capacitors': ['Capacitance', 'Package / Case', 'Voltage - Rated', 'Temperature Coefficient'],
    'Inductors, Coils, Chokes': ['Inductance', 'Package / Case'],
}
SUBSTITUTE_RANK = {'Direct': 0, 'Upgrade': 1, 'Parametric Equivalent': 2, 'Similar': 3}
VERDICT_RANK = {'drop_in': 0, 'check': 1, 'worse': 2, 'unverified': 2, 'different_package': 3}


def _categories(product: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    top = product.get('Category') or {}
    leaf = top
    while leaf.get('ChildCategories'):
        leaf = leaf['ChildCategories'][0]
    return top, leaf


def _params(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p.get('ParameterText', ''): p for p in (product.get('Parameters') or [])}


def _is_passive(product: dict[str, Any]) -> bool:
    return _categories(product)[0].get('Name') in PASSIVE_SEARCH_PARAMETERS


def _same_part(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get('ManufacturerProductNumber') or '').lower() == (b.get('ManufacturerProductNumber') or '').lower() and (
        (a.get('Manufacturer') or {}).get('Id') == (b.get('Manufacturer') or {}).get('Id')
    )


def _absolute(url: str) -> str:
    url = (url or '').strip()
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return 'https://www.digikey.com' + url
    return url


def product_card(product: dict[str, Any]) -> dict[str, Any]:
    """Display fields for a DigiKey product: description, photo, datasheet and product page."""
    description = product.get('Description')
    if isinstance(description, dict):
        description = description.get('ProductDescription') or description.get('DetailedDescription') or ''
    mpn = product.get('ManufacturerProductNumber', '')
    return {
        'mpn': mpn,
        'manufacturer': (product.get('Manufacturer') or {}).get('Name', ''),
        'description': str(description or ''),
        'photo': _absolute(product.get('PhotoUrl', '')),
        'datasheet': _absolute(product.get('DatasheetUrl', '')),
        'url': _absolute(product.get('ProductUrl', '')) or build_dk_search_url(mpn),
    }


def _alternative(
    product: dict[str, Any], need: int, source: str, original: Optional[dict[str, Any]] = None
) -> Optional[dict[str, Any]]:
    variation, status = pick_variation(product, need)
    if not variation:
        return None
    if original:
        judgement = compare_parts(original, product)
    else:
        judgement = {'verdict': 'unverified', 'summary': 'no original part to compare against', 'specs': [],
                     'worse_count': 0, 'minor_count': 0}
    return {
        **product_card(product),
        'dkpn': variation['dkpn'],
        'packaging': variation['packaging'],
        'stock': variation['stock'],
        'moq': variation['moq'],
        'unit_price': variation['unit_price'],
        'status': status,
        'orderable': status in ('ok', 'marketplace'),
        'source': source,
        'verdict': judgement['verdict'],
        'detail': judgement['summary'],
        'specs': judgement['specs'],
        'worse_count': judgement['worse_count'],
        'minor_count': judgement['minor_count'],
        'review': judgement['verdict'] != 'drop_in',
    }


def _from_substitutes(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[dict[str, Any]]:
    variations = product.get('ProductVariations') or []
    if not variations:
        return []
    subs = (dk.substitutions(variations[0].get('DigiKeyProductNumber', '')) or {}).get('ProductSubstitutes') or []

    # The endpoint lists one entry per packaging; group to one per part, keeping its best type and largest stock.
    parts: dict[tuple, dict[str, Any]] = {}
    for sub in subs:
        kind = sub.get('SubstituteType', '')
        if kind not in SUBSTITUTE_RANK or _same_part(sub, product):
            continue
        key = ((sub.get('Manufacturer') or {}).get('Id'), sub.get('ManufacturerProductNumber'))
        entry = parts.setdefault(key, {'sub': sub, 'rank': SUBSTITUTE_RANK[kind], 'stock': 0, 'kind': kind})
        entry['stock'] = max(entry['stock'], int(sub.get('QuantityAvailable') or 0))
        if SUBSTITUTE_RANK[kind] < entry['rank']:
            entry.update(rank=SUBSTITUTE_RANK[kind], kind=kind)

    ranked = sorted((p for p in parts.values() if p['stock'] >= need), key=lambda p: (p['rank'], -p['stock']))
    limit = MAX_SUBSTITUTES_CHECKED['passive' if _is_passive(product) else 'active']
    out = []
    for entry in ranked[:limit]:
        sub = entry['sub']
        full = lookup_product(dk, sub['ManufacturerProductNumber'], (sub.get('Manufacturer') or {}).get('Id'))
        alt = _alternative(full, need, f'DigiKey {entry["kind"].lower()} substitute', product) if full else None
        if alt:
            out.append(alt)
    return out


def _percent(text: str) -> Optional[float]:
    match = re.search(r'([0-9.]+)\s*%', text or '')
    return float(match.group(1)) if match else None


def _parametric_search(
    product: dict[str, Any], need: int, dk: DigiKeyV4, tolerance_ids: Optional[list[str]] = None, limit: int = 20
) -> Optional[dict[str, Any]]:
    """Search the product's category for in-stock parts with the same required parameters.

    `tolerance_ids` replaces the tolerance filter with a list of allowed tolerance values ([] = any tolerance).
    """
    top, leaf = _categories(product)
    params = _params(product)
    filters = []
    for name in PASSIVE_SEARCH_PARAMETERS.get(top.get('Name'), []):
        param = params.get(name) or {}
        if param.get('ValueId') in (None, ''):
            continue
        values = [str(param['ValueId'])]
        if name == 'Tolerance' and tolerance_ids is not None:
            if not tolerance_ids:
                continue
            values = tolerance_ids
        filters.append({'ParameterId': param['ParameterId'], 'FilterValues': [{'Id': v} for v in values]})
    if not filters or not leaf.get('CategoryId'):
        return None
    return dk.keyword_search(
        '',
        limit=limit,
        filters={
            'CategoryFilter': [{'Id': str(leaf['CategoryId'])}],
            'MinimumQuantityAvailable': need,
            'ParameterFilterRequest': {'CategoryFilter': {'Id': str(leaf['CategoryId'])}, 'ParameterFilters': filters},
        },
        sort={'Field': 'QuantityAvailable', 'SortOrder': 'Descending'},
    )


def _from_parametric(product: dict[str, Any], found: Optional[dict[str, Any]], need: int) -> list[dict[str, Any]]:
    out = []
    for candidate in merge_listings((found or {}).get('Products') or []):
        if not _same_part(candidate, product):
            alt = _alternative(candidate, need, 'parametric match', product)
            if alt:
                out.append(alt)
    return out


def _tolerance_steps(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[str]:
    """Tolerance value ids, from DigiKey's filter options, tighter than the original plus the next looser one."""
    original = _percent((_params(product).get('Tolerance') or {}).get('ValueText', ''))
    if original is None:
        return []
    probe = _parametric_search(product, need, dk, tolerance_ids=[], limit=1) or {}
    values = []
    for pf in (probe.get('FilterOptions') or {}).get('ParametricFilters') or []:
        if pf.get('ParameterName') == 'Tolerance':
            values = [(_percent(v.get('ValueName', '')), str(v.get('ValueId'))) for v in pf.get('FilterValues') or []]
    values = sorted((pct, vid) for pct, vid in values if pct is not None)
    tighter = [vid for pct, vid in values if pct < original]
    looser = [vid for pct, vid in values if pct > original][:1]
    return tighter + looser


def _dedupe(alts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per part; when the same part came from two sources, keep the orderable one."""
    best: dict[tuple, dict[str, Any]] = {}
    for alt in alts:
        key = (alt['mpn'].lower(), alt['manufacturer'].lower())
        if key not in best or (alt['orderable'] and not best[key]['orderable']):
            best[key] = alt
    return list(best.values())


def _rank(alts: list[dict[str, Any]], original_manufacturer: str = '') -> list[dict[str, Any]]:
    """Best first: orderable, DigiKey seller over marketplace (elec's PCB rules say no marketplace parts), verdict,
    fewest major specs worse, then fewest minor ones (a 0.05 mm taller part beats a worse tempco), same manufacturer
    as the original, then price."""
    return sorted(_dedupe(alts), key=lambda a: (
        not a['orderable'], a['status'] == 'marketplace', VERDICT_RANK.get(a['verdict'], 9),
        a['worse_count'] - a.get('minor_count', 0), a.get('minor_count', 0),
        a['manufacturer'] != original_manufacturer, a['unit_price'] or 1e9,
    ))


def find_alternatives(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[dict[str, Any]]:
    """Orderable replacements for a matched product that is out of stock, below MOQ, or marketplace-only."""
    alts = _from_substitutes(product, need, dk)

    def drop_ins() -> int:
        return len(_dedupe([a for a in alts if a['orderable'] and a['verdict'] == 'drop_in']))

    # Passives: keep looking until there are a few orderable drop-ins to choose from (one search call each).
    if _is_passive(product) and drop_ins() < MIN_DROP_INS:
        alts += _from_parametric(product, _parametric_search(product, need, dk), need)
        if not drop_ins():
            # Precision parts are often reel-only: try tighter tolerances, then one step looser (judged "worse").
            steps = _tolerance_steps(product, need, dk)
            if steps:
                alts += _from_parametric(product, _parametric_search(product, need, dk, tolerance_ids=steps), need)
    return _rank(alts, (product.get('Manufacturer') or {}).get('Name', ''))[:MAX_ALTERNATIVES]


def _fix_mojibake(text: str) -> str:
    """UTF-8 read as Windows-1252 somewhere along the way: "100 Âµ" -> "100 µ"."""
    if 'Â' in text or 'Ã' in text:
        try:
            return text.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text.replace('Â', '')
    return text


UNMATCHED_SOURCE_RANK = {'same part number, other manufacturer': 0, 'description match': 1, 'keyword match': 2}


def suggest_for_unmatched(
    candidates: list[tuple[str, str]], need: int, dk: DigiKeyV4, description: str = ''
) -> list[dict[str, Any]]:
    """Closest DigiKey products for a BOM line with no unique match (ambiguous or unknown part number).

    The line's description is searched too: when the "part number" is just a value ("100uF"), the description
    ("100 µF ±20% 25V Ceramic Capacitor X7R ...") is what finds the intended part.
    """
    alts: list[dict[str, Any]] = []
    searches = [(mpn, False) for mpn, _ in candidates[:2]]
    description = _fix_mojibake(description).strip()
    if description:
        searches.append((description[:120], True))
    for query, is_description in searches:
        found = dk.keyword_search(query, limit=10)
        for candidate in merge_listings(found.get('Products') or []):
            exact = not is_description and (candidate.get('ManufacturerProductNumber') or '').lower() == query.lower()
            source = 'same part number, other manufacturer' if exact else (
                'description match' if is_description else 'keyword match')
            alt = _alternative(candidate, need, source)
            if alt:
                if exact:
                    alt['detail'] = 'same part number from another manufacturer; confirm it is the part you meant'
                elif is_description:
                    alt['detail'] = 'matches the BOM description; check it is the part you meant'
                alts.append(alt)
    alts = _dedupe(alts)
    alts.sort(key=lambda a: (not a['orderable'], UNMATCHED_SOURCE_RANK.get(a['source'], 9)))
    return alts[:MAX_ALTERNATIVES]


class ManualLookupError(ValueError):
    """A pasted replacement that can't be used; the message is shown to the user as-is."""


def parse_part_query(text: str) -> str:
    """Part number from what the user pasted: a DigiKey product link, a DigiKey part number or an MPN.

    Links look like digikey.com/en/products/detail/<manufacturer>/<mpn>/<id> (older: /product-detail/en/<mfr>/<mpn>/...).
    """
    text = (text or '').strip()
    if not text:
        raise ManualLookupError('Paste a DigiKey link, DigiKey part number or manufacturer part number.')
    if not re.match(r'^(https?://|www\.|[a-z0-9-]+\.(com|net|org|io|co\.uk|de|cn)/)', text, re.IGNORECASE):
        return text
    url = urllib.parse.urlparse(text if '://' in text else 'https://' + text)
    if not url.netloc.lower().endswith('digikey.com'):
        raise ManualLookupError(
            'Only DigiKey parts can go in the DigiKey cart. To buy it elsewhere, use "Skip this line" and add a note.'
        )
    segments = [urllib.parse.unquote(s) for s in url.path.split('/') if s]
    for marker, offset in (('detail', 2), ('product-detail', 3)):
        if marker in segments and len(segments) > segments.index(marker) + offset:
            return segments[segments.index(marker) + offset]
    raise ManualLookupError('That DigiKey link is not a product page. Open the part and copy the link from there.')


def manual_replacement(
    query: str, need: int, dk: DigiKeyV4, original: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """A user-supplied replacement, judged against the original exactly like the automatic suggestions."""
    part = parse_part_query(query)
    product = lookup_product(dk, part)
    if not product:
        raise ManualLookupError(
            f'No single DigiKey product for "{part}" (not found, or made by several manufacturers). '
            'Paste the link to the DigiKey product page instead.'
        )
    alt = _alternative(product, need, 'your pick', original)
    if not alt:
        raise ManualLookupError(f'{product.get("ManufacturerProductNumber", part)} has no DigiKey listing to order from.')
    return alt
