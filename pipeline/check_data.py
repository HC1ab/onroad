#!/usr/bin/env python3
"""
한 박자 — 공공데이터 점검 스크립트 (게이트 A~D)

사용법 (repo 루트에서):
    python3 pipeline/check_data.py
결과 (data/interim/ 은 .gitignore 대상 — 공개 repo 에 수치가 바로 올라가지 않게 로컬에만 둔다):
    data/interim/data_check_report.md  — 데이터별 점검 결과 (수집 가이드 5장 보고 양식 기준)
    data/interim/inventory.csv         — 파일별 행 수·인코딩·크기·해시 목록
이슈 코멘트로 옮길 때는 R5 규칙대로 "gap>0 비율, 정의 미확정"으로 쓴다.

설계 원칙
- 표준 라이브러리만 사용한다 (XLSX만 openpyxl이 있으면 읽는다). 팀원 PC 어디서나 돌도록.
- 원본은 읽기만 하고 절대 수정하지 않는다 (가이드 1장 원본 보관 규칙).
- 칼럼명은 실제 파일을 보기 전이라 '키워드 포함'으로 자동 탐지한다.
  탐지가 틀리면 아래 COLUMN_OVERRIDES에 실제 칼럼명을 적으면 그 값이 우선한다.
- 판정 문구는 PRD 표현 원칙을 따른다: '부족' 대신 '기록값이 기준식보다 짧음'.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 설정 (PRD config.yaml 초안과 같은 값)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent      # repo 루트
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "data" / "interim"


def load_config() -> dict:
    """분석 설정값은 config.yaml 에서만 읽는다 (CLAUDE.md 기술 고정 사항)."""
    try:
        import yaml
    except ImportError:
        sys.exit("config.yaml 을 읽으려면 PyYAML 이 필요합니다: pip install pyyaml")
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


CFG = load_config()
ENTRY_S = float(CFG["entry_seconds"])                 # 진입시간 (초)
SPEEDS = tuple(float(v) for v in CFG["speeds_mps"])   # 보행속도 (m/s)
MAX_LEN_M = CFG["outlier"]["max_length_m"]            # 이상치 상한 (PRD F1)
MAX_GREEN_S = CFG["outlier"]["max_green_s"]
# 아래 세 값은 분석 설정이 아니라 '데이터 점검'용 경고선·대조값이라 여기에 둔다
GRID_LIMIT = 50_000           # R1 그리드 다운로드 행 한도 (페이지 안내)
GATE_A_HIGH, GATE_A_LOW = 0.40, 0.01  # 1.0m/s 짧음 비율 경고선 (PRD 게이트 A)
GANGSEO_SENIOR_CENTERS = 168  # 부산 강서구 경로당 공개 현황 (교차 확인용)

# 데이터 ID → 폴더 (수집 가이드 1장 구조)
FOLDERS = {
    "R1": "crosswalk", "R2": "admin_boundary", "R3": "population_65",
    "R4": "crash_zone", "O1": "protect_zone", "O2": "senior_center",
    "O3": "market", "O4": "hospital",
}
NAMES = {
    "R1": "전국횡단보도표준데이터", "R2": "admdongkor 읍면동 경계",
    "R3": "행정동별 고령 인구현황(행안부)", "R4": "노인 보행사고 다발지역 API",
    "O1": "전국노인장애인보호구역표준데이터", "O2": "전국마을회관및경로당표준데이터",
    "O3": "전국전통시장표준데이터", "O4": "HIRA 병원정보서비스",
}

# 자동 탐지가 틀렸을 때 실제 칼럼명을 적는다. 예: {"R1": {"green": "녹색신호시간(초)"}}
COLUMN_OVERRIDES: dict[str, dict[str, str]] = {}

# 역할별 칼럼 탐지 키워드 (앞쪽 키워드가 우선). exclude에 걸리면 후보에서 뺀다.
KEYWORDS = {
    "sido":    (["시도명", "시도"], []),
    "sigungu": (["시군구명", "시군구"], []),
    "length":  (["횡단보도연장", "연장"], []),
    "green":   (["녹색신호시간", "녹색"], []),
    "red":     (["적색신호시간", "적색"], []),
    "lat":     (["위도"], []),
    "lon":     (["경도"], []),
    "code":    (["행정기관코드", "행정동코드", "행정코드", "코드"], ["제공기관", "관리기관"]),
    "total":   (["총인구", "전체인구", "인구수", "총계", "_전체", "전체"], ["65", "고령", "남", "여"]),
    "age65":   (["65세이상", "65세 이상", "고령인구", "65"], ["남", "여", "비율"]),
    "type":    (["시설유형", "시설구분", "유형"], []),
    "status":  (["영업상태", "운영상태", "상태"], []),
}


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------
def read_table(path: Path) -> tuple[list[str], list[dict], str]:
    """CSV/XLSX를 (칼럼, 행, 인코딩)으로 읽는다. CSV는 인코딩을 차례로 시도한다."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            import openpyxl  # 선택 의존성
        except ImportError:
            raise RuntimeError("XLSX를 읽으려면 openpyxl이 필요합니다 (pip install openpyxl). 또는 CSV로 받으세요.")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        rows = [["" if v is None else str(v).strip() for v in r] for r in ws.iter_rows(values_only=True)]
        hdr_i = _guess_header_row(rows)
        cols = _dedupe(rows[hdr_i])
        return cols, [dict(zip(cols, r)) for r in rows[hdr_i + 1:] if any(r)], "xlsx"
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError("인코딩을 판별하지 못했습니다 (utf-8 / cp949 모두 실패)")
    rows = list(csv.reader(text.splitlines()))
    hdr_i = _guess_header_row(rows)
    cols = _dedupe([c.strip() for c in rows[hdr_i]])
    return cols, [dict(zip(cols, [v.strip() for v in r])) for r in rows[hdr_i + 1:] if any(r)], enc


