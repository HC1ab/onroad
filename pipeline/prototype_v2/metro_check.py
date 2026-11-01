"""2단계 규칙 검증: 대형 전통시장 근처 지하철역은 주민 고령 비율을 감안해도 무임 승차 비율이 높은가.

무임 승차 비율 = 무임 / 승차 (부산교통공사, 무임은 경로·장애인·유공자 포함).
주민 고령 비율(역 반경 안 행정동 면적 가중)로 회귀한 잔차를 시장 근처 역과 그 외 역으로 비교한다.

사용: python pipeline/prototype_v2/metro_check.py
"""
import re

import numpy as np
import pandas as pd

from common import OUT, P, RAW, load_markets, md_table, nearest_m, radius_elderly_ratio


def norm(name: str) -> str:
    name = re.sub(r"\(\d호선\)", "", str(name).strip()).replace("·", "")
    return re.sub(r"역$", "", re.sub(r"^\d", "", name))


def load_stations() -> tuple[pd.DataFrame, list]:
    m = pd.read_csv(next((RAW / "metro_ticket").glob("*.csv")), encoding="utf-8-sig")
    m = m[m["연월"].str.startswith(P["metro_year"])]
    m["역"] = m["역명"].map(norm)
    st = m.groupby("역")[["승차", "무임"]].sum()
    st = st[st["승차"] > 0]
    c = pd.read_csv(RAW / "station" / "전국도시철도역사정보표준데이터.csv")
    c = c[c["운영기관명"] == "부산교통공사"].copy()
    c["역"] = c["역사명"].map(norm)
    c["구"] = c["역사도로명주소"].str.extract(r"부산광역시\s+(\S+[구군])")[0]
    c = c.groupby("역").agg(lat=("역위도", "mean"), lon=("역경도", "mean"), 구=("구", "first"))
    st = st.join(c, how="left")
    missing = st.index[st["lat"].isna()].tolist()
    st = st.dropna(subset=["lat"]).copy()
    st["무임비율"] = st["무임"] / st["승차"]
    return st, missing


def ols_resid(y, X):
    X = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta, beta


def main():
    st, missing = load_stations()
    big = load_markets(big_only=True)
    allm = load_markets()
    st["반경고령비율"] = radius_elderly_ratio(st["lat"].values, st["lon"].values, P["metro_radius_m"])
    outside = st.index[st["반경고령비율"].isna()].tolist()  # 양산 등 부산 밖 역
    st = st.dropna(subset=["반경고령비율"]).copy()
    missing += [f"{s}(부산 밖)" for s in outside]
    st["대형시장_m"], _ = nearest_m(st["lat"], st["lon"], big["위도"], big["경도"])
    st["시장_m"], _ = nearest_m(st["lat"], st["lon"], allm["위도"], allm["경도"])

    y = st["무임비율"].values
    resid, beta = ols_resid(y, st["반경고령비율"].values)
    st["잔차"] = resid
    rng = np.random.default_rng(P["seed"])

    rows = []
    for label, flag in [("대형 시장 300m 안", st["대형시장_m"] <= 300), ("대형 시장 500m 안", st["대형시장_m"] <= 500),
                        ("모든 시장 300m 안", st["시장_m"] <= 300), ("모든 시장 500m 안", st["시장_m"] <= 500)]:
        f = flag.values
        raw = y[f].mean() - y[~f].mean()
        adj = resid[f].mean() - resid[~f].mean()
        perm = np.array([(lambda g: resid[g].mean() - resid[~g].mean())(rng.permutation(f))
                         for _ in range(P["permutations"])])
        p = (np.sum(perm >= adj) + 1) / (len(perm) + 1)
        rows.append({"기준": label, "근처 역": int(f.sum()), "그 외 역": int((~f).sum()),
                     "단순 차이(%p)": raw * 100, "고령 비율 감안 차이(%p)": adj * 100, "단측 p": f"{p:.4f}"})
    res = pd.DataFrame(rows)

    corr = np.corrcoef(st["반경고령비율"], y)[0, 1]
    lines = ["# 2단계 규칙 검증: 대형 전통시장 근처 역의 무임 승차 비율", "",
             f"- 부산교통공사 {P['metro_year']}년, 역 {len(st)}곳 (좌표 없음 {len(missing)}: {', '.join(missing)})",
             f"- 대형 시장 = 점포 {P['big_market_min_stores']}개 이상, 산업용재 등 제외 ({len(big)}곳). 모든 시장 {len(allm)}곳",
             f"- 역 반경 {P['metro_radius_m']}m 주민 고령 비율과 무임 비율의 상관계수 {corr:.2f}, "
             f"회귀 기울기 {beta[1]:.2f} (고령 비율 10%p ↑ → 무임 비율 {beta[1] * 10:.1f}%p ↑)",
             f"- 순열 검정 {P['permutations']:,}회, 시드 {P['seed']}. 기준 4개를 함께 봤으므로 p는 여러 번 비교한 값이다", "",
             md_table(res, digits=2), "",
             "## 해석", "",
             "- '고령 비율 감안 차이'는 주민 고령 비율로 설명되는 부분을 뺀 뒤 남는 차이다. "
             "양수이고 p가 작으면, 시장이 주민 구성과 별개로 고령 이용자를 끌어들인다는 근거가 된다.",
             "- 무임에는 장애인·국가유공자가 섞여 있고, 역 근처만 볼 수 있다.", "",
             "## 대형 시장 300m 안 역", "",
             md_table(st[st["대형시장_m"] <= 300].sort_values("무임비율", ascending=False)
                      .reset_index()[["역", "구", "무임비율", "반경고령비율", "잔차", "대형시장_m"]], digits=3), ""]
    OUT.mkdir(exist_ok=True)
    (OUT / "metro_check.md").write_text("\n".join(lines), encoding="utf-8")
    st.to_csv(OUT / "metro_stations.csv", encoding="utf-8-sig")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
