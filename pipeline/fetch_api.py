#!/usr/bin/env python3
"""
한 박자 — 공공데이터 API 수집 스크립트 (R1 횡단보도, O2 경로당, R4 사고다발지역, O4 병원)

사용법 (repo 루트에서):
    python3 pipeline/fetch_api.py probe          # 1단계: API마다 10행만 받아 응답 구조 확인 (키 문제·주소 문제를 먼저 격리)
    python3 pipeline/fetch_api.py fetch R1       # 2단계: 전체 수집 (R1 / O2 / R4 / O4 중 하나, 또는 all)

설계 원칙
- 표준 라이브러리만 사용 (설치 없이 실행).
- 인증키는 repo 루트 .env 에서만 읽고, 화면·파일·에러 메시지 어디에도 출력하지 않는다 (CLAUDE.md R3).
- 요청 주소는 pipeline/api_endpoints.json 에 둔다. 주소는 비밀이 아니므로 Git에 올린다.
- probe 로 응답 구조를 먼저 확인하고 fetch 로 넘어간다 (실패 지점을 단계별로 격리).
- 원본 보관 규칙: 받은 응답은 data/raw/<폴더>/ 에 새 파일로만 저장하고 기존 파일은 건드리지 않는다.
  data/raw/ 는 .gitignore 대상이다 (CLAUDE.md R1).
- 다운로드 기록은 data/download_log.csv 에 repo 헤더 그대로 한 줄씩 추가한다.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # repo 루트
RAW = ROOT / "data" / "raw"
LOG_PATH = ROOT / "data" / "download_log.csv"
LOG_HEADER = ["id", "file", "source_url", "downloaded_at", "source_modified", "row_count", "encoding", "license", "by"]
ENV_PATH = ROOT / ".env"
ENDPOINTS_PATH = Path(__file__).resolve().parent / "api_endpoints.json"

PAGE_SIZE = 1000        # 한 번에 받을 행 수 (서버가 더 작게 제한하면 응답의 numOfRows 를 따른다)
SLEEP_S = 0.2           # 호출 사이 대기 (서버 부담·한도 보호)
RETRIES = 3             # 일시 오류 재시도 횟수
TIMEOUT_S = 30

# R4 연도 범위: 응답이 오는 연도를 probe 와 fetch 결과로 확인한다 (PRD 열린 이슈)
R4_YEARS = range(2012, date.today().year + 1)
# R4 시도 코드 (도로교통공단 명세 표기 기준). 전국 일괄 호출이 안 될 때만 시도별로 나눠 부른다.
# 2026-07 이후 신설·변경 코드(전남광주통합 등)는 명세에서 확인되지 않아, 구 코드와 신 코드 후보를 모두 시도한다.
R4_SIDO = ["11", "26", "27", "28", "29", "30", "31", "36", "41", "42", "51", "43", "44",
           "45", "52", "46", "12", "47", "48", "50"]

# ID → (설명, 저장 폴더, 결과 형식)
TARGETS = {
    "R1": ("전국횡단보도표준데이터", "crosswalk", "csv"),
    "O2": ("전국마을회관및경로당표준데이터", "senior_center", "csv"),
    "R4": ("노인 보행사고 다발지역", "crash_zone", "json_by_year"),
    "O4": ("HIRA 병원정보(병원기본목록)", "hospital", "csv"),
}

# 응답이 '오류'임을 알려 주는 data.go.kr 공통 메시지 → 사람이 읽을 설명
KNOWN_ERRORS = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "인증키가 등록되지 않았습니다. 키 오타, Encoding/Decoding 키 혼동, 또는 승인 직후(반영까지 최대 1~2시간)일 수 있습니다.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 API에 대한 활용신청이 없거나 승인되지 않았습니다.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "일일 호출 한도를 넘었습니다. 내일 다시 실행하세요.",
    "NO_OPENAPI_SERVICE_ERROR": "요청주소가 잘못됐습니다. config/api_endpoints.json 의 주소를 확인하세요.",
}


# ---------------------------------------------------------------------------
# 설정 읽기
# ---------------------------------------------------------------------------
def load_keys() -> dict[str, str]:
    """repo 루트 .env 에서 DATA_GO_KR_KEY* 만 읽는다 (DB 설정 등 다른 줄은 무시). 키 값은 절대 출력하지 않음."""
    if not ENV_PATH.exists():
        sys.exit(f".env 파일이 없습니다: {ENV_PATH}\n"
                 "repo 루트에서 sh scripts/setup.sh 를 실행하면 .env.example 이 복사됩니다.")
    keys = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(DATA_GO_KR_KEY[A-Z0-9_]*)\s*=\s*(\S*)\s*$", line)
        if m and m.group(2):
            keys[m.group(1)] = m.group(2).strip("'\"")
    if not keys:
        sys.exit(".env 에 값이 채워진 DATA_GO_KR_KEY 가 없습니다.\n"
                 "한 줄에 이름=키 로 적으세요 (공백·따옴표 없이). 예:\n  DATA_GO_KR_KEY_R4=인증키값")
    return keys


def key_for(ds: str, keys: dict[str, str]) -> str:
    """키 선택 순서: DATA_GO_KR_KEY_<ID> → DATA_GO_KR_KEY → 다른 DATA_GO_KR_KEY_* 아무거나.
    data.go.kr 인증키는 계정당 하나라서, 신청한 API 라면 어느 이름의 키로도 호출된다."""
    k = keys.get(f"DATA_GO_KR_KEY_{ds}") or keys.get("DATA_GO_KR_KEY") or next(iter(keys.values()))
    # Encoding 키(%2B 등 포함)를 넣었으면 한 번 풀어서 Decoding 키로 만든다 (이중 인코딩 방지)
    return urllib.parse.unquote(k) if "%" in k else k


def load_endpoints() -> dict[str, str]:
    if not ENDPOINTS_PATH.exists():
        sys.exit(f"{ENDPOINTS_PATH} 가 없습니다.")
    return json.loads(ENDPOINTS_PATH.read_text(encoding="utf-8"))


def endpoint_ok(url: str) -> bool:
    return url.startswith("http") and "여기에" not in url


# ---------------------------------------------------------------------------
# 호출과 응답 해석
# ---------------------------------------------------------------------------
def mask(text: str, secret: str) -> str:
    """에러 메시지에 키가 섞여 나오지 않게 가린다."""
    for s in {secret, urllib.parse.quote(secret, safe="")}:
        text = text.replace(s, "***")
    return text


def call(url: str, params: dict, secret: str) -> bytes:
    """GET 한 번. 일시 오류(5xx, 타임아웃)는 RETRIES 번까지 재시도."""
    q = urllib.parse.urlencode({"serviceKey": secret, **params})
    full = f"{url}?{q}"
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(full, timeout=TIMEOUT_S) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * attempt)
    raise RuntimeError(mask(f"호출 실패 ({last})", secret))


def parse(body: bytes) -> dict:
    """JSON 또는 XML 응답을 {'code','msg','total','items'} 로 통일한다.
    data.go.kr 은 type=json 을 줘도 인증 오류는 XML 로 돌려주므로 둘 다 처리한다."""
    text = body.decode("utf-8", errors="replace").strip()
    for err, why in KNOWN_ERRORS.items():
        if err in text:
            return {"code": err, "msg": why, "total": 0, "items": []}
    if text.startswith("{") or text.startswith("["):
        d = json.loads(text)
        resp = d.get("response", d)
        header, body_ = resp.get("header", {}), resp.get("body", {})
        items = body_.get("items", [])
        if isinstance(items, dict):           # {"item": [...]} 또는 {"item": {...}}
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        total = body_.get("totalCount", len(items))
        return {"code": str(header.get("resultCode", "")), "msg": header.get("resultMsg", ""),
                "total": int(total or 0), "items": items or []}
    root = ET.fromstring(text)
    items = [{c.tag: (c.text or "") for c in it} for it in root.iter("item")]
    get = lambda tag: (root.findtext(f".//{tag}") or "").strip()
    return {"code": get("resultCode") or get("returnReasonCode"), "msg": get("resultMsg") or get("returnAuthMsg"),
            "total": int(get("totalCount") or len(items)), "items": items}


def ok_code(code: str) -> bool:
    # 표준 API 는 '00', 기관 API 는 '0000' 또는 'INFO-000' 형태가 정상
    return code in ("", "0", "00", "0000", "INFO-000", "NORMAL_SERVICE")


def page_params(ds: str, page: int, size: int) -> dict:
    # HIRA 는 '_type', 그 밖의 data.go.kr API 는 'type' 으로 JSON 을 요청한다
    fmt = {"_type": "json"} if ds == "O4" else {"type": "json"}
    return {"pageNo": page, "numOfRows": size, **fmt}


# ---------------------------------------------------------------------------
# probe: 1페이지만 받아 구조를 보여 준다
# ---------------------------------------------------------------------------
def probe(keys, eps):
    print("=== probe: API마다 10행만 받아 응답 구조를 확인합니다 ===")
    for ds, (name, _, _) in TARGETS.items():
        url = eps.get(ds, "")
        print(f"\n[{ds}] {name}")
        if not endpoint_ok(url):
            print("  건너뜀 — pipeline/api_endpoints.json 에 요청주소가 없습니다.")
            continue
        params = page_params(ds, 1, 10)
        if ds == "R4":
            params.update({"searchYearCd": "2023", "siDo": "", "guGun": ""})
        try:
            r = parse(call(url, params, key_for(ds, keys)))
        except Exception as e:
            print(f"  실패: {e}")
            continue
        if not ok_code(r["code"]):
            print(f"  오류 코드 {r['code']}: {r['msg']}")
            continue
        fields = list(r["items"][0].keys()) if r["items"] else []
        print(f"  정상 · 전체 {r['total']:,}건 · 받은 행 {len(r['items'])}")
        print(f"  필드 {len(fields)}개: {', '.join(fields)}")
        if ds == "O4":
            has_xy = any(f.lower() in ("xpos", "ypos") for f in fields)
            print(f"  좌표 필드(XPos/YPos): {'있음 → O4 사용 가능' if has_xy else '없음 → O4 는 여기서 중단 (가이드 4장)'}")
        if ds == "R4" and r["total"] == 0:
            print("  2023년 전국 일괄 조회 결과가 0건입니다. fetch R4 는 시도별 호출로 자동 전환합니다.")


# ---------------------------------------------------------------------------
# fetch: 전체 수집
# ---------------------------------------------------------------------------
def fetch_all_pages(ds, url, secret, extra=None) -> tuple[list[dict], int]:
    """pageNo 를 올려 가며 totalCount 만큼 받는다."""
    rows, page, total = [], 1, None
    while True:
        r = parse(call(url, {**page_params(ds, page, PAGE_SIZE), **(extra or {})}, secret))
        if not ok_code(r["code"]):
            raise RuntimeError(f"오류 코드 {r['code']}: {r['msg']}")
        total = r["total"] if total is None else total
        rows += r["items"]
        print(f"\r  {len(rows):,} / {total:,}", end="", flush=True)
        if not r["items"] or len(rows) >= total:
            break
        page += 1
        time.sleep(SLEEP_S)
    print()
    return rows, total


def save_csv(rows: list[dict], path: Path):
    """모든 행의 키를 모아 칼럼으로 쓴다 (행마다 필드가 빠져 있어도 안전). utf-8-sig = 엑셀에서 한글이 깨지지 않음."""
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def fetch_table(ds, keys, eps):
    name, folder, _ = TARGETS[ds]
    url = eps.get(ds, "")
    if not endpoint_ok(url):
        sys.exit(f"[{ds}] pipeline/api_endpoints.json 에 요청주소를 먼저 채우세요.")
    print(f"[{ds}] {name} 전체 수집")
    rows, total = fetch_all_pages(ds, url, key_for(ds, keys))
    out = RAW / folder / f"{folder}_api_{date.today():%Y%m%d}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_csv(rows, out)
    flag = "" if len(rows) == total else f"  ⚠ 전체 {total:,}건 중 {len(rows):,}건만 받음"
    print(f"  저장: {out.relative_to(ROOT)} ({len(rows):,}행){flag}")
    log(ds, out, url, len(rows))


def fetch_r4(keys, eps):
    url, secret = eps["R4"], key_for("R4", keys)
    folder = RAW / TARGETS["R4"][1]
    folder.mkdir(parents=True, exist_ok=True)
    summary = []
    for y in R4_YEARS:
        print(f"[R4] {y}년")
        try:
            rows, _ = fetch_all_pages("R4", url, secret, {"searchYearCd": str(y), "siDo": "", "guGun": ""})
        except RuntimeError as e:
            print(f"  전국 일괄 실패({e}) → 시도별 호출")
            rows = []
        if not rows:
            # 전국 일괄이 안 되면 시도별로 받아 afos_fid 기준으로 중복 제거
            seen = {}
            for sd in R4_SIDO:
                try:
                    part, _ = fetch_all_pages("R4", url, secret, {"searchYearCd": str(y), "siDo": sd, "guGun": ""})
                except RuntimeError:
                    part = []
                for it in part:
                    seen[it.get("afos_fid") or json.dumps(it, sort_keys=True)] = it
                time.sleep(SLEEP_S)
            rows = list(seen.values())
        summary.append((y, len(rows)))
        if rows:
            out = folder / f"crash_zone_{y}.json"
            out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            log("R4", out, url, len(rows))
    print("\n[R4] 연도별 건수 (가이드 R4 체크 항목: 응답이 오는 연도 범위)")
    for y, n in summary:
        print(f"  {y}: {n:,}")


def log(ds, path: Path, url: str, n: int):
    """data/download_log.csv 에 repo 헤더 그대로 한 줄 추가 (가이드 1장). 키는 기록하지 않는다.
    source_modified(페이지 수정일)와 license 는 페이지를 보고 사람이 채운다."""
    new = not LOG_PATH.exists() or LOG_PATH.stat().st_size == 0
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_HEADER)
        w.writerow([ds, str(path.relative_to(RAW)), url, f"{date.today():%Y-%m-%d}", "", n,
                    "utf-8-sig" if path.suffix == ".csv" else "utf-8", "", "fetch_api.py"])


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("probe", "fetch"):
        print(__doc__)
        return 1
    keys, eps = load_keys(), load_endpoints()
    if sys.argv[1] == "probe":
        probe(keys, eps)
        return 0
    which = sys.argv[2].upper() if len(sys.argv) > 2 else ""
    todo = list(TARGETS) if which == "ALL" else [which]
    if not all(t in TARGETS for t in todo):
        print("fetch 뒤에 R1 / O2 / R4 / O4 / all 중 하나를 쓰세요.")
        return 1
    failed = []
    for t in todo:
        try:
            fetch_r4(keys, eps) if t == "R4" else fetch_table(t, keys, eps)
        except RuntimeError as e:   # 한 데이터가 실패해도 나머지는 계속 받는다
            print(f"\n  [{t}] 실패: {e}")
            failed.append(t)
    if failed:
        print(f"\n실패한 데이터: {', '.join(failed)} — 위 메시지를 확인한 뒤 해당 ID만 다시 실행하세요.")
        return 1
    print("\n완료. 이어서  python3 pipeline/check_data.py  로 점검하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
