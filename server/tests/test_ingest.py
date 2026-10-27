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
    assert len(read_bundle(tmp_path, CONTRACTS)) == 5
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


def test_idempotent_import_and_spatial_index(conn, bundle):
    for _ in range(2):
        with conn.transaction():
            ingest(conn, bundle, True)
    areas = next(d for k, d in bundle if k == 'areas')
    detail = next(d for k, d in bundle if k == 'area_crosswalks')
    assert conn.execute('SELECT count(*) FROM admin_area').fetchone()[0] == len(areas['items'])
    assert conn.execute('SELECT count(*) FROM crosswalk_gap').fetchone()[0] == len(detail['items'])
    assert conn.execute('SELECT bool_and(ST_SRID(geom)=4326) FROM candidate').fetchone()[0]
    assert conn.execute('SELECT count(*) FROM schema_migration').fetchone()[0] == 2
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
