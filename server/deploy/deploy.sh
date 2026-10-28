#!/usr/bin/env bash
# 운영 서버 배포: 코드 갱신 → 프론트 빌드 → 컨테이너 재기동 → 상태 확인.
# 저장소 루트(/srv/onroad)에서 실행한다: sh server/deploy/deploy.sh [--no-pull]
# --no-pull: 지금 체크아웃된 커밋 그대로 배포(되돌리기용)
# 값은 루트 .env 에서 읽는다(WEB_PORT=80 등). .env 는 서버에만 둔다.
set -euo pipefail
cd "$(dirname "$0")/../.."

[ -f .env ] || { echo ".env 가 없습니다. server/deploy/README.md 를 보고 먼저 만드세요." >&2; exit 1; }
WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2)
WEB_PORT=${WEB_PORT:-8080}

echo "[1/4] 코드 갱신"
if [ "${1:-}" = "--no-pull" ]; then echo "      건너뜀 (--no-pull)"; else git pull --ff-only; fi

echo "[2/4] 프론트 빌드 (Node 컨테이너, 서버에 Node 설치 불필요)"
docker run --rm --user "$(id -u):$(id -g)" \
  -e VITE_API_MODE=real -e npm_config_cache=/tmp/.npm \
  -v "$PWD:/repo" -w /repo/web node:22-alpine \
  sh -c "npm ci --no-audit --no-fund && npm run build"

# 경계 파일은 파이프라인 결과(D6)가 web/public/data 에 들어오기 전까지 샘플 경계를 쓴다.
if [ ! -f web/dist/data/boundaries.json ]; then
  mkdir -p web/dist/data
  cp contracts/samples/boundaries.json web/dist/data/boundaries.json
  echo "      경계: 샘플 사용 (web/public/data/boundaries.json 없음)"
fi

echo "[3/4] 컨테이너 재기동"
docker compose up -d --build --remove-orphans

echo "[4/4] 상태 확인"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${WEB_PORT}/healthz" >/dev/null 2>&1; then
    echo "      healthz OK ($(git rev-parse --short HEAD))"
    exit 0
  fi
  sleep 2
done
echo "      healthz 응답 없음. docker compose logs api 로 확인하세요." >&2
exit 1
