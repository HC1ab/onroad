# A-pipeline 구역 규칙

범위: 수집 기록, F1~F4 (정제, 좌표→읍면동 공간조인, T_need·gap, 읍면동 집계, 노출 플래그).

- Python 3, pandas, geopandas. 설정은 `../config.yaml`에서만 읽는다.
- `adm_cd`는 문자열. 거리·반경·겹침은 EPSG:5179로 변환 후 계산, 저장은 EPSG:4326.
- 원본(`data/raw/`)은 읽기만 한다. 인코딩은 utf-8-sig / cp949를 모두 시도해 확인하고 `download_log.csv`에 기록.
- 제외·결측·매칭 실패는 **건수를 표로 출력**한다 (F1, F2, F4 인수 조건).
- 출력은 `../contracts/*.schema.json`을 통과해야 한다. 스키마 변경은 단독 PR.
- 시설 데이터의 전화번호·담당자 칼럼은 산출물에 넣지 않는다.
- 인증키는 환경변수(`.env`)로만 읽는다.
