"""v2_speed 테스트: 알려진 값, 경계값, 단조성."""
import numpy as np
import pytest

from pipeline import v2_speed as sp

CFG = {"walking_speed_mps": {"general": {"mean": 1.29, "p15": 1.01}, "elderly": {"mean": 1.13, "p15": 0.85}}}
WIDE = (0.1, 3.0)  # 자르기를 끄는 넓은 범위
M = sp.SpeedModel.from_config(CFG)


def test_design_speed_endpoints_match_p15():
    """p=0 이면 일반 15퍼센타일(1.01), p=1 이면 고령 15퍼센타일(0.85)이 나와야 한다."""
    v = sp.design_speed([0.0, 1.0], 0.85, M, WIDE)
    assert v[0] == pytest.approx(1.01, abs=1e-6)
    assert v[1] == pytest.approx(0.85, abs=1e-6)


def test_design_speed_monotonic_in_elderly_share_and_target():
    p = np.linspace(0, 1, 11)
    v = sp.design_speed(p, 0.85, M, WIDE)
    assert np.all(np.diff(v) <= 1e-9)  # 고령 비율이 높을수록 느려진다
    assert sp.design_speed(0.3, 0.95, M, WIDE)[0] < sp.design_speed(0.3, 0.85, M, WIDE)[0]  # 목표가 높을수록 느려진다


def test_design_speed_is_clipped_to_bounds():
    v = sp.design_speed([0.0, 1.0], 0.85, M, (0.7, 1.0))
    assert v[0] == pytest.approx(1.0) and v[1] == pytest.approx(0.85)
    assert sp.design_speed(1.0, 0.99, M, (0.7, 1.0))[0] == pytest.approx(0.7)  # 아래로 자름


def test_coverage_at_design_time_equals_target_for_elderly():
    """고령자 기준 설계 속도의 시간이면 고령 보행자 커버리지가 target 이다."""
    L, entry = 20.0, 7.0
    T = entry + L / 0.85
    assert sp.coverage(L, T, entry, M) == pytest.approx(0.85, abs=1e-6)


def test_coverage_no_time_left_is_zero_and_monotonic():
    assert sp.coverage(10.0, 7.0, 7.0, M) == 0.0  # 진입 시간만큼만 있으면 건널 시간이 없다
    assert sp.coverage(10.0, 5.0, 7.0, M) == 0.0
    c = sp.coverage(10.0, np.array([15.0, 20.0, 30.0]), 7.0, M)
    assert np.all(np.diff(c) > 0)


def test_required_time_never_below_record():
    t = sp.required_time([30.0, 10.0], [10.0, 10.0], 1.0, 7.0)
    assert t[0] == 30.0  # 기록이 더 길면 줄이지 않는다
    assert t[1] == pytest.approx(17.0)


def test_from_config_rejects_bad_percentile():
    bad = {"walking_speed_mps": {"general": {"mean": 1.0, "p15": 1.2}, "elderly": {"mean": 1.13, "p15": 0.85}}}
    with pytest.raises(ValueError):
        sp.SpeedModel.from_config(bad)


def test_elderly_p15_sensitivity_slows_design_speed():
    m76 = sp.SpeedModel.from_config(CFG, elderly_p15=0.76)
    assert sp.design_speed(1.0, 0.85, m76, WIDE)[0] == pytest.approx(0.76, abs=1e-6)
