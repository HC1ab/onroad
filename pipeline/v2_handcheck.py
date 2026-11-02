"""v2 손계산 검증: 내보낸 points_v2 파일에서 무작위 N건을 골라, 파이프라인 코드를 쓰지 않고 다시 계산해 비교한다.

독립 계산: scipy.optimize.brentq 로 속도를 찾고 math.erf 로 정규분포를 계산한다(v2_speed 를 import 하지 않는다).
입력은 내보낸 파일의 값(길이, 기록 보행시간, 단계, 고령 비율)뿐이다.
사용: python -m pipeline.v2_handcheck points_v2/0.85_300.json --n 10 --seed 20261101
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import yaml
from scipy.optimize import brentq

P_ROUND = 0.0005  # 고령 비율을 소수 셋째 자리로 반올림한 오차
TOL_V, TOL_T, TOL_COV = 5e-5, 1e-3, 6e-4  # 나머지 반올림(속도 넷째, 시간 셋째, 비율 셋째 자리)
TOLS = {"v_applied_mps": TOL_V, "t_required_s": TOL_T, "add_s": TOL_T, "coverage_now": TOL_COV, "coverage_required": TOL_COV}


def cdf(x, mu, sd):
    return 0.5 * (1 + math.erf((x - mu) / (sd * math.sqrt(2))))


def recompute(props: dict, p: float, target: float, cfg: dict) -> dict:
    """고령 비율 p 로 속도·시간·커버리지를 처음부터 다시 계산한다."""
    z = 1.0364333894937898  # 표준정규 85퍼센타일(= norm.ppf(0.85)). 독립 계산을 위해 적어 둔 값
    g, e = cfg["walking_speed_mps"]["general"], cfg["walking_speed_mps"]["elderly"]
    gm, gs = g["mean"], (g["mean"] - g["p15"]) / z
    em, es = e["mean"], (e["mean"] - e["p15"]) / z
    lo, hi = cfg["speed_bounds_mps"]
    if props["tier"] == 1:
        v = cfg["tier1_speed_mps"]
    else:
        f = lambda v: (1 - p) * cdf(v, gm, gs) + p * cdf(v, em, es) - (1 - target)  # noqa: E731
        v = min(max(brentq(f, 0.05, 4.0, xtol=1e-12), lo), hi)
    entry, L, G = cfg["entry_seconds"], props["length_m"], props["green_s"]
    t = max(G, entry + L / v)
    cov = lambda sec: 0.0 if sec - entry <= 0 else 1 - cdf(L / (sec - entry), em, es)  # noqa: E731
    return {"v_applied_mps": v, "t_required_s": t, "add_s": t - G, "coverage_now": cov(G), "coverage_required": cov(t)}


def check_row(props: dict, target: float, cfg: dict) -> dict:
    """내보낸 값이 다시 계산한 값과 맞는지. 내보낸 고령 비율은 셋째 자리로 반올림되어 있으므로
    p ± 반올림 오차로 다시 계산한 범위 안에 있으면 일치로 본다(반올림 때문에 생기는 차이를 오류로 세지 않는다)."""
    p = props["user_elderly_ratio"]
    lows = [recompute(props, min(1.0, max(0.0, p + dp)), target, cfg) for dp in (-P_ROUND, 0.0, P_ROUND)]
    mine = lows[1]
    diffs, ok = {}, True
    for k, tol in TOLS.items():
        lo_, hi_ = min(x[k] for x in lows), max(x[k] for x in lows)
        got = props[k]
        miss = max(lo_ - tol - got, got - hi_ - tol, 0.0)  # 범위 밖으로 벗어난 크기
        diffs[k] = miss
        ok = ok and miss == 0.0
    return {"cw_id": props["cw_id"], "tier": props["tier"], "ok": ok,
            "mine": {k: round(v_, 4) for k, v_ in mine.items()},
            "exported": {k: props[k] for k in mine}, "max_diff": max(diffs.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("points", type=Path)
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261101)
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    doc = json.loads(a.points.read_text(encoding="utf-8"))
    rows = [f["properties"] for f in doc["features"] if f["properties"]["status"] == "analyzed"
            and f["properties"]["v_applied_mps"] is not None]
    rnd = random.Random(a.seed)
    # 단계가 섞이도록 단계별로 먼저 하나씩 뽑고 나머지는 무작위로 채운다
    pick = [rnd.choice([r for r in rows if r["tier"] == t]) for t in (1, 2, 3)]
    rest = [r for r in rows if r not in pick]
    pick += rnd.sample(rest, max(0, a.n - len(pick)))
    results = [check_row(r, doc["target"], cfg) for r in pick]
    for r in results:
        print(f"{r['cw_id']} 단계{r['tier']} {'일치' if r['ok'] else '불일치'} 최대차 {r['max_diff']:.5f}")
    print(f"{sum(r['ok'] for r in results)}/{len(results)}건 일치")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
