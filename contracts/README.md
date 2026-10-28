# contracts — 구역 사이의 접점

파이프라인(A)이 DB에 적재하는 결과, 서버(E)가 내려주는 API 응답, 웹(C)이 읽는 형태를 여기서 정한다. 웹은 서버가 없어도 `samples/`로 먼저 개발한다(mock 모드, PRD F17).

| 스키마 | 대상 | 샘플 | 기능 |
| --- | --- | --- | --- |
| `areas.schema.json` | `GET /api/areas?speed=&radius=&sido=&sigungu=` | `samples/areas.json` | F5, F6, F7 |
| `area_crosswalks.schema.json` | `GET /api/areas/{adm_cd}/crosswalks?speed=&radius=` | `samples/area_crosswalks.json` | F7 |
| `candidates.schema.json` | `GET /api/crosswalks/candidates?bbox=&speed=&radius=` | `samples/candidates.json` | F5, F11 |
| `validation.schema.json` | `GET /api/validation` | `samples/validation.json` | F8 |
| `meta.schema.json` | `GET /api/meta` | `samples/meta.json` | F9 |
| `error.schema.json` | 4xx·5xx 오류 응답 | `samples/error.json` | 공통 |
| `boundaries.schema.json` | 읍면동 경계 정적 파일 (API 아님) | `samples/boundaries.json` | F5 |
| `static_manifest.schema.json` | 정적 묶음의 목차 `manifest.json` (API 아님) | `samples/static_manifest.json` | F18 |
| `common.schema.json` | 공통 정의 (`adm_cd`, `speed`, 비율, 노출 플래그) | — | — |

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
crosswalks/{speed}_{radius}/{adm_cd}.json  GET /api/areas/{adm_cd}/crosswalks?speed=&radius=
export/areas_{speed}_{radius}.csv          GET /api/export/areas.csv?speed=&radius=
export/crosswalks_{speed}_{radius}.csv     GET /api/export/crosswalks.csv?speed=&radius=
```
- `{speed}`는 소수 한 자리 문자열(`0.7`, `0.8`, `1.0`), `{radius}`는 `200`, `300`, `500`. 예: `areas/1.0_300.json`
- 묶음에 있는 조합과 상세는 `manifest.json`에 적는다. 없는 조합은 API의 미적재(500 `not_loaded` 안내)와 같게 보여준다(빈 결과로 보이지 않게).
- 경계는 묶음에 넣지 않는다. 웹 빌드의 `/data/boundaries.json`을 그대로 쓴다.
- 원본 데이터·인증키·전화번호 칼럼은 넣지 않는다(R4). 결과 테이블만 내보낸다.

## 규칙
- **기준은 이 폴더의 JSON Schema(2020-12)다.** 서버 응답과 파이프라인 결과는 이 스키마를 통과해야 한다. 서버의 OpenAPI 문서는 이 스키마에 맞춰 만든다.
- 속도는 요청마다 하나(`speed=0.7|0.8|1.0`)이고, 응답에는 그 속도의 값만 담는다.
- 경계 파일에는 값을 넣지 않는다. 값은 `/api/areas`에서 받아 `adm_cd`로 붙인다.
- `adm_cd`는 문자열, 좌표는 EPSG:4326, 시간은 초(`_s`), 비율은 0~1.
- 아직 계산하지 않은 검증 항목은 `null`이다.
- **변경은 단독 PR + 팀 공지.** 필드 추가는 하위 호환으로, 이름 변경·삭제는 이슈로 합의한 뒤.
- 칼럼명은 실제 CSV를 확인한 뒤 확정한다(PRD 9장은 초안).

## 샘플
- 값은 모두 가상이며 `"_sample": true`가 붙어 있다. 실제 분석 결과가 아니다.
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
