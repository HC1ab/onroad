"""v2_tiers 테스트."""
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline import v2_tiers as t

CFG = {"entry_seconds": 7, "speeds_mps": [1.0, 0.8, 0.7], "formula_tolerance_s": 0.5}


def test_classify_formula_and_overlap_goes_to_1_0():
    L = [10.0, 10.0, 10.0, 40.0]
    # 17.0 = 7+10/1.0, 19.5 = 7+10/0.8, 21.2857=7+10/0.7, 임의값
    G = [17.0, 19.5, 7 + 10 / 0.7, 33.3]
    assert list(t.classify_formula(L, G, CFG)) == ["1.0", "0.8", "0.7", "other"]
    # 허용오차 안에서 두 식에 걸리면 1.0: L=1 -> 8.0(1.0), 8.25(0.8)
    assert t.classify_formula([1.0], [8.1], CFG).iloc[0] == "1.0"


def test_data_check_only_for_other_and_shorter_than_general_formula():
    L, G = [10.0, 10.0, 10.0], [12.0, 17.0, 40.0]  # 일반식 17.0
    fc = t.classify_formula(L, G, CFG)
    assert list(t.data_check_mask(L, G, fc, CFG)) == [True, False, False]  # 12.0만 일반식보다 짧고 어느 식과도 다르다


def test_assign_tier_priority_and_boundary():
    tier = t.assign_tier([300.0, 100.0, 400.0], [50.0, 100.0, 301.0], 300)
    assert list(tier) == [1, 1, 3]  # 보호구역 우선, 경계(=300) 포함, 둘 다 밖이면 3
    assert list(t.assign_tier([500.0], [200.0], 300)) == [2]


def test_nearest_distance_empty_facility():
    d, i = t.nearest_distance(np.array([[0.0, 0.0]]), np.empty((0, 2)))
    assert np.isinf(d[0]) and i[0] == -1


def test_resident_ratio_is_area_weighted():
    # 두 동: x<0 은 0.2, x>=0 은 0.6. 원 중심이 x=0 이면 면적이 절반씩이라 0.4
    polys = [box(-1000, -1000, 0, 1000), box(0, -1000, 1000, 1000)]
    r = np.array([0.2, 0.6])
    out = t.resident_elderly_ratio(np.array([[0.0, 0.0], [-500.0, 0.0]]), polys, r, 300)
    assert out[0] == pytest.approx(0.4, abs=1e-6)
    assert out[1] == pytest.approx(0.2, abs=1e-9)  # 원이 한 동 안에만 있다


def test_resident_ratio_ignores_nan_and_nan_when_all_missing():
    polys = [box(-1000, -1000, 0, 1000), box(0, -1000, 1000, 1000)]
    out = t.resident_elderly_ratio(np.array([[0.0, 0.0]]), polys, np.array([np.nan, 0.5]), 300)
    assert out[0] == pytest.approx(0.5)
    out2 = t.resident_elderly_ratio(np.array([[0.0, 0.0], [5000.0, 5000.0]]), polys, np.array([np.nan, np.nan]), 300)
    assert np.isnan(out2).all()
