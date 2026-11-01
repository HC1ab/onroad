"""부산 F3 판정: 속도별 필요 시간(T_need)과 기록값과의 차이(gap) 계산.

    T_need(v) = entry_seconds + length_m / v        (config.yaml: entry_seconds, speeds_mps)
    gap(v)    = T_need(v) - green_s                 (green_s = 부산 엑셀의 '보행시간')

해석 규칙 (R5)
    - gap > 0  → "기록값이 기준식보다 짧음". 위험·위반 같은 표현을 쓰지 않는다.
    - 보행시간의 정의(녹색 + 점멸)는 확정 전 가정이다. 수치는 "gap>0 비율, 정의 미확정"으로 읽는다.

추가 분류: 보행시간이 어느 속도의 기준식 값과 같은지(formula_class).
    부산 보행시간은 대부분 기준식 값이라, gap 이 "노인 기준(0.7)을 반영했는가"의 신호가 된다.
"""
from __future__ import annotations

import pandas as pd

# 부동소수점 오차를 무시하는 허용치(초). 분석 설정이 아니라 수치 비교용 한계다.
# 엑셀이 소수 값(예: 15.5714...)을 그대로 저장해 두어 같은 식으로 계산해도 1e-15 정도 어긋날 수 있다.
FLOAT_TOL_S = 1e-6


def speed_key(v: float) -> str:
    """속도를 파일명·열 이름에 쓰는 문자열로 (0.7 → '0.7', 1 → '1.0')."""
    return f"{v:.1f}"


def t_need(length_m: pd.Series, speed: float, entry_s: float) -> pd.Series:
    return entry_s + length_m / speed


def is_short(gap: pd.Series) -> pd.Series:
    """gap > 0 인가. 오차 범위 안의 차이는 같음으로 본다."""
    return gap > FLOAT_TOL_S


def judge(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """속도마다 t_need_<v>, gap_<v> 열과 formula_class 를 붙여 돌려준다."""
    out = df.copy()
    entry = cfg["entry_seconds"]
    speeds = list(cfg["speeds_mps"])
    for v in speeds:
        k = speed_key(v)
        out[f"t_need_{k}"] = t_need(out["length_m"], v, entry)
        out[f"gap_{k}"] = out[f"t_need_{k}"] - out["green_s"]

    # 어느 속도의 기준식과 같은지. 먼저 맞는 속도(config 순서)가 우선이다.
    cls = pd.Series("other", index=out.index, dtype="object")
    for v in reversed(speeds):
        k = speed_key(v)
        cls[(out[f"gap_{k}"].abs() <= FLOAT_TOL_S)] = f"v{k}"
    out["formula_class"] = cls
    return out


def formula_table(judged: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """기준식 분류별 건수표와 속도별 gap>0 건수표를 하나로 합쳐 출력용으로 돌려준다."""
    n = len(judged)
    rows = []
    for v in cfg["speeds_mps"]:
        k = speed_key(v)
        rows.append({"구분": f"보행시간 = {k}m/s 기준식 값", "건수": int((judged["formula_class"] == f"v{k}").sum())})
    rows.append({"구분": "어느 기준식과도 다름", "건수": int((judged["formula_class"] == "other").sum())})
    for v in cfg["speeds_mps"]:
        k = speed_key(v)
        rows.append({"구분": f"gap>0 (기록값이 {k}m/s 기준식보다 짧음)", "건수": int(is_short(judged[f"gap_{k}"]).sum())})
    t = pd.DataFrame(rows)
    t["비율(%)"] = (t["건수"] / n * 100).round(2) if n else 0.0
    return t
