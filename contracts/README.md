# contracts — 구역 사이의 접점

파이프라인(A)·검증(B)이 만드는 정적 파일의 스키마와 샘플. 웹(C)은 `samples/`로 먼저 개발한다.

| 파일 | 만드는 곳 | 쓰는 곳 | 근거 |
| --- | --- | --- | --- |
| `area_vulnerability.json` | pipeline | web | PRD 9장 |
| `crosswalk_short.geojson` (또는 PMTiles) | pipeline | web | PRD 9장 |
| `validation.json` | validation | web | PRD 9장 |

- 스키마 파일 이름: `<파일명>.schema.json`. 샘플: `samples/<파일명>`.
- **변경은 단독 PR + 팀 공지.** 필드 추가는 하위 호환으로, 이름 변경·삭제는 이슈로 합의 후.
- 칼럼명은 실제 CSV 확인 후 확정한다(PRD 9장은 초안).
