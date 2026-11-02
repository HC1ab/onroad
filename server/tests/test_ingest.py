"""Integration tests use a disposable database only (TEST_DATABASE_DSN)."""
import copy
import os
import json
import shutil
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from jsonschema.exceptions import ValidationError

from app.ingest import ingest, read_bundle

CONTRACTS = Path(os.environ.get('TEST_CONTRACTS', '/contracts'))


@pytest.fixture
def bundle():
    if not CONTRACTS.exists():
        pytest.skip('Mount contracts to run ingestion tests')
    return read_bundle(CONTRACTS / 'samples', CONTRACTS, sample=True)


@pytest.fixture
def conn():
    dsn = os.environ.get('TEST_DATABASE_DSN')
    if not dsn:
        pytest.skip('Set TEST_DATABASE_DSN to a disposable database')
    with psycopg.connect(dsn) as connection:
        yield connection


def test_sample_cannot_be_loaded_as_real(bundle):
    with pytest.raises(ValueError, match='must not be mixed'):
        read_bundle(CONTRACTS / 'samples', CONTRACTS)


def test_real_bundle_and_schema_rejection(bundle, tmp_path):
    for kind, document in bundle:
        document = copy.deepcopy(document)
        document.pop('_sample', None)
        (tmp_path / f'{kind}.json').write_text(json.dumps(document), encoding='utf-8')
    assert len(read_bundle(tmp_path, CONTRACTS)) == 8  # 필수 5 + 선택 points·areas_v2·points_v2
    path = tmp_path / 'areas.json'
    document = json.loads(path.read_text())
    document['items'][0]['adm_cd'] = 123
    path.write_text(json.dumps(document))
    with pytest.raises(ValidationError):
        read_bundle(tmp_path, CONTRACTS)


def test_missing_bundle_file_rejected(bundle, tmp_path):
    shutil.copytree(CONTRACTS / 'samples', tmp_path, dirs_exist_ok=True)
    (tmp_path / 'meta.json').unlink()
    with pytest.raises(ValueError, match='meta'):
        read_bundle(tmp_path, CONTRACTS, True)


def real_copy(bundle, tmp_path):
    """샘플 묶음을 실데이터처럼(_sample 없이) 폴더에 쓴다. v2 는 뺀다."""
    for kind, document in bundle:
        if kind.endswith('_v2'):
            continue
        document = copy.deepcopy(document)
        document.pop('_sample', None)
        (tmp_path / f'{kind}.json').write_text(json.dumps(document), encoding='utf-8')


def test_pipeline_v2_layout_is_read(bundle, tmp_path):
    """파이프라인 결과는 areas_v2/{target}_{radius}.json 이다(샘플의 areas_v2.json 과 다르다)."""
    real_copy(bundle, tmp_path)
    for kind, document in bundle:
        if not kind.endswith('_v2'):
            continue
        (tmp_path / kind).mkdir()
        for target in ('0.85', '0.90', '0.95'):
            document = {k: v for k, v in copy.deepcopy(document).items() if k != '_sample'}
            document['target'] = float(target)
            (tmp_path / kind / f'{target}_300.json').write_text(json.dumps(document), encoding='utf-8')
    loaded = read_bundle(tmp_path, CONTRACTS)
    assert sorted(d['target'] for k, d in loaded if k == 'areas_v2') == [0.85, 0.9, 0.95]
    assert sorted(d['target'] for k, d in loaded if k == 'points_v2') == [0.85, 0.9, 0.95]


@pytest.mark.parametrize('kind,field', [('points_v2', 'target'), ('points_v2', 'speed'), ('points_v2', 'radius_m'),
                                        ('areas_v2', 'radius_m')])
def test_v2_requires_explicit_keys(bundle, tmp_path, kind, field):
    real_copy(bundle, tmp_path)
    document = copy.deepcopy(next(d for k, d in bundle if k == kind))
    document.pop('_sample', None)
    document.pop(field)
    (tmp_path / f'{kind}.json').write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError, match=kind):
        read_bundle(tmp_path, CONTRACTS)


