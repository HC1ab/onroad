"""Read precomputed exports; no analytical calculation on requests."""
import re
from contextlib import contextmanager
from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from .errors import NOT_LOADED
from .settings import get_settings
from .swagger import responses

api = APIRouter(prefix='/api')
Speed = Annotated[float, Query(enum=[0.7, 0.8, 1.0])]
Radius = Annotated[int, Query(enum=[200, 300, 500])]


def check_speed(speed):
    if speed not in (0.7, 0.8, 1.0):
        raise HTTPException(400)


def check_radius(radius):
    if radius not in (200, 300, 500):
        raise HTTPException(400)


def not_loaded():
    # 적재되지 않은 조합을 0건으로 꾸미지 않는다. 계약상 500, 문구로 사유를 알린다.
    return HTTPException(500, detail=NOT_LOADED)


@contextmanager
def reader():
    with psycopg.connect(get_settings().db_dsn) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout = '5s'")
        # Match the import lock so multiple reads cannot span two datasets.
        conn.execute('SELECT pg_advisory_xact_lock_shared(1373013)')
        yield conn


def sample_flag(conn):
    row = conn.execute('SELECT is_sample FROM dataset').fetchone()
    if row is None:
        raise HTTPException(500)
    return {'_sample': True} if row[0] else {}


@api.get('/areas', summary='읍면동별 집계', operation_id='listAreas', responses=responses('areas'))
def areas(speed: Speed = 0.8, radius: Radius = 300, sido: str | None = None, sigungu: str | None = None):
    check_speed(speed)
    check_radius(radius)
    if sigungu is not None and not sido:
        raise HTTPException(400)
    with reader() as conn:
        flag = sample_flag(conn)
        summary = conn.execute('SELECT thresholds FROM area_summary WHERE speed=%s AND radius_m=%s',
                               (speed, radius)).fetchone()
        if summary is None:
            raise not_loaded()
        clauses, params = ['v.speed=%s', 'v.radius_m=%s'], [speed, radius]
        for column, value in (('sido', sido), ('sigungu', sigungu)):
            if value is not None:
                clauses.append(f'a.{column}=%s')
                params.append(value)
        rows = conn.execute('SELECT v.payload FROM area_vulnerability v JOIN admin_area a USING(adm_cd) WHERE '
                            + ' AND '.join(clauses) + ' ORDER BY v.adm_cd', params).fetchall()
        return JSONResponse({**flag, 'speed': speed, 'radius_m': radius, 'thresholds': summary[0],
                             'items': [r[0] for r in rows]})


@api.get('/areas/{adm_cd}/crosswalks', summary='읍면동 횡단보도 목록',
         operation_id='listAreaCrosswalks', responses=responses('area_crosswalks', not_found=True))
def crosswalks(adm_cd: Annotated[str, Path(pattern=r'^[0-9]{8,10}$')], speed: Speed = 0.8, radius: Radius = 300):
    check_speed(speed)
    check_radius(radius)
    with reader() as conn:
        flag = sample_flag(conn)
        if not conn.execute('SELECT 1 FROM admin_area WHERE adm_cd=%s', (adm_cd,)).fetchone():
            raise HTTPException(404)
        if not conn.execute('SELECT 1 FROM area_detail WHERE adm_cd=%s AND speed=%s AND radius_m=%s',
                            (adm_cd, speed, radius)).fetchone():
            raise not_loaded()
        rows = conn.execute("SELECT g.payload FROM crosswalk_gap g JOIN crosswalk c USING(cw_id) "
                            "WHERE c.adm_cd=%s AND g.speed=%s AND g.radius_m=%s "
                            "ORDER BY (g.payload->>'gap_s')::numeric DESC,g.cw_id",
                            (adm_cd, speed, radius)).fetchall()
        return JSONResponse({**flag, 'adm_cd': adm_cd, 'speed': speed, 'radius_m': radius,
                             'items': [r[0] for r in rows]})


@api.get('/crosswalks/candidates', summary='후보 횡단보도 점', operation_id='listCandidates',
         responses=responses('candidates'))
def candidates(speed: Speed = 0.8, radius: Radius = 300, bbox: str | None = None):
    check_speed(speed)
    check_radius(radius)
    bounds = None
    if bbox is not None:
        if not re.fullmatch(r'-?\d+(\.\d+)?(,-?\d+(\.\d+)?){3}', bbox):
            raise HTTPException(400)
        bounds = [float(v) for v in bbox.split(',')]
        x1, y1, x2, y2 = bounds
        if not (-180 <= x1 < x2 <= 180 and -90 <= y1 < y2 <= 90):
            raise HTTPException(400)
    with reader() as conn:
        flag = sample_flag(conn)
        if not conn.execute('SELECT 1 FROM candidate_layer WHERE speed=%s AND radius_m=%s', (speed, radius)).fetchone():
            raise not_loaded()
        sql = 'SELECT payload FROM candidate WHERE speed=%s AND radius_m=%s'
        params = [speed, radius]
        if bounds:
            sql += ' AND geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)'
            params.extend(bounds)
        rows = conn.execute(sql + ' ORDER BY cw_id', params).fetchall()
        return JSONResponse({**flag, 'type': 'FeatureCollection', 'speed': speed, 'radius_m': radius,
                             'features': [r[0] for r in rows]})


def document(kind):
    with reader() as conn:
        row = conn.execute('SELECT payload FROM result_document WHERE kind=%s', (kind,)).fetchone()
        if row is None:
            raise HTTPException(500)
        # FastAPI's default encoder strips _sa* keys, including our _sample flag.
        return JSONResponse(row[0])


@api.get('/validation', summary='검증 결과 V1~V5', operation_id='getValidation', responses=responses('validation'))
def validation():
    return document('validation')


@api.get('/meta', summary='기준 정보와 한계', operation_id='getMeta', responses=responses('meta'))
def meta():
    return document('meta')
