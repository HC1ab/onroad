"""v2 보행속도 분포·적용 속도·커버리지 (결정 009). 순수 함수만 두고 입출력은 하지 않는다.

모형
    - 일반인·고령자 보행속도는 각각 정규분포라고 가정한다(가정; 결정 009 한계 2).
      평균과 15퍼센타일 두 값(config walking_speed_mps)에서 표준편차를 구한다.
    - 이용자 고령 비율이 p 이면 속도 분포는 두 분포를 (1-p):p 로 섞은 것이다.
    - 적용 속도 v: 섞은 분포에서 "v 보다 느린 사람"이 (1 - target) 이 되는 속도. 공식 범위로 자른다.
    - 커버리지: 보행시간 안에 길이를 건널 수 있는 사람의 비율. 화면 값은 고령 보행자(p=1) 기준이다.
설정은 모두 config.yaml 에서 읽어 인자로 받는다. 코드에 분석 숫자를 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

# 이분법으로 속도를 찾는 탐색 구간(m/s). 보행속도로 가능한 범위를 충분히 덮는 수치 장치이며 분석 설정이 아니다.
SEARCH_LO, SEARCH_HI = 0.05, 4.0
BISECT_ITERS = 60


@dataclass(frozen=True)
class SpeedModel:
    """일반·고령 보행속도 정규분포 (평균, 표준편차)."""
    general: tuple[float, float]
    elderly: tuple[float, float]

    @classmethod
    def from_config(cls, cfg: dict, elderly_p15: float | None = None) -> "SpeedModel":
        """config 의 평균·15퍼센타일로 만든다. elderly_p15 로 고령자 15퍼센타일만 바꿔 민감도를 볼 수 있다."""
        z = norm.ppf(0.85)  # 15퍼센타일 = 평균 - z * 표준편차
        sw = cfg["walking_speed_mps"]

        def dist(group: str, p15: float | None = None) -> tuple[float, float]:
            mean = sw[group]["mean"]
            p15 = sw[group]["p15"] if p15 is None else p15
            if not mean > p15:
                raise ValueError(f"{group}: 평균({mean})이 15퍼센타일({p15})보다 커야 한다")
            return mean, (mean - p15) / z

        return cls(general=dist("general"), elderly=dist("elderly", elderly_p15))


def slower_share(v, elderly_share, model: SpeedModel) -> np.ndarray:
    """속도 v 보다 느린 사람의 비율. 일반·고령 분포를 고령 비율로 섞는다."""
    p = np.asarray(elderly_share, dtype=float)
    return (1 - p) * norm.cdf(v, *model.general) + p * norm.cdf(v, *model.elderly)


def coverage(length_m, seconds, entry_s: float, model: SpeedModel, elderly_share=1.0) -> np.ndarray:
    """보행시간(seconds) 안에 길이를 건널 수 있는 사람의 비율.

    진입 시간(entry_s)을 뺀 나머지로 건너야 하므로 필요한 속도 = L / (seconds - entry_s).
    남은 시간이 0 이하이면 아무도 건널 수 없으므로 0 이다.
    """
    length = np.asarray(length_m, dtype=float)
    left = np.asarray(seconds, dtype=float) - entry_s
    need = np.where(left > 0, length / np.where(left > 0, left, 1.0), np.inf)
    return 1 - slower_share(need, elderly_share, model)


def design_speed(elderly_share, target: float, model: SpeedModel, bounds: tuple[float, float]) -> np.ndarray:
    """섞인 분포에서 target 비율이 건널 수 있는 속도(이분법). bounds 로 자른다."""
    if not 0 < target < 1:
        raise ValueError("target 은 0~1 사이여야 한다")
    p = np.atleast_1d(np.asarray(elderly_share, dtype=float))
    lo = np.full_like(p, SEARCH_LO)
    hi = np.full_like(p, SEARCH_HI)
    for _ in range(BISECT_ITERS):
        mid = (lo + hi) / 2
        too_fast = slower_share(mid, p, model) > 1 - target  # 이 속도보다 느린 사람이 너무 많다
        hi = np.where(too_fast, mid, hi)
        lo = np.where(too_fast, lo, mid)
    return np.clip((lo + hi) / 2, bounds[0], bounds[1])


def required_time(green_s, length_m, speed, entry_s: float) -> np.ndarray:
    """기준 적용 시 시간 = max(기록 보행시간, 진입 + L / v). 기록값보다 줄이지 않는다."""
    return np.maximum(np.asarray(green_s, dtype=float), entry_s + np.asarray(length_m, dtype=float) / speed)
