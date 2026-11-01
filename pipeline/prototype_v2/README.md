# v2 추천 보행시간 시제품 (결정 009)

결정 009(#72)의 3단계 적용 속도·필요 시간·이유·커버리지와 V6(지하철 무임 비율)을 부산 원본으로 계산한 **참고용 시제품**이다.
정식 파이프라인 이식은 D12(#75), 검증 이식은 D13(#76)에서 한다. 이식할 때 `params.yaml` 대신 `config.yaml` v2 키(설정 PR #84)를 읽고, 근사 투영을 EPSG:5179로 바꾼다.

## 원본 (`data/raw/prototype_v2/`, 커밋 금지)
| 폴더 | 파일 | 출처 |
| --- | --- | --- |
| `crosswalk_busan/` | 부산광역시 관내 횡단보도, 음향신호기, 보행자작동신호기 현황.xlsx (첫 시트) | 부산시 (출처 페이지 확인 필요) |
| `population_65/` | 202609_202609_주민등록인구기타현황(고령 인구현황)_월간*.csv (구·군별 16개, 읍면동 단위) | jumin.mois.go.kr/etcStatOldAge.do |
| `admin_boundary/` | HangJeongDong_ver20261001.geojson | github.com/vuski/admdongkor (CC BY 4.0) |
| `protect_zone/` | 전국노인장애인보호구역표준데이터.csv | data.go.kr 15034532 |
| `market/` | 전국전통시장표준데이터.csv | data.go.kr 15012894 |
| `station/` | 전국도시철도역사정보표준데이터.csv | data.go.kr 15013205 |
| `child_zone/` | 전국어린이보호구역표준데이터.csv | data.go.kr 15012891 (V7 비교) |
| `metro_ticket/` | 부산교통공사_월별 역별 권종별 승하차 정보_20241231.csv | data.go.kr 15128561 (이용허락범위 제한 없음) |

## 실행
```bash
pip install pandas numpy openpyxl shapely pyyaml
python pipeline/prototype_v2/recommend_times.py   # → data/interim/prototype_v2/crosswalk_recommendations.csv, recommend_summary.md
python pipeline/prototype_v2/metro_check.py       # → data/interim/prototype_v2/metro_check.md
```

## 기대 결과 (목표 85%)
원본 3,815 → 정제 3,751 → 동 배정 3,726 → 기록 확인 필요 108 제외 → 3,618곳.
1단계 222곳(2초 이상 추가 184), 2단계 95곳(7), 3단계 3,301곳(57). 고령 보행자 커버리지 73→95% / 70→78% / 72→76%. V7 0.7식 비율 노인 14% / 어린이 28% / 그 외 4.7%. V6: 대형 시장 300m 안 역 7곳 +10.95%p, p=0.004.

## 이식할 때 바꿀 것
- 반경 고령 비율: 위도 35.15 기준 등거리 근사 투영 → EPSG:5179(geopandas `sjoin`·`overlay`)
- 정제 규칙: 부산 v1(`busan_clean.py`)과 맞춘다. 시제품은 같은 좌표·길이·시간 중복만 뺀다
- 기준식 허용오차: 시제품 ±0.5초, v1은 1e-6초. `config.yaml` `formula_tolerance_s`로 통일
