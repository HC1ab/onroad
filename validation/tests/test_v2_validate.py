"""검증 V6·V7·V3 보강 테스트: 원본 없이 합성 데이터로 계산 규칙·재현성·스키마를 확인한다."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import v2_validate as vv  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
CRS = "EPSG:5179"


def test_norm_station_matches_m1_and_s1_spelling():
    assert vv.norm_station("서면역") == "서면"
    assert vv.norm_station("서면(1호선)") == "서면"
    assert vv.norm_station("1서면") == "서면"
    assert vv.norm_station("동래·온천장") == "동래온천장"


def test_v6_recovers_planted_market_effect_and_is_reproducible():
    rng = np.random.default_rng(0)
    n = 100
    elderly = rng.uniform(0.15, 0.40, n)
    near = np.zeros(n, dtype=bool)
    near[:8] = True
    free = 0.10 + 0.80 * elderly + 0.10 * near + rng.normal(0, 0.005, n)
    r1 = vv.v6_test(free, elderly, near, n_perm=500, seed=7)
    r2 = vv.v6_test(free, elderly, near, n_perm=500, seed=7)
    assert r1 == r2                                         # 같은 시드면 같은 결과
    assert r1["n_market_stations"] == 8 and r1["n_stations"] == n
    assert r1["diff_pp"] == pytest.approx(10, abs=1)       # 심어 둔 +10%p
    assert r1["slope"] == pytest.approx(0.8, abs=0.05)
    assert r1["uplift"] == pytest.approx(r1["diff_pp"] / 100 / r1["slope"])
    assert r1["p_value"] < 0.01


def test_v6_without_effect_is_not_significant():
    rng = np.random.default_rng(1)
    elderly = rng.uniform(0.15, 0.40, 100)
    near = np.zeros(100, dtype=bool)
    near[:8] = True
    free = 0.10 + 0.80 * elderly + rng.normal(0, 0.02, 100)
    assert vv.v6_test(free, elderly, near, n_perm=500, seed=7)["p_value"] > 0.05


def test_v7_senior_zone_takes_precedence_over_child_zone():
    cw = pd.DataFrame({
        "protect_zone_m": [100, 250, 900, 900, 900, 900],
        "child_zone_m":   [50, 900, 100, 140, 400, 800],
        "formula_class":  ["0.7", "1.0", "0.7", "0.7", "0.7", "1.0"],
    })
    g = {x["group"]: x for x in vv.v7_groups(cw, 300, 150)}
    assert (g["senior_zone"]["n"], g["senior_zone"]["n_formula_07"]) == (2, 1)   # 0번은 어린이 반경에도 있지만 노인으로
    assert (g["child_zone"]["n"], g["child_zone"]["n_formula_07"]) == (2, 2)
    assert (g["outside"]["n"], g["outside"]["n_formula_07"]) == (2, 1)
    assert g["outside"]["radius_m"] is None
    assert sum(x["n"] for x in g.values()) == len(cw)


def test_stratified_overlap_compares_within_same_sigungu():
    # 가 구는 전부 다발지역 안, 나 구는 전부 밖. 대상이 가 구에만 있으면 무작위도 가 구에서만 뽑아 배수 1
    cw = pd.DataFrame({"sigungu": ["가"] * 20 + ["나"] * 20, "length_m": np.tile(np.arange(10, 30), 2),
                       "in_crash": [True] * 20 + [False] * 20})
    target = pd.Series([True] * 5 + [False] * 35)
    r = vv.stratified_overlap(cw, target, n_perm=200, seed=3, n_bins=2)
    assert r["overlap_ratio"] == 1.0 and r["random_mean"] == 1.0 and r["ratio_vs_random"] == 1.0
    assert r == vv.stratified_overlap(cw, target, n_perm=200, seed=3, n_bins=2)


def test_stratified_overlap_detects_concentration():
    rng = np.random.default_rng(5)
    n = 400
    cw = pd.DataFrame({"sigungu": rng.choice(["가", "나"], n), "length_m": rng.uniform(5, 40, n),
                       "in_crash": rng.random(n) < 0.1})
    target = pd.Series(np.zeros(n, dtype=bool))
    target[cw.index[cw["in_crash"]][:15]] = True              # 겹치는 곳만 대상으로
    target[cw.index[~cw["in_crash"]][:15]] = True
    r = vv.stratified_overlap(cw, target, n_perm=300, seed=5, n_bins=4)
    assert r["overlap_ratio"] == pytest.approx(0.5)
    assert r["ratio_vs_random"] > 3 and r["p_value"] < 0.01


def test_radius_elderly_ratio_weights_by_overlapping_area():
    dongs = gpd.GeoDataFrame({"ratio_65plus": [0.1, 0.3]},
                             geometry=[box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000)], crs=CRS)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy([1000, 300, 5000], [500, 500, 5000]), crs=CRS)
    r = vv.radius_elderly_ratio(pts, dongs, 100)
    assert r[0] == pytest.approx(0.2, abs=1e-6)    # 경계 위: 반반
    assert r[1] == pytest.approx(0.1)              # 왼쪽 동 안
    assert np.isnan(r[2])                          # 어느 동과도 안 겹침(부산 밖)


def test_nearest_m():
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy([0, 100], [0, 0]), crs=CRS)
    tg = gpd.GeoDataFrame(geometry=gpd.points_from_xy([30, 400], [40, 0]), crs=CRS)
    assert vv.nearest_m(pts, tg).tolist() == pytest.approx([50, 6500 ** 0.5], abs=1e-6)   # (100,0)→(30,40)
    assert np.isinf(vv.nearest_m(pts, tg.iloc[0:0])).all()


def test_rounded_drops_nan_and_numpy_types():
    assert vv.rounded({"a": np.float64(1.234567), "b": float("nan"), "c": [np.int64(3), np.inf]}) == \
        {"a": 1.2346, "b": None, "c": [3, None]}


def test_document_with_v6_v7_passes_validation_schema():
    doc = {"v1": None, "v2": None, "v3": None, "v4": None, "v5": None,
           "v6": vv.rounded({"n_stations": 101, "n_market_stations": 7, "diff_pp": 10.95, "p_value": 0.0036,
                             "n_permutations": 5000, "seed": 20261101, "slope": 0.80, "uplift": 0.137,
                             "uplift_range": [0.06, 0.156],
                             "sensitivity": [{"param": "year", "value": "2024", "n_market_stations": 7,
                                              "diff_pp": 10.95, "p_value": 0.0036, "uplift": 0.137}]}),
           "v7": {"groups": vv.v7_groups(pd.DataFrame({"protect_zone_m": [10.0], "child_zone_m": [10.0],
                                                       "formula_class": ["0.7"]}), 300, 150)}}
    vv.check_schema(CONTRACTS, json.loads(json.dumps(doc)))
