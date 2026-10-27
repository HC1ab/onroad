import json
import os
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app import routes
from app.ingest import ingest, read_bundle
from app.main import app
from app.swagger import SCHEMAS

ROOT = Path(os.environ.get('TEST_CONTRACTS', '/contracts'))
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def database(monkeypatch):
    dsn = os.environ.get('TEST_DATABASE_DSN')
    if not dsn or not ROOT.exists():
        pytest.skip('Disposable DB and contracts mount required')
    with psycopg.connect(dsn) as conn:
        ingest(conn, read_bundle(ROOT / 'samples', ROOT, True), True)
    monkeypatch.setattr(routes, 'get_settings', lambda: SimpleNamespace(db_dsn=dsn))
    return dsn


@pytest.mark.parametrize('path,kind', [
    ('/api/areas', 'areas'), ('/api/areas/21090730/crosswalks', 'area_crosswalks'),
    ('/api/crosswalks/candidates', 'candidates'), ('/api/meta', 'meta'),
    ('/api/validation', 'validation'),
])
def test_response_contract_and_source_values(database, path, kind):
    response = client.get(path)
    assert response.status_code == 200
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.schema.json')}
    registry = Registry().with_resources((n, Resource.from_contents(s)) for n, s in schemas.items())
    Draft202012Validator(schemas[f'{kind}.schema.json'], registry=registry).validate(response.json())
    expected = json.loads((ROOT / 'samples' / f'{kind}.json').read_text(encoding='utf-8'))
    actual = response.json()
    if kind == 'areas':
        expected['items'].sort(key=lambda x: x['adm_cd'])
    elif kind == 'area_crosswalks':
        expected['items'].sort(key=lambda x: (-x['gap_s'], x['cw_id']))
    elif kind == 'candidates':
        expected['features'].sort(key=lambda x: x['properties']['cw_id'])
    assert actual == expected


@pytest.mark.parametrize('path', [
    '/api/areas?speed=2', '/api/areas?speed=nan', '/api/areas?speed=foo',
    '/api/areas?sigungu=x', '/api/areas/123/crosswalks',
    '/api/crosswalks/candidates?radius=400', '/api/crosswalks/candidates?radius=300.5',
    '/api/areas?radius=400', '/api/areas/21090730/crosswalks?radius=100',
    '/api/crosswalks/candidates?bbox=nan,0,1,1',
    '/api/crosswalks/candidates?bbox=10,0,1,1',
    '/api/crosswalks/candidates?bbox=-181,0,1,1',
    '/api/crosswalks/candidates?bbox=0,0,1,91',
    '/api/crosswalks/candidates?bbox=0,0,1',
])
def test_invalid_parameters_without_database(path):
    response = client.get(path)
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'bad_request'


def test_filters_and_empty_bbox(database):
    all_areas = client.get('/api/areas').json()
    filtered = client.get('/api/areas', params={'sido': '부산광역시', 'sigungu': '해운대구'}).json()
    assert filtered['items']
    assert all(i['sigungu'] == '해운대구' for i in filtered['items'])
    assert filtered['thresholds'] == all_areas['thresholds']
    assert client.get('/api/areas', params={'sido': "' OR 1=1 --"}).json()['items'] == []
    points = client.get('/api/crosswalks/candidates?bbox=129.13,35.17,129.16,35.19').json()['features']
    assert points
    for point in points:
        x, y = point['geometry']['coordinates']
        assert 129.13 <= x <= 129.16 and 35.17 <= y <= 35.19
    assert client.get('/api/crosswalks/candidates?bbox=0,0,1,1').json()['features'] == []


def test_missing_data_not_fabricated(database):
    assert client.get('/api/areas/00000000/crosswalks').status_code == 404
    for path in ('/api/areas?speed=0.7', '/api/crosswalks/candidates?radius=200',
                 '/api/areas/21090740/crosswalks', '/api/areas?radius=500',
                 '/api/areas/21090730/crosswalks?radius=200'):
        response = client.get(path)
        assert response.status_code == 500
        assert response.json()['error'] == {
            'code': 'internal_error', 'message': '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.'}


def test_radius_is_part_of_the_key(database):
    """반경별 결과를 따로 적재하고, 요청한 반경의 값만 돌려준다."""
    bundle = read_bundle(ROOT / 'samples', ROOT, True)
    extra = []
    for kind, data in bundle:
        if kind in ('areas', 'area_crosswalks'):
            copy = json.loads(json.dumps(data))
            copy['radius_m'] = 500
            if kind == 'areas':
                for item in copy['items']:
                    item['n_candidate'] = item['n_candidate'] + 1
            else:
                for item in copy['items']:
                    item['exposure_cnt'] = item['exposure_cnt'] + 1
                    item['flags']['market'] = True
            extra.append((kind, copy))
    with psycopg.connect(database) as conn:
        ingest(conn, bundle + extra, True)
    a300 = client.get('/api/areas?radius=300').json()
    a500 = client.get('/api/areas?radius=500').json()
    assert a300['radius_m'] == 300 and a500['radius_m'] == 500
    by300 = {i['adm_cd']: i['n_candidate'] for i in a300['items']}
    assert all(i['n_candidate'] == by300[i['adm_cd']] + 1 for i in a500['items'])
    c500 = client.get('/api/areas/21090730/crosswalks?radius=500').json()
    assert c500['radius_m'] == 500 and all(i['flags']['market'] for i in c500['items'])


def test_empty_imported_details_and_real_marker(database):
    bundle = read_bundle(ROOT / 'samples', ROOT, True)
    for kind, data in bundle:
        data.pop('_sample', None)
        if kind == 'area_crosswalks':
            data['items'] = []
    with psycopg.connect(database) as conn:
        ingest(conn, bundle, False)
    response = client.get('/api/areas/21090730/crosswalks')
    assert response.status_code == 200
    assert response.json()['items'] == []
    assert '_sample' not in response.json()
    assert '_sample' not in client.get('/api/areas').json()


def test_read_only_transaction(database):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with routes.reader() as conn:
            conn.execute('DELETE FROM dataset')


def test_database_errors_are_sanitized(monkeypatch):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('private-host SQL SELECT sensitive-path')
    monkeypatch.setattr(routes.psycopg, 'connect', fail)
    response = client.get('/api/areas')
    assert response.status_code == 500
    assert response.json() == {'error': {'code': 'internal_error',
        'message': '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'}}


def test_swagger_response_schemas():
    schema = client.get('/api/openapi.json').json()
    for path in ['/api/areas', '/api/areas/{adm_cd}/crosswalks', '/api/crosswalks/candidates', '/api/meta', '/api/validation']:
        response = schema['paths'][path]['get']['responses']
        assert '422' not in response
        assert response['200']['content']['application/json']['schema']['required']
    if ROOT.exists():
        assert SCHEMAS == {p.name: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.schema.json')}
