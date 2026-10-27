"""한 박자 API (읽기 전용).

엔드포인트 구현은 B3(#14)에서 /api 라우터에 붙인다. 응답 형식은 contracts/ 스키마를 따른다.
"""
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, errors
from .settings import get_settings

app = FastAPI(title="한 박자 API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
errors.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def read_only(request: Request, call_next):
    """쓰기 메서드는 라우팅 전에 거부한다."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return JSONResponse(errors.error_body("method_not_allowed"), status_code=405)
    return await call_next(request)


@app.get("/healthz")
def healthz():
    """API가 떠 있고 DB에 연결되면 200, DB 연결이 안 되면 503."""
    db_ok = db.ping()
    body = {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "down"}
    return JSONResponse(body, status_code=200 if db_ok else 503)


api = APIRouter(prefix="/api")
# B3(#14): areas, area_crosswalks, candidates, validation, meta 라우트를 여기에 추가한다.
app.include_router(api)
