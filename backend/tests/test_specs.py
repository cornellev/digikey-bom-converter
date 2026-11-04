"""Spec-comparison verdicts, using parameter values as DigiKey reports them."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from specs import compare_parts, number  # noqa: E402


def part(**params):
    names = {
        'pkg': 'Package / Case', 'vdss': 'Drain to Source Voltage (Vdss)', 'id': 'Current - Continuous Drain (Id) @ 25°C',
        'rds': 'Rds On (Max) @ Id, Vgs', 'drive': 'Drive Voltage (Max Rds On, Min Rds On)', 'qg': 'Gate Charge (Qg) (Max) @ Vgs',
        'temp': 'Operating Temperature', 'tol': 'Tolerance', 'r': 'Resistance', 'tc': 'Temperature Coefficient',
        'qual': 'Qualification', 'vr': 'Voltage - Rated',
    }
    return {'Parameters': [{'ParameterText': names[k], 'ValueText': v} for k, v in params.items()]}


ORIGINAL_FET = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='320mA (Ta)', rds='1.6Ohm @ 500mA, 10V',
                    drive='4.5V, 10V', qg='0.7 nC @ 4.5 V', temp='-55°C ~ 150°C (TJ)')


def test_number_parsing():
    assert number('320mA (Ta)') == 0.32
    assert number('±0.05%') == 0.05
    assert number('±10ppm/°C') == 10
    assert abs(number('64.9 kOhms') - 64900) < 1e-6
    assert abs(number('22 µF') - 22e-6) < 1e-12


def test_better_part_is_drop_in():
    cand = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='360mA (Ta)', rds='1.6Ohm @ 300mA, 10V',
                drive='4.5V, 10V', qg='0.7 nC @ 4.5 V', temp='-55°C ~ 150°C (TJ)')
    assert compare_parts(ORIGINAL_FET, cand)['verdict'] == 'drop_in'


def test_lower_current_and_higher_rds_is_worse():
    cand = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='115mA (Ta)', rds='7.5Ohm @ 500mA, 10V',
                drive='5V, 10V', qg='-', temp='-55°C ~ 150°C (TJ)')
    result = compare_parts(ORIGINAL_FET, cand)
    assert result['verdict'] == 'worse'
    assert 'Current - Continuous Drain' in result['summary'] and 'Rds On' in result['summary']


def test_only_minor_spec_worse_is_check():
    cand = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='320mA (Ta)', rds='1.6Ohm @ 500mA, 10V',
                drive='4.5V, 10V', qg='0.8 nC @ 4.5 V', temp='-55°C ~ 150°C (TJ)')
    assert compare_parts(ORIGINAL_FET, cand)['verdict'] == 'check'


def test_gate_drive_only_at_10v_is_check_not_worse():
    cand = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='360mA (Ta)', rds='1.6Ohm @ 300mA, 10V',
                drive='10V', qg='0.7 nC @ 4.5 V', temp='-55°C ~ 150°C (TJ)')
    result = compare_parts(ORIGINAL_FET, cand)
    assert result['verdict'] == 'check' and 'Drive Voltage' in result['summary']


def test_mounting_type_extra_detail_still_matches():
    orig = {'Parameters': [{'ParameterText': 'Mounting Type', 'ValueText': 'Surface Mount, MLCC'}]}
    soft = {'Parameters': [{'ParameterText': 'Mounting Type', 'ValueText': 'Surface Mount, MLCC, Epoxy'}]}
    tht = {'Parameters': [{'ParameterText': 'Mounting Type', 'ValueText': 'Through Hole'}]}
    assert compare_parts(orig, soft)['verdict'] == 'drop_in'
    assert compare_parts(orig, tht)['verdict'] == 'worse'


def test_different_package_wins_over_specs():
    cand = part(pkg='SC-70, SOT-323', vdss='100 V', id='1A', rds='0.5Ohm @ 500mA, 10V', drive='4.5V, 10V')
    assert compare_parts(ORIGINAL_FET, cand)['verdict'] == 'different_package'


def test_narrower_temperature_range_is_worse():
    cand = part(pkg='TO-236-3, SC-59, SOT-23-3', vdss='60 V', id='320mA (Ta)', rds='1.6Ohm @ 500mA, 10V',
                drive='4.5V, 10V', qg='0.7 nC @ 4.5 V', temp='-40°C ~ 125°C (TJ)')
    assert compare_parts(ORIGINAL_FET, cand)['verdict'] == 'worse'


def test_resistor_tolerance_and_tempco():
    orig = part(r='64.9 kOhms', pkg='0603 (1608 Metric)', tol='±0.05%', tc='±10ppm/°C')
    tighter = part(r='64.9 kOhms', pkg='0603 (1608 Metric)', tol='±0.02%', tc='±5ppm/°C')
    looser = part(r='64.9 kOhms', pkg='0603 (1608 Metric)', tol='±0.1%', tc='±10ppm/°C')
    other_value = part(r='65 kOhms', pkg='0603 (1608 Metric)', tol='±0.05%', tc='±10ppm/°C')
    assert compare_parts(orig, tighter)['verdict'] == 'drop_in'
    assert compare_parts(orig, looser)['verdict'] == 'worse'
    assert compare_parts(orig, other_value)['verdict'] == 'worse'


def test_capacitor_dielectric_and_voltage():
    orig = part(pkg='0603 (1608 Metric)', vr='16V', tc='X5R')
    assert compare_parts(orig, part(pkg='0603 (1608 Metric)', vr='25V', tc='X7R'))['verdict'] == 'drop_in'
    assert compare_parts(orig, part(pkg='0603 (1608 Metric)', vr='10V', tc='X5R'))['verdict'] == 'worse'
    assert compare_parts(orig, part(pkg='0603 (1608 Metric)', vr='16V', tc='Y5V'))['verdict'] == 'worse'


def test_losing_automotive_qualification_is_worse():
    orig = part(pkg='0603 (1608 Metric)', qual='AEC-Q200')
    assert compare_parts(orig, part(pkg='0603 (1608 Metric)', qual='-'))['verdict'] == 'worse'
    assert compare_parts(part(pkg='0603 (1608 Metric)', qual='-'), orig)['verdict'] == 'drop_in'


def test_automotive_grade_found_in_any_field():
    # TDK CGA6M (automotive) vs C3225 (commercial): DigiKey puts AEC-Q200 under "Ratings" for capacitors.
    orig = {'Parameters': [{'ParameterText': 'Package / Case', 'ValueText': '1210 (3225 Metric)'},
                           {'ParameterText': 'Ratings', 'ValueText': 'AEC-Q200'}]}
    commercial = {'Parameters': [{'ParameterText': 'Package / Case', 'ValueText': '1210 (3225 Metric)'},
                                 {'ParameterText': 'Ratings', 'ValueText': '-'}]}
    features = {'Parameters': [{'ParameterText': 'Package / Case', 'ValueText': '1210 (3225 Metric)'},
                               {'ParameterText': 'Features', 'ValueText': 'Automotive AEC-Q200, Moisture Resistant'}]}
    assert compare_parts(orig, commercial)['verdict'] == 'worse'
    assert compare_parts(orig, features)['verdict'] == 'drop_in'
