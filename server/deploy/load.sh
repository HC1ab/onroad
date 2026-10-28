#!/usr/bin/env bash
# 결과 묶음 적재. 저장소 루트에서 실행한다.
#   bash server/deploy/load.sh --sample               contracts/samples 적재
#   bash server/deploy/load.sh /srv/onroad-results    파이프라인 결과 디렉터리 적재
# 전체 교체 방식이며, 실패하면 기존 결과가 그대로 남는다. 원본 데이터는 넣지 않는다.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "${1:-}" = "--sample" ]; then
  docker compose run --rm -v "$PWD/contracts:/contracts:ro" \
    api python -m app.ingest --source /contracts/samples --sample
elif [ -n "${1:-}" ] && [ -d "$1" ]; then
  docker compose run --rm -v "$PWD/contracts:/contracts:ro" -v "$(cd "$1" && pwd):/results:ro" \
    api python -m app.ingest --source /results
else
  echo "사용법: bash server/deploy/load.sh --sample | <결과 디렉터리>" >&2
  exit 1
fi
