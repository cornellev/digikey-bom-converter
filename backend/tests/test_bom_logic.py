"""Unit tests for BOM parsing and variation choice (no DigiKey calls). Run: cd backend && python -m pytest tests"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bom_service import clean_frame, manufacturer_matches, mpn_candidates, parse_qty  # noqa: E402
from digikey_client import pick_variation  # noqa: E402


def test_candidates_altium365_name_and_part_number():
    assert mpn_candidates('VJ0603Y104KXXAP', 'Vishay VJ0603Y104KXXAP, ', '') == [('VJ0603Y104KXXAP', 'Vishay')]


def test_candidates_mpn_with_spaces_keeps_manufacturer():
    assert mpn_candidates('G5CA-1A-E DC24', 'Omron G5CA-1A-E DC24', '') == [('G5CA-1A-E DC24', 'Omron')]


def test_candidates_description_in_name_falls_back_to_part_number():
    assert mpn_candidates('147K 1% 0603(1608)', 'Panasonic ERJ-3EKF1473V', '') == [
        ('147K 1% 0603(1608)', ''),
        ('ERJ-3EKF1473V', 'Panasonic'),
    ]


def test_candidates_multiple_part_numbers_and_explicit_manufacturer_column():
    got = mpn_candidates('1N4148WS', 'onsemi 1N4148WS, Diodes 1N4148WS-7-F', 'onsemi')
    assert got == [('1N4148WS', 'onsemi'), ('1N4148WS-7-F', 'Diodes')]


def test_manufacturer_matching_is_loose_on_suffixes():
    assert manufacturer_matches('Yageo Group', 'YAGEO')
    assert manufacturer_matches('TE Connectivity', 'TE Connectivity AMP Connectors')
    assert not manufacturer_matches('Vishay', 'onsemi')
    assert not manufacturer_matches('', 'onsemi')


def test_parse_qty_uses_column_then_designators():
    assert parse_qty('4', '') == 4
    assert parse_qty('', 'C1, C3, C7') == 3
    assert parse_qty('n/a', '') == 1


def test_clean_frame_drops_previous_output_columns_and_blank_rows():
    frame = pd.DataFrame({
        'Unnamed: 0': ['', '', ''],
        'Name': ['R1V', '', 'C2V'],
        'Qty': ['1', '', '2'],
        'dkpn': ['MANUAL CHECK REQUIRED', '', 'x'],
    })
    cleaned = clean_frame(frame)
    assert list(cleaned.columns) == ['Name', 'Qty']
    assert list(cleaned['Name']) == ['R1V', 'C2V']


def _variation(dkpn, package, stock, moq=1, marketplace=False):
    return {
        'DigiKeyProductNumber': dkpn,
        'PackageType': {'Name': package},
        'QuantityAvailableforPackageType': stock,
        'MinimumOrderQuantity': moq,
        'MarketPlace': marketplace,
        'StandardPricing': [{'BreakQuantity': 1, 'UnitPrice': 0.1}],
    }


def test_pick_prefers_cut_tape_with_stock():
    product = {'ProductVariations': [
        _variation('TR', 'Tape & Reel (TR)', 10000, moq=5000),
        _variation('CT', 'Cut Tape (CT)', 50),
        _variation('DKR', 'Digi-Reel®', 50),
    ]}
    variation, status = pick_variation(product, 10)
    assert (variation['dkpn'], status) == ('CT', 'ok')


def test_pick_uses_digireel_when_cut_tape_is_short():
    product = {'ProductVariations': [_variation('CT', 'Cut Tape (CT)', 5), _variation('DKR', 'Digi-Reel®', 500)]}
    variation, status = pick_variation(product, 10)
    assert (variation['dkpn'], status) == ('DKR', 'ok')


def test_pick_reports_moq_for_reel_only_part():
    product = {'ProductVariations': [_variation('TR', 'Tape & Reel (TR)', 457984, moq=1000, marketplace=True)]}
    _, status = pick_variation(product, 2)
    assert status == 'moq'


def test_pick_reports_out_of_stock_and_marketplace():
    assert pick_variation({'ProductVariations': [_variation('CT', 'Cut Tape (CT)', 0)]}, 1)[1] == 'out_of_stock'
    assert pick_variation({'ProductVariations': [_variation('CT', 'Cut Tape (CT)', 3)]}, 10)[1] == 'low_stock'
    market = {'ProductVariations': [_variation('M', 'Cut Tape (CT)', 100, marketplace=True)]}
    assert pick_variation(market, 10)[1] == 'marketplace'
