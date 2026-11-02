"""v2 결과 만들기·내보내기 (D12 #75, 결정 009).

입력: F2 결과(`busan_f2_assigned.csv`, 부산 3,726곳), R2 경계, R3 인구, O1 보호구역, O3 전통시장, config.yaml
출력(정적 묶음 규격, contracts README): areas_v2/{target}_{radius}.json, points_v2/{target}_{radius}.json, manifest.json,
      요약 v2_summary.json/md (이슈 코멘트용 표). 모든 문서는 contracts 스키마를 통과해야 쓴다.

흐름
    기준식 분류·data_check -> 시설 거리 -> (반경별) 단계·주민 고령 비율 -> (목표별) 속도·시간·커버리지 -> 읍면동 집계
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from pipeline import busan_build as bb
from pipeline import busan_facilities as fac
from pipeline import busan_judge as jd
from pipeline import v2_speed as sp
from pipeline import v2_tiers as tr

# v2 점 문서가 v1 필수 필드(t_need_s·gap_s)를 채울 때 쓰는 속도. C3 샘플과 같다(결정 009 이슈 #75 질문 1의 기본값).
V1_FIELD_SPEED = 0.8
# 시간 값은 소수 셋째 자리까지 내보낸다(contracts README "반올림")
TIME_DIGITS = 3
RATIO_DIGITS = 3

V2_KEYS = ["target_coverage", "target_coverage_sensitivity", "speed_bounds_mps", "formula_tolerance_s",
           "walking_speed_mps", "walking_speed_elderly_p15_sensitivity", "tier1_speed_mps", "big_market_min_stores",
           "market_exclude_keywords", "market_elderly_uplift", "market_elderly_uplift_range",
           "add_seconds_threshold", "entry_seconds", "speeds_mps", "min_sample", "crs_compute", "crs_storage",
           "exposure_radius_m", "exposure_radius_sensitivity_m"]


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    miss = [k for k in V2_KEYS if k not in cfg]
    if miss:
        raise KeyError(f"config.yaml 에 없는 키: {miss}")
    if V1_FIELD_SPEED not in cfg["speeds_mps"]:
        raise ValueError(f"speeds_mps {cfg['speeds_mps']} 에 {V1_FIELD_SPEED} 가 없다")
    return cfg


def target_key(t: float) -> str:
    return f"{t:.2f}"


# ---------- 계산 ----------
def prepare(cw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """기준식 분류와 data_check 표시를 붙인다. 점 좌표(EPSG:5179)도 함께 만든다."""
    d = cw.reset_index(drop=True).copy()
    d["formula_class"] = tr.classify_formula(d["length_m"], d["green_s"], cfg).to_numpy()
    d["data_check"] = tr.data_check_mask(d["length_m"], d["green_s"], d["formula_class"], cfg)
    from pyproj import Transformer
    tf = Transformer.from_crs(cfg["crs_storage"], cfg["crs_compute"], always_xy=True)
    d["x"], d["y"] = tf.transform(d["lon"].to_numpy(), d["lat"].to_numpy())
    return d


def attach_distances(d: pd.DataFrame, protect: fac.Facility, big: tr.NamedFacility) -> pd.DataFrame:
    """가장 가까운 노인보호구역·대형 시장까지 거리(m)와 시장 이름."""
    xy = d[["x", "y"]].to_numpy()
    d = d.copy()
    d["protect_m"], _ = tr.nearest_distance(xy, protect.xy)
    d["market_m"], idx = tr.nearest_distance(xy, big.xy)
    d["market_name"] = np.where(idx >= 0, big.names[np.clip(idx, 0, max(len(big.names) - 1, 0))] if len(big.names) else "", "")
    return d


def tier_table(d: pd.DataFrame, radius: int, polys, ratio, cfg: dict) -> pd.DataFrame:
    """한 반경의 단계·주민 고령 비율. data_check 행은 계산하지 않는다(null)."""
    ok = ~d["data_check"].to_numpy()
    out = pd.DataFrame(index=d.index, columns=["tier", "resident"], dtype=float)
    out["tier"] = np.nan
    out["resident"] = np.nan
    out.loc[ok, "tier"] = tr.assign_tier(d.loc[ok, "protect_m"], d.loc[ok, "market_m"], radius)
    out.loc[ok, "resident"] = tr.resident_elderly_ratio(d.loc[ok, ["x", "y"]].to_numpy(), polys, ratio, radius)
    return out


def apply_target(d: pd.DataFrame, tiers: pd.DataFrame, target: float, cfg: dict, model: sp.SpeedModel,
                 uplift: float | None = None, market_all_elderly: bool = False) -> pd.DataFrame:
    """목표 커버리지 하나에 대한 이용자 고령 비율·적용 속도·시간·커버리지.

    uplift: 2단계 시장 보정(없으면 config). market_all_elderly: 2단계를 "이용자 전원 고령자"로(비교 시나리오).
    주민 고령 비율을 모르는 행(NaN)은 2·3단계를 계산할 수 없어 값이 NaN 으로 남는다.
    """
    uplift = cfg["market_elderly_uplift"] if uplift is None else uplift
    tier, res = tiers["tier"].to_numpy(dtype=float), tiers["resident"].to_numpy(dtype=float)
    market_share = np.ones_like(res) if market_all_elderly else np.clip(res + uplift, 0.0, 1.0)
    user = np.select([tier == 1, tier == 2], [1.0, market_share], res)  # 3단계와 기본값은 주민 비율
    speed = np.full(len(d), np.nan)
    calc = ~np.isnan(user)
    speed[calc] = sp.design_speed(user[calc], target, model, tuple(cfg["speed_bounds_mps"]))
    speed = np.where(tier == 1, cfg["tier1_speed_mps"], speed)
    L, G, entry = d["length_m"].to_numpy(float), d["green_s"].to_numpy(float), cfg["entry_seconds"]
    t_req = sp.required_time(G, L, speed, entry)  # NaN 속도면 NaN
    out = pd.DataFrame({"user": user, "v": speed, "t_req_raw": t_req}, index=d.index)
    out["add_raw"] = out["t_req_raw"] - G
    out["cov_now"] = sp.coverage(L, G, entry, model)
    out["cov_req"] = sp.coverage(L, out["t_req_raw"].to_numpy(), entry, model)
    return out.where(tiers["tier"].notna(), np.nan)  # data_check 행은 모두 NaN


def rounded_times(green, t_req_raw):
    """내보내는 값 기준으로 t_required = green + add 가 맞도록 셋째 자리로 먼저 자른다."""
    g = np.round(np.asarray(green, float), TIME_DIGITS)
    t = np.round(np.asarray(t_req_raw, float), TIME_DIGITS)
    return g, t, np.round(t - g, TIME_DIGITS)


def make_reason(tier: int, row: dict, radius: int, t_req: float, add: float) -> str:
    """결정 009 표현 원칙의 조건형 한 줄. 숫자는 내보내는 값을 소수 첫째 자리로 쓴 것이다."""
    if tier == 1:
        base = f"노인보호구역 {row['protect_m']:.0f}m → 보호구역 기준 {row['v']:.2f}m/s"
    elif tier == 2:
        base = (f"{row['market_name']} {row['market_m']:.0f}m → 이용자 고령 비율 {row['user']:.0%}"
                f"(주민 {row['resident']:.0%} + 시장 보정) → {row['v']:.2f}m/s")
    else:
        base = f"반경 {radius}m 고령 비율 {row['resident']:.0%} → {row['v']:.2f}m/s"
    if add > 0:
        tail = f", 길이 {row['length_m']:.0f}m → 기준 적용 시 {t_req:.1f}초 (+{add:.1f}초)"
    else:
        tail = ", 현재 시간으로 충분"
    return base + tail


# ---------- 문서 ----------
def _num(x, digits):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), digits)


def points_doc(d: pd.DataFrame, tiers: pd.DataFrame, res: pd.DataFrame, flags: pd.DataFrame, target: float,
               radius: int, cfg: dict) -> dict:
    """전체 횡단보도 점(analyzed + data_check). excluded 는 이번 범위에 넣지 않는다(좌표·동 배정이 없는 행이 많다)."""
    entry = cfg["entry_seconds"]
    g3, t3, add3 = rounded_times(d["green_s"], res["t_req_raw"])
    t_need = np.round(entry + d["length_m"].to_numpy(float) / V1_FIELD_SPEED, TIME_DIGITS)
    gap = np.round(t_need - g3, TIME_DIGITS)
    feats = []
    for i, r in d.iterrows():
        is_check = bool(r["data_check"])
        fl = {"senior_center": False, "market": bool(flags.at[i, "market"]), "protect_zone": bool(flags.at[i, "protect_zone"]),
              "crash_zone_past": False, "hospital": None}
        cnt = int(fl["market"]) + int(fl["protect_zone"])
        p = {"cw_id": r["cw_id"], "adm_cd": r["adm_cd2"], "status": "data_check" if is_check else "analyzed",
             "length_m": round(float(r["length_m"]), 2), "green_s": float(g3[i]),
             "t_need_s": None if is_check else float(t_need[i]), "gap_s": None if is_check else float(gap[i]),
             "flags": fl, "exposure_cnt": cnt,
             "is_candidate": False if is_check else bool(jd.is_short(pd.Series([gap[i]])).iloc[0] and cnt >= 1),
             "exclude_reason": None, "formula_class": r["formula_class"]}
        if is_check:
            p.update(tier=None, resident_elderly_ratio=None, user_elderly_ratio=None, v_applied_mps=None,
                     t_required_s=None, add_s=None, coverage_now=None, coverage_required=None, reason=None,
                     reason_parts=None,
                     check_reason=(f"기록 보행시간이 일반 기준식({entry} + L/{max(cfg['speeds_mps']):.1f})보다도 짧고 "
                                   "어느 기준식과도 다르다. 기록 방식 확인 전까지 집계에서 뺀다"))
        else:
            tier = int(tiers.at[i, "tier"])
            rr = {"protect_m": r["protect_m"], "market_m": r["market_m"], "market_name": r["market_name"],
                  "v": res.at[i, "v"], "user": res.at[i, "user"], "resident": tiers.at[i, "resident"],
                  "length_m": r["length_m"]}
            calc = not np.isnan(res.at[i, "v"])
            p.update(tier=tier, resident_elderly_ratio=_num(tiers.at[i, "resident"], RATIO_DIGITS),
                     user_elderly_ratio=_num(res.at[i, "user"], RATIO_DIGITS),
                     v_applied_mps=_num(res.at[i, "v"], 4),
                     t_required_s=float(t3[i]) if calc else None, add_s=float(add3[i]) if calc else None,
                     coverage_now=_num(res.at[i, "cov_now"], RATIO_DIGITS),
                     coverage_required=_num(res.at[i, "cov_req"], RATIO_DIGITS) if calc else None,
                     reason=make_reason(tier, rr, radius, float(t3[i]), float(add3[i])) if calc else None,
                     reason_parts={"protect_zone_m": _num(r["protect_m"], 1),
                                   "market_name": r["market_name"] or None, "market_m": _num(r["market_m"], 1)},
                     check_reason=None)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(float(r["lon"]), 6), round(float(r["lat"]), 6)]},
                      "properties": p})
    return {"type": "FeatureCollection", "speed": V1_FIELD_SPEED, "radius_m": radius, "target": target, "features": feats}


def areas_doc(d: pd.DataFrame, res: pd.DataFrame, dongs, pop: pd.DataFrame, target: float, radius: int, cfg: dict) -> dict:
    """읍면동 집계(v2). 분석 = data_check 제외. 횡단보도가 없는 동도 포함한다(회색)."""
    thr = cfg["add_seconds_threshold"]
    ok = ~d["data_check"].to_numpy()
    _, _, add3 = rounded_times(d["green_s"], res["t_req_raw"])
    a = pd.DataFrame({"adm_cd2": d["adm_cd2"], "add": add3, "cov_now": res["cov_now"], "cov_req": res["cov_req"]})[ok]
    a = a[a["add"].notna()]
    g = a.groupby("adm_cd2")
    stat = pd.DataFrame({"n_analyzed": g.size(), "mean_add_s": g["add"].mean(),
                         "n_add2": g["add"].apply(lambda s: int((s >= thr).sum())),
                         "coverage_now_mean": g["cov_now"].mean(), "coverage_required_mean": g["cov_req"].mean()})
    base = dongs[["adm_cd2", "adm_name", "sidonm", "sggnm"]].rename(columns={"sidonm": "sido", "sggnm": "sigungu"})
    t = base.merge(stat, left_on="adm_cd2", right_index=True, how="left") \
            .merge(pop[["adm_cd", "ratio_65plus"]], left_on="adm_cd2", right_on="adm_cd", how="left")
    t["n_analyzed"] = t["n_analyzed"].fillna(0).astype(int)
    t["n_add2"] = t["n_add2"].fillna(0).astype(int)
    t["low_sample"] = t["n_analyzed"] < cfg["min_sample"]
    use = ~t["low_sample"] & t["mean_add_s"].notna() & t["ratio_65plus"].notna()
    med = {"mean_add_s_median": float(t.loc[use, "mean_add_s"].median()) if use.any() else 0.0,
           "ratio_65plus_median": float(t.loc[use, "ratio_65plus"].median()) if use.any() else 0.0}
    quads = []
    for i, r in t.iterrows():  # 높음 = 중앙값 초과(v1과 같은 규칙)
        quads.append(None if not use[i] else
                     f"{'high' if r['mean_add_s'] > med['mean_add_s_median'] else 'low'}_"
                     f"{'high' if r['ratio_65plus'] > med['ratio_65plus_median'] else 'low'}")
    t["quadrant"] = pd.Series(quads, index=t.index, dtype=object)
    items = []
    for _, r in t.sort_values("adm_cd2").iterrows():
        items.append({"adm_cd": r["adm_cd2"], "adm_name": r["adm_name"], "sido": r["sido"], "sigungu": r["sigungu"],
                      "n_analyzed": int(r["n_analyzed"]), "mean_add_s": _num(r["mean_add_s"], TIME_DIGITS),
                      "n_add2": int(r["n_add2"]), "coverage_now_mean": _num(r["coverage_now_mean"], RATIO_DIGITS),
                      "coverage_required_mean": _num(r["coverage_required_mean"], RATIO_DIGITS),
                      "ratio_65plus": _num(r["ratio_65plus"], 4),
                      "quadrant": None if pd.isna(r["quadrant"]) else r["quadrant"], "low_sample": bool(r["low_sample"])})
    return {"target": target, "radius_m": radius, "min_sample": cfg["min_sample"],
            "thresholds": {k: round(v, 4) for k, v in med.items()}, "items": items}


def summarize(d: pd.DataFrame, tiers: pd.DataFrame, res: pd.DataFrame, cfg: dict) -> dict:
    """이슈 코멘트용 요약: 단계별 건수·추가 초·커버리지."""
    ok = ~d["data_check"].to_numpy()
    _, _, add3 = rounded_times(d["green_s"], res["t_req_raw"])
    df = pd.DataFrame({"tier": tiers["tier"], "add": add3, "cn": res["cov_now"], "cr": res["cov_req"]})[ok]
    df = df[df["add"].notna()]
    rows = []
    for tier, g in df.groupby("tier"):
        pos = g[g["add"] > 0]
        rows.append({"tier": int(tier), "n": len(g), "n_add": len(pos), "n_add2": int((g["add"] >= cfg["add_seconds_threshold"]).sum()),
                     "mean_add_where_added": _num(pos["add"].mean(), 2) if len(pos) else None,
                     "coverage_now": _num(g["cn"].mean(), 3), "coverage_required": _num(g["cr"].mean(), 3)})
    return {"tiers": rows, "n_analyzed": len(df), "n_add2": int((df["add"] >= cfg["add_seconds_threshold"]).sum()),
            "mean_add_where_added": _num(df.loc[df["add"] > 0, "add"].mean(), 2)}


# ---------- 실행 ----------
def run(a: argparse.Namespace) -> dict:
    cfg = load_config(a.config)
    radii = sorted({cfg["exposure_radius_m"], *cfg["exposure_radius_sensitivity_m"]})
    targets = sorted({cfg["target_coverage"], *cfg["target_coverage_sensitivity"]})
    cw = pd.read_csv(a.assigned, dtype={"adm_cd2": str})
    dongs = bb.load_dongs(a.boundary, a.sido_prefix, cfg)
    pop, ref_month = bb.load_population(a.population)

    d = prepare(cw, cfg)
    protect = fac.load_protect_zone(a.protect_zone, cfg)
    big = tr.load_big_markets(a.market, cfg)
    all_markets = fac.load_market(a.market, cfg)
    d = attach_distances(d, protect, big)

    dongs_m = dongs.to_crs(cfg["crs_compute"]).reset_index(drop=True)
    polys = list(dongs_m.geometry)
    ratio_by = pop.set_index("adm_cd")["ratio_65plus"]
    ratio = np.array([ratio_by.get(c, np.nan) for c in dongs_m["adm_cd2"]], dtype=float)

    model = sp.SpeedModel.from_config(cfg)
    check = bb.SchemaCheck(a.contracts)
    out_dir = a.bundle_v2
    xy = d[["x", "y"]].to_numpy()
    summary = {"ref_month": ref_month, "rows": len(d), "data_check": int(d["data_check"].sum()),
               "formula_classes": d["formula_class"].value_counts().to_dict(),
               "facilities": {"protect_zone": {"rows": protect.total_rows, "used": int(len(protect.xy)), "bad_coord": protect.bad_coord_rows},
                              "big_market": {"rows": big.total_rows, "kept": big.kept_rows, "used": int(len(big.xy)), "bad_coord": big.bad_coord_rows}},
               "by_combo": {}, "sensitivity": {}}
    manifest_v2, n_docs = [], 0
    for r in radii:
        tiers = tier_table(d, r, polys, ratio, cfg)
        flags = pd.DataFrame({"market": fac.count_within(xy, all_markets, r) > 0,
                              "protect_zone": d["protect_m"].to_numpy() <= r}, index=d.index)
        missing = int(tiers.loc[tiers["tier"].notna() & tiers["resident"].isna()].shape[0])
        for t in targets:
            res = apply_target(d, tiers, t, cfg, model)
            tk = f"{target_key(t)}_{r}"
            bb.write_json(out_dir / "points_v2" / f"{tk}.json", points_doc(d, tiers, res, flags, t, r, cfg), check, "points")
            bb.write_json(out_dir / "areas_v2" / f"{tk}.json", areas_doc(d, res, dongs, pop, t, r, cfg), check, "areas")
            n_docs += 2
            manifest_v2.append({"target": t, "radius_m": r, "points": True})
            s = summarize(d, tiers, res, cfg)
            s["resident_ratio_missing"] = missing
            summary["by_combo"][tk] = s
        # 민감도(기본 목표 0.85, 점 문서는 만들지 않는다): 고령자 15퍼센타일, 전원 고령자, 시장 보정 범위
        t0 = cfg["target_coverage"]
        scen = {"elderly_p15_" + str(p15): (apply_target(d, tiers, t0, cfg, sp.SpeedModel.from_config(cfg, p15)))
                for p15 in cfg["walking_speed_elderly_p15_sensitivity"]}
        scen["market_all_elderly"] = apply_target(d, tiers, t0, cfg, model, market_all_elderly=True)
        for u in cfg["market_elderly_uplift_range"]:
            scen[f"uplift_{u}"] = apply_target(d, tiers, t0, cfg, model, uplift=u)
        summary["sensitivity"][str(r)] = {k: summarize(d, tiers, v, cfg)["n_add2"] for k, v in scen.items()}
    built_at = a.built_at or datetime.now(bb.KST).isoformat(timespec="seconds")
    bb.write_json(out_dir / "manifest.json", {"built_at": built_at, "results": [], "results_v2": manifest_v2}, check, "static_manifest")
    summary["documents"] = n_docs
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "v2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("rows", "data_check", "formula_classes", "facilities", "documents")}, ensure_ascii=False, indent=1))
    base = summary["by_combo"][f"{target_key(cfg['target_coverage'])}_{cfg['exposure_radius_m']}"]
    print("\n[기본] 목표 0.85, 반경", cfg["exposure_radius_m"]); print(pd.DataFrame(base["tiers"]).to_string(index=False))
    print("2초 이상 추가:", base["n_add2"], "/ 평균 추가(추가되는 곳):", base["mean_add_where_added"])
    print("민감도(2초 이상 추가 수):", json.dumps(summary["sensitivity"][str(cfg["exposure_radius_m"])], ensure_ascii=False))
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assigned", type=Path, required=True)
    p.add_argument("--boundary", type=Path, required=True)
    p.add_argument("--population", type=Path, required=True)
    p.add_argument("--protect-zone", type=Path, required=True)
    p.add_argument("--market", type=Path, required=True)
    p.add_argument("--contracts", type=Path, default=Path("contracts"))
    p.add_argument("--config", type=Path, default=Path("config.yaml"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--bundle-v2", type=Path, required=True)
    p.add_argument("--built-at", default=None)
    p.add_argument("--sido-prefix", default="26")
    run(p.parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
