"""v2 단계 판정·반경 고령 비율·기준식 분류·data_check (결정 009).

거리·면적은 모두 EPSG:5179(미터)로 계산한다(pipeline/CLAUDE.md). 시설은 부산 밖 것도 쓴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import STRtree, points

from pipeline import busan_facilities as fac

# 원(반경 버퍼)을 다각형으로 근사할 때 4분의 1 원당 선분 수. 면적 오차가 0.1% 안쪽이 되는 수치 장치이며 분석 설정이 아니다.
CIRCLE_QUAD_SEGS = 16

FORMULA_CLASSES = ("1.0", "0.8", "0.7", "other")


# ---------- 기준식 분류·data_check ----------
def classify_formula(length_m, green_s, cfg: dict) -> pd.Series:
    """기록 보행시간이 어느 기준식(entry + L/v)과 같은지. 허용오차 config formula_tolerance_s.

    여러 식에 걸리면 1.0 이 남는다(계약: "두 식에 걸리면 1.0"). 느린 속도부터 덮어쓴다.
    """
    L = pd.Series(np.asarray(length_m, dtype=float))
    T = pd.Series(np.asarray(green_s, dtype=float))
    out = pd.Series("other", index=L.index, dtype=object)
    for v in sorted(cfg["speeds_mps"]):  # 0.7 -> 0.8 -> 1.0
        same = (T - (cfg["entry_seconds"] + L / v)).abs() <= cfg["formula_tolerance_s"]
        out[same] = f"{v:.1f}"
    return out


def data_check_mask(length_m, green_s, formula_class: pd.Series, cfg: dict) -> np.ndarray:
    """기록 보행시간이 어느 기준식과도 같지 않고, 일반 기준식(가장 빠른 속도)보다도 짧은 곳.

    기록 방식이 다를 수 있어 확인 전까지 집계에서 뺀다.
    """
    v_fast = max(cfg["speeds_mps"])
    shorter = np.asarray(green_s, dtype=float) < (
        cfg["entry_seconds"] + np.asarray(length_m, dtype=float) / v_fast - cfg["formula_tolerance_s"])
    return (formula_class.to_numpy() == "other") & shorter


# ---------- 시설 ----------
@dataclass
class NamedFacility:
    names: np.ndarray
    xy: np.ndarray  # (n, 2) EPSG:5179
    total_rows: int
    kept_rows: int
    bad_coord_rows: int


def load_big_markets(path: Path, cfg: dict) -> NamedFacility:
    """2단계 시설: 점포 수 big_market_min_stores 이상이고 제외 키워드(시장명·취급품목)가 없는 전통시장."""
    df = fac.read_csv_any(path, ["시장명", "취급품목", "점포수", "위도", "경도"])
    stores = pd.to_numeric(df["점포수"], errors="coerce")
    pattern = "|".join(map(re.escape, cfg["market_exclude_keywords"]))
    excluded = df["시장명"].fillna("").str.contains(pattern) | df["취급품목"].fillna("").str.contains(pattern)
    sel = df[(stores >= cfg["big_market_min_stores"]) & ~excluded]
    xy, names, bad = _xy_keep_names(sel, cfg)
    return NamedFacility(names, xy, len(df), len(sel), bad)


def _xy_keep_names(sel: pd.DataFrame, cfg: dict):
    """to_xy 와 같은 좌표 점검을 하되, 살아남은 행의 시장명을 함께 돌려준다."""
    lo = pd.to_numeric(sel["경도"], errors="coerce")
    la = pd.to_numeric(sel["위도"], errors="coerce")
    ok = la.between(*fac.KOREA_LAT) & lo.between(*fac.KOREA_LON)
    xy, _ = fac.to_xy(sel["경도"][ok], sel["위도"][ok], cfg["crs_compute"], cfg["crs_storage"])
    return xy, sel["시장명"][ok].to_numpy(), int((~ok).sum())


def nearest_distance(points_xy: np.ndarray, fac_xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """각 점에서 가장 가까운 시설까지 거리(m)와 그 시설의 인덱스. 시설이 없으면 (inf, -1)."""
    if len(fac_xy) == 0:
        return np.full(len(points_xy), np.inf), np.full(len(points_xy), -1)
    d, i = cKDTree(fac_xy).query(points_xy)
    return d, i


def assign_tier(dist_protect_m, dist_market_m, radius_m: float) -> np.ndarray:
    """1 노인보호구역 반경 안, 2 대형 전통시장 반경 안, 그 외 3. 먼저 걸린 하나(반경 경계 포함)."""
    return np.select([np.asarray(dist_protect_m) <= radius_m, np.asarray(dist_market_m) <= radius_m], [1, 2], 3)


# ---------- 반경 안 주민 고령 비율 ----------
def resident_elderly_ratio(points_xy: np.ndarray, dong_polys, dong_ratio: np.ndarray, radius_m: float) -> np.ndarray:
    """점마다 반경 원과 겹치는 행정동의 고령 비율을 겹친 면적으로 가중평균한다.

    dong_polys: EPSG:5179 다각형 리스트, dong_ratio: 같은 순서의 고령 비율(없으면 NaN, 가중에서 뺀다).
    원과 겹치는 동이 없거나 모두 NaN 이면 NaN.
    """
    tree = STRtree(dong_polys)
    out = np.full(len(points_xy), np.nan)
    for k, (x, y) in enumerate(points_xy):
        circle = points(x, y).buffer(radius_m, quad_segs=CIRCLE_QUAD_SEGS)
        idx = tree.query(circle, predicate="intersects")
        if len(idx) == 0:
            continue
        w = np.array([dong_polys[i].intersection(circle).area for i in idx])
        r = dong_ratio[idx]
        ok = ~np.isnan(r) & (w > 0)
        if ok.any():
            out[k] = np.average(r[ok], weights=w[ok])
    return out
