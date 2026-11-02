#!/usr/bin/env bash
# 정적 묶음 내보내기(F18). 저장소 루트에서 실행한다.
#   bash server/deploy/export_static.sh /srv/onroad-static
# 적재된 결과를 contracts/README.md "정적 묶음" 구성으로 비어 있는 폴더에 쓴다.
set -euo pipefail
cd "$(dirname "$0")/../.."

out=${1:-}
[ -n "$out" ] || { echo "사용법: bash server/deploy/export_static.sh <빈 폴더>" >&2; exit 1; }
mkdir -p "$out"
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$(cd "$out" && pwd):/out" \
  api python -m app.static_bundle --out /out
