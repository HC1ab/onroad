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

정적 묶음(서버 없이 데모, F18)은 적재 후 비어 있는 폴더로 내보낸다.
```bash
bash server/deploy/export_static.sh /srv/onroad-static/$(date +%Y%m%d)
```

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
