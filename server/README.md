# server — 읽기 전용 API와 배포 구성

구성: `db`(PostgreSQL 16 + PostGIS) · `api`(FastAPI) · `nginx`(프론트 빌드 + `/api` 프록시). 정의는 루트 `docker-compose.yml`.

## 로컬 실행
```bash
cp .env.example .env        # 처음 한 번. DB_PASSWORD 에 아무 값이나 넣기
docker compose up --build
```

| 주소 | 내용 |
| --- | --- |
| http://localhost:8080 | nginx. 프론트 빌드(`web/dist`)가 없으면 안내 페이지 |
| http://localhost:8080/healthz | 상태 확인 (DB 연결 실패 시 503) |
| http://localhost:8000/api/docs | API 문서 (로컬에서만 열림) |

프론트 개발 서버(`npm run dev`, :5173)는 `/api`를 :8000으로 프록시한다.

## 테스트
```bash
docker build -t onroad-api ./server
docker run --rm onroad-api python -m pytest -q -p no:cacheprovider tests
```
PR에서 `server/`가 바뀌면 GitHub Actions(`server.yml`)가 테스트와 `/healthz` 확인을 돌린다.

## 규칙 요약 (자세히는 `CLAUDE.md`)
- GET만 받는다. 다른 메서드는 405와 `contracts/error.schema.json` 형식으로 거부한다.
- 오류 응답에 내부 정보를 담지 않는다.
- DB 포트는 외부에 열지 않는다. API 포트는 로컬호스트(127.0.0.1)에만 열린다.
- 원본 데이터와 인증키는 서버에 두지 않는다.
# 서버 실행과 결과 적재

## B3 읽기 전용 API

적재 후 `docker compose up -d --build api`로 실행한다. Swagger: http://localhost:8000/api/docs

| 요청 | 동작 |
| --- | --- |
| `/api/areas?speed=0.8&sido=부산광역시&sigungu=해운대구` | 읍면동 집계, 지역 필터. 사분면 기준은 저장된 전국 기준 유지 |
| `/api/areas/21090730/crosswalks?speed=0.8` | gap_s 내림차순 상세 목록 |
| `/api/crosswalks/candidates?speed=0.8&radius=300&bbox=129.05,35.13,129.22,35.23` | 저장된 후보 점을 지도 범위로 필터 |
| `/api/validation` | V1~V5 결과 그대로 반환 |
| `/api/meta` | 기준일·출처·한계 그대로 반환 |

speed는 0.7/0.8/1.0(기본 0.8), radius는 200/300/500(기본 300). sigungu는 sido와 함께 사용한다. 잘못된 입력은 400, 없는 읍면동은 404다. 미적재 속도·반경·상세 또는 DB 오류는 기존 명세의 500 오류를 반환한다. 미적재 데이터를 0건으로 표시하지 않으며, 적재된 빈 목록은 200과 빈 배열로 반환한다. 현재 샘플은 0.8/300과 일부 상세만 제공한다.

조회는 읽기 전용 트랜잭션이며 적재와 공유하는 잠금으로 한 응답에 서로 다른 적재 시점의 데이터가 섞이지 않게 한다. 요청 시 분석값은 계산하지 않는다. JSONResponse로 `_sample` 표시를 보존한다.

`app/api_schemas.json`은 독립 Docker 이미지에서 Swagger를 제공하기 위한 contracts 스냅샷이다. 계약이 변경되면 함께 갱신하며, 통합 테스트가 원본과의 일치를 확인한다. 실제 응답도 원본 JSON Schema로 검사한다.

전체 테스트 실행(저장소 루트, Docker만 필요):

```sh
docker compose -p onroad-server-tests -f server/compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p onroad-server-tests -f server/compose.test.yml down
```

테스트 DB는 내부 네트워크와 임시 메모리 저장소만 사용하며 운영 DB와 분리된다.

## B2 결과 적재

저장소 루트에서 실행한다. `.env`의 DB 설정과 실행 중인 Compose DB가 필요하다.

```powershell
docker compose up -d db
docker compose build api
docker compose run --rm -v "${PWD}/contracts:/contracts:ro" api python -m app.ingest --source /contracts/samples --sample
```

실제 결과 디렉터리를 읽기 전용으로 마운트한다. 아래 `D:/onroad-results`는 실제 경로로 바꾼다. Ubuntu에서는 `/srv/onroad-results` 같은 절대 경로와 `$(pwd)/contracts`를 사용한다.

```powershell
docker compose run --rm -v "${PWD}/contracts:/contracts:ro" -v "D:/onroad-results:/results:ro" api python -m app.ingest --source /results
```

입력은 기존 contracts 응답 스키마를 만족하는 JSON 묶음이다. 디렉터리 아래 `areas.json`, `area_crosswalks.json`, `candidates.json`, `meta.json`, `validation.json`을 탐색한다. 속도·지역별 파일은 하위 폴더로 구분한다. meta와 validation은 각각 하나만 허용한다. 후보 파일은 적재 식별을 위해 speed와 radius_m이 반드시 필요하다. 파일 이름과 내용은 계약 기준이며 CSV나 원본 자료는 입력하지 않는다.

전체 묶음 교체 방식이다. 누락된 속도나 지역을 이전 적재에서 유지하지 않는다. 입력 검증 후 마이그레이션과 교체를 한 트랜잭션으로 실행하며, 실패하면 기존 결과가 유지된다. 같은 묶음을 다시 넣어도 행이 누적되지 않는다. 동시 적재는 DB 잠금으로 직렬화한다.

샘플은 `--sample`로만 적재하며 실제 결과와 혼합할 수 없다. 현재 샘플에는 0.8 m/s와 일부 상세만 있으므로 다른 속도 결과를 생성하지 않는다. 집계·상세·후보 샘플은 독립 예시로 보존한다. 후보 반경도 입력값 그대로 저장하며 요청 중 재계산하지 않는다.

읍면동·횡단보도 식별자와 검색에 필요한 속도·후보·좌표는 관계형 컬럼과 인덱스로 저장한다. 나머지 계약 항목은 JSONB로 보존한다. 경계 도형은 DB에 넣지 않는다. V1 실측 비교는 validation 문서에 보존하며 별도 field_audit 원자료 적재는 현재 계약에 없어 포함하지 않는다.

## 적재 통합 테스트

반드시 폐기 가능한 별도 PostGIS DB를 사용한다. `TEST_DATABASE_DSN`이 없으면 DB 통합 테스트는 건너뛴다. `/contracts`에 계약 디렉터리를 마운트하고 `python -m pytest -q`를 실행하면 샘플 모드 분리, 반복 적재, 공간 좌표계, 중복·잘못된 지역 입력의 롤백을 검증한다.
