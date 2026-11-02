"""노출 시설 테스트: 코드 표기 통일, 영업·유형 필터, 반경 계산, 밀집 기준."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import busan_facilities as fac  # noqa: E402

CFG = {"crs_storage": "EPSG:4326", "crs_compute": "EPSG:5179"}


def facility(points, name="x"):
    xy = np.array(points, dtype=float).reshape(-1, 2)
    return Facility_(name, xy)


def Facility_(name, xy):
    return fac.Facility(name, xy, len(xy), len(xy), 0)


def test_count_within_includes_boundary_and_excludes_beyond():
    f = facility([(0, 0), (300, 0), (301, 0)])
    pts = np.array([[0.0, 0.0]])
    assert fac.count_within(pts, f, 300)[0] == 2          # 0m 와 정확히 300m 는 포함, 301m 는 제외


def test_count_within_empty_facility():
    assert fac.count_within(np.array([[0.0, 0.0]]), facility([]), 300).tolist() == [0]


@pytest.mark.parametrize("counts,q,expected", [
    ([0, 0, 0, 0], 0.75, 1),                 # 분위수가 0 이면 1 로 막는다 (전부 밀집이 되는 것 방지)
    ([0, 1, 2, 3, 4], 0.75, 3),              # 75% 위치 = 3 → 3 이상
    ([0, 0, 1, 1, 1, 1, 1, 5], 0.75, 1),
    ([1, 2, 3, 4], 0.75, 4),                 # 선형보간 3.25 → 올림 4
])
def test_density_threshold(counts, q, expected):
    assert fac.density_threshold(np.array(counts), q) == expected


def test_flags_for_combines_three_kinds():
    facs = {
        "senior_center": facility([(0, 0), (10, 0), (20, 0), (30, 0)]),   # 첫 점 근처에 4곳
        "market": facility([(1000, 1000)]),
        "protect_zone": facility([(5, 5)]),
    }
    pts = np.array([[0.0, 0.0], [2000.0, 0.0]])
    df, thr = fac.flags_for(pts, facs, 100, 0.5)
    assert df.loc[0, ["senior_center", "market", "protect_zone"]].tolist() == [True, False, True]
    assert df.loc[1, ["senior_center", "market", "protect_zone"]].tolist() == [False, False, False]
    assert thr >= 1


def test_to_xy_drops_missing_and_out_of_range():
    xy, bad = fac.to_xy(pd.Series(["129.0", None, "129.0", "200"]), pd.Series(["35.1", "35.1", "x", "35.1"]),
                        CFG["crs_compute"], CFG["crs_storage"])
    assert len(xy) == 1 and bad == 3


def test_load_protect_zone_unifies_codes(tmp_path):
    p = tmp_path / "pz.csv"
    pd.DataFrame({"장소유형코드": ["1", "01", "2", "02", None], "위도": ["35.1"] * 5, "경도": ["129.0"] * 5}
                 ).to_csv(p, index=False, encoding="cp949")
    f = fac.load_protect_zone(p, CFG)
    assert f.kept_rows == 2 and len(f.xy) == 2              # 노인(1·01)만, 장애인(2·02)과 빈 값 제외


def test_load_senior_center_filters_type_and_open(tmp_path):
    p = tmp_path / "sc.csv"
    pd.DataFrame({
        "flctTyp": ["경로당", "마을회관및경로당", "마을회관", "경로당", "경로당"],
        "busiCodNm": ["영업", "영업", "영업", "폐업", "영업"],
        "lat": ["35.1", "35.1", "35.1", "35.1", None], "lot": ["129.0"] * 4 + ["129.0"],
        "telno": ["010-0000-0000"] * 5,                   # 전화번호 열은 읽지 않는다
    }).to_csv(p, index=False, encoding="utf-8-sig")
    f = fac.load_senior_center(p, CFG)
    assert f.kept_rows == 3 and f.bad_coord_rows == 1 and len(f.xy) == 2


def test_read_csv_any_does_not_load_unrequested_columns(tmp_path):
    p = tmp_path / "m.csv"
    pd.DataFrame({"위도": ["35.1"], "경도": ["129.0"], "전화번호": ["051-000-0000"]}).to_csv(p, index=False, encoding="cp949")
    assert list(fac.read_csv_any(p, ["위도", "경도"]).columns) == ["위도", "경도"]