def _guess_header_row(rows: list[list[str]]) -> int:
    """행안부 통계처럼 위에 제목 줄이 붙은 파일 대비: 앞 10줄 중 채워진 칸이 가장 많은 줄을 헤더로 본다."""
    head = rows[:10]
    return max(range(len(head)), key=lambda i: sum(1 for v in head[i] if str(v).strip())) if head else 0


def _dedupe(cols: list[str]) -> list[str]:
    seen: Counter = Counter()
    out = []
    for c in cols:
        seen[c] += 1
        out.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
    return out


def find_col(ds: str, role: str, cols: list[str]) -> str | None:
    """역할(role)에 맞는 칼럼을 찾는다. 공백을 무시하고 키워드 포함 여부로 판단."""
    if role in COLUMN_OVERRIDES.get(ds, {}):
        return COLUMN_OVERRIDES[ds][role]
    inc, exc = KEYWORDS[role]
    norm = {c: c.replace(" ", "") for c in cols}
    for kw in inc:
        k = kw.replace(" ", "")
        for c in cols:
            if k in norm[c] and not any(e in norm[c] for e in exc):
                return c
    return None


def num(v) -> float | None:
    """'1,234' 같은 문자열을 숫자로. 비었거나 숫자가 아니면 None."""
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}% ({a:,}/{b:,})" if b else "— (0건)"


def fill_rate(rows: list[dict], col: str | None, positive: bool = False) -> str:
    """입력률: 비어 있지 않은 비율. positive=True면 0 초과 숫자 비율도 함께."""
    if not col:
        return "칼럼 찾지 못함"
    n = len(rows)
    filled = sum(1 for r in rows if str(r.get(col, "")).strip())
    out = f"비어있지 않음 {pct(filled, n)}"
    if positive:
        pos = sum(1 for r in rows if (num(r.get(col)) or 0) > 0)
        out += f" · 0 초과 {pct(pos, n)}"
    return out


def files_of(ds: str, exts: tuple[str, ...]) -> list[Path]:
    d = RAW / FOLDERS[ds]
    return sorted(p for p in d.glob("*") if p.is_file() and p.suffix.lower() in exts) if d.exists() else []


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# 데이터별 점검
# ---------------------------------------------------------------------------
TABLE_EXT = (".csv", ".xlsx", ".xlsm")
inventory: list[dict] = []   # reports/inventory.csv
summary: dict[str, str] = {}  # 게이트 요약표용 한 줄 상태


