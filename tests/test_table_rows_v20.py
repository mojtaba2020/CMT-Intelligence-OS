from validation.synthetic_table_benchmark_v20 import fixture,benchmark
from forms.table_rows_v20 import detect_table_grid
import pytest

def test_synthetic_grid_lines():
    for v in benchmark():
        assert v['matched_lines']==v['true_lines'],v
        assert v['detected_row_regions']==v['synthetic_rows'],v

def test_grid_proposals_not_approved():
    b,_=fixture(3)
    r=detect_table_grid(b)
    assert r['autofill_allowed'] is False
    assert all(x['needs_human_review'] for x in r['row_boxes'])

def test_image_input_rejected():
    with pytest.raises(ValueError):detect_table_grid(b'not an image')

def test_ratio_bounds():
    b,_=fixture(2)
    with pytest.raises(ValueError):detect_table_grid(b,min_width_ratio=.1)
