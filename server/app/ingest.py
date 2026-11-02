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
# 없어도 되는 묶음 항목. 전체 횡단보도 점과 v2(결정 009)는 파이프라인 결과에 있을 때만 적재한다.
OPTIONAL_KINDS = ('points', 'areas_v2', 'points_v2')
# 적재 키가 되는 최상위 값. 스키마에서는 선택이라 여기서 확인한다.
KEY_FIELDS = {
    'candidates': {'speed', 'radius_m'},
    'points': {'speed', 'radius_m'},
    'areas_v2': {'target', 'radius_m'},
    'points_v2': {'target', 'speed', 'radius_m'},
}
# 반경이 없는 묶음(계약 #46 이전)은 기본 반경으로 본다.
DEFAULT_RADIUS = 300
# 반경에 따라 달라지는 항목. 횡단보도 기본 속성(위치·연장·기록값) 비교에서 뺀다.
VARIES = ('t_need_s', 'gap_s', 'is_candidate', 'flags', 'exposure_cnt')


def read_bundle(source, contracts, sample=False):
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8'))
               for p in contracts.glob('*.schema.json')}
    registry = Registry().with_resources(
        (name, Resource.from_contents(value)) for name, value in schemas.items())
    documents = []
    for kind in KINDS + OPTIONAL_KINDS:
        paths = sorted(source.rglob(f'{kind}.json'))
        if kind.endswith('_v2'):
            # 샘플은 areas_v2.json, 파이프라인 결과는 areas_v2/{target}_{radius}.json 이다.
            paths += sorted(source.rglob(f'{kind}/*.json'))
        if kind in OPTIONAL_KINDS and not paths:
            continue
        if not paths or (kind in ('meta', 'validation') and len(paths) != 1):
            raise ValueError(f'{kind}: missing or duplicate singleton document')
        schema = schemas[f"{kind.removesuffix('_v2')}.schema.json"]
        for path in paths:
            data = json.loads(path.read_text(encoding='utf-8'))
            Draft202012Validator(schema, registry=registry).validate(data)
            if data.get('_sample', False) != sample:
                raise ValueError('Sample and real results must not be mixed')
            if not KEY_FIELDS.get(kind, set()) <= data.keys():
                raise ValueError(f'{kind} requires explicit {sorted(KEY_FIELDS[kind])}')
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
    conn.execute('TRUNCATE crosswalk_point_v2, point_layer_v2, area_vulnerability_v2, area_summary_v2, crosswalk_point, point_layer, candidate, candidate_layer, crosswalk_gap, crosswalk, area_detail, area_vulnerability, area_summary, admin_area, result_document, dataset')
    conn.execute('INSERT INTO dataset (is_sample) VALUES (%s)', (sample,))
    areas = {}
    base_crosswalks = {}

    def add_area(item):
        """v1·v2 집계에 함께 나오는 읍면동 속성. 같은 코드의 속성이 다르면 적재를 멈춘다."""
        code = item['adm_cd']
        attrs = tuple(item[k] for k in ('adm_name', 'sido', 'sigungu'))
        if code in areas and areas[code] != attrs:
            raise ValueError('Conflicting area attributes')
        if code not in areas:
            conn.execute('INSERT INTO admin_area VALUES (%s,%s,%s,%s)', (code, *attrs))
            areas[code] = attrs

    for kind, data in documents:
        if kind == 'areas':
            speed = data['speed']
            radius = data.get('radius_m', DEFAULT_RADIUS)
            conn.execute('INSERT INTO area_summary (speed, radius_m, thresholds, min_sample) VALUES (%s,%s,%s,%s)',
                         (speed, radius, Jsonb(data['thresholds']), data.get('min_sample')))
            for item in data['items']:
                add_area(item)
                conn.execute('INSERT INTO area_vulnerability (speed, radius_m, adm_cd, payload) VALUES (%s,%s,%s,%s)',
                             (speed, radius, item['adm_cd'], Jsonb(item)))
        elif kind == 'areas_v2':
            target, radius = data['target'], data['radius_m']
            conn.execute('INSERT INTO area_summary_v2 VALUES (%s,%s,%s,%s)',
                         (target, radius, Jsonb(data['thresholds']), data.get('min_sample')))
            for item in data['items']:
                add_area(item)
                conn.execute('INSERT INTO area_vulnerability_v2 VALUES (%s,%s,%s,%s)',
                             (target, radius, item['adm_cd'], Jsonb(item)))
    seen_details = set()
    for kind, data in documents:
        if kind == 'area_crosswalks':
            radius = data.get('radius_m', DEFAULT_RADIUS)
            key = (data['adm_cd'], data['speed'], radius)
            if key in seen_details:
                raise ValueError('Duplicate area detail document')
            seen_details.add(key)
            if key[0] not in areas:
                raise ValueError('Unknown area in detail document')
            conn.execute('INSERT INTO area_detail (adm_cd, speed, radius_m) VALUES (%s,%s,%s)', key)
            for item in data['items']:
                base = {k: v for k, v in item.items() if k not in VARIES}
                identity = (data['adm_cd'], base)
                cw_id = item['cw_id']
                if cw_id in base_crosswalks and base_crosswalks[cw_id] != identity:
                    raise ValueError('Conflicting crosswalk attributes')
                if cw_id not in base_crosswalks:
                    conn.execute('INSERT INTO crosswalk VALUES (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                                 (cw_id, data['adm_cd'], item['lon'], item['lat'], Jsonb(base)))
                    base_crosswalks[cw_id] = identity
                conn.execute('INSERT INTO crosswalk_gap (cw_id, speed, radius_m, is_candidate, payload) '
                             'VALUES (%s,%s,%s,%s,%s)', (cw_id, data['speed'], radius, item['is_candidate'], Jsonb(item)))
        elif kind == 'candidates':
            conn.execute('INSERT INTO candidate_layer VALUES (%s,%s)', (data['speed'], data['radius_m']))
            for feature in data['features']:
                p = feature['properties']
                lon, lat = feature['geometry']['coordinates']
                conn.execute('INSERT INTO candidate VALUES (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                             (data['speed'], data['radius_m'], p['cw_id'], p['adm_cd'], lon, lat, Jsonb(feature)))
        elif kind == 'points':
            conn.execute('INSERT INTO point_layer VALUES (%s,%s)', (data['speed'], data['radius_m']))
            for feature in data['features']:
                p = feature['properties']
                lon, lat = feature['geometry']['coordinates']
                conn.execute('INSERT INTO crosswalk_point VALUES (%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                             (data['speed'], data['radius_m'], p['cw_id'], p['adm_cd'], p['status'], lon, lat,
                              Jsonb(feature)))
        elif kind == 'points_v2':
            target, radius = data['target'], data['radius_m']
            conn.execute('INSERT INTO point_layer_v2 VALUES (%s,%s,%s)', (target, radius, data['speed']))
            for feature in data['features']:
                p = feature['properties']
                lon, lat = feature['geometry']['coordinates']
                conn.execute('INSERT INTO crosswalk_point_v2 VALUES (%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s)',
                             (target, radius, p['cw_id'], p['adm_cd'], p['status'], lon, lat, Jsonb(feature)))
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
