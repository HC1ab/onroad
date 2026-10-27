# 한 박자 (onroad)

전국 횡단보도의 기록된 녹색신호시간을 기준식 `7 + L/v`와 전수 비교하고, 고령 거주 비율과 목적지·사고 노출을 겹쳐 점검 우선순위 후보 지역을 보여주는 웹 서비스.

- **처음 왔다면 여기부터:** [팀 온보딩 문서 (웹)](https://hc1ab.github.io/onroad/onboarding.html) — 원본은 [docs/onboarding.html](docs/onboarding.html)
- 기획: [docs/PRD.md](docs/PRD.md)
- 데이터 수집: [docs/data-collection-guide.md](docs/data-collection-guide.md)
- **API 명세 (Swagger):** https://hc1ab.github.io/onroad/api/ — 원본은 [contracts/openapi.yaml](contracts/openapi.yaml)
- 협업 규칙: [CLAUDE.md](CLAUDE.md)
- 작업 보드: [MVP 작업 보드 이슈 #29](https://github.com/HC1ab/onroad/issues/29)

## 구성

```text
브라우저 ──> nginx(:8080) ──> /       프론트 빌드 (web/dist)
                         └──> /api/*  FastAPI(:8000, 읽기 전용) ──> PostgreSQL + PostGIS
```

| 폴더 | 내용 | 자세히 |
| --- | --- | --- |
| `web/` | React + TypeScript + Vite, MapLibre 지도 | [web/README.md](web/README.md) |
| `server/` | FastAPI, nginx 설정 | [server/README.md](server/README.md) |
| `contracts/` | API 응답 스키마와 샘플 (구역 사이의 약속) | [contracts/README.md](contracts/README.md) |
| `pipeline/`, `validation/` | 데이터 처리·검증 (Python) | 각 폴더 `CLAUDE.md` |
| `docker-compose.yml` | db · api · nginx | — |

## 1. 필요한 도구

| 도구 | 버전 | 용도 |
| --- | --- | --- |
| Git | 최신 | |
| Docker Desktop | Compose v2 이상 | DB·API·nginx 실행 (Python을 따로 설치하지 않아도 됨) |
| Node.js | 22 이상 | 프론트 개발 |
| GitHub CLI (`gh`) | 최신 | 이슈 읽기·쓰기 (`gh auth login`) |
| gitleaks | 선택 | 커밋 전 키 유출 검사 |

## 2. 처음 한 번 설정

```bash
git clone git@github.com:HC1ab/onroad.git
cd onroad
sh scripts/setup.sh
```

`setup.sh`가 하는 일: Git 훅(유출 방지) 설치, 한글 파일명 표시 설정, `.env` 생성.

그다음 `.env`를 열어 **`DB_PASSWORD`에 아무 값이나** 넣는다(로컬 전용, 비우면 서버가 시작되지 않는다). 공공데이터 인증키는 데이터 담당만 필요하다.

```bash
cd web && npm install && cd ..
```

## 3. 실행

### 프론트만 (서버 없이, mock 모드)
가장 빠른 방법. `contracts/samples`의 가상 데이터로 화면을 띄운다.

```bash
cd web
npm run dev
```
→ http://localhost:5173 (상단에 "샘플 데이터(mock)" 표시)

### 서버까지 (real 모드)
```bash
docker compose up --build          # db + api + nginx
```

| 주소 | 내용 |
| --- | --- |
| http://localhost:8080 | nginx (프론트 빌드 + `/api`). 빌드 전에는 안내 페이지 |
| http://localhost:8080/healthz | 상태 확인 (`{"status":"ok","db":"ok"}`) |
| http://localhost:8000/api/docs | API 문서 |

프론트 개발 서버를 서버와 함께 쓰려면 `.env`에 `VITE_API_MODE=real`을 넣고 `cd web && npm run dev`. `/api`는 :8000으로 프록시된다.

배포와 같은 형태로 보려면 프론트를 빌드한 뒤 :8080으로 연다.
```bash
cd web && npm run build && cd ..   # web/dist → nginx 가 제공
```

### 종료
```bash
docker compose down                # 컨테이너만 내림 (DB 데이터 유지)
docker compose down -v             # DB 데이터까지 삭제
```

## 4. 검사 (PR 전에)

| 대상 | 명령 |
| --- | --- |
| 프론트 | `cd web && npm run lint && npm run build` |
| 서버 | `docker build -t onroad-api ./server && docker run --rm onroad-api python -m pytest -q -p no:cacheprovider tests` |
| 계약 샘플 | [contracts/README.md](contracts/README.md)의 검사 명령 |

PR을 올리면 GitHub Actions가 바뀐 구역의 검사를 자동으로 돌린다(`.github/workflows/`).

## 5. 작업 방법 (요약)

1. 이슈를 고른다 ([작업 보드 #29](https://github.com/HC1ab/onroad/issues/29)). AI 세션에는 `gh issue view 번호 --comments`로 이슈를 읽힌다.
2. `main`에서 브랜치: `구역/이슈번호-주제` (예: `web/18-choropleth`)
3. 자기 구역 폴더만 수정, 파일을 지정해 `git add`
4. 결과를 이슈 코멘트로 남기고 PR (`Closes #번호`), squash merge

자세한 규칙은 [CLAUDE.md](CLAUDE.md)와 [온보딩 문서](https://hc1ab.github.io/onroad/onboarding.html).

## 자주 막히는 곳

| 증상 | 해결 |
| --- | --- |
| `DB_PASSWORD 를 .env 에 넣어주세요` | `.env`의 `DB_PASSWORD`에 값 입력 |
| `failed to connect to the docker API` | Docker Desktop 실행 |
| `localhost:8080`에 안내 페이지만 보임 | 프론트 빌드 전. `cd web && npm run build` |
| 지도가 회색으로만 보임 | 배경 지도 로딩 중이거나 네트워크 차단. 잠시 기다리거나 `VITE_BASEMAP_STYLE` 확인 |
| 커밋이 `BLOCKED`로 막힘 | 훅이 원본 데이터·키·대용량을 막은 것. 해당 파일을 빼고 다시 커밋 (`--no-verify` 금지) |
| 포트 충돌 | `.env`의 `WEB_PORT`, `API_PORT` 변경 |

---

원본 데이터와 인증키는 저장소에 없다. 받는 법은 수집 가이드, 키는 `.env`(`.env.example` 참고).

이 도구는 연관성까지만 보여주며 개별 횡단보도를 "위험"이나 "위반"으로 단정하지 않는다.
