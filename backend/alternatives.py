"""Suggest orderable replacements for BOM lines that can't be bought as-is.

Two sources, both from the DigiKey Product Information v4 API:
1. DigiKey's own substitutes (`/search/{part}/substitutions`): Direct / Upgrade / Similar parts.
2. A parametric search in the same category for passives (same value, package, tolerance or tighter, ...), which
   covers niche parts DigiKey lists no substitutes for. Not used for ICs and other actives: "same package and similar
   specs" is not a safe swap there. Actives only get DigiKey's own substitutes, with the package compared and anything
   short of a Direct substitute labelled for engineer review.
"""

import re
from typing import Any, Optional

from digikey_client import DigiKeyV4, build_dk_search_url, pick_variation

MAX_ALTERNATIVES = 5
MAX_SUBSTITUTES_CHECKED = 3  # each costs one productdetails call (API budget is ~1000 calls/day)

# Top-level category -> (parameters that must match exactly, parameters that improve the ranking when they match).
PASSIVE_PARAMETERS: dict[str, tuple[list[str], list[str]]] = {
    'Resistors': (
        ['Resistance', 'Package / Case', 'Tolerance'],
        ['Temperature Coefficient', 'Power (Watts)', 'Composition', 'Ratings'],
    ),
    'Capacitors': (
        ['Capacitance', 'Package / Case', 'Voltage - Rated', 'Temperature Coefficient'],
        ['Tolerance', 'Operating Temperature', 'Ratings', 'Height - Seated (Max)'],
    ),
    'Inductors, Coils, Chokes': (
        ['Inductance', 'Package / Case'],
        ['Current Rating (Amps)', 'Tolerance', 'Shielding', 'DC Resistance (DCR)', 'Current - Saturation (Isat)'],
    ),
}
SUBSTITUTE_RANK = {'Direct': 0, 'Upgrade': 1, 'Parametric Equivalent': 2, 'Similar': 3}


