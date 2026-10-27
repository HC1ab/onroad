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
