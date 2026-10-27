# contracts — 구역 사이의 접점

파이프라인(A)이 DB에 적재하는 결과 테이블, 서버(E)가 내려주는 API 응답, 웹(C)이 읽는 형태의 스키마와 샘플. 웹은 서버가 없어도 `samples/`로 먼저 개발한다(mock 모드, PRD F17).

| 응답 / 파일 | 만드는 곳 | 쓰는 곳 | 근거 |
| --- | --- | --- | --- |
| `GET /api/areas` | server (pipeline 결과 조회) | web | PRD 8장 |
| `GET /api/areas/{adm_cd}/crosswalks` | server | web | PRD 8장 |
| `GET /api/crosswalks/candidates` | server | web | PRD 8장 |
| `GET /api/validation` | server (validation 결과 조회) | web | PRD 8장 |
| `GET /api/meta` | server | web | PRD 8장 |
| 읍면동 경계 파일 (단순화·gzip) | pipeline | web (정적 제공) | PRD 8장 |

- 기준은 서버가 자동 생성하는 OpenAPI 스키마다. 응답 하나당 `<이름>.schema.json`과 `samples/<이름>.json`을 둔다.
- 샘플은 실제 응답과 같은 형태여야 한다(mock 모드가 그대로 읽는다). 값은 가상이면 `_sample: true`를 붙인다.
- **변경은 단독 PR + 팀 공지.** 필드 추가는 하위 호환으로, 이름 변경·삭제는 이슈로 합의 후.
- 칼럼명은 실제 CSV 확인 후 확정한다(PRD 9장은 초안). `adm_cd`는 문자열, 좌표는 EPSG:4326.
