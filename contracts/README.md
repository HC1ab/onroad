# contracts — 구역 사이의 접점

파이프라인(A)이 DB에 적재하는 결과, 서버(E)가 내려주는 API 응답, 웹(C)이 읽는 형태를 여기서 정한다. 웹은 서버가 없어도 `samples/`로 먼저 개발한다(mock 모드, PRD F17).

| 스키마 | 대상 | 샘플 | 기능 |
| --- | --- | --- | --- |
| `areas.schema.json` | `GET /api/areas?speed=&radius=&sido=&sigungu=` | `samples/areas.json` | F5, F6, F7 |
| `areas.schema.json` (v2) | `GET /api/areas?target=&radius=&sido=&sigungu=` | `samples/areas_v2.json` | F19, F20 |
| `area_crosswalks.schema.json` | `GET /api/areas/{adm_cd}/crosswalks?speed=&radius=` | `samples/area_crosswalks.json` | F7 |
| `candidates.schema.json` | `GET /api/crosswalks/candidates?bbox=&speed=&radius=` | `samples/candidates.json` | F5, F11 |
| `points.schema.json` | `GET /api/crosswalks?bbox=&speed=&radius=` (전체 횡단보도 점, 분석 제외 포함) | `samples/points.json` | F5, F7 |
| `points.schema.json` (v2) | `GET /api/crosswalks?bbox=&target=&radius=` (v2 필드 포함, `data_check` 포함) | `samples/points_v2.json` | F19, F20, F21 |
| `validation.schema.json` | `GET /api/validation` (V1~V5, v2 V6·V7) | `samples/validation.json` | F8 |
| `meta.schema.json` | `GET /api/meta` (원본 기준일·갱신 주기, v2 계수) | `samples/meta.json` | F9 |
| `error.schema.json` | 4xx·5xx 오류 응답 | `samples/error.json` | 공통 |
| `boundaries.schema.json` | 읍면동 경계 정적 파일 (API 아님) | `samples/boundaries.json` | F5 |
| `static_manifest.schema.json` | 정적 묶음의 목차 `manifest.json` (API 아님) | `samples/static_manifest.json` | F18 |
| `common.schema.json` | 공통 정의 (`adm_cd`, `speed`, `target`, 비율, 노출 플래그) | — | — |

## v2: 3단계 기준 (결정 009, C3 #73)
`target`(목표 커버리지 0.85·0.9·0.95)을 주면 결정 009의 3단계 기준 값을 담는다. 기존 v1 필드는 그대로 두어 하위 호환이다.

| 응답 | 추가 필드 | 비고 |
| --- | --- | --- |
| `points` | `formula_class`, `tier`, `resident_elderly_ratio`, `user_elderly_ratio`, `v_applied_mps`, `t_required_s`, `add_s`, `coverage_now`, `coverage_required`, `reason`, `reason_parts{protect_zone_m, market_name, market_m}`, `check_reason` | `status`에 `data_check` 추가(시간 값 null). v2 값은 `status=analyzed`일 때만 |
| `areas` | `target`, `mean_add_s`, `n_add2`, `coverage_now_mean`, `coverage_required_mean`, `thresholds.mean_add_s_median` | `target`이 있으면 v2 형태, `speed`가 있으면 v1 형태(한 응답에 하나) |
| `validation` | `v6`(지하철 무임 비율), `v7`(0.7식 비율 비교) | 없으면 `null` 또는 생략 |
| `meta` | `coefficients[]`(계수와 근거), `sensitivity[]`, `sources[].as_of·update_cycle·fetched_at·id·role` | 화면 "계수와 근거", "이 결과는 언제 데이터 기준인가" |

- 시간: `t_required_s = max(green_s, 7 + length_m / v_applied_mps)`, `add_s = t_required_s - green_s`(0 이상).
- 반올림: 시간 값(`green_s`, `t_need_s`, `gap_s`, `t_required_s`, `add_s`)은 **소수 셋째 자리**까지 내보낸다. 부산 기록 보행시간의 약 12%가 `7 + n/0.7`(예: 24.142857) 꼴이라, 1자리로 자르면 `t_required_s = green_s + add_s`가 0.1초 어긋난다. 화면은 소수 첫째 자리로 표시한다.
- `reason`의 숫자는 위에서 내보낸 값을 소수 첫째 자리로 쓴 것이다. 그래서 화면에 표시한 `t_required_s`·`add_s`와 항상 같다.
- 커버리지는 **고령 보행자 기준**(config `coverage_basis`)이며 "시간 안에 건널 수 있는 보행자 비율"이다. 추천이 맞을 확률(신뢰도)이 아니다.
- 읍면동 `mean_add_s`는 분석 횡단보도 전체(추가 0 포함)의 평균이다. `data_check`는 집계에서 뺀다.
- `reason`은 파이프라인이 만든 한 줄이다. 화면은 그대로 쓰고, 다시 조합할 때만 `reason_parts`를 쓴다.
- `meta.sources[].update_cycle`은 출처의 갱신 주기다(`monthly`·`yearly`·`irregular`·`unknown` 등). 화면은 `as_of`로 결과의 데이터 기준일을 보여준다.

## API 명세 (Swagger)
- [`openapi.yaml`](openapi.yaml): 엔드포인트·파라미터·오류 응답을 담은 OpenAPI 3.1 명세. 응답 본문은 위 JSON Schema를 `$ref`로 참조한다.
- 보기: https://hc1ab.github.io/onroad/api/ (main 기준). 다른 브랜치는 `?url=<raw 주소>`를 붙인다.
- 로컬 서버를 띄우면 http://localhost:8000/api/docs 에서도 볼 수 있다(B3 #14에서 이 명세와 맞춘다).
- 엔드포인트나 파라미터를 바꿀 때는 이 파일과 스키마를 같은 PR에서 함께 고친다.

