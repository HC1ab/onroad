"""부산 v2 검증 V6·V7·V3 보강 → validation.json 의 v6·v7 (이슈 #76 D13, 결정 009).

입력
    - points_v2 묶음: D12 가 내보내는 GET /api/crosswalks?target= 형식(contracts points.schema.json).
      V7·V3 보강은 이 묶음만 쓴다. 구역 사이 접점은 contracts 이기 때문이다.
    - 원본(data/raw, 커밋 금지): V6 은 metro_ticket(M1)·station(S1)·market(O3)·population_65(R3)·
      admin_boundary(R2), V7 은 child_zone(C1), V3 보강은 crash_zone(R4 연도별 crash_zone_<연도>.json).
출력
    - <bundle>/validation.json: 있으면 v6·v7 만 넣고(busan_validate.py 의 v1~v5 는 그대로), 없으면 v1~v5 null 로 만든다.
      contracts 스키마를 통과하지 못하면 쓰지 않는다.
    - <bundle>/../v2_validation_notes.json: 화면에 다 싣지 않는 표(V6 민감도 전체, V7 구별·반경 민감도, V3 보강).

원칙
    - 결과가 기대와 달라도 그대로 보고한다. 연관성까지만 말하고 인과 표현을 쓰지 않는다.
    - 사고다발지역은 단계를 정하는 데 쓰지 않았다(순환 방지). V3 보강에서만 쓴다.
    - 무작위 비교는 시드를 고정해 같은 입력이면 같은 결과가 나온다.
    - 거리·면적은 config crs_compute(EPSG:5179)로 계산한다.

V6  무임 비율 = 무임 / 승차. 역 반경(metro_radius_m) 안 행정동 고령 비율(면적 가중)로 회귀한 잔차를
    대형 시장 반경 안 역과 그 외 역으로 비교한다(단측 순열 검정). 시장 보정 = 차이 / 기울기.
    민감도: 점포 기준, 시장 반경, 연도, 시장 근처 역 하나씩 빼기와 수안·부전 함께 빼기.
V7  기록 보행시간이 0.7 기준식과 같은(formula_class 0.7) 비율을 노인보호구역 반경 안 / 어린이보호구역 반경 안
    (노인 아님) / 둘 다 밖으로 비교한다. 민감도: 어린이보호구역 반경, 구별 분포.
V3+ 1단계(노인보호구역 반경 안) 중 기록값이 0.7 기준식이 아닌 횡단보도가 다발지역 안에 있는 비율을,
    같은 구·같은 길이 구간에서 무작위로 뽑은 분석 횡단보도의 비율과 비교한다(008·busan_validate.py 방식).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from shapely.geometry import shape

WGS84 = "EPSG:4326"
SIDO = "부산광역시"
METRO_OPERATOR = "부산교통공사"
STORE_THRESHOLDS = (100, 150, 200, 300)    # 이슈 #76 V6 민감도: 점포 기준
MARKET_RADII_M = (300, 500)                # 이슈 #76 V6 민감도: 시장 반경
CHILD_RADII_M = (100, 150, 300)            # 이슈 #76 V7 민감도: 어린이보호구역 반경
PAIR_DROP = ("수안", "부전")                # 결정 009: 둘을 함께 빼면 보정이 가장 작아진다


# ---------- 원본 읽기 ----------
def read_dongs(raw: Path, crs: str) -> gpd.GeoDataFrame:
    """R2 부산 행정동 경계와 R3 고령 비율을 adm_cd2(10자리)로 붙인다."""
    path = next((raw / "admin_boundary").glob("*.geojson"))
    g = gpd.read_file(path)
    g = g[g["sidonm"] == SIDO][["adm_cd", "adm_cd2", "sggnm", "geometry"]].copy()
    ratio = read_elderly_ratio(raw)
    g["ratio_65plus"] = g["adm_cd2"].map(ratio)
    return g.to_crs(crs)


def sigungu_of(adm_cd: pd.Series, dongs: pd.DataFrame) -> pd.Series:
    """점의 adm_cd → 구·군 이름. D12 는 adm_cd2(10자리), C3 샘플은 adm_cd(8자리)라 둘 다 받는다.

    구·군을 못 붙인 점이 있으면 층화 비교가 조용히 비므로 멈춘다.
    """
    lookup = pd.concat([dongs.set_index("adm_cd2")["sggnm"], dongs.set_index("adm_cd")["sggnm"]])
    out = adm_cd.astype(str).map(lookup)
    if out.isna().any():
        bad = adm_cd[out.isna()].astype(str).unique()[:5].tolist()
        raise ValueError(f"구·군을 붙이지 못한 점 {int(out.isna().sum())}곳 (adm_cd 예: {bad})")
    return out


def read_elderly_ratio(raw: Path) -> pd.Series:
    """R3 구·군별 파일(cp949)을 합쳐 adm_cd2 → 65세 이상 비율. 구·군 합계 행(끝 5자리 00000)은 뺀다."""
    frames = [pd.read_csv(f, encoding="cp949", dtype=str) for f in sorted((raw / "population_65").glob("*.csv"))]
    df = pd.concat(frames, ignore_index=True)
    total_col = next(c for c in df.columns if c.endswith("_전체") and "65세" not in c)
    old_col = next(c for c in df.columns if c.endswith("65세이상전체"))
    df["adm_cd2"] = df["행정구역"].str.extract(r"\((\d{10})\)")[0]
    df = df[df["adm_cd2"].notna() & ~df["adm_cd2"].str.endswith("00000")]
    num = lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")
    df = df.assign(total=num(df[total_col]), old=num(df[old_col])).drop_duplicates("adm_cd2")
    return (df["old"] / df["total"]).set_axis(df["adm_cd2"])


def read_markets(raw: Path, exclude: list[str], crs: str) -> gpd.GeoDataFrame:
    """O3 부산 전통시장(좌표 있는 것). 고령자 목적지로 보기 어려운 상가는 excluded=True."""
    mk = pd.read_csv(next((raw / "market").glob("*.csv")))
    addr = mk["소재지도로명주소"].fillna(mk["소재지지번주소"])
    mk = mk[addr.str.startswith("부산", na=False)].dropna(subset=["위도", "경도"]).copy()
    pattern = "|".join(map(re.escape, exclude))
    mk["excluded"] = mk["시장명"].str.contains(pattern) | mk["취급품목"].fillna("").str.contains(pattern)
    mk["stores"] = pd.to_numeric(mk["점포수"], errors="coerce").fillna(0)
    return points_gdf(mk[["시장명", "stores", "excluded", "위도", "경도"]], "위도", "경도", crs)


def norm_station(name: str) -> str:
    """역 이름 맞추기: '(1호선)'·가운뎃점·앞 숫자·끝 '역'을 지운다. M1 과 S1 표기가 달라서."""
    name = re.sub(r"\(\d호선\)", "", str(name).strip()).replace("·", "")
    return re.sub(r"역$", "", re.sub(r"^\d", "", name))


def read_metro(raw: Path) -> pd.DataFrame:
    """M1 월별 역별 승차·무임. 연월('2024년 1월')에서 연도를 뽑는다."""
    m = pd.read_csv(next((raw / "metro_ticket").glob("*.csv")), encoding="utf-8-sig")
    m["year"] = m["연월"].astype(str).str[:4]
    m["station"] = m["역명"].map(norm_station)
    return m


def read_station_coords(raw: Path) -> pd.DataFrame:
    """S1 부산교통공사 역 좌표(환승역은 노선별 좌표 평균)와 구."""
    c = pd.read_csv(next((raw / "station").glob("*.csv")))
    c = c[c["운영기관명"] == METRO_OPERATOR].copy()
    c["station"] = c["역사명"].map(norm_station)
    c["gu"] = c["역사도로명주소"].str.extract(r"부산광역시\s+(\S+[구군])")[0]
    return c.groupby("station").agg(lat=("역위도", "mean"), lon=("역경도", "mean"), gu=("gu", "first"))


def read_child_zones(raw: Path, crs: str) -> gpd.GeoDataFrame:
    """C1 부산 어린이보호구역 시설. 지정여부 칸이 대부분 비어 시설 전체를 쓴다(결정 009 검수 보완)."""
    cz = pd.read_csv(next((raw / "child_zone").glob("*.csv")))
    addr = cz["소재지도로명주소"].fillna(cz["소재지지번주소"])
    cz = cz[addr.str.startswith("부산", na=False)].dropna(subset=["위도", "경도"])
    return points_gdf(cz[["위도", "경도"]], "위도", "경도", crs)


def read_crash_zones(crash_dir: Path, years: list[int], crs: str) -> gpd.GeoSeries:
    """R4 연도별 JSON 에서 부산 다발지역 폴리곤을 모은다(busan_validate.py 와 같은 형식)."""
    geoms = []
    for y in years:
        for z in json.loads((crash_dir / f"crash_zone_{y}.json").read_text(encoding="utf-8")):
            if str(z["sido_sgg_nm"]).startswith("부산"):
                geoms.append(shape(json.loads(z["geom_json"])))
    return gpd.GeoSeries(geoms, crs=WGS84).to_crs(crs)


def read_points_v2(path: Path, crs: str) -> gpd.GeoDataFrame:
    """points_v2 묶음 → 분석 횡단보도(status=analyzed)만, 속성을 열로 펼친다."""
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [{**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
            for f in d["features"] if f["properties"]["status"] == "analyzed"]
    df = pd.DataFrame(rows)
    df["protect_zone_m"] = [rp["protect_zone_m"] if rp else np.nan for rp in df["reason_parts"]]
    return points_gdf(df, "lat", "lon", crs)


def points_gdf(df: pd.DataFrame, lat: str, lon: str, crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs=WGS84).to_crs(crs)


# ---------- 공간 계산 ----------
def nearest_m(points: gpd.GeoDataFrame, targets: gpd.GeoDataFrame) -> np.ndarray:
    """각 점에서 가장 가까운 대상까지 거리(m). 대상이 없으면 inf."""
    if len(targets) == 0:
        return np.full(len(points), np.inf)
    j = gpd.sjoin_nearest(points[["geometry"]].reset_index(names="_i"), targets[["geometry"]], distance_col="d")
    return j.groupby("_i")["d"].min().reindex(range(len(points))).to_numpy()


def radius_elderly_ratio(points: gpd.GeoDataFrame, dongs: gpd.GeoDataFrame, radius_m: float) -> np.ndarray:
    """점마다 반경 원과 겹치는 행정동의 고령 비율을 겹친 면적으로 가중평균한다. 부산 밖이면 NaN."""
    circles = gpd.GeoDataFrame({"_i": range(len(points))}, geometry=points.geometry.buffer(radius_m).values,
                               crs=points.crs)
    ov = gpd.overlay(circles, dongs[["ratio_65plus", "geometry"]].dropna(subset=["ratio_65plus"]),
                     how="intersection", keep_geom_type=True)
    ov["w"] = ov.geometry.area
    ov = ov[ov["w"] > 0]
    out = (ov.assign(wr=ov["w"] * ov["ratio_65plus"]).groupby("_i")[["wr", "w"]].sum())
    return (out["wr"] / out["w"]).reindex(range(len(points))).to_numpy()


# ---------- V6 ----------
def station_table(metro: pd.DataFrame, coords: pd.DataFrame, year: str) -> tuple[pd.DataFrame, list[str]]:
    """한 해의 역별 승차·무임 합계와 좌표. 승차 0(미개통)은 빼고, 좌표 없는 역은 목록으로 돌려준다."""
    st = metro[metro["year"] == str(year)].groupby("station")[["승차", "무임"]].sum()
    st = st[st["승차"] > 0].join(coords, how="left")
    missing = sorted(st.index[st["lat"].isna()])
    st = st.dropna(subset=["lat"]).copy()
    st["free_ratio"] = st["무임"] / st["승차"]
    return st, missing


def ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """y = a + b x 의 잔차와 기울기 b."""
    X = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta, float(beta[1])


def v6_test(free_ratio: np.ndarray, elderly: np.ndarray, near: np.ndarray, n_perm: int, seed: int) -> dict:
    """시장 근처 역(near)과 그 외 역의 잔차 평균 차이, 단측 순열 p, 시장 보정."""
    resid, slope = ols(free_ratio, elderly)
    diff = resid[near].mean() - resid[~near].mean() if near.any() and (~near).any() else np.nan
    rng = np.random.default_rng(seed)
    perm = np.array([(lambda g: resid[g].mean() - resid[~g].mean())(rng.permutation(near)) for _ in range(n_perm)])
    p = (np.sum(perm >= diff) + 1) / (n_perm + 1) if np.isfinite(diff) else None
    return {"n_stations": int(len(near)), "n_market_stations": int(near.sum()),
            "raw_diff_pp": float((free_ratio[near].mean() - free_ratio[~near].mean()) * 100) if near.any() else None,
            "diff_pp": float(diff * 100), "p_value": float(p) if p is not None else None,
            "slope": slope, "uplift": float(diff / slope) if slope > 0 else None}


def v6(st: pd.DataFrame, markets: gpd.GeoDataFrame, dongs: gpd.GeoDataFrame, cfg: dict, metro: pd.DataFrame,
       coords: pd.DataFrame, n_perm: int, seed: int) -> tuple[dict, dict]:
    crs = cfg["crs_compute"]
    base_stores, base_radius = cfg["big_market_min_stores"], cfg["exposure_radius_m"]
    usable = markets[~markets["excluded"]]

    def prepare(table: pd.DataFrame) -> gpd.GeoDataFrame:
        g = points_gdf(table.reset_index(), "lat", "lon", crs)
        g["elderly"] = radius_elderly_ratio(g, dongs, cfg["metro_radius_m"])
        return g[g["elderly"].notna()].reset_index(drop=True)   # 부산 밖 역(양산 등)은 뺀다

    def run(g: gpd.GeoDataFrame, stores: int, radius: int) -> dict:
        d = nearest_m(g, usable[usable["stores"] >= stores].reset_index(drop=True))
        return v6_test(g["free_ratio"].to_numpy(), g["elderly"].to_numpy(), d <= radius, n_perm, seed)

    g = prepare(st)
    base = run(g, base_stores, base_radius)
    rows = [{"param": "min_stores", "value": str(s), **run(g, s, base_radius)} for s in STORE_THRESHOLDS]
    rows += [{"param": "radius_m", "value": str(r), **run(g, base_stores, r)} for r in MARKET_RADII_M]
    for y in sorted(metro["year"].unique()):
        gy = prepare(station_table(metro, coords, y)[0])
        rows.append({"param": "year", "value": y, **run(gy, base_stores, base_radius)})

    near_names = g.loc[nearest_m(g, usable[usable["stores"] >= base_stores].reset_index(drop=True)) <= base_radius,
                       "station"].tolist()
    drops = [(n,) for n in near_names] + [PAIR_DROP]
    for names in drops:
        gd = g[~g["station"].isin(names)].reset_index(drop=True)
        rows.append({"param": "drop_station", "value": "·".join(names), **run(gd, base_stores, base_radius)})

    drop_uplifts = [r["uplift"] for r in rows if r["param"] == "drop_station" and r["uplift"] is not None]
    result = {k: base[k] for k in ("n_stations", "n_market_stations", "diff_pp", "p_value", "slope", "uplift")}
    result.update({"n_permutations": n_perm, "seed": seed,
                   "uplift_range": [min(drop_uplifts + [base["uplift"]]), max(drop_uplifts + [base["uplift"]])],
                   "sensitivity": [{k: r[k] for k in ("param", "value", "n_market_stations", "diff_pp", "p_value",
                                                      "uplift")} for r in rows]})
    notes = {"near_market_stations": near_names, "sensitivity_full": rows,
             "config_uplift": cfg.get("market_elderly_uplift"), "config_uplift_range": cfg.get("market_elderly_uplift_range")}
    return result, notes


# ---------- V7 ----------
def v7_groups(cw: pd.DataFrame, senior_radius: float, child_radius: float) -> list[dict]:
    """노인보호구역 반경 안 / 어린이보호구역 반경 안(노인 아님) / 둘 다 밖. 노인 쪽이 우선이다."""
    senior = cw["protect_zone_m"] <= senior_radius
    child = (cw["child_zone_m"] <= child_radius) & ~senior
    is07 = cw["formula_class"] == "0.7"
    out = []
    for group, radius, mask in [("senior_zone", senior_radius, senior), ("child_zone", child_radius, child),
                                ("outside", None, ~senior & ~child)]:
        out.append({"group": group, "radius_m": int(radius) if radius is not None else None,
                    "n": int(mask.sum()), "n_formula_07": int((mask & is07).sum())})
    return out


def v7(cw: pd.DataFrame, cfg: dict) -> tuple[dict, dict]:
    senior_r, child_r = cfg["exposure_radius_m"], cfg["child_zone_radius_m"]
    result = {"groups": v7_groups(cw, senior_r, child_r)}
    by_radius = {str(r): v7_groups(cw, senior_r, r) for r in CHILD_RADII_M}
    by_gu = []
    for gu, sub in cw.groupby("sigungu"):
        for g in v7_groups(sub, senior_r, child_r):
            by_gu.append({"sigungu": gu, **g})
    return result, {"child_radius_sensitivity": by_radius, "by_sigungu": by_gu}


# ---------- V3 보강 ----------
def length_bins(length_m: pd.Series, n_bins: int) -> pd.Series:
    """길이 분위수 구간. 같은 값이 많아 구간이 겹치면 줄인다."""
    return pd.qcut(length_m.rank(method="first"), q=n_bins, labels=False)


def stratified_overlap(cw: pd.DataFrame, target: pd.Series, n_perm: int, seed: int, n_bins: int) -> dict:
    """target 횡단보도의 다발지역 겹침 비율을, 같은 (구, 길이 구간)에서 같은 수를 무작위로 뽑은 비율과 비교."""
    cw = cw.assign(_bin=length_bins(cw["length_m"], n_bins), _t=target.to_numpy())
    obs = float(cw.loc[cw["_t"], "in_crash"].mean())
    rng = np.random.default_rng(seed)
    strata = [(int(g["_t"].sum()), g["in_crash"].to_numpy()) for _, g in cw.groupby(["sigungu", "_bin"])]
    strata = [(k, pool) for k, pool in strata if k > 0]
    n_target = sum(k for k, _ in strata)
    rand = np.array([sum(rng.choice(pool, size=k, replace=False).sum() for k, pool in strata) / n_target
                     for _ in range(n_perm)])
    mean_rand = float(rand.mean())
    return {"n_target": int(target.sum()), "n_overlap": int(cw.loc[cw["_t"], "in_crash"].sum()),
            "overlap_ratio": obs, "random_mean": mean_rand,
            "ratio_vs_random": obs / mean_rand if mean_rand > 0 else None,
            "p_value": float((np.sum(rand >= obs) + 1) / (n_perm + 1)), "n_permutations": n_perm, "seed": seed,
            "length_bins": n_bins, "strata_used": len(strata)}


def v3_tier1(cw: gpd.GeoDataFrame, zones: gpd.GeoSeries, years: list[int], zone_pool: pd.Series, n_perm: int,
             seed: int, n_bins: int) -> dict:
    """비교 1: 분석 횡단보도 전체에서 같은 구·길이 구간. 비교 2: 보호구역(노인·어린이) 근처 횡단보도 안에서만.
    보호구역은 원래 번화가에 몰려 있어 다발지역과 겹치기 쉬우므로, 비교 1만 보면 그 효과가 배수에 섞인다."""
    hit = gpd.sjoin(cw[["geometry"]], gpd.GeoDataFrame(geometry=zones), predicate="within", how="left")
    cw = cw.assign(in_crash=hit.groupby(level=0)["index_right"].count().gt(0).reindex(cw.index).to_numpy())
    tier1 = cw["tier"] == 1
    not07 = tier1 & (cw["formula_class"] != "0.7")
    pool = zone_pool.to_numpy() | tier1.to_numpy()
    sub = cw[pool].reset_index(drop=True)
    return {"years": years, "n_zones": int(len(zones)), "n_analyzed": int(len(cw)),
            "overlap_all": float(cw["in_crash"].mean()),
            "tier1_not_07": stratified_overlap(cw, not07, n_perm, seed, n_bins),
            "tier1_not_07_within_zones": {"n_pool": int(pool.sum()),
                                          **stratified_overlap(sub, not07[pool].reset_index(drop=True), n_perm, seed,
                                                               n_bins)},
            "tier1_07": {"n": int((tier1 & ~not07).sum()),
                         "overlap_ratio": float(cw.loc[tier1 & ~not07, "in_crash"].mean()) if (tier1 & ~not07).any()
                         else None}}


# ---------- 출력 ----------
def check_schema(contracts: Path, data: dict) -> None:
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in contracts.glob("*.schema.json")}
    reg = Registry().with_resources((n, Resource.from_contents(s)) for n, s in schemas.items())
    Draft202012Validator(schemas["validation.schema.json"], registry=reg).validate(data)


def rounded(x, digits=4):
    """JSON 에 쓸 값: 실수는 자릿수를 줄이고 NaN·inf 는 null."""
    if isinstance(x, dict):
        return {k: rounded(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v, digits) for v in x]
    if isinstance(x, (float, np.floating)):
        return round(float(x), digits) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    return x


def run(a: argparse.Namespace) -> dict:
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    crs = cfg["crs_compute"]
    n_perm = a.n_perm or cfg["permutations"]
    seed = a.seed if a.seed is not None else cfg["seed"]
    y0, y1 = cfg["crash_validation_years"]
    years = list(range(y0, y1 + 1))

    dongs = read_dongs(a.raw, crs)
    metro, coords = read_metro(a.raw), read_station_coords(a.raw)
    st, missing = station_table(metro, coords, cfg["metro_year"])
    markets = read_markets(a.raw, cfg["market_exclude_keywords"], crs)
    r6, n6 = v6(st, markets, dongs, cfg, metro, coords, n_perm, seed)
    n6["stations_without_coords"] = missing

    cw = read_points_v2(a.points_v2, crs)
    cw["child_zone_m"] = nearest_m(cw, read_child_zones(a.raw, crs))
    cw["sigungu"] = sigungu_of(cw["adm_cd"], dongs)
    r7, n7 = v7(cw, cfg)
    near_zone = (cw["protect_zone_m"] <= cfg["exposure_radius_m"]) | (cw["child_zone_m"] <= cfg["child_zone_radius_m"])
    r3 = v3_tier1(cw, read_crash_zones(a.crash_dir, years, crs), years, near_zone, n_perm, seed, a.length_bins)

    out = a.out
    doc = json.loads(out.read_text(encoding="utf-8")) if out.exists() else \
        {"v1": None, "v2": None, "v3": None, "v4": None, "v5": None}
    doc["v6"] = rounded({k: r6[k] for k in ("n_stations", "n_market_stations", "diff_pp", "p_value", "n_permutations",
                                            "seed", "slope", "uplift", "uplift_range", "sensitivity")})
    doc["v7"] = r7
    check_schema(a.contracts, doc)   # 스키마를 통과하지 못하면 파일을 쓰지 않는다
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    notes = rounded({"params": {"points_v2": str(a.points_v2), "target": a.target, "n_permutations": n_perm,
                                "seed": seed, "crash_years": years, "length_bins": a.length_bins,
                                "metro_year": cfg["metro_year"], "metro_radius_m": cfg["metro_radius_m"]},
                     "v6": n6, "v7": n7, "v3_tier1": r3,
                     "limits": ["무임에는 경로 외 장애인·국가유공자가 포함된다", "역 근처만 본다",
                                "연관성이며 인과가 아니다", "보행시간 = 녹색 + 점멸 가정(정의 미확정)"]})
    a.notes.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"v6": doc["v6"], "v7": r7, "v3_tier1": notes["v3_tier1"]}


def report(res: dict) -> None:
    v6r, v7r, v3r = res["v6"], res["v7"], res["v3_tier1"]
    print(f"V6  역 {v6r['n_stations']}곳, 대형 시장 근처 {v6r['n_market_stations']}곳: 고령 비율 감안 차이 "
          f"{v6r['diff_pp']:+.2f}%p, p={v6r['p_value']}, 기울기 {v6r['slope']:.3f} → 보정 {v6r['uplift']:.3f} "
          f"(범위 {v6r['uplift_range'][0]:.3f}~{v6r['uplift_range'][1]:.3f})")
    for r in v6r["sensitivity"]:
        u = "-" if r["uplift"] is None else f"{r['uplift']:.3f}"
        print(f"    {r['param']:<13}{r['value']:<8} 근처 {r['n_market_stations']:>2}  차이 {r['diff_pp']:+6.2f}%p  "
              f"p={r['p_value']}  보정 {u}")
    for g in v7r["groups"]:
        print(f"V7  {g['group']:<12} 반경 {g['radius_m']}  {g['n_formula_07']}/{g['n']} = "
              f"{g['n_formula_07'] / g['n']:.1%}" if g["n"] else f"V7  {g['group']} 0곳")
    for key, label in [("tier1_not_07", "비교 1 전체"), ("tier1_not_07_within_zones", "비교 2 보호구역 근처")]:
        t = v3r[key]
        print(f"V3+ {label}: 1단계 중 0.7식 아님 {t['n_target']}곳, 다발지역 안 {t['n_overlap']}곳 "
              f"({t['overlap_ratio']:.1%}), 무작위 평균 {t['random_mean']:.1%}, {t['ratio_vs_random']:.2f}배, "
              f"p={t['p_value']} (반복 {t['n_permutations']}, 시드 {t['seed']})")
    print(f"V3+ 참고: 1단계 중 0.7식 {v3r['tier1_07']['n']}곳 겹침 {v3r['tier1_07']['overlap_ratio']:.1%}, "
          f"분석 전체 {v3r['overlap_all']:.1%}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points-v2", type=Path, default=Path("data/interim/bundle/points_v2/0.85_300.json"),
                    help="D12 v2 점 묶음 (contracts points.schema.json, target 포함)")
    ap.add_argument("--target", type=float, default=0.85, help="points_v2 의 목표 커버리지(기록용)")
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--crash-dir", type=Path, default=Path("data/raw/crash_zone"),
                    help="R4 연도별 JSON 폴더 (crash_zone_<연도>.json)")
    ap.add_argument("--contracts", type=Path, default=Path("contracts"))
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, default=Path("data/interim/bundle/validation.json"))
    ap.add_argument("--notes", type=Path, default=Path("data/interim/v2_validation_notes.json"))
    ap.add_argument("--n-perm", type=int, default=None, help="기본: config permutations")
    ap.add_argument("--seed", type=int, default=None, help="기본: config seed")
    ap.add_argument("--length-bins", type=int, default=4, help="V3 보강 무작위 비교의 길이 구간 수 (분위수)")
    a = ap.parse_args(argv)
    report(run(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
