"""검증 V2·V3·V4 테스트: 순위·동점 처리, 무작위 비교의 재현성, 스키마 통과."""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import busan_validate as bv  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
CRS = "EPSG:5179"


def areas(ratios, low=None, adm=None, sigungu="중구", r65=None):
    n = len(ratios)
    return pd.DataFrame({
        "adm_cd": adm or [f"26110000{i:02d}" for i in range(n)],
        "sigungu": sigungu if not isinstance(sigungu, str) else [sigungu] * n,
        "short_ratio": ratios, "n_analyzed": [10] * n,
        "low_sample": low or [False] * n,
        "ratio_65plus": r65 if r65 is not None else [0.1 * (i + 1) for i in range(n)],
    })


def test_top_set_ties_prefer_more_crosswalks_then_code():
    a = pd.DataFrame({"adm_cd": ["c", "a", "b", "d"], "short_ratio": [0.5, 0.5, 0.5, 0.9],
                      "n_analyzed": [10, 10, 20, 5], "low_sample": [False] * 4})
    assert bv.top_set(a, 2) == {"d", "b"}                  # 0.9 가 먼저, 동점 0.5 중에서는 분석 20곳인 b
    assert bv.top_set(a, 3) == {"d", "b", "a"}             # 그 다음은 코드순(a < c)


def test_top_set_excludes_low_sample():
    a = areas([0.9, 0.8], low=[True, False])
    assert bv.top_set(a, 5) == {a["adm_cd"][1]}


def test_v2_identical_rankings_and_reversed():
    base = areas([0.1, 0.2, 0.3, 0.4, 0.5])
    rev = areas([0.5, 0.4, 0.3, 0.2, 0.1])
    out = bv.v2({0.7: base, 0.8: base.copy(), 1.0: rev}, top_n=2)
    p = {(x["a"], x["b"]): x for x in out["pairs"]}
    assert p[(0.7, 0.8)]["spearman"] == 1.0 and p[(0.7, 0.8)]["top_n_overlap"] == 2
    assert p[(0.7, 1.0)]["spearman"] == -1.0 and p[(0.7, 1.0)]["top_n_overlap"] == 0


def test_v2_constant_ratio_is_an_error_not_a_silent_nan():
    const = areas([0.0, 0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        bv.v2({0.7: areas([0.1, 0.2, 0.3, 0.4]), 0.8: const}, top_n=2)


def crosswalks(n_cand_in_zone, n_cand_out, n_other_in, n_other_out):
    """후보/비후보 × 다발지역 안/밖 횡단보도. 안 = (129.0, 35.0) 근처, 밖 = 멀리."""
    rows = []
    for cand, inside, n in [(True, True, n_cand_in_zone), (True, False, n_cand_out),
                            (False, True, n_other_in), (False, False, n_other_out)]:
        for i in range(n):
            rows.append({"cw_id": f"{int(cand)}{int(inside)}-{i}", "adm_cd": "A", "is_candidate": cand,
                         "lon": 129.0 if inside else 129.5, "lat": 35.0 if inside else 35.5, "length_m": 20.0 + i % 3})
    return pd.DataFrame(rows)


def zone():
    return gpd.GeoSeries([box(128.99, 34.99, 129.01, 35.01)], crs="EPSG:4326").to_crs(CRS)


def test_v3_observed_overlap_and_seed_reproducible():
    cw = crosswalks(6, 14, 4, 76)                           # 후보 20 중 6 이 다발지역 안 → 0.3, 전체 10/100
    a, na = bv.v3(cw, {"A": "중구"}, zone(), 0.7, [2021, 2025], n_perm=200, seed=1, n_bins=2, crs_compute=CRS)
    b, _ = bv.v3(cw, {"A": "중구"}, zone(), 0.7, [2021, 2025], n_perm=200, seed=1, n_bins=2, crs_compute=CRS)
    assert a["overlap_ratio"] == 0.3 and na["candidates_in_zone"] == 6
    assert a == b                                           # 같은 시드 → 같은 결과
    assert 0 < a["p_value"] <= 1 and len(a["random_distribution"]) == 200
    assert a["ratio_vs_random"] > 1                         # 후보가 전체(0.1)보다 겹침이 높게 만들어 둔 입력


def test_v3_all_candidates_is_deterministic_and_ratio_one():
    cw = crosswalks(5, 5, 0, 0)                             # 후보 = 전체 → 무작위 추출이 항상 같은 집합
    out, _ = bv.v3(cw, {"A": "중구"}, zone(), 0.7, [2021], n_perm=50, seed=3, n_bins=1, crs_compute=CRS)
    assert out["ratio_vs_random"] == 1.0
    assert out["p_value"] == 1.0                            # 무작위가 항상 관측값과 같음 → (1+50)/(50+1)


def test_v3_requires_candidates():
    cw = crosswalks(0, 0, 3, 3)
    with pytest.raises(ValueError):
        bv.v3(cw, {"A": "중구"}, zone(), 0.7, [2021], n_perm=10, seed=1, n_bins=1, crs_compute=CRS)


def test_v4_groups_skip_small_and_inside_outside():
    a = areas([0.1, 0.3, 0.2, 0.9, 0.5, 0.4], sigungu=["갑", "갑", "갑", "을", "을", "을"],
              r65=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    cw = pd.DataFrame({"gap_s": [1.0, -1.0, 2.0, 3.0], "senior_center": [True, True, False, False],
                       "market": [True, False, True, False], "protect_zone": [False] * 4})
    out, notes = bv.v4(a, cw, 0.7, min_group=3)
    assert {g["group"] for g in out["by_group"]} == {"갑", "을"} and notes["groups_skipped_for_small_n"] == []
    out2, notes2 = bv.v4(a, cw, 0.7, min_group=4)
    assert out2["by_group"] == [] and set(notes2["groups_skipped_for_small_n"]) == {"갑", "을"}
    io = {x["facility"]: x for x in out["inside_outside"]}
    assert io["senior_center"]["inside_short_ratio"] == 0.5 and io["senior_center"]["outside_short_ratio"] == 1.0
    assert io["market"]["inside_short_ratio"] == 1.0 and io["market"]["outside_short_ratio"] == 0.5


def test_formula_split():
    cw = pd.DataFrame({"cw_id": ["a", "b", "c", "d"], "senior_center": [True, True, False, False],
                       "market": [False] * 4, "protect_zone": [False] * 4})
    j = pd.DataFrame({"cw_id": ["a", "b", "c", "d"], "formula_class": ["v0.7", "v1.0", "v1.0", "other"]})
    r = {x["facility"]: x for x in bv.formula_split(cw, j)}
    assert r["senior_center"]["inside_v0.7_formula_ratio"] == 0.5 and r["senior_center"]["outside_v0.7_formula_ratio"] == 0.0


def test_schema_accepts_null_v1_v5_and_rejects_bad_v2():
    ok = {"v1": None, "v2": {"top_n": 20, "pairs": [{"a": 0.7, "b": 0.8, "spearman": 0.9, "top_n_overlap": 10}]},
          "v3": None, "v4": None, "v5": None}
    bv.check_schema(CONTRACTS, ok)
    bad = {**ok, "v2": {"top_n": 20, "pairs": [{"a": 0.7, "b": 0.8, "spearman": 1.5, "top_n_overlap": 10}]}}
    with pytest.raises(Exception):
        bv.check_schema(CONTRACTS, bad)
