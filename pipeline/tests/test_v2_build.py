"""v2_build 테스트: 합성 데이터로 계산·반올림·문서 구성을 확인한다(실데이터 없이)."""
import numpy as np
import pandas as pd
import pytest

from pipeline import v2_build as vb
from pipeline import v2_speed as sp

CFG = {"entry_seconds": 7, "speeds_mps": [1.0, 0.8, 0.7], "formula_tolerance_s": 0.5, "speed_bounds_mps": [0.7, 1.0],
       "tier1_speed_mps": 0.7, "market_elderly_uplift": 0.137, "add_seconds_threshold": 2, "min_sample": 2,
       "walking_speed_mps": {"general": {"mean": 1.29, "p15": 1.01}, "elderly": {"mean": 1.13, "p15": 0.85}}}
M = sp.SpeedModel.from_config(CFG)


def _frame(tier, resident, length=20.0, green=20.0):
    d = pd.DataFrame({"length_m": [length], "green_s": [green], "data_check": [False]})
    t = pd.DataFrame({"tier": [float(tier)], "resident": [resident]})
    return d, t


def test_tier1_uses_fixed_speed_and_elderly_share_one():
    d, t = _frame(1, 0.2)
    r = vb.apply_target(d, t, 0.85, CFG, M)
    assert r.at[0, "v"] == pytest.approx(0.7) and r.at[0, "user"] == 1.0
    assert r.at[0, "t_req_raw"] == pytest.approx(7 + 20 / 0.7)  # 기록(20)보다 길다


def test_tier2_adds_uplift_and_caps_at_one():
    d, t = _frame(2, 0.30)
    assert vb.apply_target(d, t, 0.85, CFG, M).at[0, "user"] == pytest.approx(0.437)
    d, t = _frame(2, 0.95)
    assert vb.apply_target(d, t, 0.85, CFG, M).at[0, "user"] == 1.0
    assert vb.apply_target(*_frame(2, 0.3), 0.85, CFG, M, market_all_elderly=True).at[0, "user"] == 1.0


def test_tier3_uses_resident_ratio_and_never_shortens_record():
    d, t = _frame(3, 0.25, length=10.0, green=60.0)
    r = vb.apply_target(d, t, 0.85, CFG, M)
    assert r.at[0, "user"] == 0.25
    assert r.at[0, "t_req_raw"] == 60.0 and r.at[0, "add_raw"] == 0.0  # 기록이 더 길면 그대로


def test_data_check_and_missing_resident_stay_nan():
    d = pd.DataFrame({"length_m": [20.0, 20.0], "green_s": [12.0, 20.0], "data_check": [True, False]})
    t = pd.DataFrame({"tier": [np.nan, 3.0], "resident": [np.nan, np.nan]})
    r = vb.apply_target(d, t, 0.85, CFG, M)
    assert r.loc[0].isna().all()  # data_check 행은 계산하지 않는다
    assert np.isnan(r.at[1, "v"]) and np.isnan(r.at[1, "t_req_raw"])  # 주민 비율을 모르면 속도를 정하지 않는다


def test_rounded_times_keep_identity():
    g, t, add = vb.rounded_times([24.142857, 30.0], [24.9999, 30.0])
    assert t[0] == pytest.approx(g[0] + add[0], abs=1e-9)  # t_required = green + add 가 내보내는 값에서 성립
    assert add[1] == 0.0


def test_reason_is_conditional_and_matches_rounded_values():
    row = {"protect_m": 37.2, "market_m": 5000.0, "market_name": "동래시장", "v": 0.7, "user": 1.0, "resident": 0.2,
           "length_m": 20.0}
    assert vb.make_reason(1, row, 300, 35.571, 15.571) == \
        "노인보호구역 37m → 보호구역 기준 0.70m/s, 길이 20m → 기준 적용 시 35.6초 (+15.6초)"
    assert vb.make_reason(1, row, 300, 25.0, 0.0).endswith("현재 시간으로 충분")
    row3 = dict(row, v=0.91, resident=0.18)
    assert vb.make_reason(3, row3, 200, 29.0, 1.0).startswith("반경 200m 고령 비율 18% → 0.91m/s")
    for banned in ("위험", "위반", "불법", "늘려야", "부족"):
        assert banned not in vb.make_reason(2, dict(row, user=0.4), 300, 30.0, 2.0)


def test_target_key_two_decimals():
    assert vb.target_key(0.9) == "0.90" and vb.target_key(0.85) == "0.85"


def test_exclude_reason_mapping():
    import math
    assert vb.exclude_reason("length_invalid", math.nan, 7.0) == "length_missing"
    assert vb.exclude_reason("length_invalid", 0.0, 7.0) == "length_out_of_range"
    assert vb.exclude_reason("outlier_length", 120.0, 30.0) == "length_out_of_range"
    assert vb.exclude_reason("green_invalid", 10.0, math.nan) == "green_missing"
    assert vb.exclude_reason("outlier_green", 10.0, 300.0) == "green_out_of_range"
    assert vb.exclude_reason("duplicate", 10.0, 30.0) is None  # 계약에 대응하는 사유가 없다
    assert vb.exclude_reason("coord_missing", 10.0, 30.0) is None