def load_one(ds: str, out: list[str]):
    """폴더의 표 파일을 읽어 (경로, 칼럼, 행, 인코딩) 반환. 없거나 실패하면 None."""
    fs = files_of(ds, TABLE_EXT)
    if not fs:
        out.append(f"- 상태: **파일 없음** — `data/raw/{FOLDERS[ds]}/`에 내려받은 파일을 넣어 주세요.")
        summary[ds] = "파일 없음"
        return None
    if len(fs) > 1:
        out.append(f"- 참고: 파일이 {len(fs)}개라 첫 파일 `{fs[0].name}`만 점검했습니다. 나머지: " + ", ".join(f.name for f in fs[1:]))
    p = fs[0]
    try:
        cols, rows, enc = read_table(p)
    except Exception as e:  # 읽기 실패는 그대로 보고 (가이드: 막힌 점을 그대로 적는다)
        out.append(f"- 상태: **읽기 실패** — `{p.name}`: {e}")
        summary[ds] = "읽기 실패"
        return None
    inventory.append({"id": ds, "file": f"{FOLDERS[ds]}/{p.name}", "rows": len(rows),
                      "encoding": enc, "bytes": p.stat().st_size, "sha256_16": sha256(p)})
    out += [f"- 파일: `{p.name}` ({p.stat().st_size / 1e6:.1f} MB)",
            f"- 인코딩: {enc}", f"- 행 수: {len(rows):,}",
            f"- 칼럼 {len(cols)}개: " + ", ".join(f"`{c}`" for c in cols)]
    return p, cols, rows, enc


def check_r1(out: list[str]):
    """R1 횡단보도 — 게이트 A."""
    got = load_one("R1", out)
    if not got:
        return
    _, cols, rows, _ = got
    c = {k: find_col("R1", k, cols) for k in ("sido", "sigungu", "length", "green", "red", "lat", "lon")}
    out.append("- 칼럼 자동 탐지: " + ", ".join(f"{k}→`{v}`" if v else f"{k}→**찾지 못함**" for k, v in c.items()))
    if len(rows) in (GRID_LIMIT, GRID_LIMIT - 1) or len(rows) % 10_000 == 0:
        out.append(f"- ⚠ 행 수가 {len(rows):,}건으로 딱 떨어집니다. 그리드 다운로드 한도(5만 행)에서 잘렸는지 확인하세요.")
    if len(cols) != 25:
        out.append(f"- 참고: 칼럼 수가 페이지 요약(25개)과 다릅니다 ({len(cols)}개).")

    out.append("- 핵심 필드 입력률:")
    for k, positive in (("length", True), ("green", True), ("red", True), ("lat", True), ("lon", True)):
        out.append(f"  - {k}: {fill_rate(rows, c[k], positive)}")

    # 녹색신호시간 빈칸이 '신호등 없는 횡단보도'라서인지, 신호 횡단보도의 입력 누락인지 나눠 본다
    sig_col = next((x for x in cols if "보행자신호등" in x), None)
    if sig_col and c["green"]:
        out.append(f"- 녹색신호시간 입력률 (`{sig_col}`별):")
        for val, grp in sorted(Counter(r.get(sig_col, "") or "(빈칸)" for r in rows).items()):
            sub = [r for r in rows if (r.get(sig_col, "") or "(빈칸)") == val]
            out.append(f"  - {val}: {fill_rate(sub, c['green'], True)}")
        sido_col = c["sido"]
        if sido_col:
            sig = [r for r in rows if r.get(sig_col, "") == "Y"]
            by = Counter(r.get(sido_col, "") for r in sig)
            filled = Counter(r.get(sido_col, "") for r in sig if (num(r.get(c["green"])) or 0) > 0)
            out.append("  - 신호 횡단보도(Y)의 시도별 녹색신호시간 입력률: "
                       + ", ".join(f"{k} {filled[k] / v:.0%}({v:,})" for k, v in by.most_common()))

    busan = [r for r in rows if c["sido"] and "부산" in r.get(c["sido"], "")]
    out.append(f"- 부산 행 수: {len(busan):,}")
    if busan and c["sigungu"]:
        cnt = Counter(r.get(c["sigungu"], "") or "(빈칸)" for r in busan)
        out.append("  - 시군구별: " + ", ".join(f"{k} {v:,}" for k, v in cnt.most_common()))

    if not (c["length"] and c["green"]):
        out.append("- 게이트 A 계산 불가: 연장 또는 녹색신호시간 칼럼을 찾지 못했습니다. COLUMN_OVERRIDES를 채워 주세요.")
        summary["R1"] = "칼럼 확인 필요"
        return

    # PRD F1 정제 규칙 + 제외 사유별 건수
    def clean(rs):
        ok, why = [], Counter()
        for r in rs:
            L, G = num(r.get(c["length"])), num(r.get(c["green"]))
            if L is None or L <= 0: why["연장 없음/0 이하"] += 1
            elif G is None or G <= 0: why["녹색 없음/0 이하"] += 1
            elif L > MAX_LEN_M: why[f"연장>{MAX_LEN_M}m"] += 1
            elif G > MAX_GREEN_S: why[f"녹색>{MAX_GREEN_S}s"] += 1
            else: ok.append((L, G))
        return ok, why

    for label, rs in (("전국", rows), ("부산", busan)):
        ok, why = clean(rs)
        out.append(f"- [{label}] 분석 가능 {pct(len(ok), len(rs))} · 제외 사유: "
                   + (", ".join(f"{k} {v:,}" for k, v in why.most_common()) or "없음"))
        if not ok:
            continue
        # 기준식 T_need = 7 + L/v, gap = T_need - G_rec > 0 이면 '기록값이 기준식보다 짧음'
        for v in SPEEDS:
            short = sum(1 for L, G in ok if ENTRY_S + L / v - G > 0)
            out.append(f"  - v={v} m/s: gap>0 비율(정의 미확정) {pct(short, len(ok))}")
        if label == "전국":
            r10 = sum(1 for L, G in ok if ENTRY_S + L / 1.0 - G > 0) / len(ok)
            if r10 > GATE_A_HIGH:
                summary["R1"] = f"⚠ 1.0m/s gap>0 비율 {r10:.0%}, 정의 미확정 (>40%: 녹색 정의·점멸 제외 의심)"
            elif r10 < GATE_A_LOW:
                summary["R1"] = f"⚠ 1.0m/s gap>0 비율 {r10:.1%}, 정의 미확정 (<1%: 자동 입력 의심)"
            else:
                summary["R1"] = f"1.0m/s gap>0 비율 {r10:.1%}, 정의 미확정 (경고선 안)"
    out.append("- 녹색신호시간 정의(점멸 포함 여부): **스크립트로 확인 불가** — 표준 정의서·제공기관 문의·V1 실측으로 확인해 적으세요.")