def test_v1_shape_rejected_as_areas_v2(bundle, tmp_path):
    real_copy(bundle, tmp_path)
    document = copy.deepcopy(next(d for k, d in bundle if k == 'areas'))
    document.pop('_sample', None)
    (tmp_path / 'areas_v2.json').write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError, match='areas_v2'):
        read_bundle(tmp_path, CONTRACTS)


def test_v2_only_area_is_registered(conn, bundle):
    broken = copy.deepcopy(bundle)
    areas_v2 = next(d for k, d in broken if k == 'areas_v2')
    extra = copy.deepcopy(areas_v2['items'][0])
    extra.update(adm_cd='21099999', adm_name='샘플동')
    areas_v2['items'].append(extra)
    with conn.transaction():
        ingest(conn, broken, True)
    assert conn.execute("SELECT adm_name FROM admin_area WHERE adm_cd='21099999'").fetchone()[0] == '샘플동'


def test_conflicting_v2_area_rolls_back(conn, bundle):
    with conn.transaction():
        ingest(conn, bundle, True)
    broken = copy.deepcopy(bundle)
    next(d for k, d in broken if k == 'areas_v2')['items'][0]['adm_name'] = '다른 이름'
    with pytest.raises(ValueError, match='Conflicting area'):
        with conn.transaction():
            ingest(conn, broken, True)
    assert conn.execute('SELECT count(*) FROM crosswalk_point_v2').fetchone()[0] == len(
        next(d for k, d in bundle if k == 'points_v2')['features'])


def test_idempotent_import_and_spatial_index(conn, bundle):
    for _ in range(2):
        with conn.transaction():
            ingest(conn, bundle, True)
    areas = next(d for k, d in bundle if k == 'areas')
    detail = next(d for k, d in bundle if k == 'area_crosswalks')
    assert conn.execute('SELECT count(*) FROM admin_area').fetchone()[0] == len(areas['items'])
    assert conn.execute('SELECT count(*) FROM crosswalk_gap').fetchone()[0] == len(detail['items'])
    assert conn.execute('SELECT bool_and(ST_SRID(geom)=4326) FROM candidate').fetchone()[0]
    assert conn.execute('SELECT count(*) FROM schema_migration').fetchone()[0] == 5
    assert conn.execute('SELECT count(*) FROM crosswalk_point').fetchone()[0] == len(next(d for k, d in bundle if k == 'points')['features'])
    assert conn.execute('SELECT count(*) FROM crosswalk_point_v2').fetchone()[0] == len(next(d for k, d in bundle if k == 'points_v2')['features'])
    assert conn.execute('SELECT count(*) FROM area_vulnerability_v2').fetchone()[0] == len(next(d for k, d in bundle if k == 'areas_v2')['items'])
    assert conn.execute('SELECT DISTINCT target FROM area_summary_v2').fetchall() == [(Decimal('0.85'),)]
    assert conn.execute('SELECT DISTINCT radius_m FROM area_summary').fetchall() == [(300,)]
    assert conn.execute('SELECT is_sample FROM dataset').fetchone()[0] is True
    assert conn.execute('SELECT DISTINCT speed FROM area_summary').fetchall() == [(Decimal('0.8'),)]


def test_duplicate_input_rolls_back_previous_results(conn, bundle):
    with conn.transaction():
        ingest(conn, bundle, True)
    before = conn.execute('SELECT payload FROM area_vulnerability ORDER BY adm_cd').fetchall()
    broken = copy.deepcopy(bundle)
    areas = next(d for k, d in broken if k == 'areas')
    areas['items'].append(areas['items'][0])
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            ingest(conn, broken, True)
    assert conn.execute('SELECT payload FROM area_vulnerability ORDER BY adm_cd').fetchall() == before


def test_unknown_area_rolls_back(conn, bundle):
    with conn.transaction():
        ingest(conn, bundle, True)
    broken = copy.deepcopy(bundle)
    next(d for k, d in broken if k == 'area_crosswalks')['adm_cd'] = '00000000'
    with pytest.raises(ValueError, match='Unknown area'):
        with conn.transaction():
            ingest(conn, broken, True)
    assert conn.execute('SELECT count(*) FROM crosswalk').fetchone()[0] > 0
