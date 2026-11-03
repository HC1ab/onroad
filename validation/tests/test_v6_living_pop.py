"""V6 생활인구 교차 확인 테스트: 원본 없이 합성 데이터로 읽기·계산 규칙·재현성을 확인한다."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v6_living_pop as lp  # noqa: E402

CRS = "EPSG:5179"
AGES = ["20세미만", "20대", "30대", "40대", "50대", "60세이상"]


def page(items):
    return {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": items}, "totalCount": len(items)}}}


def item(code, age, h, v, month="202609"):
    return {"stdYm": month, "hcode": code, "hname": f"동{code[-3:]}", "ages": age,
            "hpopAvg": str(h), "wpopAvg": "0", "vpopAvg": str(v)}


def test_read_living_drops_exact_duplicates_and_other_months(tmp_path):
    rows = [item("2611051000", a, 10, 20) for a in AGES]
    (tmp_path / "p1.json").write_text(json.dumps(page(rows + rows[:3])), encoding="utf-8")   # API 처럼 두 번씩
    (tmp_path / "p2.json").write_text(json.dumps(page(rows[3:] + [item("2611051000", "20대", 1, 1, "202608")])),
                                      encoding="utf-8")
    df = lp.read_living(tmp_path, "202609")
    assert len(df) == 6
    assert df.attrs == {"rows_received": 13, "rows_unique": 6}
    assert df["vpopAvg"].dtype.kind in "if"


def test_read_living_stops_on_conflicting_values(tmp_path):
    rows = [item("2611051000", "20대", 10, 20), item("2611051000", "20대", 10, 99)]
    (tmp_path / "p1.json").write_text(json.dumps(page(rows)), encoding="utf-8")
    with pytest.raises(ValueError, match="값이 다른 행"):
        lp.read_living(tmp_path, "202609")


def test_single_item_page_is_read(tmp_path):
    (tmp_path / "p1.json").write_text(json.dumps(page(item("2611051000", "20대", 1, 2))), encoding="utf-8")
    assert len(lp.read_living(tmp_path, "202609")) == 1


def test_elderly_band_is_the_single_top_band():
    assert lp.elderly_band(pd.Series(AGES)) == "60세이상"
    with pytest.raises(ValueError):
        lp.elderly_band(pd.Series(["60세이상", "70세이상"]))
    with pytest.raises(ValueError):
        lp.elderly_band(pd.Series(["20대", "30대"]))


def test_dong_shares():
    rows = [item("A", a, h, v) for a, h, v in zip(AGES, [10] * 6, [10, 10, 10, 10, 20, 40])]
    rows += [item("B", a, 0, 0) for a in AGES]                       # 방문인구 0: 비율 NaN
    df = pd.DataFrame(rows)
    for c in lp.NUM_COLS:
        df[c] = pd.to_numeric(df[c])
    s = lp.dong_shares(df)
    assert s.attrs["band"] == "60세이상"
    assert s.at["A", "visit_old_share"] == pytest.approx(0.4)
    assert s.at["A", "resident_old_share"] == pytest.approx(1 / 6)
    assert np.isnan(s.at["B", "visit_old_share"])


def test_market_distance_uses_config_rules():
    dongs = gpd.GeoDataFrame(geometry=[box(0, 0, 100, 100), box(1000, 0, 1100, 100), box(5000, 0, 5100, 100)], crs=CRS)
    markets = gpd.GeoDataFrame({"stores": [250, 250, 500], "excluded": [False, False, True]},
                               geometry=[Point(50, 50), Point(1300, 50), Point(5050, 50)], crs=CRS)
    d = lp.market_distance(dongs, markets, 200)
    assert d[0] == 0                               # 시장이 동 안
    assert d[1] == pytest.approx(200)              # 동 경계에서 200m
    assert d[2] > 1000                             # 제외 상가는 대형 시장으로 보지 않는다
    assert lp.market_distance(dongs, markets, 300)[0] > 0   # 점포 기준 미달


def synthetic(n=150, effect=0.08, slope=0.6, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.uniform(0.12, 0.40, n)
    near = np.zeros(n, dtype=bool)
    near[:12] = True
    y = 0.10 + slope * x + effect * near + rng.normal(0, 0.004, n)
    df = pd.DataFrame({"hname": [f"동{i}" for i in range(n)], "visit_old_share": y, "ratio_65plus": x,
                       "resident_old_share": x * 1.2}, index=[f"26{i:08d}" for i in range(n)])
    dist = {s: np.where(near, 0.0, 5000.0) for s in (100, 150, 200, 300)}
    return df, dist


def test_analyze_recovers_planted_effect_and_is_reproducible():
    df, dist = synthetic()
    r1 = lp.analyze(df, dist, 200, 300, n_perm=300, seed=7)
    r2 = lp.analyze(df, dist, 200, 300, n_perm=300, seed=7)
    assert r1 == r2
    assert r1["n_market_dongs"] == 12 and r1["n_dongs"] == 150
    assert r1["diff_pp"] == pytest.approx(8, abs=0.5)
    assert r1["uplift"] == pytest.approx(0.08 / 0.6, rel=0.08)
    assert r1["p_value"] < 0.01
    drops = [s for s in r1["sensitivity"] if s["param"] == "drop_dong"]
    assert len(drops) == 12 and all(s["n_market_dongs"] == 11 for s in drops)
    lo, hi = r1["uplift_range"]
    assert lo <= r1["uplift"] <= hi
    assert {s["param"] for s in r1["sensitivity"]} == {"min_stores", "radius_m", "x", "drop_dong"}


def test_no_effect_is_reported_as_is():
    df, dist = synthetic(effect=0.0)
    r = lp.analyze(df, dist, 200, 300, n_perm=300, seed=7)
    assert abs(r["diff_pp"]) < 0.5 and r["p_value"] > 0.05


def test_compare_with_config_range():
    assert lp.compare(0.10, [0.08, 0.12], 0.137, [0.060, 0.156]) == {
        "config_uplift": 0.137, "config_range": [0.060, 0.156], "uplift_in_config_range": True, "ranges_overlap": True}
    c = lp.compare(0.01, [-0.02, 0.03], 0.137, [0.060, 0.156])
    assert not c["uplift_in_config_range"] and not c["ranges_overlap"]
