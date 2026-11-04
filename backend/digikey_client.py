"""DigiKey Product API client and offer selection helpers."""

import json
import os
import threading
import time
import urllib.parse
from typing import Any, Optional

import requests

# --- Configs/Constants ---
V4_BASE = {
    'prod': 'https://api.digikey.com/products/v4',
    'sandbox': 'https://sandbox-api.digikey.com/products/v4',
}


# --- Environment Variable Helpers ---
def env_name() -> str:
    env = os.getenv('DIGIKEY_ENVIRONMENT', 'prod').strip().lower()
    return env if env in V4_BASE else 'prod'


def locale_site() -> str:
    return os.getenv('DIGIKEY_LOCALE_SITE', 'US').strip()


def locale_language() -> str:
    return os.getenv('DIGIKEY_LOCALE_LANGUAGE', 'en').strip()


def locale_currency() -> str:
    return os.getenv('DIGIKEY_LOCALE_CURRENCY', 'USD').strip()


def locale_ship_to_country() -> str:
    return os.getenv('DIGIKEY_LOCALE_SHIPTOCOUNTRY', 'us').strip()


# --- DigiKey Product API Client ---
MAX_RATE_LIMIT_WAIT_S = 15  # longer Retry-After = the daily quota is used up, so stop instead of waiting


class QuotaExceeded(RuntimeError):
    """DigiKey's API quota for the app is used up (HTTP 429 with a long or missing Retry-After)."""

    def __init__(self, retry_after_s: Optional[int]):
        self.retry_after_s = retry_after_s
        if retry_after_s:
            hours, minutes = divmod(round(retry_after_s / 60), 60)
            when = f'in about {hours} h {minutes} min' if hours else f'in about {max(minutes, 1)} min'
        else:
            when = 'later (the limit resets daily)'
        super().__init__(f'DigiKey API limit reached for today. Try again {when}.')



