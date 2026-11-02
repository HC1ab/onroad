import csv
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app import routes, static_bundle
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
    ('/api/validation', 'validation'), ('/api/crosswalks', 'points'),
    ('/api/areas?target=0.85&radius=300', 'areas_v2'), ('/api/crosswalks?target=0.85&radius=300', 'points_v2'),
])
def test_response_contract_and_source_values(database, path, kind):
    response = client.get(path)
    assert response.status_code == 200
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.schema.json')}
    registry = Registry().with_resources((n, Resource.from_contents(s)) for n, s in schemas.items())
    schema = schemas[f"{kind.removesuffix('_v2')}.schema.json"]
    Draft202012Validator(schema, registry=registry).validate(response.json())
    expected = json.loads((ROOT / 'samples' / f'{kind}.json').read_text(encoding='utf-8'))
    actual = response.json()
    if kind in ('areas', 'areas_v2'):
        expected['items'].sort(key=lambda x: x['adm_cd'])
    elif kind == 'area_crosswalks':
        expected['items'].sort(key=lambda x: (-x['gap_s'], x['cw_id']))
    elif kind in ('candidates', 'points', 'points_v2'):
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
    '/api/crosswalks?bbox=10,0,1,1', '/api/crosswalks?radius=250',
    '/api/areas?target=0.8', '/api/areas?target=foo', '/api/areas?target=',
    '/api/crosswalks?target=1', '/api/crosswalks?target=nan',
    '/api/areas?target=0.85&speed=2', '/api/crosswalks?target=0.85&radius=400',
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
    for path in ['/api/areas', '/api/areas/{adm_cd}/crosswalks', '/api/crosswalks/candidates', '/api/crosswalks', '/api/meta', '/api/validation']:
        response = schema['paths'][path]['get']['responses']
        assert '422' not in response
        assert response['200']['content']['application/json']['schema']['required']
    for path in ['/api/areas', '/api/crosswalks']:
        assert 'target' in [p['name'] for p in schema['paths'][path]['get']['parameters']]
    if ROOT.exists():
        assert SCHEMAS == {p.name: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.schema.json')}


def test_csv_exports(database):
    response = client.get('/api/export/areas.csv?speed=0.8&radius=300')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/csv')
    assert 'areas_0.8_300_sample.csv' in response.headers['content-disposition']
    assert response.content.startswith(b'\xef\xbb\xbf')
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    expected = json.loads((ROOT / 'samples' / 'areas.json').read_text(encoding='utf-8'))
    assert [r['adm_cd'] for r in rows] == sorted(i['adm_cd'] for i in expected['items'])
    assert rows[0]['low_sample'] in ('true', 'false')
    assert rows[0]['n_short'] != ''
    # CSV 는 v1 형식 그대로다. C3 스키마의 v2 전용 필드가 빈 칼럼으로 섞이지 않는다.
    assert not {'mean_add_s', 'n_add2', 'coverage_now_mean', 'coverage_required_mean'} & rows[0].keys()

    response = client.get('/api/export/crosswalks.csv')
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    detail = json.loads((ROOT / 'samples' / 'area_crosswalks.json').read_text(encoding='utf-8'))
    candidates = [i for i in detail['items'] if i['is_candidate']]
    assert len(rows) == len(candidates) and rows
    assert all(r['adm_cd'] == detail['adm_cd'] and r['is_candidate'] == 'true' for r in rows)
    assert 'flags.senior_center' in rows[0] and 'flags' not in rows[0]

    for path in ('/api/export/areas.csv?speed=0.7', '/api/export/crosswalks.csv?radius=500'):
        response = client.get(path)
        assert response.status_code == 500
        assert response.json()['error']['message'] == '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.'
    assert client.get('/api/export/areas.csv?radius=400').status_code == 400


def test_static_bundle_matches_api(database, tmp_path):
    with routes.reader() as conn:
        manifest = static_bundle.build(conn, tmp_path)
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.schema.json')}
    registry = Registry().with_resources((n, Resource.from_contents(s)) for n, s in schemas.items())
    Draft202012Validator(schemas['static_manifest.schema.json'], registry=registry).validate(manifest)
    assert manifest['_sample'] is True
    assert manifest['results'] == [{'speed': 0.8, 'radius_m': 300, 'points': True, 'details': ['21090730']}]
    assert manifest['results_v2'] == [{'target': 0.85, 'radius_m': 300, 'points': True}]
    for file, path in (('areas/0.8_300.json', '/api/areas'), ('candidates/0.8_300.json', '/api/crosswalks/candidates'),
                       ('crosswalks/0.8_300/21090730.json', '/api/areas/21090730/crosswalks'),
                       ('points/0.8_300.json', '/api/crosswalks'),
                       ('areas_v2/0.85_300.json', '/api/areas?target=0.85'),
                       ('points_v2/0.85_300.json', '/api/crosswalks?target=0.85'),
                       ('meta.json', '/api/meta'), ('validation.json', '/api/validation')):
        assert json.loads((tmp_path / file).read_text(encoding='utf-8')) == client.get(path).json()
    for name in ('areas', 'crosswalks'):
        csv_file = (tmp_path / 'export' / f'{name}_0.8_300.csv').read_bytes()
        assert csv_file == client.get(f'/api/export/{name}.csv').content
    assert not (tmp_path / 'areas' / '0.7_300.json').exists()


def test_points_layer(database):
    """전체 점: 분석·분석 제외를 함께 주고, bbox 로 거르고, 미적재 조합은 빈 결과가 아니라 안내."""
    data = client.get('/api/crosswalks').json()
    statuses = {f['properties']['status'] for f in data['features']}
    assert statuses == {'analyzed', 'excluded'}
    excluded = [f['properties'] for f in data['features'] if f['properties']['status'] == 'excluded']
    assert all(p['gap_s'] is None and p['exclude_reason'] for p in excluded)
    inside = client.get('/api/crosswalks?bbox=129.13,35.17,129.16,35.19').json()['features']
    assert 0 < len(inside) < len(data['features'])
    for f in inside:
        x, y = f['geometry']['coordinates']
        assert 129.13 <= x <= 129.16 and 35.17 <= y <= 35.19
    response = client.get('/api/crosswalks?radius=500')
    assert response.status_code == 500
    assert response.json()['error']['message'] == '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.'


def test_min_sample_and_points_optional(database):
    assert client.get('/api/areas').json()['min_sample'] == 5
    # 점 파일이 없는 묶음도 적재된다(선택 항목). 그때 전체 점은 미적재 안내.
    bundle = [(k, d) for k, d in read_bundle(ROOT / 'samples', ROOT, True) if k != 'points']
    with psycopg.connect(database) as conn:
        ingest(conn, bundle, True)
    assert client.get('/api/crosswalks').status_code == 500
    assert client.get('/api/areas').status_code == 200


NOT_LOADED_MESSAGE = '요청한 속도·반경·지역의 결과가 아직 적재되지 않았습니다.'


def test_v2_shape_keeps_v1_responses_apart(database):
    v1, v2 = client.get('/api/areas').json(), client.get('/api/areas?target=0.85').json()
    assert 'target' not in v1 and 'speed' in v1 and 'n_short' in v1['items'][0]
    assert 'speed' not in v2 and v2['target'] == 0.85 and 'mean_add_s' in v2['items'][0]
    assert v2['min_sample'] == 5 and 'mean_add_s_median' in v2['thresholds']
    # 같은 cw_id 라도 target 없는 요청에는 v2 필드가 없다.
    v1_point = client.get('/api/crosswalks').json()['features'][0]['properties']
    assert 'tier' not in v1_point


def test_v2_speed_handling(database):
    """areas 는 target 이 있으면 speed 를 무시하고, 점의 v1 필드는 적재된 속도만 내준다."""
    assert client.get('/api/areas?target=0.85&speed=0.7').json() == client.get('/api/areas?target=0.85').json()
    assert client.get('/api/crosswalks?target=0.85&speed=0.8').status_code == 200
    response = client.get('/api/crosswalks?target=0.85&speed=0.7')
    assert response.status_code == 500
    assert response.json()['error']['message'] == NOT_LOADED_MESSAGE


def test_v2_not_loaded_is_not_empty(database):
    for path in ('/api/areas?target=0.9', '/api/areas?target=0.95', '/api/areas?target=0.85&radius=500',
                 '/api/crosswalks?target=0.9', '/api/crosswalks?target=0.85&radius=200'):
        response = client.get(path)
        assert response.status_code == 500
        assert response.json()['error']['message'] == NOT_LOADED_MESSAGE


def test_v2_filters_and_data_check(database):
    filtered = client.get('/api/areas', params={'target': 0.85, 'sido': '부산광역시', 'sigungu': '해운대구'}).json()
    everything = client.get('/api/areas?target=0.85').json()
    assert 0 < len(filtered['items']) < len(everything['items'])
    assert all(i['sigungu'] == '해운대구' for i in filtered['items'])
    assert filtered['thresholds'] == everything['thresholds']

    features = client.get('/api/crosswalks?target=0.85').json()['features']
    assert {f['properties']['status'] for f in features} == {'analyzed', 'excluded', 'data_check'}
    for p in (f['properties'] for f in features if f['properties']['status'] == 'data_check'):
        assert p['check_reason'] and p['is_candidate'] is False
        assert p['t_need_s'] is None and p['gap_s'] is None and p['t_required_s'] is None and p['add_s'] is None
        assert p['tier'] is None
    box = '129.13,35.17,129.16,35.19'
    inside = client.get(f'/api/crosswalks?target=0.85&bbox={box}').json()['features']
    assert 0 < len(inside) < len(features)
    for f in inside:
        x, y = f['geometry']['coordinates']
        assert 129.13 <= x <= 129.16 and 35.17 <= y <= 35.19
    assert client.get('/api/crosswalks?target=0.85&bbox=0,0,1,1').json()['features'] == []


def test_target_is_part_of_the_key(database):
    """목표 커버리지별 결과를 따로 적재하고, 요청한 target 의 값만 돌려준다."""
    bundle = read_bundle(ROOT / 'samples', ROOT, True)
    extra = []
    for kind, data in bundle:
        if kind == 'areas_v2':
            copy = json.loads(json.dumps(data))
            copy['target'] = 0.9
            for item in copy['items']:
                item['n_add2'] = item['n_add2'] + 1
            extra.append((kind, copy))
        elif kind == 'points_v2':
            copy = json.loads(json.dumps(data))
            copy['target'] = 0.9
            copy['features'] = copy['features'][:3]
            extra.append((kind, copy))
    with psycopg.connect(database) as conn:
        ingest(conn, bundle + extra, True)
    a85, a90 = client.get('/api/areas?target=0.85').json(), client.get('/api/areas?target=0.90').json()
    assert a90['target'] == 0.9
    by85 = {i['adm_cd']: i['n_add2'] for i in a85['items']}
    assert all(i['n_add2'] == by85[i['adm_cd']] + 1 for i in a90['items'])
    assert len(client.get('/api/crosswalks?target=0.9').json()['features']) == 3
    assert len(client.get('/api/crosswalks?target=0.85').json()['features']) == 87


def test_v2_documents_pass_through(database):
    validation = client.get('/api/validation').json()
    assert validation['v6']['uplift_range'] and validation['v7']['groups']
    assert client.get('/api/meta').json()['coefficients']


def test_bundle_without_v2_keeps_v1(database):
    bundle = [(k, d) for k, d in read_bundle(ROOT / 'samples', ROOT, True) if not k.endswith('_v2')]
    with psycopg.connect(database) as conn:
        ingest(conn, bundle, True)
    assert client.get('/api/areas').status_code == 200
    assert client.get('/api/crosswalks').status_code == 200
    assert client.get('/api/areas?target=0.85').status_code == 500
    assert client.get('/api/crosswalks?target=0.85').status_code == 500


def test_static_bundle_omits_v2_when_not_loaded(database, tmp_path):
    bundle = [(k, d) for k, d in read_bundle(ROOT / 'samples', ROOT, True) if not k.endswith('_v2')]
    with psycopg.connect(database) as conn:
        ingest(conn, bundle, True)
    with routes.reader() as conn:
        manifest = static_bundle.build(conn, tmp_path)
    assert 'results_v2' not in manifest
    assert not (tmp_path / 'areas_v2').exists()


def test_v1_points_accept_data_check(database):
    """C3: v1 점 묶음에도 status=data_check 가 올 수 있다."""
    bundle = read_bundle(ROOT / 'samples', ROOT, True)
    points = next(d for k, d in bundle if k == 'points')
    p = next(f['properties'] for f in points['features'] if f['properties']['status'] == 'analyzed')
    p.update(status='data_check', t_need_s=None, gap_s=None, is_candidate=False, check_reason='기록 방식 확인 필요')
    with psycopg.connect(database) as conn:
        ingest(conn, bundle, True)
    statuses = {f['properties']['status'] for f in client.get('/api/crosswalks').json()['features']}
    assert 'data_check' in statuses