## 정적 묶음 (F18)
서버 없이 데모하기 위해 서버가 DB 결과를 그대로 파일로 내보낸 것. 각 파일 내용은 같은 API 응답과 같고 같은 스키마를 통과한다. 웹은 `VITE_API_MODE=static`에서 `/api` 대신 이 파일을 읽는다(놓는 위치는 웹이 정한다).

```text
manifest.json                              목차 (static_manifest.schema.json)
meta.json                                  GET /api/meta
validation.json                            GET /api/validation
areas/{speed}_{radius}.json                GET /api/areas?speed=&radius=  (전국. 지역 필터는 화면에서)
candidates/{speed}_{radius}.json           GET /api/crosswalks/candidates?speed=&radius=  (전국. bbox 필터는 화면에서)
points/{speed}_{radius}.json               GET /api/crosswalks?speed=&radius=  (전국 전체 점. 없을 수 있음, bbox 필터는 화면에서)
crosswalks/{speed}_{radius}/{adm_cd}.json  GET /api/areas/{adm_cd}/crosswalks?speed=&radius=
export/areas_{speed}_{radius}.csv          GET /api/export/areas.csv?speed=&radius=
export/crosswalks_{speed}_{radius}.csv     GET /api/export/crosswalks.csv?speed=&radius=
areas_v2/{target}_{radius}.json            GET /api/areas?target=&radius=  (v2. manifest results_v2)
points_v2/{target}_{radius}.json           GET /api/crosswalks?target=&radius=  (v2. 없을 수 있음, manifest results_v2[].points)
```
- `{speed}`는 소수 한 자리 문자열(`0.7`, `0.8`, `1.0`), `{radius}`는 `200`, `300`, `500`. 예: `areas/1.0_300.json`
- `{target}`은 소수 두 자리 문자열(`0.85`, `0.90`, `0.95`). 예: `areas_v2/0.85_300.json`
- 전체 점(`points/`)은 파이프라인 결과에 있을 때만 들어간다. manifest 조합의 `points: true`로 표시한다.
- 묶음에 있는 조합과 상세는 `manifest.json`에 적는다. 없는 조합은 API의 미적재(500 `not_loaded` 안내)와 같게 보여준다(빈 결과로 보이지 않게).
- 경계는 묶음에 넣지 않는다. 웹 빌드의 `/data/boundaries.json`을 그대로 쓴다.
- 원본 데이터·인증키·전화번호 칼럼은 넣지 않는다(R4). 결과 테이블만 내보낸다.

## 규칙
- **기준은 이 폴더의 JSON Schema(2020-12)다.** 서버 응답과 파이프라인 결과는 이 스키마를 통과해야 한다. 서버의 OpenAPI 문서는 이 스키마에 맞춰 만든다.
- 속도는 요청마다 하나(`speed=0.7|0.8|1.0`)이고, 응답에는 그 속도의 값만 담는다. v2 목표 커버리지(`target=0.85|0.9|0.95`)도 요청마다 하나다.
- 경계 파일에는 값을 넣지 않는다. 값은 `/api/areas`에서 받아 `adm_cd`로 붙인다.
- `adm_cd`는 문자열, 좌표는 EPSG:4326, 시간은 초(`_s`), 비율은 0~1.
- 아직 계산하지 않은 검증 항목은 `null`이다.
- **변경은 단독 PR + 팀 공지.** 필드 추가는 하위 호환으로, 이름 변경·삭제는 이슈로 합의한 뒤.
- 칼럼명은 실제 CSV를 확인한 뒤 확정한다(PRD 9장은 초안).

## 샘플
- v1 샘플의 값은 모두 가상이며 `"_sample": true`가 붙어 있다. 실제 분석 결과가 아니다.
- v2 샘플(`points_v2.json`, `areas_v2.json`, `validation.json`의 `v6`·`v7`, `meta.json`의 계수·출처)은 v2 시제품 분석을 부산 원본으로 다시 돌린 결과(2026-11-02)에서 일부를 뽑은 것이다. 그래도 `"_sample": true`이며 화면 개발용이다.
  - `points_v2.json`: 해운대·수영 28개 동의 1단계 전부(20)·3단계 50곳, 다른 구의 2단계 6곳(해운대·수영에는 대형 시장이 없다), `data_check` 6곳, `excluded` 5곳. 2단계 점의 `adm_cd`는 경계 샘플 밖이다.
  - v1 필드(`speed` 0.8, `flags`)도 같은 원본으로 계산했다. `senior_center`는 v2에서 쓰지 않아 `false`로 두었다.
  - `areas_v2.json`: 28개 동. 사분면 경계(`thresholds`)는 부산 전체 동(표본 5곳 이상)의 중앙값이다.
- `samples/boundaries.json`은 부산 해운대구·수영구 28개 읍면동 경계를 단순화한 것이다. 출처: [admdongkor](https://github.com/vuski/admdongkor) ver20260701, CC BY 4.0. 다른 샘플의 `adm_cd`는 이 경계와 맞춰져 있어 mock 모드에서 지도를 그대로 칠할 수 있다.
- 3개 읍면동은 `low_sample: true`(표본 부족) 사례로 넣었다.

## 검사
```bash
pip install "jsonschema>=4.18" referencing
python contracts/check_samples.py
```
로컬에 Python이 없으면 Docker로 실행한다.
```bash
docker run --rm -v "$PWD/contracts:/c:ro" python:3.12-slim sh -c "pip install -q 'jsonschema>=4.18' referencing && python /c/check_samples.py"
```
PR에서 `contracts/`가 바뀌면 GitHub Actions(`.github/workflows/contracts.yml`)가 같은 검사를 자동으로 돌린다.
