"""부산 횡단보도별 추천 보행시간·이유·커버리지를 3단계 규칙으로 계산한다.

1단계: 노인보호구역 반경 안 → 0.7m/s (현행 보호구역 기준)
2단계: 대형 전통시장 반경 안 → 이용자 고령 비율 = 주민 고령 비율 + 시장 보정(지하철 무임 비율로 측정)
3단계: 그 외 → 이용자 고령 비율 = 반경 안 주민 고령 비율
2·3단계 속도는 일반·고령 보행속도 분포를 이용자 고령 비율로 섞어, 목표 비율이 건너는 속도다.
필요 시간은 현재 시간보다 줄이지 않는다. 비교 시나리오로 2단계를 "이용자 전원 고령자"(국토부 방식)로도 계산한다.

사용: python pipeline/prototype_v2/recommend_times.py
"""
import numpy as np
import pandas as pd

from common import (OUT, P, coverage, design_speed, load_child_zones, load_crosswalks, load_markets, load_protect_zones,
                    md_table, nearest_m, radius_elderly_ratio)


def classify_formula(length, seconds):
    out = pd.Series("그 외", index=length.index)
    for v, name in [(0.7, "0.7식"), (0.8, "0.8식"), (1.0, "1.0식")]:  # 겹치면 마지막(1.0식)이 남는다
        out[(seconds - (P["entry_seconds"] + length / v)).abs() <= P["formula_tolerance_s"]] = name
    return out


def recommend(cw: pd.DataFrame, target: float, market_all_elderly: bool = False) -> pd.DataFrame:
    r = P["radius_m"]
    tier = np.select([cw["보호구역_m"] <= r, cw["대형시장_m"] <= r], [1, 2], 3)
    resident = cw["반경고령비율"].values
    market = 1.0 if market_all_elderly else np.clip(resident + P["market_elderly_uplift"], 0, 1)
    # 커버리지를 볼 이용자 고령 비율: 1단계는 고령자 기준, 2단계는 주민 + 시장 보정, 3단계는 주민
    user_share = np.select([tier == 1, tier == 2], [1.0, market], resident)
    speed = np.where(tier == 1, P["tier1_speed_mps"], design_speed(user_share, target))
    L, T = cw["세로길이"], cw["보행시간"]
    rec = np.maximum(T, P["entry_seconds"] + L / speed)
    return pd.DataFrame({"단계": tier, "적용속도": speed, "추천시간": rec, "추가초": rec - T,
                         "이용자고령비율": user_share,
                         # 화면 커버리지는 고령 보행자 기준으로 통일한다(결정 009 검수 보완)
                         "커버리지_현재": coverage(L, T, 1.0),
                         "커버리지_추천": coverage(L, rec, 1.0)}, index=cw.index)


def reason(row) -> str:
    if row["단계"] == 1:
        base = f"노인보호구역 {row['보호구역_m']:.0f}m → 보호구역 기준 {row['적용속도']:.2f}m/s"
    elif row["단계"] == 2:
        base = (f"{row['대형시장명']} {row['대형시장_m']:.0f}m → 이용자 고령 비율 {row['이용자고령비율']:.0%}"
                f"(주민 {row['반경고령비율']:.0%} + 시장 보정) → {row['적용속도']:.2f}m/s")
    else:
        base = f"반경 {P['radius_m']}m 고령 비율 {row['반경고령비율']:.0%} → {row['적용속도']:.2f}m/s"
    tail = (f", 길이 {row['세로길이']:.0f}m → {row['추천시간']:.1f}초(+{row['추가초']:.1f})"
            if row["추가초"] > 1e-6 else ", 현재 시간으로 충분")
    return base + tail


