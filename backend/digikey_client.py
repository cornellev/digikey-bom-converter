"""DigiKey Product API client and offer selection helpers."""

import os
import time
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


# --- Digi-Key Product API Client ---
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
    ):
        self.base = v4_base.rstrip('/')
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
                retry_after = response.headers.get('Retry-After')
                wait = int(retry_after) if (retry_after and retry_after.isdigit()) else (2 ** attempt)
                time.sleep(wait)
                last = response
                continue
            if status in (500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                last = response
                continue
            return response
        return last or response

    def _get(self, path: str) -> dict[str, Any]:
        response = self._request_with_retry('GET', f'{self.base}{path}')
        if response.status_code == 404:
            return {'__not_found__': True}
        if response.status_code == 401:
            raise RuntimeError('401 Unauthorized: token invalid/expired or subscription mismatch.')
        if response.status_code >= 400:
            raise RuntimeError(f'HTTP {response.status_code}: {response.text[:800]}')
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request_with_retry('POST', f'{self.base}{path}', json=payload)
        if response.status_code == 401:
            raise RuntimeError('401 Unauthorized: token invalid/expired or subscription mismatch.')
        if response.status_code >= 400:
            raise RuntimeError(f'HTTP {response.status_code}: {response.text[:800]}')
        return response.json()

    def productdetails_by_mpn(self, mpn: str) -> dict[str, Any]:
        return self._get(f'/search/{mpn}/productdetails')

    def keyword_search(self, mpn: str, limit: int = 5) -> dict[str, Any]:
        return self._post('/search/keyword', {'Keywords': mpn, 'Limit': limit})


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


def prefer_cut_tape(offers: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not offers:
        return None

    def score(offer: dict[str, Any]) -> tuple[int, int]:
        pkg = (offer.get('packaging') or '').lower()
        stock = int(offer.get('quantityAvailable') or 0)
        if 'cut tape' in pkg or '(ct)' in pkg:
            base = 0
        elif 'digi-reel' in pkg:
            base = 1
        elif 'reel' in pkg:
            base = 2
        else:
            base = 3
        return (base, -stock)

    return sorted(offers, key=score)[0]


def offers_from_productdetails(data: dict[str, Any]) -> list[dict[str, Any]]:
    product = (data or {}).get('Product') or {}
    variations = product.get('ProductVariations') or []
    offers: list[dict[str, Any]] = []
    for variation in variations:
        offers.append(
            {
                'dkpn': variation.get('DigiKeyProductNumber') or variation.get('DigiKeyPartNumber') or variation.get('PartNumber'),
                'packaging': ((variation.get('PackageType') or {}).get('Name'))
                or variation.get('Packaging')
                or variation.get('ProductPackaging')
                or '',
                'quantityAvailable': variation.get('QuantityAvailableforPackageType') or variation.get('QuantityAvailable') or 0,
            }
        )
    return [o for o in offers if o.get('dkpn')]


def offers_from_keyword(data: dict[str, Any]) -> list[dict[str, Any]]:
    products = (data or {}).get('Products') or []
    offers: list[dict[str, Any]] = []
    for product in products:
        for variation in (product.get('ProductVariations') or []):
            offers.append(
                {
                    'dkpn': variation.get('DigiKeyProductNumber') or variation.get('DigiKeyPartNumber') or variation.get('PartNumber'),
                    'packaging': ((variation.get('PackageType') or {}).get('Name'))
                    or variation.get('Packaging')
                    or variation.get('ProductPackaging')
                    or '',
                    'quantityAvailable': variation.get('QuantityAvailableforPackageType') or variation.get('QuantityAvailable') or 0,
                }
            )
    return [o for o in offers if o.get('dkpn')]
