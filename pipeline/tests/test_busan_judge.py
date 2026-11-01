"""F3 판정 테스트: 손계산 값과 비교하고 부동소수점 경계를 확인한다."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import busan_judge as jd  # noqa: E402

CFG = {"entry_seconds": 7, "speeds_mps": [1.0, 0.8, 0.7]}


def make(*pairs):
    """(길이, 보행시간) 쌍으로 입력표를 만든다."""
    return pd.DataFrame([{"cw_id": f"t{i}", "length_m": L, "green_s": g} for i, (L, g) in enumerate(pairs)])


def test_hand_calculation():
    # L=20, 보행시간=27: T(1.0)=27, T(0.8)=32, T(0.7)=7+20/0.7=35.5714...
    out = jd.judge(make((20, 27)), CFG)
    r = out.iloc[0]
    assert r["t_need_1.0"] == pytest.approx(27.0)
    assert r["t_need_0.8"] == pytest.approx(32.0)
    assert r["t_need_0.7"] == pytest.approx(7 + 20 / 0.7)
    assert r["gap_1.0"] == pytest.approx(0.0)
    assert r["gap_0.8"] == pytest.approx(5.0)
    assert r["gap_0.7"] == pytest.approx(7 + 20 / 0.7 - 27)


def test_equal_to_formula_is_not_short_even_with_float_noise():
    green = 7 + 26 / 0.7                      # 0.7m/s 기준식 값 그대로 (엑셀이 저장한 소수)
    out = jd.judge(make((26, green), (28, 35)), CFG)
    assert out["formula_class"].tolist() == ["v0.7", "v1.0"]
    assert not jd.is_short(out["gap_0.7"]).iloc[0]       # 오차 1e-15 가 '짧음'으로 잡히면 안 된다
    assert not jd.is_short(out["gap_1.0"]).iloc[1]


def test_short_and_long_and_other():
    out = jd.judge(make((20, 20), (20, 40)), CFG)         # 20초: 1.0식(27)보다 짧음, 40초: 모든 식보다 김
    assert jd.is_short(out["gap_1.0"]).tolist() == [True, False]
    assert out["formula_class"].tolist() == ["other", "other"]


def test_formula_table_counts():
    out = jd.judge(make((20, 27), (20, 7 + 20 / 0.7), (20, 20)), CFG)
    t = jd.formula_table(out, CFG).set_index("구분")["건수"]
    assert t["보행시간 = 1.0m/s 기준식 값"] == 1
    assert t["보행시간 = 0.7m/s 기준식 값"] == 1
    assert t["어느 기준식과도 다름"] == 1
    assert t["gap>0 (기록값이 1.0m/s 기준식보다 짧음)"] == 1
