"""busan_clean 단위 테스트. 작은 가짜 데이터로 F1 사유 우선순위와 F2 배정·실패 처리를 확인한다."""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import busan_clean as bc  # noqa: E402

CFG = {"outlier": {"max_length_m": 80, "max_green_s": 200},
       "crs_storage": "EPSG:4326", "crs_compute": "EPSG:5179"}


def row(seq, **kw):
    """정상 행 하나를 만들고 필요한 값만 바꾼다."""
    base = dict(seq=seq, gu_raw="중구", dong_raw="중앙동", jibun="1-1", crossing="x",
                signal_yn="유", length_m=20.0, green_s=27.0, lon=129.03, lat=35.10)
    base.update(kw)
    return base


def test_first_reason_wins_and_counts():
    df = pd.DataFrame([
        row(1),                                   # 정상
        row(2, lat=None),                         # 좌표 없음
        row(3, lat=50.0),                         # 좌표 범위 밖
        row(4, length_m=None, green_s=-1),        # 길이·보행시간 둘 다 나쁨 → 길이만 기록
        row(5, green_s=0),                        # 보행시간 0
        row(6, length_m=81),                      # 길이 이상치
        row(7, green_s=201),                      # 보행시간 이상치
    ])
    kept, ex = bc.clean(df, CFG)
    assert list(kept["seq"]) == [1]
    got = dict(zip(ex["seq"], ex["reason"]))
    assert got == {2: "coord_missing", 3: "coord_range", 4: "length_invalid",
                   5: "green_invalid", 6: "outlier_length", 7: "outlier_green"}


def test_duplicate_keeps_lowest_seq_and_ignores_already_excluded():
    df = pd.DataFrame([row(10), row(11), row(12, length_m=None), row(13, length_m=None)])
    kept, ex = bc.clean(df, CFG)
    assert list(kept["seq"]) == [10]
    reasons = dict(zip(ex["seq"], ex["reason"]))
    assert reasons[11] == "duplicate"                       # 10 번과 같은 행
    assert reasons[12] == reasons[13] == "length_invalid"   # 앞 사유가 우선, 중복으로 세지 않는다


def test_green_is_not_rounded_and_cw_id_is_stable():
    df = pd.DataFrame([row(7, green_s=15.571428571428571)])
    kept, _ = bc.clean(df, CFG)
    assert kept.loc[0, "green_s"] == pytest.approx(15.571428571428571, abs=0)
    assert kept.loc[0, "cw_id"] == "busan-00007"


def test_reason_table_shows_zero_rows():
    df = pd.DataFrame([row(1), row(2, lat=None)])
    _, ex = bc.clean(df, CFG)
    t = bc.reason_table(ex, total=2).set_index("reason")
    assert t.loc["coord_missing", "건수"] == 1 and t.loc["coord_missing", "비율(%)"] == 50.0
    assert t.loc["outlier_green", "건수"] == 0           # 0건인 사유도 표에 나온다


def _boundary():
    """가로로 붙은 두 동. 서쪽 = 중구 A동(코드 2611), 동쪽 = 서구 B동(코드 2612)."""
    g = gpd.GeoDataFrame({
        "adm_cd2": ["2611000001", "2612000001"],
        "adm_nm": ["부산광역시 중구 A동", "부산광역시 서구 B동"],
        "sggnm": ["중구", "서구"],
        "geometry": [box(129.00, 35.00, 129.05, 35.20), box(129.05, 35.00, 129.10, 35.20)],
    }, crs="EPSG:4326")
    return g


def test_assign_matches_flags_name_mismatch_and_reports_unmatched_distance():
    kept = pd.DataFrame([
        row(1, lon=129.02, dong_raw="A동"),                         # 중구 A동 안, 이름 일치
        row(2, lon=129.07, gu_raw="중구", dong_raw="A동"),          # 서구 B동 안인데 엑셀은 중구 → 구 불일치
        row(3, lon=128.99),                                        # 경계 밖(서쪽)
    ])
    kept, _ = bc.clean(kept, CFG)
    assigned, unmatched = bc.assign(kept, _boundary(), CFG)
    a = assigned.set_index("seq")
    assert a.loc[1, "adm_cd2"] == "2611000001" and a.loc[1, "gu_match"] and a.loc[1, "dong_match"]
    assert a.loc[2, "adm_cd2"] == "2612000001" and not a.loc[2, "gu_match"]
    assert a.loc[2, "gu_dist_m"] > 0                               # 엑셀이 적은 구(중구)까지 거리가 잰다
    assert list(unmatched["seq"]) == [3]
    assert 0 < unmatched.loc[0, "dist_m"] < 2000                    # 약 0.01도(미터 단위로 환산) 안쪽
    assert unmatched.loc[0, "nearest_adm_cd2"] == "2611000001"
    assert isinstance(assigned.loc[0, "adm_cd2"], str)              # 코드는 문자열


def test_dong_name_compare_ignores_numbers():
    kept = pd.DataFrame([row(1, lon=129.02, dong_raw="A동")])
    kept, _ = bc.clean(kept, CFG)
    b = _boundary()
    b.loc[0, "adm_nm"] = "부산광역시 중구 A1동"                     # 행정동은 번호가 붙는다
    assigned, _ = bc.assign(kept, b, CFG)
    assert bool(assigned.loc[0, "dong_match"])