def check_r2(out: list[str]):
    """R2 읍면동 경계 (GeoJSON)."""
    fs = files_of("R2", (".geojson", ".json"))
    if not fs:
        out.append("- 상태: **파일 없음**")
        summary["R2"] = "파일 없음"
        return None
    p = fs[0]
    d = json.loads(p.read_text(encoding="utf-8"))
    feats = d.get("features", [])
    props = [f["properties"] for f in feats]
    keys = list(props[0].keys()) if props else []
    crs = (d.get("crs") or {}).get("properties", {}).get("name", "명시 없음")
    inventory.append({"id": "R2", "file": f"{FOLDERS['R2']}/{p.name}", "rows": len(feats),
                      "encoding": "utf-8", "bytes": p.stat().st_size, "sha256_16": sha256(p)})
    out += [f"- 파일: `{p.name}` ({p.stat().st_size / 1e6:.1f} MB)",
            f"- 읍면동 수: {len(feats):,}", f"- 속성 칼럼: " + ", ".join(f"`{k}`" for k in keys),
            f"- 좌표계: {crs} (CRS84 = WGS84 경위도)"]
    for k in ("adm_cd", "adm_cd2"):
        if k in keys:
            lens = Counter(len(str(x[k])) for x in props)
            out.append(f"- `{k}` 자리수: " + ", ".join(f"{a}자리 {b:,}" for a, b in lens.items())
                       + f" · 중복 {len(props) - len({str(x[k]) for x in props}):,}건")
    if "sidonm" in keys:
        out.append(f"- 부산 읍면동 수: {sum(1 for x in props if '부산' in x['sidonm']):,}")
    summary["R2"] = f"{len(feats):,}개 읍면동, WGS84"
    return props


