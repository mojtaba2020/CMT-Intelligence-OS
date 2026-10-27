"""v1.5 read-only cross-document reconciliation for CMT pilot evidence.

This is a conservative discrepancy *screen* for manually transcribed or independently
verified documents. It does not call AI, certify results, decide ASTM compliance,
or export to ElmTree. No records are persisted. All data must be synthetic or
expressly authorized. Comparison thresholds are user-supplied, not standards.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FIELD_UNITS = {
    'wet_density': ('pcf', {'pcf': Decimal('1'), 'kg/m3': Decimal('0.062427960576145')}),
    'dry_density': ('pcf', {'pcf': Decimal('1'), 'kg/m3': Decimal('0.062427960576145')}),
    'moisture': ('%', {'%': Decimal('1')}),
    'slump': ('in', {'in': Decimal('1'), 'mm': Decimal('0.03937007874015748')}),
    'air': ('%', {'%': Decimal('1')}),
    'temperature': ('F', {'F': Decimal('1'), 'C': Decimal('1.8')}),
}
REQUIRED = {'ndg': ('wet_density', 'moisture'), 'fresh_concrete': ('slump', 'air', 'temperature')}
OTHER = {'ndg': 'gauge_printout', 'fresh_concrete': 'concrete_ticket'}
MAX_ABS = Decimal('10000000')


def dec(value: str) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 32:
        raise ValueError('Expected an explicit decimal string')
    try:
        v = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid decimal value') from None
    if not v.is_finite() or abs(v) > MAX_ABS:
        raise ValueError('Non-finite or out-of-range value')
    return v


def fmt(x: Decimal) -> str:
    return str(x.quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    field: Literal['wet_density', 'dry_density', 'moisture', 'slump', 'air', 'temperature']
    value: str = Field(min_length=1, max_length=32)
    unit: str = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def valid_measurement(self):
        number = dec(self.value)
        if self.unit not in FIELD_UNITS[self.field][1]:
            raise ValueError(f'Unsupported/ambiguous unit for {self.field}')
        if self.field != 'temperature' and number < 0:
            raise ValueError('Negative non-temperature measurement')
        if self.field in ('moisture', 'air') and number > 100:
            raise ValueError('Moisture/air outside plausible percentage range')
        return self


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
    source_type: Literal['field_form', 'gauge_printout', 'concrete_ticket']
    project_id: str = Field(min_length=1, max_length=80)
    test_id: str = Field(min_length=1, max_length=80)
    observations: list[Observation] = Field(min_length=1, max_length=10)

    @field_validator('project_id', 'test_id')
    @classmethod
    def text_id(cls, value: str):
        if not value.strip() or value.strip() != value or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid identifier')
        return value

    @model_validator(mode='after')
    def no_duplicate_keys(self):
        keys = [x.field for x in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate measurements in one source')
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    test_type: Literal['ndg', 'fresh_concrete']
    documents: list[Document] = Field(min_length=2, max_length=2)
    screen_tolerances: dict[str, str] = Field(default_factory=dict, max_length=6)
    synthetic: bool  # mandatory evidence-origin flag, not a permission to use employer records

    @model_validator(mode='after')
    def structure(self):
        if {d.source_type for d in self.documents} != {'field_form', OTHER[self.test_type]}:
            raise ValueError('Expected exactly a field_form and correct independent source')
        if len({d.source_id for d in self.documents}) != 2:
            raise ValueError('Source IDs must differ')
        expected = set(REQUIRED[self.test_type]) | ({'dry_density'} if self.test_type == 'ndg' else set())
        for d in self.documents:
            if set(x.field for x in d.observations) - expected:
                raise ValueError(f'Unexpected {self.test_type} field')
        for k, v in self.screen_tolerances.items():
            if k not in expected or dec(v) < 0:
                raise ValueError('Tolerance must be explicit, non-negative and for this test')
        return self


def normalized(observation: Observation) -> Decimal:
    v = dec(observation.value)
    if observation.field == 'temperature' and observation.unit == 'C':
        return v * Decimal('1.8') + Decimal('32')
    return v * FIELD_UNITS[observation.field][1][observation.unit]


def reconcile(case: Case) -> dict:
    """Never returns ACCEPTED/PASSED; screens for disagreements only."""
    bytype = {d.source_type: d for d in case.documents}
    left, right = bytype['field_form'], bytype[OTHER[case.test_type]]
    a = {o.field: o for o in left.observations}
    b = {o.field: o for o in right.observations}
    issues: list[dict] = []
    comparisons: list[dict] = []
    derived: list[dict] = []
    for field in ('project_id', 'test_id'):
        if getattr(left, field) != getattr(right, field):
            issues.append({'code': 'IDENTIFIER_MISMATCH', 'field': field,
                           'details': f'{field} differs across documents; verify source identity'})
    for field in REQUIRED[case.test_type]:
        if field not in a or field not in b:
            issues.append({'code': 'MISSING_MEASUREMENT', 'field': field,
                           'details': 'Required comparison measurement absent in at least one document'})

    for field in REQUIRED[case.test_type] + (('dry_density',) if case.test_type == 'ndg' else ()): 
        if field not in a or field not in b:
            continue
        x, y = normalized(a[field]), normalized(b[field])
        gap = abs(x-y)
        tolerance = dec(case.screen_tolerances.get(field, '0'))
        mismatch = gap > tolerance
        record = {'field': field, 'from_form': fmt(x), 'from_other': fmt(y),
                  'base_unit': FIELD_UNITS[field][0], 'absolute_difference': fmt(gap),
                  'screen_tolerance': fmt(tolerance), 'different': mismatch,
                  'source_ids': [left.source_id, right.source_id]}
        comparisons.append(record)
        if mismatch:
            issues.append({'code': 'VALUE_MISMATCH', 'field': field,
                           'details': 'Measured values differ beyond operator-supplied screen tolerance'})

    if case.test_type == 'ndg':
        for doc in (left, right):
            field_map = a if doc is left else b
            if {'wet_density', 'moisture'} <= set(field_map):
                wet = normalized(field_map['wet_density'])
                moisture = normalized(field_map['moisture'])
                dry = wet / (Decimal('1') + moisture / Decimal('100'))
                derived.append({'source_id': doc.source_id, 'derived_dry_density_pcf': fmt(dry),
                                'note': 'Calculated solely from that source; not an approved Proctor MDD'})
                if 'dry_density' in field_map:
                    actual = normalized(field_map['dry_density'])
                    tolerance = dec(case.screen_tolerances.get('dry_density', '0'))
                    if abs(actual-dry) > tolerance:
                        issues.append({'code': 'INTERNAL_CALCULATION_MISMATCH', 'field': 'dry_density',
                                       'details': f'Reported dry density disagrees with that source wet-density/moisture formula ({doc.source_id})'})

    result = {
        'mode': 'LOCAL_READ_ONLY_RECONCILIATION', 'test_type': case.test_type,
        'review_status': 'REVIEW_REQUIRED' if issues else 'NO_DIFFERENCE_IN_CHECKED_FIELDS',
        'engineer_approved': False, 'official_acceptance': None,
        'synthetic': case.synthetic,
        'comparison_threshold_policy': 'Operator-provided screening only; NOT ASTM/AASHTO criteria or acceptance rounding',
        'sources': [{'source_id': d.source_id, 'source_type': d.source_type} for d in (left, right)],
        'comparisons': comparisons, 'derived': derived, 'issues': issues,
        'limitations': [
            'Source identities and values require independent human confirmation.',
            'No official material acceptance, PE signature, or ElmTree synchronization.',
            'An empty issue list does not establish field-data accuracy or standards compliance.',
        ],
    }
    digest_input = json.dumps({'case': case.model_dump(), 'report': result}, sort_keys=True,
                              ensure_ascii=False, separators=(',', ':'))
    result['sha256_for_local_change_detection_only'] = sha256(digest_input.encode('utf-8')).hexdigest()
    return result
