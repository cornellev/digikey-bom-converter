"""Compare a candidate part's DigiKey parameters against the original part and reach a verdict.

Each parameter is classed by name: must match (package, value, topology...), higher is better (voltage/current/power
ratings), lower is better (tolerance, Rds(on), leakage...), or a temperature range the candidate must cover. Anything
else is informational and ignored. The verdict:

- `drop_in`: same package and every compared spec equal or better. Safe to substitute without review.
- `check`: no major spec worse, but a minor one is (gate charge, height...) or some specs aren't listed.
- `worse`: at least one spec is worse (the reasons say which, with both values).
- `different_package`: not a drop-in regardless of specs.
"""

import re
from typing import Any, Optional

# Parameter-name prefixes (DigiKey ParameterText), checked in order.
MATCH = [
    'Package / Case', 'Mounting Type', 'FET Type', 'Transistor Type', 'Diode Type', 'Technology', 'Topology',
    'Output Type', 'Output Configuration', 'Function', 'Number of Outputs', 'Number of Channels', 'Resistance',
    'Capacitance', 'Inductance', 'Number of Terminations', 'Number of Positions', 'Pitch', 'Contact Form',
    'Coil Voltage', 'Synchronous Rectifier', 'Composition', 'Polarization', 'Shielding',
]
HIGHER = [
    'Drain to Source Voltage', 'Current - Continuous Drain', 'Power', 'Voltage - Rated', 'Current Rating',
    'Current - Saturation', 'Voltage - Input (Max)', 'Current - Output', 'Vgs (Max)', 'Voltage - Output (Max)',
    'Voltage - DC Reverse', 'Current - Average Rectified', 'Voltage - Breakdown', 'Current - Collector (Ic)',
    'Voltage - Collector Emitter Breakdown', 'Frequency - Self Resonant', 'Contact Rating',
]
LOWER = [
    'Rds On', 'Tolerance', 'DC Resistance', 'Vgs(th)', 'Voltage - Input (Min)', 'Voltage - Forward',
    'Current - Reverse Leakage', 'Gate Charge', 'Height', 'Reverse Recovery', 'ESR',
]
RANGE = ['Operating Temperature']
# Second-order specs: being slightly worse here earns a "check", not a "worse".
MINOR = ['Gate Charge', 'Height', 'Reverse Recovery', 'ESR', 'Drive Voltage', 'Vgs(th)']

# Ceramic dielectrics, best first (stability over temperature).
DIELECTRICS = ['C0G', 'NP0', 'U2J', 'X8R', 'X8L', 'X7R', 'X7S', 'X7T', 'X6S', 'X5R', 'X6T', 'Y5V', 'Z5U']
AUTOMOTIVE_RE = re.compile(r'AEC-Q\d+|Automotive', re.IGNORECASE)

SI = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9}
NUMBER_RE = re.compile(r'(-?\d+(?:\.\d+)?)\s*([pnuµmkKMG]?)(?!pm)(?=[A-Za-zΩ%°/"]|\s|$)')


def number(text: str) -> Optional[float]:
    """First number in a DigiKey value, with SI prefix applied: '320mA (Ta)' -> 0.32, '±0.05%' -> 0.05."""
    match = NUMBER_RE.search((text or '').replace('±', ''))
    if not match:
        return None
    prefix = match.group(2)
    return float(match.group(1)) * SI.get(prefix, 1.0)


def temp_range(text: str) -> Optional[tuple[float, float]]:
    values = [float(v) for v in re.findall(r'(-?\d+(?:\.\d+)?)\s*°C', text or '')]
    return (min(values), max(values)) if len(values) >= 2 else None


def _kind(name: str) -> Optional[str]:
    if name.startswith('Supplier Device Package'):
        return None
    for kind, prefixes in (('match', MATCH), ('higher', HIGHER), ('lower', LOWER), ('range', RANGE)):
        if any(name.startswith(p) for p in prefixes):
            return kind
    if name.startswith('Temperature Coefficient'):
        return 'tempco'
    if name.startswith('Drive Voltage'):
        return 'drive'
    return None


def _missing(value: str) -> bool:
    return value.strip() in ('', '-', '*')