def check_r3(out: list[str]):
    """R3 고령 인구 — 게이트 B."""
    got = load_one("R3", out)
    if not got:
        return None
    _, cols, rows, _ = got
    c = {k: find_col("R3", k, cols) for k in ("code", "total", "age65")}
    if not c["code"]:
        # jumin 사이트 형식: "행정구역" 값이 "부산광역시 해운대구 우1동  (2635051000)" → 괄호 속 10자리를 코드로 쓴다
        for col in cols:
            if rows and sum(1 for r in rows[:20] if re.search(r"\(\d{10}\)", r.get(col, ""))) >= min(5, len(rows)):
                for r in rows:
                    m = re.search(r"\((\d{10})\)", r.get(col, ""))
                    r["__code"] = m.group(1) if m else ""
                c["code"] = "__code"
                out.append(f"- 코드: `{col}` 값 안 괄호에서 10자리 행정기관코드를 추출했습니다.")
                break
    if c["code"]:
        lv = Counter("시도" if x.endswith("00000000") else "시군구" if x.endswith("00000") else "읍면동"
                     for x in (re.sub(r"\D", "", r.get(c["code"], "")) for r in rows) if len(x) == 10)
        out.append("- 단위별 행 수: " + ", ".join(f"{k} {v:,}" for k, v in lv.items()))
        if not lv.get("읍면동"):
            out.append("- ⚠ **읍면동 행이 없습니다.** 조회 단위를 읍면동까지 내려 다시 받아야 합니다.")
        # 출장소: 인구 표에는 따로 있고 경계에는 없다. 소속 읍면 인구에서 빠져 있으므로 F4 에서 합쳐야 한다
        name_col = next((x for x in cols if "행정구역" in x), cols[0])
        offices = [r for r in rows if "출장소" in r.get(name_col, "")]
        if offices and c["total"]:
            pop = sum(num(r.get(c["total"])) or 0 for r in offices)
            out.append(f"- 이름에 '출장소'가 들어간 행: {len(offices):,}곳, 인구 합계 {pop:,.0f}명. "
                       "이 중 경계에 없는 곳(게이트 C의 인구 쪽 미매칭)은 소속 읍면 인구에서 빠져 있으므로 F4에서 합쳐야 한다")
    out.append("- 칼럼 자동 탐지: " + ", ".join(f"{k}→`{v}`" if v else f"{k}→**찾지 못함**" for k, v in c.items()))
    if c["code"]:
        codes = [re.sub(r"\D", "", r.get(c["code"], "")) for r in rows]
        lens = Counter(len(x) for x in codes)
        out.append("- 코드 자리수: " + ", ".join(f"{a}자리 {b:,}" for a, b in lens.most_common()))
        # 10자리 행정기관코드: 뒤 5자리가 00000이면 시도·시군구 합계 행
        agg = sum(1 for x in codes if len(x) == 10 and x.endswith("00000"))
        out.append(f"- 시도·시군구 합계로 보이는 행(코드 끝 00000): {agg:,}건 → 결합 전에 제외 필요" if agg
                   else "- 합계 행(코드 끝 00000): 없음")
    out.append(f"- 총인구 필드: {'있음 `' + c['total'] + '`' if c['total'] else '**찾지 못함** — 비율 계산을 위해 총인구 표가 따로 필요'}")
    out.append(f"- 65세 이상 필드: {'있음 `' + c['age65'] + '`' if c['age65'] else '**찾지 못함**'}")
    if c["total"] and c["age65"]:
        # 합계 행(코드 끝 00000)은 읍면동이 아니므로 분포에서 뺀다
        def is_agg(r):
            code = re.sub(r"\D", "", r.get(c["code"], "")) if c["code"] else ""
            return len(code) == 10 and code.endswith("00000")
        ratios = [num(r.get(c["age65"])) / num(r.get(c["total"])) for r in rows
                  if not is_agg(r) and (num(r.get(c["total"])) or 0) > 0 and num(r.get(c["age65"])) is not None]
        if ratios:
            ratios.sort()
            out.append(f"- 65세 이상 비율 분포: 최소 {ratios[0]:.1%} · 중앙값 {ratios[len(ratios)//2]:.1%} · 최대 {ratios[-1]:.1%}")
    n_emd = sum(1 for r in rows if len(re.sub(r"\D", "", r.get(c["code"], "") if c["code"] else "")) == 10
                and not re.sub(r"\D", "", r.get(c["code"], "")).endswith("00000"))
    summary["R3"] = ("⚠ 읍면동 행 없음 — 재다운로드 필요" if c["code"] and n_emd == 0
                     else f"읍면동 {n_emd:,}행, 총인구·65+ 확인" if (c["total"] and c["age65"]) else "필드 확인 필요")
    return [re.sub(r"\D", "", r.get(c["code"], "")) for r in rows] if c["code"] else None


