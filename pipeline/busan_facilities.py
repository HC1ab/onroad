"""부산 F4 노출 시설: 보호구역(O1)·전통시장(O3)·경로당(O2)을 읽고 횡단보도 반경 안 시설 수를 센다.

원칙 (pipeline/CLAUDE.md)
    - 거리·반경은 EPSG:5179(미터)로 계산한다. 시설은 부산 밖 것도 모두 쓴다(경계 근처 횡단보도 때문).
    - 시설 좌표가 없거나 한국 범위 밖이면 제외하고 그 건수를 보고한다. 지오코딩하지 않는다.
    - 전화번호·담당자 같은 열은 읽지 않는다 (산출물에 넣지 않음).
    - 인코딩은 utf-8-sig / cp949 를 모두 시도한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

# 한국 영역의 대략적 범위(도). 좌표 오입력을 걸러내는 물리적 한계이며 분석 설정이 아니다.
KOREA_LAT = (33.0, 39.0)
KOREA_LON = (124.0, 132.0)

# 노인 보호구역 장소유형코드. 1·01 = 노인, 2·02 = 장애인 (파일에 두 표기가 섞여 있다).
ELDERLY_ZONE_CODES = {"1"}
# 경로당 밀집에 쓰는 시설 유형과 영업 상태. 마을회관 단독은 노인 전용 시설이 아니라 제외한다.
SENIOR_TYPES = {"경로당", "마을회관및경로당"}
SENIOR_OPEN = "영업"


@dataclass
class Facility:
    """시설 한 종류: 미터 좌표 배열과 제외 건수."""
    name: str
    xy: np.ndarray  # (n, 2) EPSG:5179
    total_rows: int  # 필터 전 행 수
    kept_rows: int  # 조건에 맞는 행 수(좌표 점검 전)
    bad_coord_rows: int  # 조건에 맞지만 좌표가 없거나 범위 밖이라 뺀 행 수


def read_csv_any(path: Path, usecols: list[str]) -> pd.DataFrame:
    """utf-8-sig 로 먼저, 안 되면 cp949 로 읽는다. 필요한 열만 읽는다."""
    last = None
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, usecols=usecols)
        except UnicodeDecodeError as e:  # 인코딩이 다르면 다음 인코딩으로
            last = e
    raise last  # type: ignore[misc]


def to_xy(lon: pd.Series, lat: pd.Series, crs_compute: str, crs_storage: str) -> tuple[np.ndarray, int]:
    """경도·위도를 미터 좌표로 바꾼다. 좌표가 없거나 범위 밖인 행은 빼고 그 건수를 함께 돌려준다."""
    lo = pd.to_numeric(lon, errors="coerce")
    la = pd.to_numeric(lat, errors="coerce")
    ok = la.between(*KOREA_LAT) & lo.between(*KOREA_LON)
    tf = Transformer.from_crs(crs_storage, crs_compute, always_xy=True)
    x, y = tf.transform(lo[ok].to_numpy(), la[ok].to_numpy())
    return np.column_stack([x, y]), int((~ok).sum())


def load_protect_zone(path: Path, cfg: dict) -> Facility:
    df = read_csv_any(path, ["장소유형코드", "위도", "경도"])
    code = df["장소유형코드"].fillna("").str.strip().str.lstrip("0")  # '01' → '1'
    sel = df[code.isin(ELDERLY_ZONE_CODES)]
    xy, bad = to_xy(sel["경도"], sel["위도"], cfg["crs_compute"], cfg["crs_storage"])
    return Facility("protect_zone", xy, len(df), len(sel), bad)


def load_market(path: Path, cfg: dict) -> Facility:
    df = read_csv_any(path, ["위도", "경도"])
    xy, bad = to_xy(df["경도"], df["위도"], cfg["crs_compute"], cfg["crs_storage"])
    return Facility("market", xy, len(df), len(df), bad)


def load_senior_center(path: Path, cfg: dict) -> Facility:
    df = read_csv_any(path, ["flctTyp", "busiCodNm", "lat", "lot"])
    sel = df[df["flctTyp"].isin(SENIOR_TYPES) & (df["busiCodNm"] == SENIOR_OPEN)]
    xy, bad = to_xy(sel["lot"], sel["lat"], cfg["crs_compute"], cfg["crs_storage"])
    return Facility("senior_center", xy, len(df), len(sel), bad)


def count_within(points_xy: np.ndarray, fac: Facility, radius_m: float) -> np.ndarray:
    """각 점 반경 안(경계 포함) 시설 수."""
    if len(fac.xy) == 0:
        return np.zeros(len(points_xy), dtype=int)
    tree = cKDTree(fac.xy)
    return np.asarray(tree.query_ball_point(points_xy, r=radius_m, return_length=True), dtype=int)


def density_threshold(counts: np.ndarray, quantile: float) -> int:
    """경로당 밀집 기준: 부산 횡단보도 분포의 quantile 분위수를 올림한 값. 최소 1.

    개수는 정수이므로 올림해야 '분위수 이상'과 같은 뜻이 된다.
    0개인 곳이 절반을 넘어 분위수가 0이 되면 모든 곳이 밀집이 되므로 1로 막는다.
    """
    q = float(np.quantile(counts, quantile)) if len(counts) else 1.0
    return max(1, int(np.ceil(q)))


def flags_for(points_xy: np.ndarray, facs: dict[str, Facility], radius_m: float, quantile: float
              ) -> tuple[pd.DataFrame, int]:
    """횡단보도마다 플래그 3종(bool)과 경로당 개수를 돌려준다. 두 번째 값은 밀집 기준(개수)."""
    sc = count_within(points_xy, facs["senior_center"], radius_m)
    thr = density_threshold(sc, quantile)
    df = pd.DataFrame({
        "senior_center_n": sc,
        "senior_center": sc >= thr,
        "market": count_within(points_xy, facs["market"], radius_m) > 0,
        "protect_zone": count_within(points_xy, facs["protect_zone"], radius_m) > 0,
    })
    return df, thr
