#!/usr/bin/env bash
# 결과 묶음 하나를 서버에 반영한다: 경계 교체(바뀐 경우 다시 빌드) → 적재 → current 링크 → LOADED.log 기록.
# 저장소 루트(/srv/onroad)에서 실행한다:
#   bash server/deploy/load_bundle.sh /srv/onroad-results/YYYYMMDD [zip sha256 앞 16자]
# 폴더는 받은 zip 을 그대로 푼 모양이어야 한다: <폴더>/bundle/(적재 대상), <폴더>/web/boundaries.json(선택).
# 이전 날짜 폴더를 넣으면 데이터 되돌리기가 된다. 규칙은 server/deploy/README.md "결과 데이터 관리".
set -euo pipefail
cd "$(dirname "$0")/../.."

DIR=${1:-}
ZIP_SHA=${2:--}
[ -n "$DIR" ] && [ -d "$DIR" ] || { echo "사용법: bash server/deploy/load_bundle.sh <결과 날짜 폴더> [zip 해시]" >&2; exit 1; }
DIR=$(cd "$DIR" && pwd)
ROOT=$(dirname "$DIR")
NAME=$(basename "$DIR")

[ -d "$DIR/bundle" ] || { echo "$DIR/bundle 이 없습니다. zip 을 날짜 폴더에 그대로 푸세요." >&2; exit 1; }
N_JSON=$(find "$DIR/bundle" -name '*.json' | wc -l)
[ "$N_JSON" -gt 0 ] || { echo "$DIR/bundle 에 JSON 이 없습니다." >&2; exit 1; }
echo "[1/4] 묶음 확인: $NAME (JSON $N_JSON개)"

echo "[2/4] 경계"
SRC_B="$DIR/web/boundaries.json"
DST_B="web/public/data/boundaries.json"
if [ ! -f "$SRC_B" ]; then
  echo "      묶음에 경계 없음, 지금 경계 유지"
elif cmp -s "$SRC_B" "$DST_B"; then
  echo "      바뀐 것 없음"
else
  mkdir -p "$(dirname "$DST_B")"
  cp "$SRC_B" "$DST_B"
  echo "      교체, 프론트 다시 빌드 (지금 커밋 그대로)"
  bash server/deploy/deploy.sh --no-pull
fi

echo "[3/4] 적재 (전체 교체, 그동안 API 오류)"
OUT=$(bash server/deploy/load.sh "$DIR/bundle" 2>&1 | tee /dev/stderr | grep -E '^Imported ' || true)
[ -n "$OUT" ] || { echo "      적재 실패. current 와 LOADED.log 는 그대로입니다." >&2; exit 1; }

echo "[4/4] 기록"
ln -sfn "$NAME" "$ROOT/current"
printf '%s\t%s\tzip=%s\t%s\tcommit=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NAME" "$ZIP_SHA" "$OUT" "$(git rev-parse --short HEAD)" >> "$ROOT/LOADED.log"
echo "      current -> $NAME"
tail -n 1 "$ROOT/LOADED.log"
