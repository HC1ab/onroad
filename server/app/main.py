"""한 박자 API (읽기 전용).

미리 적재한 결과를 /api 라우터에서 조회한다. 응답 형식은 contracts/ 스키마를 따른다.
"""
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, errors
from .settings import get_settings
from .routes import api

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


app.include_router(api)


def openapi():
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        for path in schema['paths'].values():
            for operation in path.values():
                operation.get('responses', {}).pop('422', None)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = openapi
