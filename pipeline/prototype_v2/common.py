"""분석 스크립트 공용: 경로, 설정, 원본 읽기, 거리·면적 계산, 보행속도 분포."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from shapely import STRtree, points
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
# 원본 폴더 구성은 같은 폴더 README.md. 결과는 data/interim 아래(커밋 금지 경로)에 쓴다
RAW = ROOT / "data" / "raw" / "prototype_v2"
INTERIM = ROOT / "data" / "interim"
OUT = INTERIM / "prototype_v2"
P = yaml.safe_load((Path(__file__).parent / "params.yaml").read_text(encoding="utf-8"))

# 부산 중심 위도에서의 등거리 근사 투영(m). 부산 범위(약 50km)에서 오차는 1% 미만
LAT0 = 35.15
M_PER_DEG_LAT = 110_540
M_PER_DEG_LON = 111_320 * math.cos(math.radians(LAT0))


def to_m(lon, lat):
    return np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT


def geom_to_m(geom):
    return transform(lambda x, y, z=None: to_m(x, y), geom)


def haversine_m(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = (np.sin((lat2 - lat1) * p / 2) ** 2
         + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6_371_000 * np.arcsin(np.sqrt(a))


def nearest_m(lat, lon, plat, plon):
    """각 점에서 가장 가까운 대상까지 거리와 그 대상의 위치(인덱스)."""
    d = haversine_m(np.asarray(lat)[:, None], np.asarray(lon)[:, None],
                    np.asarray(plat)[None, :], np.asarray(plon)[None, :])
    return d.min(axis=1), d.argmin(axis=1)


# ---------- 원본 읽기 ----------
def load_dongs() -> tuple[list[dict], list]:
    geo = json.loads((RAW / "admin_boundary" / "HangJeongDong_ver20261001.geojson").read_text(encoding="utf-8"))
    feats = [f["properties"] for f in geo["features"] if f["properties"]["sidonm"] == "부산광역시"]
    polys = [shape(f["geometry"]) for f in geo["features"] if f["properties"]["sidonm"] == "부산광역시"]
    return feats, polys


def load_population() -> pd.DataFrame:
    """R3 구·군별 파일 16개를 읍면동 한 표로 합친다. 구·군 합계 행은 뺀다."""
    frames = [pd.read_csv(f, encoding="cp949", dtype=str) for f in sorted((RAW / "population_65").glob("*.csv"))]
    df = pd.concat(frames, ignore_index=True)
    total_col = next(c for c in df.columns if c.endswith("_전체") and "65세" not in c)
    old_col = next(c for c in df.columns if c.endswith("65세이상전체"))
    df["adm_cd2"] = df["행정구역"].str.extract(r"\((\d{10})\)")[0]
    df["이름"] = df["행정구역"].str.replace(r"\s*\(\d{10}\)", "", regex=True).str.strip()
    df["전체"] = pd.to_numeric(df[total_col].str.replace(",", ""), errors="coerce")
    df["65세이상"] = pd.to_numeric(df[old_col].str.replace(",", ""), errors="coerce")
    df = df[~df["adm_cd2"].str.endswith("00000")]  # 구·군 합계 행
    df["고령비율"] = df["65세이상"] / df["전체"]
    return df[["adm_cd2", "이름", "전체", "65세이상", "고령비율"]].drop_duplicates("adm_cd2").reset_index(drop=True)


def load_crosswalks() -> tuple[pd.DataFrame, dict]:
    """부산 엑셀 첫 시트 → 정제 → 행정동 배정. 세로길이 = 횡단 거리, 보행시간 = 녹색 + 점멸 가정."""
    path = next((RAW / "crosswalk_busan").glob("*.xlsx"))
    cw = pd.read_excel(path, sheet_name=0)
    counts = {"원본": len(cw)}
    for c in ["세로길이", "가로길이", "보행시간", "위도", "경도"]:
        cw[c] = pd.to_numeric(cw[c], errors="coerce")
    cw = cw[(cw["세로길이"] > 0) & (cw["보행시간"] > 0) & cw["위도"].notna() & cw["경도"].notna()]
    cw = cw[(cw["세로길이"] <= P["max_length_m"]) & (cw["보행시간"] <= P["max_walk_s"])]
    cw = cw.drop_duplicates(["위도", "경도", "세로길이", "보행시간"]).reset_index(drop=True)
    counts["정제"] = len(cw)

    feats, polys = load_dongs()
    pi, gi = STRtree(polys).query(points(cw["경도"].values, cw["위도"].values), predicate="within")
    cw.loc[pi, "adm_cd2"] = [feats[i]["adm_cd2"] for i in gi]
    cw.loc[pi, "adm_nm"] = [feats[i]["adm_nm"] for i in gi]
    cw = cw[cw["adm_cd2"].notna()].reset_index(drop=True)
    counts["동 배정"] = len(cw)
    return cw, counts


def load_markets(big_only: bool = False) -> pd.DataFrame:
    mk = pd.read_csv(RAW / "market" / "전국전통시장표준데이터.csv")
    addr = mk["소재지도로명주소"].fillna(mk["소재지지번주소"])
    mk = mk[addr.str.startswith("부산", na=False)].dropna(subset=["위도", "경도"])
    pattern = "|".join(map(re.escape, P["market_exclude_keywords"]))
    mk = mk.assign(제외=mk["시장명"].str.contains(pattern) | mk["취급품목"].fillna("").str.contains(pattern))
    if big_only:
        mk = mk[(mk["점포수"] >= P["big_market_min_stores"]) & ~mk["제외"]]
    return mk.reset_index(drop=True)


def load_protect_zones() -> pd.DataFrame:
    pz = pd.read_csv(RAW / "protect_zone" / "전국노인장애인보호구역표준데이터.csv", dtype={"장소유형코드": str})
    is_busan = pz["시도명"].str.startswith("부산", na=False)
    is_elderly = pz["장소유형코드"].str.lstrip("0").eq("1")  # 1·01 노인, 2·02 장애인
    return pz[is_busan & is_elderly].dropna(subset=["위도", "경도"]).reset_index(drop=True)


# ---------- 반경 안 고령 비율 ----------
def radius_elderly_ratio(lat, lon, radius_m: float) -> np.ndarray:
    """점마다 반경 원과 겹치는 행정동의 고령 비율을 겹친 면적으로 가중평균한다."""
    feats, polys = load_dongs()
    pop = load_population().set_index("adm_cd2")["고령비율"]
    polys_m = [geom_to_m(p) for p in polys]
    ratio = np.array([pop.get(f["adm_cd2"], np.nan) for f in feats])
    tree = STRtree(polys_m)
    x, y = to_m(lon, lat)
    out = np.full(len(x), np.nan)
    for k, (px, py) in enumerate(zip(x, y)):
        circle = points(px, py).buffer(radius_m, quad_segs=16)
        idx = tree.query(circle, predicate="intersects")
        w = np.array([polys_m[i].intersection(circle).area for i in idx])
        r = ratio[idx]
        ok = ~np.isnan(r) & (w > 0)
        if ok.any():
            out[k] = np.average(r[ok], weights=w[ok])
    return out


# ---------- 보행속도 분포 ----------
Z15 = 1.0364  # 표준정규 85퍼센타일


def _dist(group: str) -> tuple[float, float]:
    g = P["walking_speed_mps"][group]
    return g["mean"], (g["mean"] - g["p15"]) / Z15


def _cdf(x, mu, sd):
    return 0.5 * (1 + np.vectorize(math.erf)((np.asarray(x) - mu) / (sd * math.sqrt(2))))


def slower_share(v, elderly_share):
    """속도 v보다 느린 사람의 비율. 일반·고령 분포를 고령 비율로 섞는다."""
    p = np.asarray(elderly_share)
    return (1 - p) * _cdf(v, *_dist("general")) + p * _cdf(v, *_dist("elderly"))


def coverage(length, seconds, elderly_share):
    """보행시간 안에 길이를 건널 수 있는 사람 비율."""
    need = np.asarray(length) / np.maximum(np.asarray(seconds) - P["entry_seconds"], 1e-9)
    return 1 - slower_share(need, elderly_share)


def design_speed(elderly_share, target: float) -> np.ndarray:
    """섞인 분포에서 target 비율이 건널 수 있는 속도(이분법), 공식 범위로 자른다."""
    p = np.atleast_1d(np.asarray(elderly_share, dtype=float))
    lo, hi = np.full_like(p, 0.1), np.full_like(p, 2.5)
    for _ in range(60):
        mid = (lo + hi) / 2
        too_fast = slower_share(mid, p) > 1 - target
        hi, lo = np.where(too_fast, mid, hi), np.where(too_fast, lo, mid)
    vmin, vmax = P["speed_bounds_mps"]
    return np.clip((lo + hi) / 2, vmin, vmax)


def md_table(df: pd.DataFrame, pct_cols=(), digits=1) -> str:
    fmt = df.copy()
    for c in fmt.columns:
        if c in pct_cols:
            fmt[c] = fmt[c].map(lambda x: "" if pd.isna(x) else f"{x:.1%}")
        elif pd.api.types.is_float_dtype(fmt[c]):
            fmt[c] = fmt[c].map(lambda x: "" if pd.isna(x) else f"{x:.{digits}f}")
    head = "| " + " | ".join(map(str, fmt.columns)) + " |"
    sep = "|" + "---|" * len(fmt.columns)
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in fmt.itertuples(index=False)]
    return "\n".join([head, sep, *body])
