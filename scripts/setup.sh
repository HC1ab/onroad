#!/bin/sh
# 클론 후 1회 실행: sh scripts/setup.sh
git config core.hooksPath .githooks
git config core.quotepath false
git config pull.rebase true
chmod +x .githooks/pre-commit .githooks/pre-push 2>/dev/null
[ -f .env ] || cp .env.example .env
echo "완료: hooksPath=.githooks, .env 생성(값은 직접 채우기)."
command -v gh >/dev/null 2>&1 || echo "gh CLI 가 없습니다: winget install GitHub.cli"
command -v gitleaks >/dev/null 2>&1 || echo "권장: winget install gitleaks.gitleaks"
