# pipeline — 데이터 수집과 점검

A-pipeline 구역. 수집 가이드(`docs/data-collection-guide.md`)의 데이터를 API로 받고(`fetch_api.py`), 게이트 A~D 항목을 점검한다(`check_data.py`). 판정식·데이터 선택의 근거는 `docs/decisions/`에 있다.

모든 명령은 **repo 루트**에서 실행한다.

## 1. 준비 (처음 한 번)

```bash
sh scripts/setup.sh        # 훅 설정, .env.example → .env 복사
pip install pyyaml         # check_data.py 가 config.yaml 을 읽는 데 필요
```

`.env`에 data.go.kr **일반 인증키(Decoding)** 를 넣는다. 인증키는 계정당 하나라서 한 줄이면 R1·O2·R4·O4 모두 호출된다.

```
DATA_GO_KR_KEY_R4=인증키
```

- 이름과 키는 같은 줄에, `=` 앞뒤 공백·따옴표 없이 쓴다.
- 키 선택 순서: `DATA_GO_KR_KEY_<ID>` → `DATA_GO_KR_KEY` → 값이 있는 다른 `DATA_GO_KR_KEY_*`.
- 키는 문서·이슈·PR·채팅·스크린샷에 쓰지 않는다(CLAUDE.md R3).

API별 활용신청은 따로 해야 한다(R1 전국횡단보도표준데이터, O2 전국마을회관및경로당표준데이터, R4 노인 보행사고 다발지역, O4 HIRA 병원정보서비스). 요청주소는 `pipeline/api_endpoints.json`에 있다.

## 2. 수집

```bash
python3 pipeline/fetch_api.py probe       # API마다 10행만 받아 키·주소·응답 구조 확인
python3 pipeline/fetch_api.py fetch all   # 전체 수집 (R1 / O2 / R4 / O4 하나만도 가능)
```

첫 실행은 반드시 `probe`부터 한다.

| probe 메시지 | 할 일 |
| --- | --- |
| `정상 · 전체 N건` | `fetch`로 진행 |
| `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | 키 오타, Encoding/Decoding 혼동 확인. 승인 직후면 1~2시간 뒤 다시 |
| `SERVICE_ACCESS_DENIED_ERROR` | 해당 API 활용신청 |
| `NO_OPENAPI_SERVICE_ERROR` | `api_endpoints.json`의 주소 확인 |
| O4 `좌표 필드 없음` | O4 중단 (P2, 가이드 4장) |

- 결과는 `data/raw/<폴더>/<폴더>_api_<날짜>.csv`로 새로 저장한다. 기존 파일은 건드리지 않는다. R4는 연도별 `crash_zone_<연도>.json`.
- R4는 전국 일괄 조회가 0건이면 시도별로 나눠 받고 `afos_fid`로 중복을 제거한다. 끝에 연도별 건수를 출력한다.
- `data/download_log.csv`에 한 줄씩 자동 기록된다. `source_modified`(페이지 수정일)와 `license`는 직접 채운다.
- 파일로 받는 데이터(R2·R3·O1·O3)는 가이드대로 `data/raw/<폴더>/`에 원본 파일명 그대로 넣는다.

## 3. 점검

```bash
python3 pipeline/check_data.py
```

결과는 `data/interim/data_check_report.md`와 `data/interim/inventory.csv`에 쓴다. `data/interim/`은 Git에 올라가지 않는다. 수치를 이슈 코멘트로 옮길 때는 "gap>0 비율, 정의 미확정"으로 쓴다(CLAUDE.md R5).

| 게이트 | 자동 확인 |
| --- | --- |
| A (R1) | 행 수와 5만 행 잘림 의심, 연장·녹색·적색·위경도 입력률, 보행자신호등 유무별·시도별 녹색신호시간 입력률, 부산 시군구별 행 수, 제외 사유별 건수, 속도별 gap>0 비율(전국·부산), 40%·1% 경고 |
| B (R3) | 제목 줄 건너뛰기, 이름 속 10자리 코드 추출, 단위별 행 수, 합계 행, 출장소 행, 총인구·65세 이상 필드, 비율 분포 |
| C (R2×R3) | `adm_cd`(8자리)·`adm_cd2`(10자리) 일치율, 미매칭 코드 예시 |
| D (R4, O1~O3) | 연도별 항목 수와 폴리곤 필드, 좌표 입력률, 한국 범위 밖 좌표, 시군구 분포, 경로당 시설유형·영업상태, 부산 강서구 168개소 교차 확인 |

- 판정식 값(진입시간, 속도, 이상치 상한)은 `config.yaml`에서 읽는다.
- 칼럼 이름은 키워드로 자동 탐지한다. 리포트의 "칼럼 자동 탐지" 줄이 틀렸으면 `check_data.py`의 `COLUMN_OVERRIDES`에 실제 칼럼명을 적는다.
- 녹색신호시간의 점멸 포함 여부와 데이터별 라이선스는 스크립트로 확인할 수 없다.
