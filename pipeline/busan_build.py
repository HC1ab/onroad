"""부산 F3~F4 빌드: 판정 + 노출 플래그 + 읍면동 집계 → contracts 스키마를 통과하는 결과 묶음.

입력  data/interim/busan_f2_assigned.csv (busan_clean.py 결과), busan_meta.json, R3, O1·O2·O3, R2
출력  <bundle>/meta.json
      <bundle>/<speed>_<radius>/areas.json, candidates.json, crosswalks/<adm_cd>/area_crosswalks.json
      <bundle>/../web/boundaries.json (지도용 단순화 경계)
      data/interim/busan_f3_judged.csv, busan_f4_tables.json (건수표)

규칙
    - 후보 = 그 속도에서 gap>0 이고 노출 플래그 1개 이상 (contracts 의 is_candidate 정의와 같다).
    - 노출 플래그 3종: protect_zone, market, senior_center(밀집). 사고다발지역은 쓰지 않는다 (검증 V3 전용).
    - 사분면: 짧음 비율·65세 이상 비율이 각각 부산 중앙값보다 '큰' 쪽이 high. 같으면 low.
    - 표본이 min_sample 미만인 동은 low_sample=true, quadrant=null (회색, 순위 제외).
    - validation.json 은 validation/ 구역이 같은 묶음 폴더에 만든다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

sys.path.insert(0, str(Path(__file__).resolve().parent))
import busan_facilities as fac  # noqa: E402
import busan_judge as jd  # noqa: E402

RADII = (200, 300, 500)  # contracts 의 radius_m enum. config 의 exposure_radius_m·sensitivity 와 같아야 한다.
FLAG_NAMES = ("senior_center", "market", "protect_zone")
KST = timezone(timedelta(hours=9))


# ---------- 설정·입력 ----------
def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    need = ["entry_seconds", "speeds_mps", "min_sample", "exposure_radius_m",
            "exposure_radius_sensitivity_m", "crs_storage", "crs_compute", "senior_center_density_quantile"]
    miss = [k for k in need if k not in cfg]
    if miss:
        raise KeyError(f"config.yaml 에 없는 키: {miss}")
    radii = tuple(sorted({cfg["exposure_radius_m"], *cfg["exposure_radius_sensitivity_m"]}))
    if radii != RADII:
        raise ValueError(f"config 의 반경 {radii} 이 contracts 의 {RADII} 와 다르다")
    return cfg


def load_population(path: Path) -> tuple[pd.DataFrame, str]:
    """R3: 읍면동별 총인구·65세 이상. 코드는 이름 뒤 괄호 10자리. 월(ref_month)도 열 이름에서 읽는다."""
    df = pd.read_csv(path, encoding="cp949", dtype=str)
    name_col = df.columns[0]
    total_col = next(c for c in df.columns if c.endswith("_전체"))
    old_col = next(c for c in df.columns if c.endswith("_65세이상전체"))
    m = re.match(r"(\d{4})년(\d{2})월", total_col)
    ref_month = f"{m.group(1)}-{m.group(2)}" if m else ""
    code = df[name_col].str.extract(r"\((\d{10})\)")[0]
    num = lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce")  # noqa: E731
    out = pd.DataFrame({"adm_cd": code, "pop_total": num(df[total_col]), "pop_65": num(df[old_col])})
    out = out.dropna(subset=["adm_cd"]).drop_duplicates("adm_cd")
    out["ratio_65plus"] = out["pop_65"] / out["pop_total"]
    return out.reset_index(drop=True), ref_month


def load_dongs(boundary: Path, sido_prefix: str, cfg: dict) -> gpd.GeoDataFrame:
    g = gpd.read_file(boundary)
    g["adm_cd2"] = g["adm_cd2"].astype(str)
    g = g[g["adm_cd2"].str.startswith(sido_prefix)].copy()
    if g.crs is None:
        g = g.set_crs(cfg["crs_storage"])
    g = g.to_crs(cfg["crs_storage"])
    g["adm_name"] = g["adm_nm"].str.split().str[-1]
    return g.reset_index(drop=True)


# ---------- 계산 ----------
def attach_flags(cw: pd.DataFrame, facs: dict, cfg: dict) -> tuple[dict, dict]:
    """반경별 플래그 표(DataFrame)와 밀집 기준을 돌려준다. 순서는 cw 와 같다."""
    pts = gpd.GeoSeries(gpd.points_from_xy(cw["lon"], cw["lat"]), crs=cfg["crs_storage"]).to_crs(cfg["crs_compute"])
    xy = np.column_stack([pts.x, pts.y])
    flags, thr = {}, {}
    for r in RADII:
        flags[r], thr[r] = fac.flags_for(xy, facs, r, cfg["senior_center_density_quantile"])
    return flags, thr


def area_rows(cw: pd.DataFrame, flags: pd.DataFrame, speed: float, cfg: dict) -> pd.DataFrame:
    """한 (속도, 반경) 조합의 횡단보도별 값. gap, 후보 여부, 노출 개수를 붙인다."""
    k = jd.speed_key(speed)
    d = cw[["cw_id", "adm_cd2", "lat", "lon", "length_m", "green_s"]].copy()
    d["t_need_s"] = cw[f"t_need_{k}"]
    d["gap_s"] = cw[f"gap_{k}"]
    for f in FLAG_NAMES:
        d[f] = flags[f].to_numpy()
    d["exposure_cnt"] = d[list(FLAG_NAMES)].sum(axis=1).astype(int)
    d["short"] = jd.is_short(d["gap_s"])
    d["is_candidate"] = d["short"] & (d["exposure_cnt"] >= 1)
    return d


def build_area_items(rows: pd.DataFrame, dongs: gpd.GeoDataFrame, pop: pd.DataFrame, min_sample: int
                     ) -> tuple[list[dict], dict]:
    """동별 집계. 횡단보도가 없는 동도 포함한다(회색)."""
    g = rows.groupby("adm_cd2")
    stat = pd.DataFrame({
        "n_analyzed": g.size(),
        "n_short": g["short"].sum().astype(int),
        "n_candidate": g["is_candidate"].sum().astype(int),
        "mean_gap_s": rows[rows["short"]].groupby("adm_cd2")["gap_s"].mean(),
    })
    base = dongs[["adm_cd2", "adm_name", "sidonm", "sggnm"]].rename(columns={"sidonm": "sido", "sggnm": "sigungu"})
    t = base.merge(stat, left_on="adm_cd2", right_index=True, how="left") \
            .merge(pop[["adm_cd", "ratio_65plus"]], left_on="adm_cd2", right_on="adm_cd", how="left")
    for c in ("n_analyzed", "n_short", "n_candidate"):
        t[c] = t[c].fillna(0).astype(int)
    t["short_ratio"] = np.where(t["n_analyzed"] > 0, t["n_short"] / t["n_analyzed"].where(t["n_analyzed"] > 0), np.nan)
    t["low_sample"] = t["n_analyzed"] < min_sample

    # 사분면 경계: 표본이 충분하고 두 값이 모두 있는 동의 중앙값
    ok = ~t["low_sample"] & t["short_ratio"].notna() & t["ratio_65plus"].notna()
    med = {"short_ratio_median": float(t.loc[ok, "short_ratio"].median()) if ok.any() else 0.0,
           "ratio_65plus_median": float(t.loc[ok, "ratio_65plus"].median()) if ok.any() else 0.0}

    def quad(r):
        if not (r.name in t.index[ok]):
            return None
        hi_s = r["short_ratio"] > med["short_ratio_median"]
        hi_o = r["ratio_65plus"] > med["ratio_65plus_median"]
        return f"{'high' if hi_s else 'low'}_{'high' if hi_o else 'low'}"

    # None 이 NaN 으로 바뀌지 않도록 object 열로 만든다 (스키마는 null 만 허용)
    t["quadrant"] = pd.Series([quad(r) for _, r in t.iterrows()], index=t.index, dtype=object)
    nn = lambda x: None if pd.isna(x) else x  # noqa: E731
    items = []
    for _, r in t.sort_values("adm_cd2").iterrows():
        items.append({
            "adm_cd": r["adm_cd2"], "adm_name": r["adm_name"], "sido": r["sido"], "sigungu": r["sigungu"],
            "n_analyzed": int(r["n_analyzed"]), "n_short": int(r["n_short"]),
            "short_ratio": None if pd.isna(r["short_ratio"]) else round(float(r["short_ratio"]), 4),
            "mean_gap_s": None if pd.isna(r["mean_gap_s"]) else round(float(r["mean_gap_s"]), 2),
            "ratio_65plus": None if pd.isna(nn(r["ratio_65plus"])) else round(float(r["ratio_65plus"]), 4),
            "quadrant": None if pd.isna(r["quadrant"]) else r["quadrant"], "n_candidate": int(r["n_candidate"]), "low_sample": bool(r["low_sample"]),
        })
    return items, {k: round(v, 4) for k, v in med.items()}


def crosswalk_items(rows: pd.DataFrame) -> list[dict]:
    """한 동의 횡단보도 목록. gap_s 내림차순(스키마의 기본 정렬)."""
    out = []
    for _, r in rows.sort_values(["gap_s", "cw_id"], ascending=[False, True]).iterrows():
        out.append({
            "cw_id": r["cw_id"], "lat": round(float(r["lat"]), 6), "lon": round(float(r["lon"]), 6),
            "length_m": round(float(r["length_m"]), 2), "green_s": round(float(r["green_s"]), 4),
            "t_need_s": round(float(r["t_need_s"]), 2), "gap_s": round(float(r["gap_s"]), 2),
            "flags": {"senior_center": bool(r["senior_center"]), "market": bool(r["market"]),
                      "protect_zone": bool(r["protect_zone"]), "hospital": None},
            "exposure_cnt": int(r["exposure_cnt"]), "is_candidate": bool(r["is_candidate"]),
        })
    return out


def candidate_doc(rows: pd.DataFrame, speed: float, radius: int) -> dict:
    feats = []
    for _, r in rows[rows["is_candidate"]].sort_values("cw_id").iterrows():
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(float(r["lon"]), 6), round(float(r["lat"]), 6)]},
                      "properties": {"cw_id": r["cw_id"], "adm_cd": r["adm_cd2"],
                                     "gap_s": round(float(r["gap_s"]), 2), "exposure_cnt": int(r["exposure_cnt"])}})
    return {"type": "FeatureCollection", "speed": speed, "radius_m": radius, "features": feats}


def meta_doc(ref_month: str, input_rows: int, assigned: int, sources: list[dict], built_at: str) -> dict:
    return {
        "ref_month": ref_month, "built_at": built_at,
        "coverage_ratio": round(assigned / input_rows, 4),  # 분석 가능(동 배정까지 된) 횡단보도 / 엑셀 전체
        "green_def_status": "unconfirmed",
        "sources": sources,
        "limits_text": '한계: 부산 한정 · 보행시간(녹색 + 점멸로 가정) 정의 확정 전 · 읍면동 평균은 개별 이용자 구성이 아님 · 인과 미검증 · "점검 우선순위 후보"이며 위험·위반 판정이 아님',
    }


def simplify_boundaries(dongs: gpd.GeoDataFrame, tolerance_m: float, cfg: dict) -> dict:
    """지도용 단순화 경계. 미터 좌표계에서 단순화한 뒤 위·경도로 돌려 소수 5자리로 줄인다."""
    g = dongs.to_crs(cfg["crs_compute"]).copy()
    g["geometry"] = g.geometry.simplify(tolerance_m, preserve_topology=True)
    g = g.to_crs(cfg["crs_storage"])
    feats = []
    for _, r in g.sort_values("adm_cd2").iterrows():
        geo = json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"]
        feats.append({"type": "Feature", "geometry": _round_coords(geo),
                      "properties": {"adm_cd": r["adm_cd2"], "adm_name": r["adm_name"],
                                     "sido": r["sidonm"], "sigungu": r["sggnm"]}})
    return {"type": "FeatureCollection", "features": feats}


def _round_coords(geo: dict) -> dict:
    def rnd(c):
        return [round(c[0], 5), round(c[1], 5)] if isinstance(c[0], (int, float)) else [rnd(x) for x in c]
    return {"type": geo["type"], "coordinates": rnd(geo["coordinates"])}


# ---------- 검증·저장 ----------
class SchemaCheck:
    """contracts/*.schema.json 으로 문서를 검사한다 (check_samples.py 와 같은 방식)."""

    def __init__(self, contracts: Path):
        self.schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in contracts.glob("*.schema.json")}
        self.registry = Registry().with_resources((n, Resource.from_contents(s)) for n, s in self.schemas.items())

    def check(self, kind: str, data: dict) -> None:
        Draft202012Validator(self.schemas[f"{kind}.schema.json"], registry=self.registry).validate(data)


def write_json(path: Path, data: dict, check: SchemaCheck | None = None, kind: str | None = None) -> None:
    if check and kind:
        check.check(kind, data)  # 스키마를 통과하지 못하면 파일을 쓰지 않고 예외가 난다
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def run(a: argparse.Namespace) -> dict:
    cfg = load_config(a.config)
    cw = pd.read_csv(a.assigned, dtype={"adm_cd2": str})
    f2 = json.loads((a.assigned.parent / "busan_meta.json").read_text(encoding="utf-8"))
    dongs = load_dongs(a.boundary, a.sido_prefix, cfg)
    pop, ref_month = load_population(a.population)

    judged = jd.judge(cw, cfg)
    judged.to_csv(a.out / "busan_f3_judged.csv", index=False, encoding="utf-8-sig")

    facs = {"protect_zone": fac.load_protect_zone(a.protect_zone, cfg),
            "market": fac.load_market(a.market, cfg),
            "senior_center": fac.load_senior_center(a.senior_center, cfg)}
    flags, thr = attach_flags(judged, facs, cfg)

    check = SchemaCheck(a.contracts)
    bundle = a.bundle
    n_docs = 0
    short_by_speed = {}
    for v in cfg["speeds_mps"]:
        for r in RADII:
            rows = area_rows(judged, flags[r], v, cfg)
            tag = f"{jd.speed_key(v)}_{r}"
            items, med = build_area_items(rows, dongs, pop, cfg["min_sample"])
            write_json(bundle / tag / "areas.json",
                       {"speed": v, "radius_m": r, "thresholds": med, "items": items}, check, "areas")
            write_json(bundle / tag / "candidates.json", candidate_doc(rows, v, r), check, "candidates")
            n_docs += 2
            for adm, g in rows.groupby("adm_cd2"):
                write_json(bundle / tag / "crosswalks" / adm / "area_crosswalks.json",
                           {"adm_cd": adm, "speed": v, "radius_m": r, "items": crosswalk_items(g)},
                           check, "area_crosswalks")
                n_docs += 1
            short_by_speed[tag] = {"n_short": int(rows["short"].sum()), "n_candidate": int(rows["is_candidate"].sum()),
                                   "n_low_sample_dongs": sum(i["low_sample"] for i in items), "thresholds": med}

    built_at = a.built_at or datetime.now(KST).isoformat(timespec="seconds")
    sources = json.loads(a.sources.read_text(encoding="utf-8")) if a.sources else []
    write_json(bundle / "meta.json", meta_doc(ref_month, f2["f1"]["input_rows"], len(cw), sources, built_at), check, "meta")
    write_json(a.web_out / "boundaries.json", simplify_boundaries(dongs, a.simplify_m, cfg), check, "boundaries")

    # 건수표: 플래그별 해당 건수, 시설 좌표 결측 건수, R3 코드 일치율
    n = len(judged)
    flag_rows = []
    for r in RADII:
        for name in FLAG_NAMES:
            flag_rows.append({"반경(m)": r, "플래그": name, "해당 횡단보도": int(flags[r][name].sum()),
                              "비율(%)": round(float(flags[r][name].mean() * 100), 2)})
    fac_rows = [{"시설": f.name, "전체 행": f.total_rows, "조건에 맞는 행": f.kept_rows,
                 "좌표 없음·범위 밖": f.bad_coord_rows, "사용한 시설 수": int(len(f.xy))} for f in facs.values()]
    pop_codes = set(pop["adm_cd"])
    dong_codes = set(dongs["adm_cd2"])
    unmatched_codes = sorted(dong_codes - pop_codes)
    pd.DataFrame({"adm_cd2": unmatched_codes}).to_csv(a.out / "busan_f4_population_unmatched.csv", index=False)
    tables = {
        "formula": jd.formula_table(judged, cfg).to_dict("records"),
        "flags": flag_rows, "facilities": fac_rows,
        "senior_center_threshold": {str(r): thr[r] for r in RADII},
        "r3_code_match": {"dongs": len(dong_codes), "matched": len(dong_codes & pop_codes),
                          "rate_pct": round(len(dong_codes & pop_codes) / len(dong_codes) * 100, 2)},
        "combos": short_by_speed, "ref_month": ref_month, "documents": n_docs, "crosswalks": n,
    }
    (a.out / "busan_f4_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[F3] 기준식 분류와 gap>0 건수 (정의 미확정)"); print(pd.DataFrame(tables["formula"]).to_string(index=False))
    print("\n[F4] 노출 플래그"); print(pd.DataFrame(flag_rows).to_string(index=False))
    print("\n[F4] 경로당 밀집 기준(반경 안 개수 이상):", tables["senior_center_threshold"])
    print("\n[F4] 시설 좌표 점검"); print(pd.DataFrame(fac_rows).to_string(index=False))
    print(f"\n[F4] R3 코드 일치 {tables['r3_code_match']['matched']}/{tables['r3_code_match']['dongs']}"
          f" ({tables['r3_code_match']['rate_pct']}%), ref_month={ref_month}")
    print(f"결과 문서 {n_docs}개 + meta + boundaries 를 스키마 검사 후 저장")
    return tables


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assigned", type=Path, default=Path("data/interim/busan_f2_assigned.csv"))
    ap.add_argument("--boundary", type=Path, required=True, help="R2 geojson")
    ap.add_argument("--population", type=Path, required=True, help="R3 고령 인구 CSV")
    ap.add_argument("--protect-zone", type=Path, required=True, help="O1")
    ap.add_argument("--market", type=Path, required=True, help="O3")
    ap.add_argument("--senior-center", type=Path, required=True, help="O2")
    ap.add_argument("--contracts", type=Path, default=Path("contracts"))
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, default=Path("data/interim"))
    ap.add_argument("--bundle", type=Path, default=Path("data/interim/bundle"))
    ap.add_argument("--web-out", type=Path, default=Path("data/interim/web"))
    ap.add_argument("--sources", type=Path, help="meta.sources JSON (출처·이용허락범위). 없으면 빈 목록")
    ap.add_argument("--built-at", help="meta.built_at (재현 비교용). 없으면 지금 시각")
    ap.add_argument("--simplify-m", type=float, default=15.0, help="지도 경계 단순화 허용 오차(m)")
    ap.add_argument("--sido-prefix", default="26")
    run(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
