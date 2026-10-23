# 한 박자 (onroad)

전국 횡단보도의 기록된 녹색신호시간을 기준식 `7 + L/v`와 전수 비교하고, 고령 거주 비율과 목적지·사고 노출을 겹쳐 점검 우선순위 후보 지역을 보여주는 웹 서비스.

- 기획: [docs/PRD.md](docs/PRD.md)
- 데이터 수집: [docs/data-collection-guide.md](docs/data-collection-guide.md)
- 협업 규칙: [CLAUDE.md](CLAUDE.md)

## 시작

```bash
sh scripts/setup.sh
```

원본 데이터와 인증키는 repo에 없다. 받는 법은 수집 가이드, 키는 `.env`(`.env.example` 참고).

이 도구는 연관성까지만 보여주며 개별 횡단보도를 "위험"이나 "위반"으로 단정하지 않는다.
