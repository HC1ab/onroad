"""Validated, atomic replacement of exported results; never reads raw data."""
import argparse
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from .settings import get_settings

KINDS = ('areas', 'area_crosswalks', 'candidates', 'validation', 'meta')


def read_bundle(source, contracts, sample=False):
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8'))
               for p in contracts.glob('*.schema.json')}
    registry = Registry().with_resources(
        (name, Resource.from_contents(value)) for name, value in schemas.items())
    documents = []
    for kind in KINDS:
        paths = sorted(source.rglob(f'{kind}.json'))
        if not paths or (kind in ('meta', 'validation') and len(paths) != 1):
            raise ValueError(f'{kind}: missing or duplicate singleton document')
        for path in paths:
            data = json.loads(path.read_text(encoding='utf-8'))
            Draft202012Validator(schemas[f'{kind}.schema.json'], registry=registry).validate(data)
            if data.get('_sample', False) != sample:
                raise ValueError('Sample and real results must not be mixed')
            if kind == 'candidates' and not {'speed', 'radius_m'} <= data.keys():
                raise ValueError('Candidate import requires explicit speed and radius_m')
            documents.append((kind, data))
    return documents


def migrate(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migration (version text PRIMARY KEY)')
    for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
        if not conn.execute('SELECT 1 FROM schema_migration WHERE version=%s', (path.name,)).fetchone():
            conn.execute(path.read_text(encoding='utf-8'))
            conn.execute('INSERT INTO schema_migration VALUES (%s)', (path.name,))


def ingest(conn, documents, sample=False):
    """Caller transaction covers migrations and all writes, including replacement."""
    conn.execute('SELECT pg_advisory_xact_lock(1373013)')
    migrate(conn)
    conn.execute('TRUNCATE candidate, candidate_layer, crosswalk_gap, crosswalk, area_detail, area_vulnerability, area_summary, admin_area, result_document, dataset')
    conn.execute('INSERT INTO dataset (is_sample) VALUES (%s)', (sample,))
    areas = {}
    base_crosswalks = {}
    for kind, data in documents:
        if kind != 'areas':
            continue
        speed = data['speed']
        conn.execute('INSERT INTO area_summary VALUES (%s,%s)', (speed, Jsonb(data['thresholds'])))
        for item in data['items']:
            code = item['adm_cd']
            attrs = tuple(item[k] for k in ('adm_name', 'sido', 'sigungu'))
            if code in areas and areas[code] != attrs:
                raise ValueError('Conflicting area attributes')
            if code not in areas:
                conn.execute('INSERT INTO admin_area VALUES (%s,%s,%s,%s)', (code, *attrs))
                areas[code] = attrs
            conn.execute('INSERT INTO area_vulnerability VALUES (%s,%s,%s)', (speed, code, Jsonb(item)))
    seen_details = set()
    for kind, data in documents:
        if kind == 'area_crosswalks':
            key = (data['adm_cd'], data['speed'])
            if key in seen_details:
                raise ValueError('Duplicate area detail document')
            seen_details.add(key)
            if key[0] not in areas:
                raise ValueError('Unknown area in detail document')
            conn.execute('INSERT INTO area_detail VALUES (%s,%s)', key)
            for item in data['items']:
                base = {k: v for k, v in item.items() if k not in ('t_need_s', 'gap_s', 'is_candidate')}
                identity = (data['adm_cd'], base)
                cw_id = item['cw_id']
                if cw_id in base_crosswalks and base_crosswalks[cw_id] != identity:
                    raise ValueError('Conflicting crosswalk attributes')
                if cw_id not in base_crosswalks:
                    conn.execute('INSERT INTO crosswalk VALUES (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                                 (cw_id, data['adm_cd'], item['lon'], item['lat'], Jsonb(base)))
                    base_crosswalks[cw_id] = identity
                conn.execute('INSERT INTO crosswalk_gap VALUES (%s,%s,%s,%s)',
                             (cw_id, data['speed'], item['is_candidate'], Jsonb(item)))
        elif kind == 'candidates':
            conn.execute('INSERT INTO candidate_layer VALUES (%s,%s)', (data['speed'], data['radius_m']))
            for feature in data['features']:
                p = feature['properties']
                lon, lat = feature['geometry']['coordinates']
                conn.execute('INSERT INTO candidate VALUES (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                             (data['speed'], data['radius_m'], p['cw_id'], p['adm_cd'], lon, lat, Jsonb(feature)))
        elif kind in ('meta', 'validation'):
            conn.execute('INSERT INTO result_document VALUES (%s,%s)', (kind, Jsonb(data)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--contracts', type=Path, default=Path('/contracts'))
    parser.add_argument('--sample', action='store_true')
    args = parser.parse_args()
    try:
        documents = read_bundle(args.source, args.contracts, args.sample)
        with psycopg.connect(get_settings().db_dsn) as conn:
            ingest(conn, documents, args.sample)
    except (ValueError, OSError, ValidationError, psycopg.Error) as exc:
        parser.exit(1, f'Import failed ({type(exc).__name__}); existing results preserved.\n')
    print(f'Imported {len(documents)} documents; sample={args.sample}')


if __name__ == '__main__':
    main()