def _compare(kind: str, orig: str, cand: str) -> str:
    """Return 'same', 'better', 'worse' or 'unknown' for one parameter."""
    if kind == 'match' and orig.startswith(('Surface Mount', 'Through Hole', 'Chassis', 'Panel')):
        # Mounting Type: "Surface Mount, MLCC, Epoxy" (soft termination) is still surface mount.
        return 'same' if orig.split(',')[0].strip().lower() == cand.split(',')[0].strip().lower() else 'worse'
    if kind == 'match':
        return 'same' if orig.strip().lower() == cand.strip().lower() else 'worse'
    if kind in ('higher', 'lower'):
        a, b = number(orig), number(cand)
        if a is None or b is None:
            return 'same' if orig.strip() == cand.strip() else 'unknown'
        if abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-30):
            return 'same'
        return 'better' if (b > a) == (kind == 'higher') else 'worse'
    if kind == 'range':
        a, b = temp_range(orig), temp_range(cand)
        if not a or not b:
            return 'unknown'
        if b == a:
            return 'same'
        return 'better' if b[0] <= a[0] and b[1] >= a[1] else 'worse'
    if kind == 'tempco':
        da = next((d for d in DIELECTRICS if d in orig.upper()), None)
        db = next((d for d in DIELECTRICS if d in cand.upper()), None)
        if da and db:
            ra, rb = DIELECTRICS.index(da), DIELECTRICS.index(db)
            return 'same' if ra == rb else ('better' if rb < ra else 'worse')
        return _compare('lower', orig, cand)  # resistor ppm/°C
    if kind == 'drive':
        # "4.5V, 10V" = Rds(on) specified down to 4.5 V gate drive; a candidate specified only at 10 V is worse.
        a = [number(v) for v in orig.split(',')]
        b = [number(v) for v in cand.split(',')]
        a, b = [v for v in a if v is not None], [v for v in b if v is not None]
        if not a or not b:
            return 'unknown'
        return 'same' if min(a) == min(b) else ('better' if min(b) < min(a) else 'worse')
    return 'unknown'


# DigiKey records automotive grade in different fields depending on the category.
AUTOMOTIVE_FIELDS = ('Qualification', 'Grade', 'Ratings', 'Applications', 'Features')


def is_automotive(params: dict[str, str]) -> bool:
    return any(AUTOMOTIVE_RE.search(params.get(field, '')) for field in AUTOMOTIVE_FIELDS)


def parameters(product: dict[str, Any]) -> dict[str, str]:
    return {p.get('ParameterText', ''): str(p.get('ValueText', '')) for p in (product.get('Parameters') or [])}


def compare_parts(original: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare candidate to original. Returns verdict, a one-line summary and per-parameter rows for display."""
    po, pc = parameters(original), parameters(candidate)
    rows = []
    for name, orig in po.items():
        kind = _kind(name)
        if not kind or _missing(orig):
            continue
        cand = pc.get(name, '')
        result = 'unknown' if _missing(cand) else _compare(kind, orig, cand)
        rows.append({'name': name, 'original': orig, 'candidate': cand or '-', 'result': result})
    auto_o, auto_c = is_automotive(po), is_automotive(pc)
    if auto_o or auto_c:
        rows.append({
            'name': 'Automotive (AEC-Q)', 'original': 'yes' if auto_o else 'no', 'candidate': 'yes' if auto_c else 'no',
            'result': 'same' if auto_o == auto_c else ('better' if auto_c else 'worse'),
        })

    minor = [r for r in rows if r['result'] == 'worse' and any(r['name'].startswith(m) for m in MINOR)]
    worse = [r for r in rows if r['result'] == 'worse' and r not in minor]
    unknown = [r for r in rows if r['result'] == 'unknown']
    better = [r for r in rows if r['result'] == 'better']
    package_differs = any(r['name'].startswith('Package / Case') and r['result'] == 'worse' for r in rows)

    def short(name: str) -> str:
        return re.split(r'\s[@(]', name)[0]

    if package_differs:
        verdict = 'different_package'
        package = pc.get('Package / Case', '?')
        summary = f'different package ({package}), not a drop-in'
    elif worse:
        verdict = 'worse'
        summary = 'worse on ' + '; '.join(f'{short(r["name"])}: {r["candidate"]} vs {r["original"]}' for r in worse)
    elif unknown or minor:
        verdict = 'check'
        parts = []
        if minor:
            parts.append('slightly worse on ' + '; '.join(
                f'{short(r["name"])}: {r["candidate"]} vs {r["original"]}' for r in minor))
        if unknown:
            parts.append('not listed: ' + ', '.join(short(r['name']) for r in unknown))
        summary = 'no major spec worse; ' + '; '.join(parts)
    else:
        verdict = 'drop_in'
        summary = 'meets or beats every listed spec' + (
            ' (better: ' + ', '.join(short(r['name']) for r in better) + ')' if better else ''
        )
    return {'verdict': verdict, 'summary': summary, 'specs': rows, 'worse_count': len(worse) + len(minor),
            'minor_count': len(minor)}
