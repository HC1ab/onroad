"""부산 검증 V2·V3·V4 → validation.json (이슈: 부산 검증 V2·V3·V4).

입력은 pipeline 이 만든 결과 묶음(contracts 형식)뿐이다. 구역 사이 접점은 contracts 이기 때문이다.
V1(현장 실측)과 V5(보정 연관성)는 이번 범위에서 제외해 null 로 둔다.

원칙
    - 결과가 기대와 달라도 그대로 보고한다. 연관성까지만 말하고 인과 표현을 쓰지 않는다.
    - 사고다발지역은 후보 선정에 쓰지 않았다. V3 에서만 2021~2025년(config.yaml crash_validation_years)
      부산 다발지역 전체를 쓴다.
    - 무작위 비교는 시드를 고정해 같은 입력이면 같은 결과가 나온다.
    - "gap>0 비율, 정의 미확정": 보행시간 정의(녹색 + 점멸)는 확정 전 가정이다.

V2  속도 쌍(0.7·0.8, 0.7·1.0, 0.8·1.0)별 읍면동 짧음 비율 순위의 Spearman 상관과 상위 N 중복 수.
V3  후보 횡단보도가 다발지역 안에 있는 비율을, 같은 구·같은 길이 구간에서 무작위로 뽑은 횡단보도의
    비율과 비교한다 (permutation). 겹침이 높아도 인과가 아니다(보행량·도로 규모 등 미통제).
V4  (a) 읍면동 짧음 비율과 65세 이상 비율의 Spearman, 구·군별 (b) 시설 반경 안과 밖의 짧음 비율.
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from scipy.stats import spearmanr
from shapely.geometry import shape

FACILITIES = ("senior_center", "market", "protect_zone")


def tag(speed: float, radius: int) -> str:
    return f"{speed:.1f}_{radius}"


# ---------- 입력 ----------
def read_areas(bundle: Path, speed: float, radius: int) -> pd.DataFrame:
    d = json.loads((bundle / tag(speed, radius) / "areas.json").read_text(encoding="utf-8"))
    return pd.DataFrame(d["items"])


def read_crosswalks(bundle: Path, speed: float, radius: int) -> pd.DataFrame:
    """한 (속도, 반경)의 모든 횡단보도를 한 표로. 플래그는 열로 펼친다."""
    rows = []
    for p in sorted((bundle / tag(speed, radius) / "crosswalks").glob("*/area_crosswalks.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for it in d["items"]:
            rows.append({**{k: v for k, v in it.items() if k != "flags"}, **it["flags"], "adm_cd": d["adm_cd"]})
    return pd.DataFrame(rows)


def read_crash_zones(crash_dir: Path, years: list[int], sido_prefix: str, crs_compute: str) -> gpd.GeoSeries:
    """R4 연도별 JSON 에서 해당 시도의 다발지역 폴리곤을 모아 미터 좌표계로 돌려준다."""
    geoms = []
    for y in years:
        for z in json.loads((crash_dir / f"crash_zone_{y}.json").read_text(encoding="utf-8")):
            if str(z["sido_sgg_nm"]).startswith(sido_prefix):
                geoms.append(shape(json.loads(z["geom_json"])))
    return gpd.GeoSeries(geoms, crs="EPSG:4326").to_crs(crs_compute)


# ---------- V2 ----------
def top_set(areas: pd.DataFrame, n: int) -> set[str]:
    """짧음 비율이 큰 순서로 상위 n 개 동. 동점이면 분석 횡단보도가 많은 동, 그래도 같으면 코드 순."""
    ok = areas[~areas["low_sample"] & areas["short_ratio"].notna()]
    ranked = ok.sort_values(["short_ratio", "n_analyzed", "adm_cd"], ascending=[False, False, True])
    return set(ranked["adm_cd"].head(n))


def v2(areas_by_speed: dict[float, pd.DataFrame], top_n: int) -> dict:
    pairs = []
    for a, b in combinations(sorted(areas_by_speed), 2):
        m = areas_by_speed[a].merge(areas_by_speed[b], on="adm_cd", suffixes=("_a", "_b"))
        m = m[~m["low_sample_a"] & ~m["low_sample_b"] & m["short_ratio_a"].notna() & m["short_ratio_b"].notna()]
        rho = float(spearmanr(m["short_ratio_a"], m["short_ratio_b"]).statistic)
        if np.isnan(rho):
            raise ValueError(f"속도 {a}·{b}: 순위 상관을 정의할 수 없다 (한쪽이 상수)")
        pairs.append({"a": a, "b": b, "spearman": round(rho, 3),
                      "top_n_overlap": len(top_set(areas_by_speed[a], top_n) & top_set(areas_by_speed[b], top_n))})
    return {"top_n": top_n, "pairs": pairs}


# ---------- V3 ----------
def length_bins(length_m: pd.Series, n_bins: int) -> pd.Series:
    """연장을 분위수 기준 n 개 구간으로 나눈다 (같은 부산 분포 안에서). 동점이 많으면 구간 수가 줄 수 있다."""
    return pd.qcut(length_m, q=n_bins, labels=False, duplicates="drop")


def v3(cw: pd.DataFrame, sigungu_of: dict[str, str], zones: gpd.GeoSeries, speed: float, years: list[int],
       n_perm: int, seed: int, n_bins: int, crs_compute: str) -> tuple[dict, dict]:
    pts = gpd.GeoSeries(gpd.points_from_xy(cw["lon"], cw["lat"]), crs="EPSG:4326").to_crs(crs_compute)
    in_zone = pts.within(zones.union_all()).to_numpy()  # 다발지역 폴리곤 안에 있는가
    cand = cw["is_candidate"].to_numpy()
    if not cand.any():
        raise ValueError("후보가 없어 V3 를 계산할 수 없다")
    observed = float(in_zone[cand].mean())

    strata = cw["adm_cd"].map(sigungu_of).astype(str) + "|" + length_bins(cw["length_m"], n_bins).astype(str)
    rng = np.random.default_rng(seed)
    pools, ks = [], []
    for _, idx in pd.Series(np.arange(len(cw))).groupby(strata.to_numpy()):
        i = idx.to_numpy()
        k = int(cand[i].sum())
        if k:
            pools.append(in_zone[i]); ks.append(k)
    rand = np.empty(n_perm)
    for p in range(n_perm):
        hit = 0
        for pool, k in zip(pools, ks):  # 후보 수만큼 같은 구·같은 길이 구간에서 비복원 추출
            hit += int(pool[rng.choice(len(pool), size=k, replace=False)].sum())
        rand[p] = hit / cand.sum()
    mean_rand = float(rand.mean())
    if mean_rand == 0:
        raise ValueError("무작위 겹침 비율의 평균이 0 이라 배수를 정의할 수 없다")
    out = {"speed": speed, "recent_years": years, "overlap_ratio": round(observed, 4),
           "ratio_vs_random": round(observed / mean_rand, 3),
           "p_value": round(float((1 + (rand >= observed).sum()) / (n_perm + 1)), 4),
           "n_permutations": n_perm, "random_distribution": [round(float(x), 4) for x in rand]}
    notes = {"candidates": int(cand.sum()), "candidates_in_zone": int(in_zone[cand].sum()),
             "all_crosswalks": int(len(cw)), "all_in_zone_ratio": round(float(in_zone.mean()), 4),
             "strata_used": len(pools), "random_mean": round(mean_rand, 4), "seed": seed, "length_bins": n_bins,
             "zones": int(len(zones))}
    return out, notes


# ---------- V4 ----------
def v4(areas: pd.DataFrame, cw: pd.DataFrame, speed: float, min_group: int) -> tuple[dict, dict]:
    ok = areas[~areas["low_sample"] & areas["short_ratio"].notna() & areas["ratio_65plus"].notna()]
    rho = float(spearmanr(ok["short_ratio"], ok["ratio_65plus"]).statistic)
    groups, skipped = [], []
    for name, g in ok.groupby("sigungu"):
        if len(g) < min_group:
            skipped.append(name); continue
        r = spearmanr(g["short_ratio"], g["ratio_65plus"]).statistic
        if not np.isnan(r):
            groups.append({"group": name, "spearman": round(float(r), 3), "n": int(len(g))})
    short = cw["gap_s"] > 0
    inout = []
    for f in FACILITIES:
        inout.append({"facility": f, "inside_short_ratio": round(float(short[cw[f]].mean()), 4),
                      "outside_short_ratio": round(float(short[~cw[f]].mean()), 4)})
    notes = {"dongs_used": int(len(ok)), "groups_skipped_for_small_n": skipped,
             "inside_n": {f: int(cw[f].sum()) for f in FACILITIES},
             "outside_n": {f: int((~cw[f]).sum()) for f in FACILITIES}}
    return {"speed": speed, "spearman": round(rho, 3), "by_group": groups, "inside_outside": inout}, notes


def formula_split(cw: pd.DataFrame, judged: pd.DataFrame) -> list[dict]:
    """시설 반경 안과 밖에서 보행시간이 0.7m/s 기준식 값인 횡단보도의 비율 (이미 조정됐나 보조 확인)."""
    m = cw.merge(judged[["cw_id", "formula_class"]], on="cw_id", how="left")
    is07 = m["formula_class"] == "v0.7"
    return [{"facility": f, "inside_v0.7_formula_ratio": round(float(is07[m[f]].mean()), 4),
             "outside_v0.7_formula_ratio": round(float(is07[~m[f]].mean()), 4)} for f in FACILITIES]


# ---------- 실행 ----------
def check_schema(contracts: Path, data: dict) -> None:
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in contracts.glob("*.schema.json")}
    reg = Registry().with_resources((n, Resource.from_contents(s)) for n, s in schemas.items())
    Draft202012Validator(schemas["validation.schema.json"], registry=reg).validate(data)


def run(a: argparse.Namespace) -> dict:
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    y0, y1 = cfg["crash_validation_years"]
    years = list(range(y0, y1 + 1))
    speeds = list(cfg["speeds_mps"])
    radius = cfg["exposure_radius_m"]

    areas = {v: read_areas(a.bundle, v, radius) for v in speeds}
    cw = read_crosswalks(a.bundle, a.speed, radius)
    zones = read_crash_zones(a.crash_dir, years, a.crash_sido, cfg["crs_compute"])
    sigungu_of = dict(zip(areas[a.speed]["adm_cd"], areas[a.speed]["sigungu"]))

    r2 = v2(areas, a.top_n)
    r3, n3 = v3(cw, sigungu_of, zones, a.speed, years, a.n_perm, a.seed, a.length_bins, cfg["crs_compute"])
    r4, n4 = v4(areas[a.speed], cw, a.speed, cfg["min_sample"])
    doc = {"v1": None, "v2": r2, "v3": r3, "v4": r4, "v5": None}
    check_schema(a.contracts, doc)  # 스키마를 통과하지 못하면 파일을 쓰지 않는다

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    notes = {"params": {"speed": a.speed, "radius_m": radius, "top_n": a.top_n, "n_permutations": a.n_perm,
                        "seed": a.seed, "length_bins": a.length_bins, "crash_years": years},
             "v3": n3, "v4": n4,
             # 결과를 읽을 때 함께 적어야 하는 한계 (R5: 연관성까지만 말한다)
             "caveats": [
                 "후보는 노출 플래그(시설 반경)에 의존한다. 0.7m/s 에서는 대부분의 횡단보도가 gap>0 이라 후보가 곧 "
                 "시설 가까이 있는 횡단보도에 가깝다. V3 의 겹침 차이는 시설 위치(도심·생활권)와 구분되지 않는다.",
                 "무작위 비교는 같은 구·같은 길이 구간만 맞춘다. 보행량·도로 규모는 통제하지 않았다.",
                 "보행시간의 정의(녹색 + 점멸)가 확정 전이라 모든 짧음 비율은 gap>0 비율, 정의 미확정이다.",
             ]}
    if a.judged and a.judged.exists():
        notes["v4_formula_split"] = formula_split(cw, pd.read_csv(a.judged))
    a.notes.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[V2] 상위 {a.top_n} 기준"); print(pd.DataFrame(r2["pairs"]).to_string(index=False))
    print(f"\n[V3] 속도 {a.speed}, 반경 {radius}m, 다발지역 {years[0]}~{years[-1]}년 {n3['zones']}곳")
    print(f"  후보 {n3['candidates']}곳 중 다발지역 안 {n3['candidates_in_zone']}곳 (겹침 {r3['overlap_ratio']:.1%})")
    print(f"  전체 횡단보도 중 다발지역 안 {n3['all_in_zone_ratio']:.1%}, 무작위 평균 {n3['random_mean']:.1%}")
    print(f"  무작위 대비 {r3['ratio_vs_random']}배, p={r3['p_value']} (반복 {a.n_perm}, 시드 {a.seed})")
    print(f"\n[V4] 속도 {a.speed}: 읍면동 짧음 비율 × 65세 이상 비율 Spearman {r4['spearman']} (동 {n4['dongs_used']}개)")
    print(pd.DataFrame(r4["by_group"]).to_string(index=False))
    print(pd.DataFrame(r4["inside_outside"]).to_string(index=False))
    if "v4_formula_split" in notes:
        print("\n[V4 보조] 0.7m/s 기준식 값인 횡단보도 비율"); print(pd.DataFrame(notes["v4_formula_split"]).to_string(index=False))
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", type=Path, default=Path("data/interim/bundle"))
    ap.add_argument("--crash-dir", type=Path, required=True, help="R4 연도별 JSON 폴더 (crash_zone_<연도>.json)")
    ap.add_argument("--judged", type=Path, default=Path("data/interim/busan_f3_judged.csv"), help="V4 보조 표용(없어도 됨)")
    ap.add_argument("--contracts", type=Path, default=Path("contracts"))
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, default=None, help="기본: <bundle>/validation.json")
    ap.add_argument("--notes", type=Path, default=None, help="계산 조건·보조 수치. 기본: <bundle>/../busan_validation_notes.json")
    ap.add_argument("--speed", type=float, default=0.7, help="V3·V4 에 쓰는 속도. 0.7 = 노인 기준")
    ap.add_argument("--top-n", type=int, default=20, help="V2 상위 N (config 에 없는 계산 조건)")
    ap.add_argument("--n-perm", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--length-bins", type=int, default=4, help="V3 무작위 비교의 길이 구간 수 (분위수)")
    ap.add_argument("--crash-sido", default="부산")
    a = ap.parse_args(argv)
    a.out = a.out or a.bundle / "validation.json"
    a.notes = a.notes or a.bundle.parent / "busan_validation_notes.json"
    run(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
