"""오류 응답을 contracts/error.schema.json 형식으로 통일한다.

내부 경로·쿼리·스택 트레이스는 응답에 담지 않는다.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("onroad.api")

_CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 422: "bad_request", 429: "rate_limited"}
_MESSAGES = {
    "bad_request": "요청 값이 올바르지 않습니다.",
    "not_found": "요청한 대상을 찾을 수 없습니다.",
    "method_not_allowed": "읽기 전용 API입니다. GET 요청만 받습니다.",
    "rate_limited": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    "internal_error": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
}


# 상황별 안내 문구(HTTPException detail 로 지정). 코드는 계약의 enum 을 그대로 쓴다.
NOT_LOADED = 'not_loaded'
_DETAIL_MESSAGES = {
    NOT_LOADED: '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.',
}


def error_body(code: str, message: str | None = None) -> dict:
    return {"error": {"code": code, "message": message or _MESSAGES[code]}}


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = _CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "bad_request")
        message = _DETAIL_MESSAGES.get(exc.detail) if isinstance(exc.detail, str) else None
        return JSONResponse(error_body(code, message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(error_body("bad_request"), status_code=400)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(error_body("internal_error"), status_code=500)