class DigiKeyV4:
    def __init__(
        self,
        client_id: str,
        access_token: str,
        v4_base: str,
        site: str,
        language: str,
        currency: str,
        ship_to_country: str,
        cache: Optional[dict[str, Any]] = None,
        cache_ttl_s: int = 3600,
    ):
        self.base = v4_base.rstrip('/')
        # Response cache shared across worker threads: {key: {'t': epoch, 'v': payload}}.
        self.cache = cache if cache is not None else {}
        self.cache_ttl_s = cache_ttl_s
        self.calls = 0
        self.rate_remaining: Optional[int] = None
        self._lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update(
            {
                'Authorization': f'Bearer {access_token}',
                'X-DIGIKEY-Client-Id': client_id,
                'X-DIGIKEY-Locale-Site': site,
                'X-DIGIKEY-Locale-Language': language,
                'X-DIGIKEY-Locale-Currency': currency,
                'X-DIGIKEY-Locale-ShipToCountry': ship_to_country,
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
        )

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', 10)
        last = None
        for attempt in range(4):
            response = self.session.request(method, url, **kwargs)
            status = response.status_code
            if status == 429:
                retry_after = response.headers.get('Retry-After', '')
                wait = int(retry_after) if retry_after.isdigit() else None
                if wait is None or wait > MAX_RATE_LIMIT_WAIT_S:
                    raise QuotaExceeded(wait)
                time.sleep(wait)  # short per-minute burst limit: wait it out
                last = response
                continue
            if status in (500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                last = response
                continue
            return response
        return last or response

    def _note_response(self, response: requests.Response) -> None:
        with self._lock:
            self.calls += 1
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining and remaining.isdigit():
                self.rate_remaining = int(remaining)

    def _cached(self, key: str, fetch) -> dict[str, Any]:
        hit = self.cache.get(key)
        if hit and time.time() - hit.get('t', 0) < self.cache_ttl_s:
            return hit['v']
        value = fetch()
        # Errors raise before this point, so only real answers (including 404s) are cached.
        self.cache[key] = {'t': time.time(), 'v': value}
        return value

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        def fetch() -> dict[str, Any]:
            response = self._request_with_retry('GET', f'{self.base}{path}', params=params)
            self._note_response(response)
            if response.status_code == 429:
                raise QuotaExceeded(None)
            if response.status_code == 404:
                try:
                    detail = (response.json() or {}).get('detail', '')
                except ValueError:
                    detail = ''
                return {'__not_found__': True, 'detail': detail}
            if response.status_code == 401:
                raise RuntimeError('401 Unauthorized: token invalid/expired or subscription mismatch.')
            if response.status_code >= 400:
                raise RuntimeError(f'HTTP {response.status_code}: {response.text[:800]}')
            return response.json()

        return self._cached(f'GET {path} {sorted((params or {}).items())}', fetch)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        def fetch() -> dict[str, Any]:
            response = self._request_with_retry('POST', f'{self.base}{path}', json=payload)
            self._note_response(response)
            if response.status_code == 429:
                raise QuotaExceeded(None)
            if response.status_code == 401:
                raise RuntimeError('401 Unauthorized: token invalid/expired or subscription mismatch.')
            if response.status_code >= 400:
                raise RuntimeError(f'HTTP {response.status_code}: {response.text[:800]}')
            return response.json()

        return self._cached(f'POST {path} {json.dumps(payload, sort_keys=True)}', fetch)

    def productdetails_by_mpn(self, mpn: str, manufacturer_id: Optional[int] = None) -> dict[str, Any]:
        # MPNs can contain '/', '#', spaces etc.; they must be encoded as a single path segment.
        params = {'manufacturerId': manufacturer_id} if manufacturer_id else None
        return self._get(f'/search/{urllib.parse.quote(mpn, safe="")}/productdetails', params)

    def substitutions(self, product_number: str) -> dict[str, Any]:
        return self._get(f'/search/{urllib.parse.quote(product_number, safe="")}/substitutions')

    def keyword_search(
        self,
        keywords: str,
        limit: int = 5,
        filters: Optional[dict[str, Any]] = None,
        sort: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {'Keywords': keywords, 'Limit': limit}
        if filters:
            payload['FilterOptionsRequest'] = filters
        if sort:
            payload['SortOptions'] = sort
        return self._post('/search/keyword', payload)


def merge_listings(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DigiKey can list one part several times under different supplier prefixes (e.g. a reel-only 2571-... listing
    and a 4713-... listing with cut tape). Merge them per manufacturer + MPN so packaging is chosen across all of them."""
    merged: dict[tuple, dict[str, Any]] = {}
    for product in products:
        key = ((product.get('Manufacturer') or {}).get('Id'), (product.get('ManufacturerProductNumber') or '').lower())
        if key not in merged:
            merged[key] = {**product, 'ProductVariations': list(product.get('ProductVariations') or [])}
            continue
        seen = {v.get('DigiKeyProductNumber') for v in merged[key]['ProductVariations']}
        merged[key]['ProductVariations'] += [
            v for v in product.get('ProductVariations') or [] if v.get('DigiKeyProductNumber') not in seen
        ]
    return list(merged.values())


def lookup_product(dk: DigiKeyV4, mpn: str, manufacturer_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    """Product details for an MPN (optionally pinned to a manufacturer), with every DigiKey listing merged.

    productdetails answers "Duplicate Products found" when DigiKey lists the same part more than once, even with the
    manufacturer pinned. Then the keyword results with that exact MPN are merged instead; if they still span several
    manufacturers the part is genuinely ambiguous and None is returned.
    """
    details = dk.productdetails_by_mpn(mpn, manufacturer_id)
    product = details.get('Product') if not details.get('__not_found__') else None
    if product:
        return product
    if 'duplicate' not in str(details.get('detail', '')).lower():
        return None
    matches = [
        p for p in (dk.keyword_search(mpn, limit=50).get('Products') or [])
        if (p.get('ManufacturerProductNumber') or '').lower() == mpn.lower()
        and (manufacturer_id is None or (p.get('Manufacturer') or {}).get('Id') == manufacturer_id)
    ]
    merged = merge_listings(matches)
    return merged[0] if len(merged) == 1 else None


# --- Offer Extraction/Ranking Helpers ---
def build_dk_search_url(mpn: str) -> str:
    safe = requests.utils.quote(mpn)
    return f'https://www.digikey.com/en/products/result?keywords={safe}'


def label_packaging(name: Optional[str]) -> str:
    if not name:
        return ''
    n = name.lower()
    if 'cut tape' in n or '(ct)' in n:
        return 'Cut Tape (CT)'
    if 'digi-reel' in n or 'digireel' in n:
        return 'Digi-Reel'
    if 'tape & reel' in n or 'tape and reel' in n or 'reel' in n:
        return 'Tape & Reel'
    if 'tray' in n:
        return 'Tray'
    if 'bulk' in n:
        return 'Bulk'
    return name


def _packaging_rank(label: str) -> int:
    """Lower is better for small orders: cut tape and loose packaging, then Digi-Reel (reeling fee), then full reels."""
    if label == 'Tape & Reel':
        return 2
    if label == 'Digi-Reel':
        return 1
    return 0


def unit_price_at(pricing: list[dict[str, Any]], qty: int) -> Optional[float]:
    best = None
    for tier in sorted(pricing or [], key=lambda t: t.get('BreakQuantity') or 0):
        if (tier.get('BreakQuantity') or 0) <= max(qty, 1):
            best = tier.get('UnitPrice')
    return best


def summarize_variation(variation: dict[str, Any], need: int) -> dict[str, Any]:
    packaging = label_packaging(((variation.get('PackageType') or {}).get('Name')) or variation.get('Packaging') or '')
    stock = int(variation.get('QuantityAvailableforPackageType') or variation.get('QuantityAvailable') or 0)
    moq = int(variation.get('MinimumOrderQuantity') or 1)
    return {
        'dkpn': variation.get('DigiKeyProductNumber') or variation.get('DigiKeyPartNumber') or '',
        'packaging': packaging,
        'stock': stock,
        'moq': moq,
        'marketplace': bool(variation.get('MarketPlace')),
        'unit_price': unit_price_at(variation.get('StandardPricing') or [], need),
        'feasible': stock >= need and moq <= need,
    }


def pick_variation(product: dict[str, Any], need: int) -> tuple[Optional[dict[str, Any]], str]:
    """Choose the DigiKey variation to order `need` pieces of; return (variation, status).

    Status is 'ok', 'marketplace' (orderable but sold by a third party), 'moq' (in stock but the minimum order exceeds
    the need), 'low_stock' (some stock, not enough), or 'out_of_stock'.
    """
    variations = [summarize_variation(v, need) for v in (product.get('ProductVariations') or [])]
    variations = [v for v in variations if v['dkpn']]
    if not variations:
        return None, 'out_of_stock'

    def key(v: dict[str, Any]) -> tuple:
        return (not v['feasible'], v['marketplace'], _packaging_rank(v['packaging']), -v['stock'])

    best = sorted(variations, key=key)[0]
    if best['feasible']:
        return best, 'marketplace' if best['marketplace'] else 'ok'
    if any(v['stock'] >= need for v in variations):
        return best, 'moq'
    if any(v['stock'] > 0 for v in variations):
        return best, 'low_stock'
    return best, 'out_of_stock'
