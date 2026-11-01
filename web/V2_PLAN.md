# v2 화면 작업 계획 (W14 #80 · W15 #81 · W16 #82)

작업이 끊겨도 이 파일만 보고 이어서 한다. 단계를 끝낼 때마다 체크하고 커밋한다.

## 이어서 하는 법
1. `git checkout web/80-v2-screens && git pull` (원격에 있으면). `git log --oneline frontend..` 로 끝난 단계 확인
2. 아래 체크리스트에서 첫 번째 `[ ]` 단계부터
3. 단계마다: `npx tsc -b && npm run lint && npx vitest run` → 커밋 `feat(web): ... (W1x)` + `Refs #8x`
4. 브라우저 확인: `.claude/launch.json` 의 `web` (mock, :5173)

## 전제와 결정
- 기준: 결정 009 (`docs/decisions/009-추천-보행시간-3단계.md`), 계약 C3 (#73) 완료 조건, `config.yaml` v2 키
- **C3 계약·샘플이 아직 없다(2026-11-02).** 그래서 웹 안에서 #73 완료 조건대로 타입을 정하고, mock 은 기존 샘플(`points.json`, `areas.json`)에서 009 식으로 v2 값을 계산해 만든다(`lib/mockV2.ts`). C3 가 병합되면 mock 을 `contracts/samples` 로 바꾸고 타입을 맞춘다.
- v2 필드는 모두 선택(optional)으로 두어 v1 응답도 그대로 읽힌다. real·static 모드에서 v2 가 없으면 미적재 안내(기존 NOT_LOADED 흐름).
- 상단 전환: `basis = 'recorded' | 'v2'`, `target = 0.85 | 0.90 | 0.95`(기본 0.85).
  - `recorded`: 지금 화면 그대로(속도 선택 유지, `short_ratio` 채색, 짧은 초 점 색).
  - `v2`: 속도 선택 대신 목표 커버리지 선택. 채색 `mean_add_s`, 점 색 = 단계, 크기 = `add_s`.
  - 속도 3종 비교 설명은 검증 V2 카드로 옮긴다(#82).
- 문구는 조건형: "기준 적용 시 59.9초(+7.9초)". 금지어 검사 `wording.test.ts`.
- 커버리지 = 고령 보행자 기준(`coverage_basis: elderly`). "정답 확률이 아님"을 같이 적는다.

## mock 계산 (009 요약, 숫자는 config.yaml 값을 mock 전용 상수로 옮김)
- 단계: `protect_zone` → 1, `market` → 2, 그 외 3 (기존 샘플 flags 사용)
- 이용자 고령 비율 p: 1단계 고령자 기준, 2단계 주민 비율 + 0.137, 3단계 주민 비율(읍면동 `ratio_65plus`)
- v: 일반 N(1.29, σg)·고령 N(1.13, σe) 를 p 로 섞은 분포의 (1 − target) 분위수, [0.7, 1.0] 로 자름. 1단계는 0.7
  - σ = (mean − p15) / 1.0364 (15퍼센타일 z) → 일반·고령 모두 약 0.270 (009 "약 0.27"과 같음)
- `t_required_s = max(green_s, 7 + L/v)`, `add_s = t_required_s − green_s`
- 커버리지(고령) = P(고령 속도 ≥ L / (t − 7)), 기록값·필요 시간 각각
- `data_check`: 샘플에 없으므로 기록값 < 7 + L/1.0 − 0.5 인 점을 `data_check` 로 바꿔 1건 이상 만든다

## 체크리스트
- [x] S1 타입·계산·mock: `api/types.ts` v2 타입, `lib/recommend.ts`(+테스트), `lib/mockV2.ts`, `api/client.ts` `areasV2`·`pointsV2`·`validation` V6·V7·`meta.coefficients`
- [x] S2 상단 전환(#80): `AppState` basis·target, `BasisSelector`(기록값/3단계 + 85·90·95), recorded 일 때만 속도 선택
- [x] S3 점 레이어 v2(#81): 단계 색·`add_s` 크기, data_check·excluded 속 빈 회색, `PointCard` v2(기록 → 기준 적용 +초, reason, 고령 커버리지, 정의 미확정 고지), 추가 초 2초 이상 필터, `AreaDetail` 같은 필드
- [x] S4 채색·사분면(#80): `mean_add_s` 채색·범례, 툴팁 `n_add2`, 사분면 가로 `mean_add_s`·경계 중앙값
- [x] S5 계수와 근거·민감도(#80): About 에 `meta.coefficients` 표, 범례·카드에 시장 보정 0.063~0.157, 고령 속도 0.76 결과
- [ ] S6 목록·검증(#82): TopList 횡단보도 우선순위(add_s 큰 순 → 단계 1·2·3, 지역 필터 연동), V6·V7 카드, V2 카드에 속도 3종 비교, 카드별 한계 한 줄
- [ ] S7 마무리: tsc·lint·vitest·build·static build, 브라우저 확인(mock), push, PR → frontend (`Refs #80 #81 #82`), 이슈 코멘트

## 진행 기록
- 2026-11-02: 계획 작성. 브랜치 `web/80-v2-screens` (frontend 9654ead 기준)
