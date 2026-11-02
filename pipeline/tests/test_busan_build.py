"""F4 집계·결과 묶음 테스트: 중앙값, 사분면, 표본 하한, 후보 정의, 스키마 통과."""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import busan_build as bb  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def dongs():
    return gpd.GeoDataFrame({
        "adm_cd2": ["2611000001", "2611000002", "2611000003", "2611000004"],
        "adm_nm": [f"부산광역시 중구 동{i}" for i in range(1, 5)],
        "sidonm": ["부산광역시"] * 4, "sggnm": ["중구"] * 4,
        "adm_name": [f"동{i}" for i in range(1, 5)],
        "geometry": [box(129 + i * 0.01, 35, 129.01 + i * 0.01, 35.01) for i in range(4)],
    }, crs="EPSG:4326")


def pop():
    return pd.DataFrame({"adm_cd": ["2611000001", "2611000002", "2611000003"],
                         "ratio_65plus": [0.10, 0.30, 0.20]})


def rows(adm, n, n_short, n_cand=0):
    """한 동의 횡단보도 n 개 중 n_short 개가 짧음, 그 중 n_cand 개가 후보."""
    out = []
    for i in range(n):
        short = i < n_short
        out.append({"cw_id": f"{adm}-{i}", "adm_cd2": adm, "lat": 35.0, "lon": 129.0, "length_m": 20.0,
                    "green_s": 20.0, "t_need_s": 27.0, "gap_s": 7.0 if short else -3.0,
                    "senior_center": i < n_cand, "market": False, "protect_zone": False,
                    "exposure_cnt": 1 if i < n_cand else 0, "short": short, "is_candidate": short and i < n_cand})
    return out


def test_area_items_medians_quadrant_and_low_sample():
    r = pd.DataFrame(rows("2611000001", 10, 2) + rows("2611000002", 10, 8, 3) + rows("2611000003", 10, 5)
                     + rows("2611000004", 2, 2))                 # 4번 동: 표본 2곳 → low_sample
    items, med = bb.build_area_items(r, dongs(), pop(), min_sample=5)
    by = {i["adm_cd"]: i for i in items}
    assert med == {"short_ratio_median": 0.5, "ratio_65plus_median": 0.2}   # 3개 동의 중앙값 (low_sample 제외)
    assert by["2611000001"]["quadrant"] == "low_low"          # 0.2 < 0.5, 0.10 < 0.2
    assert by["2611000002"]["quadrant"] == "high_high"        # 0.8 > 0.5, 0.30 > 0.2
    assert by["2611000003"]["quadrant"] == "low_low"          # 중앙값과 '같으면' low
    assert by["2611000004"]["low_sample"] and by["2611000004"]["quadrant"] is None
    assert by["2611000002"]["n_candidate"] == 3 and by["2611000002"]["mean_gap_s"] == 7.0
    assert by["2611000004"]["ratio_65plus"] is None           # 인구 미매칭


def test_area_without_crosswalks_is_included_as_gray():
    r = pd.DataFrame(rows("2611000001", 10, 2))
    items, _ = bb.build_area_items(r, dongs(), pop(), min_sample=5)
    empty = [i for i in items if i["adm_cd"] == "2611000003"][0]
    assert empty["n_analyzed"] == 0 and empty["short_ratio"] is None and empty["low_sample"]


def test_candidate_needs_both_short_and_flag():
    r = pd.DataFrame(rows("2611000001", 4, 2, n_cand=3))      # i=0,1 짧음, i=0,1,2 플래그 → 후보는 0,1
    assert r["is_candidate"].sum() == 2
    doc = bb.candidate_doc(r, 0.7, 300)
    assert len(doc["features"]) == 2 and all(f["properties"]["exposure_cnt"] >= 1 for f in doc["features"])


def test_documents_pass_real_schemas():
    chk = bb.SchemaCheck(CONTRACTS)
    r = pd.DataFrame(rows("2611000001", 10, 2) + rows("2611000002", 10, 8, 3) + rows("2611000004", 2, 2))
    items, med = bb.build_area_items(r, dongs(), pop(), min_sample=5)
    chk.check("areas", {"speed": 0.7, "radius_m": 300, "thresholds": med, "items": items})   # null 사분면 포함
    chk.check("candidates", bb.candidate_doc(r, 0.7, 300))
    chk.check("area_crosswalks", {"adm_cd": "2611000002", "speed": 0.7, "radius_m": 300,
                                   "items": bb.crosswalk_items(r[r["adm_cd2"] == "2611000002"])})
    chk.check("meta", bb.meta_doc("2026-09", 100, 98, [{"name": "x", "url": ""}], "2026-11-01T00:00:00+09:00"))
    chk.check("boundaries", bb.simplify_boundaries(dongs(), 15.0, {"crs_compute": "EPSG:5179", "crs_storage": "EPSG:4326"}))


def test_crosswalk_items_sorted_by_gap_desc_and_hospital_null():
    r = pd.DataFrame(rows("2611000001", 4, 2))
    items = bb.crosswalk_items(r)
    assert [i["gap_s"] for i in items] == sorted([i["gap_s"] for i in items], reverse=True)
    assert all(i["flags"]["hospital"] is None for i in items)


def test_schema_check_rejects_bad_document():
    chk = bb.SchemaCheck(CONTRACTS)
    with pytest.raises(Exception):
        chk.check("candidates", {"type": "FeatureCollection", "features": [{"type": "Feature"}]})


def test_load_population_parses_codes_numbers_and_month(tmp_path):
    p = tmp_path / "r3.csv"
    pd.DataFrame({"행정구역": ["부산광역시 중구 중앙동(2611051000)", "부산광역시  (2600000000)"],
                  "2026년09월_전체": ["3,124", "3,228,188"], "2026년09월_65세이상전체": ["537", "848,138"]}
                 ).to_csv(p, index=False, encoding="cp949")
    df, month = bb.load_population(p)
    assert month == "2026-09"
    assert df.set_index("adm_cd").loc["2611051000", "ratio_65plus"] == pytest.approx(537 / 3124)


def test_config_radii_must_match_contract(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("entry_seconds: 7\nspeeds_mps: [1.0]\nmin_sample: 5\nexposure_radius_m: 300\n"
                 "exposure_radius_sensitivity_m: [100]\ncrs_storage: a\ncrs_compute: b\n"
                 "senior_center_density_quantile: 0.75\n", encoding="utf-8")
    with pytest.raises(ValueError):
        bb.load_config(p)