def check_gate_c(out: list[str], r2_props, r3_codes):
    """게이트 C — 인구 코드와 경계 코드 일치율 (8자리·10자리 모두)."""
    if not r2_props or not r3_codes:
        out.append("- R2와 R3가 모두 있어야 계산할 수 있습니다.")
        summary["GateC"] = "대기"
        return
    pop = {x for x in r3_codes if x and not (len(x) == 10 and x.endswith("00000"))}  # 합계 행 제외
    best = None
    for k in ("adm_cd", "adm_cd2"):
        bnd = {str(p[k]) for p in r2_props if k in p}
        hit = pop & bnd
        rate = len(hit) / len(pop) if pop else 0
        out.append(f"- `{k}` 기준: 인구 코드 {len(pop):,}개 중 일치 {len(hit):,}개 ({rate:.1%}) · 경계 쪽 미매칭 {len(bnd - pop):,}개")
        if best is None or rate > best[1]:
            best = (k, rate, sorted(pop - bnd)[:15])
    out.append(f"- 더 잘 맞는 쪽: `{best[0]}` ({best[1]:.1%}). 인구 쪽 미매칭 예시: " + (", ".join(best[2]) or "없음"))
    summary["GateC"] = f"{best[0]} 일치 {best[1]:.1%}"


def _largest_list(obj):
    """API 응답 JSON에서 가장 긴 리스트(=항목 목록)를 찾는다. 응답 구조를 모를 때 쓰는 안전한 방법."""
    best = []
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, list):
            if len(o) > len(best) and all(isinstance(x, dict) for x in o[:5]):
                best = o
            stack.extend(o)
        elif isinstance(o, dict):
            stack.extend(o.values())
    return best


