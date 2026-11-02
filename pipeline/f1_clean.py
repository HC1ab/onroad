#!/usr/bin/env python3
"""
F1 정제 — 판정에 쓸 수 있는 횡단보도만 남긴다 (PRD F1, A-pipeline).

사용법 (repo 루트에서):
    python3 pipeline/f1_clean.py                      # data/raw/crosswalk/ 의 가장 최근 *_api_*.csv
    python3 pipeline/f1_clean.py --input <CSV 경로>

입력: R1 전국횡단보도표준데이터 (fetch_api.py 로 받은 API CSV, 영문 칼럼명)
출력 (data/interim/ — .gitignore 대상, 공개 repo 에 올라가지 않음):
    f1_crosswalk.csv     전체 행 + excluded_reason (빈칸 = 분석 대상). 이후 F2~F4 의 입력
    f1_exclusions.csv    제외 사유별 건수 (PRD F1 인수 조건: "제외 사유별 건수가 표로 나온다")
    f1_by_region.csv     시도·시군구별 전체/분석 대상 건수 (커버리지 확인용)
    f1_meta.json         입력 파일, 설정값, 건수 (재현·meta.json 작성용)

원칙
- 원본은 읽기만 한다. 결측을 채우거나 값을 고치지 않는다 (CLAUDE.md, 결측 채우기는 이슈 합의 전 금지).
- 한 행에는 '처음 걸린' 제외 사유 하나만 붙인다 → 사유별 건수의 합 = 제외 건수.
- 이상치 상한은 config.yaml 에서만 읽는다.
- 전화번호·담당자 칼럼은 결과에 넣지 않는다 (CLAUDE.md R4).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent          # repo 루트
RAW_DIR = ROOT / "data" / "raw" / "crosswalk"
OUT_DIR = ROOT / "data" / "interim"

# API 영문 칼럼 → pipeline 공통 이름 (PRD 9장 crosswalk 테이블 이름에 맞춤). 여기 없는 칼럼은 버린다.
COLUMNS = {
    "insttCode": "provider_code", "crslkManageNo": "manage_no",
    "ctprvnNm": "sido", "signguNm": "sigungu",
    "rdnmadr": "addr_road", "lnmadr": "addr_jibun",
    "latitude": "lat", "longitude": "lon",
    "cartrkCo": "lanes", "et": "length_m",
    "greenSgngnrTime": "green_s", "redSgngnrTime": "red_s",
    "tfclghtYn": "signal_yn", "referenceDate": "reference_date",
}
NUMERIC = ["lat", "lon", "lanes", "length_m", "green_s", "red_s"]
# 한국 영역 대략 범위 (위경도 뒤바뀜·오입력 걸러내기용, 데이터 점검 기준이라 config 가 아닌 여기 둔다)
KOREA_LAT, KOREA_LON = (33.0, 39.0), (124.0, 132.0)
# 같은 횡단보도로 볼 키 (관리번호는 교차로 단위라 단독으로는 중복 판정에 못 씀)
DUP_KEY = ["provider_code", "manage_no", "lat", "lon", "length_m", "green_s"]


def load_config() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def latest_input() -> Path:
    files = sorted(RAW_DIR.glob("*_api_*.csv"))
    if not files:
        sys.exit(f"{RAW_DIR} 에 API CSV 가 없습니다. 먼저 python3 pipeline/fetch_api.py fetch R1")
    return files[-1]


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"필요한 칼럼이 없습니다: {missing}")
    df = df[list(COLUMNS)].rename(columns=COLUMNS)
    for c in NUMERIC:                                   # 숫자가 아니면 NaN (값을 추정해 채우지 않음)
        df[c] = pd.to_numeric(df[c].str.strip(), errors="coerce")
    return df


def assign_ids(df: pd.DataFrame) -> pd.DataFrame:
    """cw_id = 제공기관코드-관리번호-순번. 관리번호가 교차로 단위라 같은 번호 안에서 위치·연장 순으로 번호를 붙인다.
    같은 입력 파일이면 항상 같은 id 가 나온다 (데이터가 갱신되면 바뀔 수 있음)."""
    df = df.sort_values(["provider_code", "manage_no", "lat", "lon", "length_m", "reference_date"], kind="mergesort")
    seq = df.groupby(["provider_code", "manage_no"]).cumcount() + 1
    df.insert(0, "cw_id", df["provider_code"] + "-" + df["manage_no"] + "-" + seq.astype(str))
    return df.reset_index(drop=True)


def apply_rules(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    max_len, max_green = cfg["outlier"]["max_length_m"], cfg["outlier"]["max_green_s"]
    # 중복: 같은 키 중 기준일이 가장 최신인 행만 남긴다
    newest_first = df.sort_values("reference_date", ascending=False, kind="mergesort")
    dup = newest_first.duplicated(DUP_KEY, keep="first").reindex(df.index)
    rules = [  # (사유, 조건, 설명) — 위에서부터 처음 걸린 사유 하나만 기록
        ("중복 행", dup, "제공기관·관리번호·좌표·연장·녹색이 같은 행 중 최신 기준일 외"),
        ("좌표 없음·범위 밖", df.lat.isna() | df.lon.isna() | ~df.lat.between(*KOREA_LAT) | ~df.lon.between(*KOREA_LON),
         "읍면동에 배정할 수 없음"),
        ("연장 없음·0 이하", df.length_m.isna() | (df.length_m <= 0), "필요시간(7+L/v)을 계산할 수 없음"),
        ("녹색 없음·0 이하", df.green_s.isna() | (df.green_s <= 0), "비교할 기록값이 없음"),
        (f"연장 {max_len}m 초과", df.length_m > max_len, "입력 오류로 봄 (config.yaml outlier.max_length_m)"),
        (f"녹색 {max_green}s 초과", df.green_s > max_green, "입력 오류로 봄 (config.yaml outlier.max_green_s)"),
    ]
    reason = pd.Series("", index=df.index)
    for name, cond, _ in rules:
        reason = reason.mask((reason == "") & cond.fillna(False), name)
    df["excluded_reason"] = reason
    # 빼지는 않지만 표시: 신호등 유무가 N 인데 녹색신호시간이 있음 (데이터 표기 불일치)
    df["signal_conflict"] = (df.signal_yn != "Y") & (df.green_s > 0)
    return df, [(n, d) for n, _, d in rules]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path)
    args = ap.parse_args()
    src = args.input or latest_input()
    cfg = load_config()

    df = assign_ids(load(src))
    df, rules = apply_rules(df, cfg)
    n, kept = len(df), (df.excluded_reason == "").sum()

    # 제외 사유별 건수표 (합계 = 전체 − 분석 대상)
    ex = pd.DataFrame([(name, int((df.excluded_reason == name).sum()), desc) for name, desc in rules],
                      columns=["사유", "건수", "설명"])
    ex["비율"] = (ex["건수"] / n).map(lambda v: f"{v:.1%}")
    region = (df.assign(kept=df.excluded_reason == "")
                .groupby(["sido", "sigungu"]).agg(전체=("cw_id", "size"), 분석대상=("kept", "sum"))
                .reset_index().sort_values("분석대상", ascending=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "f1_crosswalk.csv", index=False, encoding="utf-8")
    ex.to_csv(OUT_DIR / "f1_exclusions.csv", index=False, encoding="utf-8-sig")
    region.to_csv(OUT_DIR / "f1_by_region.csv", index=False, encoding="utf-8-sig")
    meta = {
        "step": "F1", "input": str(src.relative_to(ROOT)),
        "run_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "config": {"outlier": cfg["outlier"]},
        "rows": int(n), "kept": int(kept), "excluded": int(n - kept),
        "exclusions": {r: int(c) for r, c in zip(ex["사유"], ex["건수"])},
        "signal_conflict_kept": int((df.signal_conflict & (df.excluded_reason == "")).sum()),
        "regions_with_kept": int((region["분석대상"] > 0).sum()),
    }
    (OUT_DIR / "f1_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 화면 출력 (PRD 인수 조건: 표로)
    print(f"입력: {meta['input']} ({n:,}행)")
    print(f"분석 대상: {kept:,}행 ({kept / n:.1%}) · 제외 {n - kept:,}행\n")
    print("| 제외 사유 | 건수 | 비율 |\n| --- | ---: | ---: |")
    for _, r in ex.iterrows():
        print(f"| {r['사유']} | {r['건수']:,} | {r['비율']} |")
    print(f"| **합계** | **{n - kept:,}** | {(n - kept) / n:.1%} |")
    print(f"\n분석 대상이 있는 시군구: {meta['regions_with_kept']}곳")
    print(f"신호등 유무 N 이지만 녹색신호시간이 있어 남긴 행: {meta['signal_conflict_kept']:,}")
    print(f"\n결과: {OUT_DIR.relative_to(ROOT)}/f1_crosswalk.csv 외 3개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