def _categories(product: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    top = product.get('Category') or {}
    leaf = top
    while leaf.get('ChildCategories'):
        leaf = leaf['ChildCategories'][0]
    return top, leaf


def _params(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p.get('ParameterText', ''): p for p in (product.get('Parameters') or [])}


def _is_passive(product: dict[str, Any]) -> bool:
    return _categories(product)[0].get('Name') in PASSIVE_PARAMETERS


def _same_part(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get('ManufacturerProductNumber') or '').lower() == (b.get('ManufacturerProductNumber') or '').lower() and (
        (a.get('Manufacturer') or {}).get('Id') == (b.get('Manufacturer') or {}).get('Id')
    )


def _alternative(product: dict[str, Any], need: int, source: str, detail: str = '') -> Optional[dict[str, Any]]:
    variation, status = pick_variation(product, need)
    if not variation:
        return None
    mpn = product.get('ManufacturerProductNumber', '')
    return {
        'mpn': mpn,
        'manufacturer': (product.get('Manufacturer') or {}).get('Name', ''),
        'description': (product.get('Description') or {}).get('ProductDescription', '')
        if isinstance(product.get('Description'), dict) else str(product.get('Description') or ''),
        'dkpn': variation['dkpn'],
        'packaging': variation['packaging'],
        'stock': variation['stock'],
        'moq': variation['moq'],
        'unit_price': variation['unit_price'],
        'status': status,
        'orderable': status in ('ok', 'marketplace'),
        'source': source,
        'detail': detail,
        'review': False,
        'url': build_dk_search_url(mpn),
    }


def _from_substitutes(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[dict[str, Any]]:
    variations = product.get('ProductVariations') or []
    if not variations:
        return []
    subs = (dk.substitutions(variations[0].get('DigiKeyProductNumber', '')) or {}).get('ProductSubstitutes') or []
    package = (_params(product).get('Package / Case') or {}).get('ValueText', '')

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
    out = []
    for entry in ranked[:MAX_SUBSTITUTES_CHECKED]:
        sub = entry['sub']
        details = dk.productdetails_by_mpn(sub['ManufacturerProductNumber'], (sub.get('Manufacturer') or {}).get('Id'))
        full = details.get('Product') if not details.get('__not_found__') else None
        if not full:
            continue
        sub_package = (_params(full).get('Package / Case') or {}).get('ValueText', '')
        notes = []
        if package and sub_package and sub_package != package:
            notes.append(f'DIFFERENT package: {sub_package} (was {package}), not a drop-in')
        elif package and sub_package:
            notes.append(f'same package {package}')
        alt = _alternative(full, need, f'DigiKey substitute ({entry["kind"].lower()})', '; '.join(notes))
        if alt:
            different_package = bool(package and sub_package and sub_package != package)
            alt['review'] = different_package or (entry['kind'] != 'Direct' and not _is_passive(product))
            out.append(alt)
    # Same-package swaps first; keep DigiKey's ranking otherwise.
    out.sort(key=lambda a: a['detail'].startswith('DIFFERENT'))
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
    required, _ = PASSIVE_PARAMETERS.get(top.get('Name'), ([], []))
    params = _params(product)
    filters = []
    for name in required:
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


def _rank_parametric(product: dict[str, Any], found: Optional[dict[str, Any]], need: int) -> list[dict[str, Any]]:
    top, _ = _categories(product)
    required, preferred = PASSIVE_PARAMETERS.get(top.get('Name'), ([], []))
    params = _params(product)
    original_tolerance = _percent((params.get('Tolerance') or {}).get('ValueText', ''))
    scored = []
    for candidate in (found or {}).get('Products') or []:
        if _same_part(candidate, product):
            continue
        cparams = _params(candidate)
        same = [n for n in required if n in params and n in cparams
                and cparams[n].get('ValueText') == params[n].get('ValueText')]
        matched = [n for n in preferred if n in params and n in cparams
                   and cparams[n].get('ValueText') == params[n].get('ValueText')]
        differs = [f'{n} {cparams[n].get("ValueText")} (was {params[n].get("ValueText")})'
                   for n in required + preferred if n in params and n in cparams and n not in same + matched]
        detail = 'same ' + ', '.join(params[n].get('ValueText', '') for n in same)
        detail += f'; differs: {"; ".join(differs)}' if differs else '; other specs match'
        alt = _alternative(candidate, need, 'parametric match', detail)
        if not alt:
            continue
        tolerance = _percent((cparams.get('Tolerance') or {}).get('ValueText', ''))
        alt['review'] = bool(original_tolerance is not None and tolerance is not None and tolerance > original_tolerance)
        if alt['review']:
            alt['detail'] = 'LOOSER tolerance, check the circuit; ' + alt['detail']
        scored.append((alt['review'], -len(matched), alt))
    scored.sort(key=lambda s: (s[0], not s[2]['orderable'], s[2]['status'] == 'marketplace', s[1], s[2]['unit_price'] or 1e9))
    return [alt for _, _, alt in scored]


def _tolerance_steps(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[str]:
    """Tolerance value ids, from DigiKey's filter options, that are tighter than the original plus the next looser one."""
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
    seen, out = set(), []
    for alt in alts:
        key = (alt['mpn'].lower(), alt['manufacturer'].lower())
        if key not in seen:
            seen.add(key)
            out.append(alt)
    return out


def find_alternatives(product: dict[str, Any], need: int, dk: DigiKeyV4) -> list[dict[str, Any]]:
    """Orderable replacements for a matched product that is out of stock, below MOQ, or marketplace-only."""
    alts = _from_substitutes(product, need, dk)
    if _is_passive(product) and len([a for a in alts if a['orderable']]) < MAX_ALTERNATIVES:
        alts += _rank_parametric(product, _parametric_search(product, need, dk), need)
        if not any(a['orderable'] for a in alts):
            # Precision parts are often reel-only: try tighter tolerances, then one step looser (flagged for review).
            steps = _tolerance_steps(product, need, dk)
            if steps:
                alts += _rank_parametric(product, _parametric_search(product, need, dk, tolerance_ids=steps), need)
    alts = _dedupe(alts)
    # Stable sort: keeps DigiKey's / parameter ranking within each group.
    alts.sort(key=lambda a: (not a['orderable'], a['review'], a['status'] == 'marketplace'))
    return alts[:MAX_ALTERNATIVES]


def suggest_for_unmatched(candidates: list[tuple[str, str]], need: int, dk: DigiKeyV4) -> list[dict[str, Any]]:
    """Closest DigiKey products for a BOM line with no unique match (ambiguous or unknown part number)."""
    alts: list[dict[str, Any]] = []
    for mpn, _ in candidates[:2]:
        found = dk.keyword_search(mpn, limit=10)
        for candidate in found.get('Products') or []:
            exact = (candidate.get('ManufacturerProductNumber') or '').lower() == mpn.lower()
            alt = _alternative(candidate, need, 'same part number, other manufacturer' if exact else 'keyword match')
            if alt:
                alts.append(alt)
    alts = _dedupe(alts)
    alts.sort(key=lambda a: (not a['orderable'], a['source'] != 'same part number, other manufacturer'))
    return alts[:MAX_ALTERNATIVES]
