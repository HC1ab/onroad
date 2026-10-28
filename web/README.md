# web — 프론트엔드

React + TypeScript + Vite, 지도는 MapLibre GL JS, 배경 지도는 [OpenFreeMap](https://openfreemap.org/)(키 없음, 출처 표기는 지도에 자동 표시).

## 실행
```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

| 모드 | 설정 (루트 `.env`) | 데이터 |
| --- | --- | --- |
| mock (기본) | `VITE_API_MODE=mock` 또는 미설정 | `contracts/samples/` 가상 데이터. 화면 상단에 "샘플 데이터" 표시 |
| real | `VITE_API_MODE=real` | 개발 서버가 `/api`를 `localhost:8000`(docker compose)으로 프록시 |

### real 모드를 샘플 데이터로 확인하기 (통합 I1)
서버에 샘플을 적재하고 프론트를 real 모드로 띄운다(저장소 루트에서).
```bash
docker compose up -d db
docker compose run --rm -v "$PWD/contracts:/contracts:ro" api python -m app.ingest --source /contracts/samples --sample
docker compose up -d api
npm --prefix web run dev -- --mode real   # 루트 .env.real 에 VITE_API_MODE=real
```
- 샘플에는 0.8 m/s · 300m 와 우1동 상세만 있다. 다른 속도·반경·동을 고르면 "결과가 아직 적재되지 않았습니다" 안내가 정상이다.
- 실제 경계 파일(`web/public/data/boundaries.json`, D6 #9)이 없으면 개발 서버가 샘플 경계(부산 일부)를 대신 내준다. 빌드·배포에는 적용되지 않는다.
- 서버가 샘플을 내려주면 real 모드에서도 상단에 "샘플 데이터"가 표시된다.

배경 지도를 바꾸려면 `VITE_BASEMAP_STYLE`에 MapLibre 스타일 URL을 넣는다.

## 빌드
```bash
npm run build      # web/dist → nginx 가 제공 (docker compose 의 :8080)
npm run lint
```

## 구조
```text
src/
  api/types.ts        contracts 스키마와 같은 타입
  api/client.ts       real/mock 전환, 오류 메시지 처리
  hooks/useApi.ts     로딩·오류·다시 시도, 마지막 요청만 반영
  state/AppState.tsx  선택 속도·선택 읍면동 (화면 전체 공유)
  components/         지도, 범례, 속도 선택, 요약, 하단 고지
```

- 경계(`boundaries`)는 한 번만 받고, 속도를 바꾸면 `areas` 값만 다시 받아 지도 색을 바꾼다(`feature-state`).
- real 모드의 경계 파일은 `/data/boundaries.json`(D6 #9가 `web/public/data/`에 생성)을 읽는다.
- 표시 문구는 PRD 3장 원칙을 따른다("점검 우선순위 후보", "기준식보다 짧음").
