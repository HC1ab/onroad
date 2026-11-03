"""V6 교차 확인(D15 #90): 부산 행정동 생활인구(연령, 통신)로 대형 전통시장 주변 동의 고령 방문 비율을 본다.

결정 009의 2단계 시장 보정(V6, 지하철 무임 비율)은 역 몇 곳에 크게 기댄다. 지하철과 다른 데이터로 같은 방향이
보이는지 확인한다.

입력 (data/raw, 커밋 금지)
    - living_pop_age/*.json: data.go.kr 15164376 getDongPopAge 응답을 페이지별로 저장한 것.
      같은 행이 두 번씩 오므로 완전히 같은 행은 하나만 남긴다.
    - admin_boundary(R2)·population_65(R3)·market(O3): v2_validate.py(V6)와 같은 함수로 읽는다.
출력
    - data/interim/v6_living_pop_notes.json (결과·민감도). 화면 계약(validation.json)에는 넣지 않는다.

방법 (V6과 같은 틀, 단위만 역 → 행정동)
    y = 동의 고령 방문인구 / 방문인구 합계. 연령 구간의 맨 위가 '60세이상'이라 65·70세로는 나눌 수 없다.
    x = 주민 65세 이상 비율(R3). y 를 x 로 회귀한 잔차를 대형 시장 반경에 걸친 동과 그 외 동으로 비교한다(단측 순열).
    시장 보정 = 차이 / 기울기. config market_elderly_uplift(·_range)와 같은 단위(주민 고령 비율)다.
    민감도: 시장 점포 기준, 반경(0 = 시장이 동 안에 있을 때만), 시장 동 하나씩 빼기, x 를 같은 자료의 주거인구 고령 비율로.

원칙: 결과가 기대와 달라도 그대로 보고한다. 연관성까지만 말한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_validate as vv  # noqa: E402  같은 V6 함수와 민감도 기준을 쓴다

SOURCE_ID = "15164376"
NUM_COLS = ("hpopAvg", "wpopAvg", "vpopAvg")   # 주거·직장·방문인구 월별 일평균
RADII_M = (0,) + vv.MARKET_RADII_M             # 0: 시장이 동 경계 안에 있을 때만


# ---------- 읽기 ----------
def read_living(folder: Path, month: str) -> pd.DataFrame:
    """페이지별 응답 JSON 을 합친다. 완전히 같은 행은 하나만 남기고, 같은 동·연령에 값이 다른 행이 있으면 멈춘다."""
    items = []
    for f in sorted(folder.glob("*.json")):
        body = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]
        got = (body.get("items") or {}).get("item") or []
        items += got if isinstance(got, list) else [got]
    if not items:
        raise ValueError(f"{folder}: 생활인구 행이 없다")
    raw = pd.DataFrame(items)
    df = raw.drop_duplicates()
    df = df[df["stdYm"].astype(str) == str(month)].copy()
    clash = df.duplicated(["hcode", "ages"], keep=False)
    if clash.any():
        raise ValueError(f"같은 동·연령에 값이 다른 행 {int(clash.sum())}개 (예: {df.loc[clash, 'hcode'].iloc[0]})")
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="raise")
    df.attrs.update(rows_received=len(raw), rows_unique=len(df))
    return df


def elderly_band(ages: pd.Series) -> str:
    """맨 위 연령 구간('…이상'). 하나가 아니면 자료 형식이 바뀐 것이라 멈춘다."""
    top = sorted({a for a in ages.astype(str) if a.endswith("이상")})
    if len(top) != 1:
        raise ValueError(f"맨 위 연령 구간을 하나로 정할 수 없다: {top}")
    return top[0]


def dong_shares(living: pd.DataFrame) -> pd.DataFrame:
    """동별 방문·주거인구의 고령 구간 비율. 방문인구 합계가 0인 동은 비율을 NaN 으로 둔다."""
    band = elderly_band(living["ages"])
    total = living.groupby("hcode")[["vpopAvg", "hpopAvg"]].sum()
    old = living[living["ages"] == band].set_index("hcode")[["vpopAvg", "hpopAvg"]]
    out = pd.DataFrame({
        "hname": living.groupby("hcode")["hname"].first(),
        "visit_total": total["vpopAvg"],
        "visit_old_share": (old["vpopAvg"] / total["vpopAvg"].replace(0, np.nan)),
        "resident_old_share": (old["hpopAvg"] / total["hpopAvg"].replace(0, np.nan)),
    })
    out.attrs["band"] = band
    return out


# ---------- 계산 ----------
def market_distance(dongs, markets, min_stores: int) -> np.ndarray:
    """동 경계에서 가장 가까운 대형 시장(제외 상가 뺌, 점포 min_stores 이상)까지 거리(m). 동 안에 있으면 0."""
    usable = markets[~markets["excluded"] & (markets["stores"] >= min_stores)].reset_index(drop=True)
    return vv.nearest_m(dongs.reset_index(drop=True), usable)


def test_row(df: pd.DataFrame, x_col: str, near: np.ndarray, n_perm: int, seed: int) -> dict:
    """V6 과 같은 검정. 이름만 역 → 동으로 바꾼다."""
    r = vv.v6_test(df["visit_old_share"].to_numpy(), df[x_col].to_numpy(), near, n_perm, seed)
    return {"n_dongs": r["n_stations"], "n_market_dongs": r["n_market_stations"], "raw_diff_pp": r["raw_diff_pp"],
            "diff_pp": r["diff_pp"], "p_value": r["p_value"], "slope": r["slope"], "uplift": r["uplift"]}


def analyze(df: pd.DataFrame, dist: dict[int, np.ndarray], base_stores: int, base_radius: int,
            n_perm: int, seed: int) -> dict:
    """df: 동별 visit_old_share·ratio_65plus·resident_old_share. dist: 점포 기준 → 동별 시장 거리."""
    near = dist[base_stores] <= base_radius
    base = test_row(df, "ratio_65plus", near, n_perm, seed)
    rows = [{"param": "min_stores", "value": str(s), **test_row(df, "ratio_65plus", dist[s] <= base_radius, n_perm, seed)}
            for s in sorted(dist)]
    rows += [{"param": "radius_m", "value": str(r), **test_row(df, "ratio_65plus", dist[base_stores] <= r, n_perm, seed)}
             for r in RADII_M]
    rows.append({"param": "x", "value": "resident_old_share",
                 **test_row(df, "resident_old_share", near, n_perm, seed)})
    for code in df.index[near]:
        keep = df.index != code
        rows.append({"param": "drop_dong", "value": str(code),
                     **test_row(df[keep], "ratio_65plus", near[keep], n_perm, seed)})
    drops = [r["uplift"] for r in rows if r["param"] == "drop_dong" and r["uplift"] is not None]
    span = drops + ([base["uplift"]] if base["uplift"] is not None else [])
    return {**base, "uplift_range": [min(span), max(span)] if span else None,
            "near_market_dongs": [{"adm_cd": str(c), "name": df.at[c, "hname"]} for c in df.index[near]],
            "sensitivity": rows}


def compare(uplift, uplift_range, cfg_uplift, cfg_range) -> dict:
    """지하철 기반 보정(config)과 견준다. 판정은 '범위 안/밖'까지만 한다."""
    lo, hi = cfg_range
    inside = uplift is not None and lo <= uplift <= hi
    overlap = uplift_range is not None and uplift_range[0] <= hi and uplift_range[1] >= lo
    return {"config_uplift": cfg_uplift, "config_range": [lo, hi], "uplift_in_config_range": inside,
            "ranges_overlap": overlap}


# ---------- 실행 ----------
def run(a: argparse.Namespace) -> dict:
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    crs = cfg["crs_compute"]
    n_perm = a.n_perm or cfg["permutations"]
    seed = a.seed if a.seed is not None else cfg["seed"]

    living = read_living(a.living, a.month)
    shares = dong_shares(living)
    dongs = vv.read_dongs(a.raw, crs).set_index("adm_cd2")
    joined = dongs.join(shares, how="inner")
    unmatched = {"living_not_in_boundary": sorted(set(shares.index) - set(dongs.index)),
                 "boundary_not_in_living": sorted(set(dongs.index) - set(shares.index))}
    used = joined.dropna(subset=["visit_old_share", "ratio_65plus", "resident_old_share"])

    markets = vv.read_markets(a.raw, cfg["market_exclude_keywords"], crs)
    stores = sorted(set(vv.STORE_THRESHOLDS) | {cfg["big_market_min_stores"]})
    dist = {s: market_distance(used, markets, s) for s in stores}
    res = analyze(used, dist, cfg["big_market_min_stores"], cfg["exposure_radius_m"], n_perm, seed)
    res["compare"] = compare(res["uplift"], res["uplift_range"], cfg.get("market_elderly_uplift"),
                             cfg.get("market_elderly_uplift_range"))

    notes = vv.rounded({
        "params": {"source": SOURCE_ID, "month": a.month, "elderly_band": shares.attrs["band"],
                   "rows_received": living.attrs["rows_received"], "rows_unique": living.attrs["rows_unique"],
                   "n_dongs_living": int(len(shares)), "n_dongs_used": int(len(used)), "unmatched": unmatched,
                   "min_stores": cfg["big_market_min_stores"], "radius_m": cfg["exposure_radius_m"],
                   "n_permutations": n_perm, "seed": seed, "crs": crs},
        "result": res,
        "limits": ["연령 구간 맨 위가 60세 이상이라 65세(주민 기준)·70세 경계로 나눌 수 없다",
                   "행정동 단위다. 시장 300m 원이 아니라 그 원에 걸친 동 전체를 본다",
                   "통신사 추정치(월별 일평균)다", "연관성이며 인과가 아니다"],
    })
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    return notes


def report(notes: dict) -> None:
    p, r = notes["params"], notes["result"]
    c = r["compare"]
    print(f"생활인구 {p['month']}: 받은 행 {p['rows_received']} → 중복 제거 {p['rows_unique']}, "
          f"동 {p['n_dongs_living']} 중 분석 {p['n_dongs_used']}, 고령 구간 '{p['elderly_band']}'")
    print(f"V6-생활인구  동 {r['n_dongs']}곳, 대형 시장 반경 {p['radius_m']}m 에 걸친 동 {r['n_market_dongs']}곳: "
          f"방문 고령 비율 차이 {r['raw_diff_pp']:+.2f}%p, 주민 고령 비율 감안 {r['diff_pp']:+.2f}%p, p={r['p_value']}, "
          f"기울기 {r['slope']:.3f} → 보정 {r['uplift']}"
          f" (범위 {r['uplift_range']})")
    print(f"    지하철 기반 config {c['config_uplift']} (범위 {c['config_range']}): "
          f"보정이 범위 안 {c['uplift_in_config_range']}, 범위가 겹침 {c['ranges_overlap']}")
    for s in r["sensitivity"]:
        u = "-" if s["uplift"] is None else f"{s['uplift']:.3f}"
        print(f"    {s['param']:<11}{s['value']:<20} 시장 동 {s['n_market_dongs']:>3}  차이 {s['diff_pp']:+6.2f}%p  "
              f"p={s['p_value']}  보정 {u}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--living", type=Path, default=Path("data/raw/living_pop_age"),
                    help="getDongPopAge 응답 JSON 폴더 (페이지별 파일)")
    ap.add_argument("--month", default="202609", help="기준년월 (R3 와 같은 달)")
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, default=Path("data/interim/v6_living_pop_notes.json"))
    ap.add_argument("--n-perm", type=int, default=None, help="기본: config permutations")
    ap.add_argument("--seed", type=int, default=None, help="기본: config seed")
    a = ap.parse_args(argv)
    report(run(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