def main():
    cw, counts = load_crosswalks()
    pz, big = load_protect_zones(), load_markets(big_only=True)
    cw["보호구역_m"], _ = nearest_m(cw["위도"], cw["경도"], pz["위도"], pz["경도"])
    cw["대형시장_m"], idx = nearest_m(cw["위도"], cw["경도"], big["위도"], big["경도"])
    cw["대형시장명"] = big["시장명"].values[idx]
    cw["반경고령비율"] = radius_elderly_ratio(cw["위도"].values, cw["경도"].values, P["radius_m"])
    cw["기준식"] = classify_formula(cw["세로길이"], cw["보행시간"])
    # 일반 기준식(1.0m/s)보다도 짧은 "그 외"는 기록 방식이 다를 수 있어 추천 집계에서 뺀다
    cw["데이터확인"] = (cw["기준식"] == "그 외") & (
        cw["보행시간"] < P["entry_seconds"] + cw["세로길이"] - P["formula_tolerance_s"])
    flagged = cw[cw["데이터확인"]]
    cw = cw[~cw["데이터확인"]]

    base = recommend(cw, P["target_coverage"])
    res = pd.concat([cw, base], axis=1)
    res["이유"] = res.apply(reason, axis=1)

    keep = ["순번", "행정구역(구)", "adm_nm", "교차로", "위도", "경도", "세로길이", "보행시간", "기준식",
            "반경고령비율", "보호구역_m", "대형시장명", "대형시장_m", "단계", "적용속도", "추천시간", "추가초",
            "커버리지_현재", "커버리지_추천", "이유"]
    OUT.mkdir(parents=True, exist_ok=True)
    res[keep].to_csv(OUT / "crosswalk_recommendations.csv", index=False, encoding="utf-8-sig")
    flagged[keep[:9]].to_csv(OUT / "crosswalk_data_check.csv", index=False, encoding="utf-8-sig")

    # ---------- 요약 ----------
    lines = ["# 부산 횡단보도 추천 보행시간 (시제품)", "",
             f"- 목표 커버리지 {P['target_coverage']:.0%}, 반경 {P['radius_m']}m, 보행진입시간 {P['entry_seconds']}초",
             f"- 행 수: " + " → ".join(f"{k} {v:,}" for k, v in counts.items()),
             f"- 부산 노인보호구역(노인) {len(pz)}곳, 대형 전통시장(점포 {P['big_market_min_stores']}개 이상, "
             f"산업용재 등 제외) {len(big)}곳", "",
             "## 기준식 분류 (현재 보행시간이 어느 식과 같은가)", "",
             md_table(pd.concat([res, flagged])["기준식"].value_counts()
                      .rename_axis("기준식").rename("횡단보도").reset_index()), "",
             f"## 데이터 확인 필요 {len(flagged)}곳 (추천 집계에서 제외)", "",
             f"- 보행시간이 일반 기준식(7 + L/1.0)보다도 짧은 곳. 구별: "
             + ", ".join(f"{k} {v}" for k, v in flagged["행정구역(구)"].value_counts().items()),
             "- 값이 대부분 `7 + n/0.7`(12.7, 15.6, 19.9초 …) 꼴인데 n이 세로길이보다 짧다. "
             "기록 방식이 다른지 담당 기관 확인 필요. 목록: `outputs/crosswalk_data_check.csv`", "",
             "## 단계별 결과", ""]
    tier_names = {1: "1 노인보호구역", 2: "2 대형 전통시장", 3: "3 주민 고령 비율"}
    g = res.groupby("단계").apply(lambda d: pd.Series({
        "횡단보도": len(d), "추가 필요": int((d["추가초"] > 1e-6).sum()),
        "2초 이상 추가": int((d["추가초"] >= 2).sum()),
        "평균 추가초(필요한 곳)": d.loc[d["추가초"] > 1e-6, "추가초"].mean(),
        "최대 추가초": d["추가초"].max(),
        "적용속도 범위": f"{d['적용속도'].min():.2f}~{d['적용속도'].max():.2f}",
        "커버리지 현재": d["커버리지_현재"].mean(), "커버리지 추천": d["커버리지_추천"].mean()}),
        include_groups=False).reset_index()
    g["단계"] = g["단계"].map(tier_names)
    lines += [md_table(g, pct_cols=("커버리지 현재", "커버리지 추천")), "",
              "커버리지는 고령 보행자 기준이다(단계끼리 같은 잣대). 이용자 구성은 적용 속도 계산에만 쓴다.", ""]

    lines += ["## 민감도 (목표 커버리지, 2단계 방식)", ""]
    sens = []
    for t, all_elderly in [(P["target_coverage"], False), *[(x, False) for x in P["coverage_sensitivity"]],
                           (P["target_coverage"], True)]:
        s = recommend(cw, t, market_all_elderly=all_elderly)
        sens.append({"목표": f"{t:.0%}" + (" · 2단계 전원 고령자(국토부 방식)" if all_elderly else ""),
                     "추가 필요": int((s["추가초"] > 1e-6).sum()),
                     "2초 이상": int((s["추가초"] >= 2).sum()),
                     "평균 추가초(필요한 곳)": s.loc[s["추가초"] > 1e-6, "추가초"].mean(),
                     "3단계 속도 범위": f"{s.loc[s['단계'] == 3, '적용속도'].min():.2f}~"
                                     f"{s.loc[s['단계'] == 3, '적용속도'].max():.2f}"})
    lines += [md_table(pd.DataFrame(sens)), ""]

    lines += ["## 정책 반영 점검(V7): 0.7식 비율", ""]
    cz = load_child_zones()
    res["어린이보호_m"], _ = nearest_m(res["위도"], res["경도"], cz["위도"], cz["경도"])
    old_zone, child = res["보호구역_m"] <= P["radius_m"], res["어린이보호_m"] <= P["child_zone_radius_m"]
    is07 = res["기준식"] == "0.7식"
    v7 = [{"위치": name, "횡단보도": int(m.sum()), "0.7식": int((m & is07).sum()), "비율": (m & is07).sum() / m.sum()}
          for name, m in [(f"노인보호구역 {P['radius_m']}m 안", old_zone),
                          (f"어린이보호구역 {P['child_zone_radius_m']}m 안(노인 아님)", child & ~old_zone),
                          ("둘 다 밖", ~old_zone & ~child)]]
    lines += [md_table(pd.DataFrame(v7), pct_cols=("비율",)), ""]

    area = res.groupby("adm_nm").agg(n=("추가초", "size"), mean_add_s=("추가초", "mean"),
                                     n_add2=("추가초", lambda x: int((x >= P["add_seconds_threshold"]).sum())))
    area = area[area["n"] >= 5]
    lines += ["## 읍면동 평균 추가 초 (표본 5곳 이상)", "",
              f"- {len(area)}개 동, 평균 추가 초 분위(10/50/90%): "
              + " / ".join(f"{area['mean_add_s'].quantile(q):.2f}" for q in (0.1, 0.5, 0.9)) + "초", ""]

    lines += ["## 추가 초가 큰 15곳", "",
              md_table(res.sort_values("추가초", ascending=False).head(15)[
                  ["행정구역(구)", "교차로", "세로길이", "보행시간", "추천시간", "추가초", "이유"]]), ""]
    lines += ["## 한계", "",
              "1. 보행시간 = 녹색 + 점멸 가정(정의 미확정). 커버리지는 이 가정 위의 값이다.",
              "2. 보행속도 분포는 한 연구(한음 외 2020) 초록의 평균·15퍼센타일을 정규분포로 근사했다.",
              "3. 주민 고령 비율은 사는 사람 기준이다. 실제 건너는 사람 구성과 다를 수 있다.",
              "4. 보호구역·시장은 점 좌표라 실제 구역 범위와 반경 원이 다를 수 있다.",
              "5. 커버리지는 시간 안에 건널 수 있는 보행자 비율이지 추천의 정답 확률이 아니다.", ""]
    (OUT / "recommend_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