def check_r4(out: list[str]):
    """R4 사고다발지역 — 연도별 파일(crash_zone_<연도>.json)의 건수와 필드."""
    fs = files_of("R4", (".json", ".geojson", ".csv"))
    if not fs:
        out.append("- 상태: **파일 없음** — API 응답을 연도별로 `crash_zone_<연도>.json`으로 저장하세요.")
        summary["R4"] = "파일 없음"
        return
    out.append("| 파일 | 연도 | 항목 수 |\n| --- | --- | --- |")
    fields: Counter = Counter()
    years = []
    for p in fs:
        y = re.search(r"(19|20)\d{2}", p.name)
        try:
            if p.suffix.lower() == ".csv":
                _, items, _ = read_table(p)
            else:
                items = _largest_list(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            out.append(f"| {p.name} | — | 읽기 실패: {e} |")
            continue
        for it in items[:50]:
            fields.update(it.keys())
        years.append(y.group(0) if y else "?")
        inventory.append({"id": "R4", "file": f"{FOLDERS['R4']}/{p.name}", "rows": len(items),
                          "encoding": "utf-8", "bytes": p.stat().st_size, "sha256_16": sha256(p)})
        out.append(f"| {p.name} | {y.group(0) if y else '파일명에 없음'} | {len(items):,} |")
    out.append("- 항목 필드: " + ", ".join(f"`{k}`" for k in fields))
    has_geom = [k for k in fields if any(t in k.lower() for t in ("geom", "polygon", "la_crd", "lo_crd", "좌표"))]
    out.append(f"- 위치/폴리곤 필드 후보: {', '.join(has_geom) or '**찾지 못함**'}")
    summary["R4"] = f"연도 {', '.join(sorted(set(years)))}" if years else "읽기 실패"


def check_poi(ds: str, out: list[str]):
    """O1~O3 시설 데이터 — 좌표 입력률, 시군구별 행 수 (게이트 D)."""
    got = load_one(ds, out)
    if not got:
        return
    _, cols, rows, _ = got
    c = {k: find_col(ds, k, cols) for k in ("sido", "sigungu", "lat", "lon", "type", "status")}
    out.append("- 위도 입력률: " + fill_rate(rows, c["lat"], True))
    out.append("- 경도 입력률: " + fill_rate(rows, c["lon"], True))
    # 좌표가 한국 범위(위도 33~39, 경도 124~132) 밖인 행: 위경도 뒤바뀜·오입력 탐지
    if c["lat"] and c["lon"]:
        bad = sum(1 for r in rows if (num(r.get(c["lat"])) or 0) > 0 and not (
            33 <= (num(r.get(c["lat"])) or 0) <= 39 and 124 <= (num(r.get(c["lon"])) or 0) <= 132))
        out.append(f"- 한국 범위 밖 좌표: {bad:,}건")
    if ds == "O2":
        for k in ("type", "status"):
            if c[k]:
                out.append(f"- `{c[k]}` 값: " + ", ".join(f"{a or '(빈칸)'} {b:,}" for a, b in Counter(r.get(c[k], '') for r in rows).most_common(10)))
        if c["sigungu"]:
            gs = [r for r in rows if "강서" in r.get(c["sigungu"], "") and (not c["sido"] or "부산" in r.get(c["sido"], ""))]
            gs_sc = [r for r in gs if not c["type"] or "경로당" in r.get(c["type"], "")]
            out.append(f"- 교차 확인: 부산 강서구 경로당 {len(gs_sc):,}건 vs 공개 현황 {GANGSEO_SENIOR_CENTERS}개소 (차이 {len(gs_sc) - GANGSEO_SENIOR_CENTERS:+,})")
    if c["sido"] and c["sigungu"]:
        cnt = Counter(f"{r.get(c['sido'], '')} {r.get(c['sigungu'], '')}".strip() for r in rows)
        low = sorted(cnt.items(), key=lambda kv: kv[1])[:10]
        out.append(f"- 시군구 {len(cnt):,}곳에 분포. 가장 적은 10곳(누락 의심): " + ", ".join(f"{k} {v}" for k, v in low))
    if c["lat"]:
        n_xy = sum(1 for r in rows if (num(r.get(c["lat"])) or 0) > 0)
        summary[ds] = f"{len(rows):,}행, 좌표 입력 {n_xy / len(rows):.1%}" if rows else "0행"
    else:
        summary[ds] = f"{len(rows):,}행, 위도 칼럼 찾지 못함"


def check_o4(out: list[str]):
    fs = [p for p in (RAW / FOLDERS["O4"]).glob("*") if p.is_file()] if (RAW / FOLDERS["O4"]).exists() else []
    out.append("- P2 항목. 응답에 좌표(XPos/YPos 등) 필드가 있는지 먼저 확인합니다." if not fs
               else f"- 파일 {len(fs)}개 있음: " + ", ".join(p.name for p in fs))
    summary["O4"] = "P2 (보류)" if not fs else f"{len(fs)}개 파일"


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    sec: dict[str, list[str]] = {k: [] for k in ("R1", "R2", "R3", "GateC", "R4", "O1", "O2", "O3", "O4")}
    check_r1(sec["R1"])
    r2 = check_r2(sec["R2"])
    r3 = check_r3(sec["R3"])
    check_gate_c(sec["GateC"], r2, r3)
    check_r4(sec["R4"])
    for ds in ("O1", "O2", "O3"):
        check_poi(ds, sec[ds])
    check_o4(sec["O4"])

    gate_rows = [("A", "R1 횡단보도", summary.get("R1")), ("B", "R3 고령 인구", summary.get("R3")),
                 ("C", "R2×R3 코드 결합", summary.get("GateC")), ("D", "R4 사고다발지역", summary.get("R4")),
                 ("D", "O1 보호구역", summary.get("O1")), ("D", "O2 경로당", summary.get("O2")),
                 ("D", "O3 전통시장", summary.get("O3")), ("—", "O4 병원(P2)", summary.get("O4")),
                 ("—", "R2 읍면동 경계", summary.get("R2"))]
    lines = [f"# 한 박자 — 데이터 점검 리포트",
             f"\n생성: {datetime.now(timezone(timedelta(hours=9))):%Y-%m-%d %H:%M} KST · `pipeline/check_data.py` 자동 생성 (원본은 읽기만 함)\n",
             "## 게이트 요약\n", "| 게이트 | 대상 | 결과 |", "| --- | --- | --- |"]
    lines += [f"| {g} | {n} | {s or '—'} |" for g, n, s in gate_rows]
    titles = {"GateC": "게이트 C — R2×R3 코드 일치율"}
    for k, body in sec.items():
        lines.append(f"\n## {titles.get(k, f'{k} {NAMES.get(k, k)}')}\n")
        lines += body
    lines.append("\n---\n※ gap>0 비율은 녹색신호시간 정의(점멸 포함 여부)가 확정되기 전의 잠정 집계다. 이슈·PR에는 '정의 미확정'과 함께 쓴다(CLAUDE.md R5).")
    (REPORTS / "data_check_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (REPORTS / "inventory.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "file", "rows", "encoding", "bytes", "sha256_16"])
        w.writeheader()
        w.writerows(inventory)
    print(f"리포트: {REPORTS / 'data_check_report.md'}")
    for g, n, s in gate_rows:
        print(f"  [{g}] {n}: {s or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
