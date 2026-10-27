# 한 박자 (onroad) — 전체 규칙

전국 횡단보도 녹색신호시간을 기준식(7 + L/v)과 전수 비교하고 고령 거주 비율·목적지·사고 노출을 겹쳐 "점검 우선순위 후보"를 찾는 프로젝트. 기획은 `docs/PRD.md`, 데이터 수집은 `docs/data-collection-guide.md`.
이 repo는 **퍼블릭**이다. 쓰는 모든 글(코드, 커밋, 이슈, PR)은 공개된다고 가정한다.

## 세션 시작 (매번)
1. 자기 트랙 브랜치를 최신으로: `git checkout <트랙> && git pull origin <트랙>` (트랙은 아래 "브랜치" 표)
2. 맡은 이슈를 읽는다: `gh issue view <번호> --comments` (연결된 이슈와 `docs/decisions/`도 확인)
3. 트랙 브랜치에서 작업 브랜치를 만든다: `<구역>/<이슈번호>-<주제>` (예: `pipeline/5-f1-clean`)

## 세션 종료 (매번)
1. 이슈에 코멘트로 남긴다: 한 일, 수치, 이상한 점, 막힌 점, 후속 작업
2. 후속 작업·수정 요청은 새 이슈로 만든다 (채팅·구두로만 남기지 않는다)
3. **자기 트랙 브랜치로** PR을 만든다(`--base <트랙>`). 본문에 `Refs #번호`. 작은 PR로.
   - `Closes #번호`는 main으로 가는 PR에서만 이슈를 닫는다. 작업 PR에서는 `Refs`, 이슈는 트랙 → main PR에서 닫는다.

## 구역 (폴더 = 담당)
| 구역 | 폴더 | 내용 |
| --- | --- | --- |
| A-pipeline | `pipeline/`, `data/download_log.csv` | 수집·정제·공간조인·gap·집계 (F1~F4) |
| B-validation | `validation/` | V1~V5, 현장 실측 |
| C-web | `web/` | 지도·사분면·슬라이더 (F5~F7, F9~F12, F17) |
| D-docs | `docs/` | 게이트 보고서, 결정 기록, 발표 |
| E-server | `server/` | 읽기 전용 API, Docker Compose, Ubuntu 배포 (F15, F16, F18) |

- **자기 구역 밖 파일은 수정하지 않는다.** 필요하면 담당에게 이슈로 요청한다.
- 공유 파일(`config.yaml`, `contracts/`)은 단독 PR로만 수정하고 팀에 공지한다.
- 구역 사이 접점은 `contracts/`의 스키마와 샘플뿐이다. 웹은 서버가 없어도 `contracts/samples/`로 먼저 개발한다(mock 모드).
- 로컬 개발: DB와 API는 `docker compose up`, 프론트는 `/api`를 :8000으로 프록시한다. 환경 값은 `.env`에만 둔다(`.env.example` 참고).
- 병렬 작업은 `git worktree`를 쓴다. 한 폴더에서 AI 세션 두 개를 돌리지 않는다.

## R1~R6 유출 방지·공개 규칙
- **R1 올리지 않는다:** `data/raw/`, `data/interim/`, `*.gpkg`, `*.parquet`, `*.xlsx`, `.env`, `field/photos/`, 50MB 초과 파일. `git add -A` / `git add .` 대신 파일을 지정해 add 한다.
- **R2 올려도 되는 것:** `data/download_log.csv`, `contracts/`, `web/public/data/`의 최종 산출물, `.env.example`.
- **R3 키:** 인증키는 `.env`에만. 코드, 이슈, PR, 채팅, 스크린샷에 값을 쓰지 않는다. 유출되면 숨기지 말고 즉시 키 재발급 후 팀에 알린다.
- **R4 산출물 공개 전 점검:** 시설 데이터의 전화번호·담당자 칼럼 제거, `download_log.csv`에 이용허락범위 기록, 출처 표기(admdongkor CC BY 4.0 등).
- **R5 글쓰기:** 녹색신호시간의 점멸 포함 여부가 확정되기 전에는 이슈·PR·커밋에 "부족 N%" 같은 확정형 수치를 쓰지 않는다("gap>0 비율, 정의 미확정"으로 쓴다). "위험", "위반", "불법", "늘려야 한다"는 쓰지 않는다. 허용: "점검 우선순위 후보", "기록값이 기준식보다 짧음".
- **R6 자동 장치:** `.githooks/`의 pre-commit·pre-push가 위를 막는다. 클론 후 `sh scripts/setup.sh`를 한 번 실행한다. 훅을 우회(`--no-verify`)하지 않는다.

## 기술 고정 사항 (되돌리기 어려움)
- 저장 좌표계 EPSG:4326, 거리·겹침 계산은 EPSG:5179로 변환해서 한다.
- 읍면동 코드 `adm_cd`는 항상 문자열(앞자리 0 보존).
- 원본 파일은 수정하지 않는다(엑셀로 열어 저장 금지). 확인은 복사본으로.
- 분석 설정값은 `config.yaml`에서만 읽는다. 코드에 숫자를 박지 않는다.
- 주소→좌표 지오코딩, 결측 채우기는 먼저 이슈로 합의한다.

## 브랜치 (트랙 브랜치 방식)
```text
main ─┬─ frontend ── web/18-choropleth        작업 PR → 트랙 (squash)
      ├─ backend  ── server/13-db-schema
      └─ data     ── pipeline/5-f1-clean
트랙 → main : 통합 단계마다 PR (merge commit)
```

| 트랙 브랜치 | 구역(폴더) | 이슈 라벨 |
| --- | --- | --- |
| `frontend` | `web/` | `frontend` |
| `backend` | `server/`, `docker-compose.yml` | `backend` |
| `data` | `pipeline/`, `validation/`, `data/download_log.csv` | `db` |

- **작업 PR은 자기 트랙 브랜치로**, squash merge. 작업 브랜치 수명은 1~2일.
- **트랙 → main은 통합 단계(I1 10/30 등)마다 PR**, "Create a merge commit"으로 병합한다(squash 하면 트랙과 main의 이력이 갈라져 다음 동기화 때 충돌이 생긴다). 이 PR 본문에 완료된 이슈를 `Closes #번호`로 모두 적는다.
- **동기화: main이 바뀌면 각 트랙에 바로 받는다.** `git checkout <트랙> && git pull origin <트랙> && git merge origin/main && git push`. rebase·force push 하지 않는다. 특히 `contracts/` 변경은 당일 반영한다.
- **main 직행 예외:** 공유 파일(`contracts/`, `config.yaml`)과 공통 문서(`docs/`, `README.md`, `CLAUDE.md`)는 main으로 바로 PR하고, 병합 후 세 트랙이 동기화한다.
- 보호 규칙은 main에만 있다(PR 필수, force push 금지). 트랙 브랜치는 보호가 없으니 직접 push하지 말고 PR로 넣는다.
- 트랙 이름과 같은 접두어(`frontend/…`, `backend/…`, `data/…`)의 브랜치는 만들 수 없다. 작업 브랜치는 구역 접두어(`web/`, `server/`, `pipeline/`, `validation/`)를 쓴다.

## Git 규칙
- 커밋: `type(구역): 내용` (예: `feat(pipeline): F1 제외 사유 표 추가`). 타입: feat, fix, docs, chore, refactor.
- main에 직접 push 하지 않는다.
- 작업 브랜치 수명은 1~2일. 길어지면 쪼갠다.
