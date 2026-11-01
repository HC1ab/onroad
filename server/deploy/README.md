# 운영 서버 배포 (F16)

로컬과 같은 `docker-compose.yml`과 같은 이미지를 쓴다. 차이는 서버의 `.env` 값뿐이다.
접속 주소·계정·포트 같은 SSH 정보는 이 문서와 이슈에 쓰지 않는다.

## 구성
```text
브라우저 ─HTTPS→ 학과 게이트웨이 ─HTTP→ 서버 :80 nginx ─┬─ 프론트 빌드(web/dist)
                                                         └─ /api → api:8000 → db(PostGIS)
```
- HTTPS는 게이트웨이가 처리한다. 서버는 80만 연다.
- DB(5432)는 포트를 열지 않는다. API(8000)는 서버 내부(127.0.0.1)에만 열린다.
- 방화벽(ufw)은 22, 80만 허용한다.

## 처음 한 번
```bash
# Docker Engine + compose plugin (공식 저장소). 설치 후 다시 로그인해 docker 그룹 적용
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw --force enable

sudo mkdir -p /srv/onroad && sudo chown "$USER": /srv/onroad
git clone https://github.com/HC1ab/onroad.git /srv/onroad
cd /srv/onroad
cp .env.example .env && chmod 600 .env
```
`.env`에서 바꿀 값:

| 키 | 값 |
| --- | --- |
| `DB_PASSWORD` | 서버에서 만든 긴 무작위 값 (`openssl rand -hex 24`). 서버 밖으로 꺼내지 않는다 |
| `WEB_PORT` | `80` |
| `ALLOWED_ORIGINS` | 공개 URL (`https://…`) |
| `DATA_GO_KR_KEY_*` | 비워 둔다. 서버에는 인증키를 두지 않는다 |

## 배포·적재
```bash
cd /srv/onroad
bash server/deploy/deploy.sh                 # git pull → 프론트 빌드 → compose up → /healthz 확인
bash server/deploy/load.sh --sample          # 샘플 적재 (실데이터 전까지)
bash server/deploy/load.sh /srv/onroad-results   # 파이프라인 결과 적재 (scp 로 결과 JSON만 올린다)
```
- 프론트는 Node 컨테이너로 빌드하므로 서버에 Node를 설치하지 않는다.
- `web/public/data/boundaries.json`(D6 결과)이 없으면 샘플 경계를 쓴다.
- 적재는 전체 교체다. 실패하면 이전 결과가 남는다.

## 재부팅
Docker 서비스가 부팅 때 켜지고, 컨테이너는 `restart: unless-stopped`로 다시 뜬다.
`docker compose down`으로 직접 내린 컨테이너는 재부팅 뒤에도 내려간 상태로 남는다.

## 확인과 되돌리기
```bash
docker compose ps
docker compose logs --tail 50 api
git checkout <이전 커밋> && bash server/deploy/deploy.sh --no-pull   # 되돌리기
git checkout main && bash server/deploy/deploy.sh                       # 다시 최신으로
```

## 자동 배포 (self-hosted runner)
`main`에 병합되면 `.github/workflows/deploy.yml`이 서버에서 `deploy.sh`를 실행한다. 문서(`docs/`, `*.md`)만 바뀐 병합은 배포하지 않는다.
학과 게이트웨이 뒤라 GitHub Actions가 SSH로 들어올 수 없으므로, 서버에 runner를 설치해 **서버가 GitHub로 나가는 연결**만 쓴다.

### 퍼블릭 저장소 보안 (먼저, 관리자)
self-hosted runner는 그 워크플로를 실행하는 누구의 코드든 서버에서 돌린다. 아래 세 가지를 runner 등록 **전에** 켠다.
1. Settings → Actions → General → Fork pull request workflows from outside collaborators → **Require approval for all outside collaborators**
2. Settings → Environments → `production` 생성 → Deployment branches and tags → **Selected branches: `main`**
3. `deploy.yml`은 `push`(main)와 수동 실행만 받는다. 다른 워크플로에 `runs-on: self-hosted`를 쓰지 않는다(리뷰에서 확인)

### runner 설치 (서버, 배포 계정으로)
- 배포 계정은 `/srv/onroad` 소유자이고 `docker` 그룹이어야 한다(위 "처음 한 번").
- Settings → Actions → Runners → **New self-hosted runner** → Linux x64 화면의 명령을 그대로 실행한다. 등록 토큰은 그 화면에만 있고 1시간 뒤 만료된다. 토큰을 이슈·PR·채팅에 붙이지 않는다.
- `./config.sh` 질문에서 라벨에 **`onroad-prod`**를 추가한다. runner 폴더는 저장소 밖(예: `~/actions-runner`)에 둔다.
- 서비스로 등록해 재부팅 뒤에도 뜨게 한다.
```bash
cd ~/actions-runner
sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status
```

### 켜기·끄기 (관리자)
- Settings → Secrets and variables → Actions → Variables
  - `DEPLOY_ENABLED` = `true` (끄려면 `false` 또는 삭제. 꺼져 있으면 job이 건너뛰어진다)
  - `DEPLOY_DIR` = 저장소 경로 (기본 `/srv/onroad`면 안 만들어도 된다)
- 시크릿은 필요 없다. 서버 `.env`는 지금처럼 서버에만 둔다.

### 확인과 되돌리기
- Actions → deploy 실행 로그 마지막 줄이 `healthz OK (<커밋>)`이고, Summary에 컨테이너 상태가 나온다.
- 되돌리기: Actions → deploy → Run workflow → `ref`에 이전 커밋 SHA → 실행 (`deploy.sh --no-pull`). 다시 최신으로: `ref`를 비우고 실행.
- runner가 꺼져 있으면 job이 대기한다. 급하면 위 "배포·적재"처럼 서버에서 직접 실행한다.
