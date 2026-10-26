"""Independent educational arithmetic oracle, not an ASTM compliance implementation.

Compare a small set of values to the JavaScript fixtures. Uses Decimal wherever
possible to avoid duplicating the JS implementation or its internal evaluation logic.
Run: python validation/reference_oracle.py
"""
from decimal import Decimal, getcontext
from math import pi
getcontext().prec = 30
D = Decimal
values = {
    'ndg_dry_pcf': D('126') / (D('1') + D('11.8') / D('100')),
    'soil_oven_moisture_pct': D('100') * (D('210') - D('190')) / (D('190') - D('90')),
    'plasticity_index': D('42') - D('23'),
    'sandcone_dry_pcf': (D('7.8') / D('0.0625')) / (D('1') + D('10') / D('100')),
    'single_sieve_passing_pct': D('100') * (D('1') - D('225') / D('1000')),
    'concrete_unit_weight_pcf': (D('56.0') - D('20.8')) / D('0.25'),
    'asphalt_core_bulk_sg': D('1160') / (D('1165') - D('674')),
    'asphalt_air_void_pct': D('100') * (D('1') - D('2.35') / D('2.50')),
}
values['ndg_compaction_pct'] = values['ndg_dry_pcf'] / D('120') * D('100')
values['cylinder_psi'] = D('141372') / D(str(pi)) / D('4')
expected = {
    'ndg_dry_pcf': '112.70',
    'ndg_compaction_pct': '93.92',
    'soil_oven_moisture_pct': '20.00',
    'plasticity_index': '19.00',
    'sandcone_dry_pcf': '113.45',
    'single_sieve_passing_pct': '77.50',
    'concrete_unit_weight_pcf': '140.80',
    'asphalt_core_bulk_sg': '2.36',
    'asphalt_air_void_pct': '6.00',
    'cylinder_psi': '11250.03',
}
for name, true_value in values.items():
    rounded = true_value.quantize(D('0.01'))
    assert rounded == D(expected[name]), f'{name}: independent oracle drift: {rounded}'
    print(f'{name:27s} {rounded} (unrounded={true_value})')
print(f'{len(values)} independent numeric oracle cases passed. NOT a method-conformance test.')
