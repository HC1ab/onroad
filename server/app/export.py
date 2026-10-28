"""CSV 내려받기(F12) 형식. API와 정적 묶음이 같은 칼럼·같은 파일을 쓴다.

칼럼은 contracts 스키마의 항목 순서를 따르고, 객체(flags)는 `flags.senior_center`처럼 펼친다.
"""
import csv
import io

from .swagger import SCHEMAS, inline


def _columns(item_schema, prefix=''):
    columns = []
    for name, spec in inline(item_schema)['properties'].items():
        if spec.get('type') == 'object' and 'properties' in spec:
            columns += _columns(spec, f'{prefix}{name}.')
        else:
            columns.append(prefix + name)
    return columns


AREA_COLUMNS = _columns(SCHEMAS['areas.schema.json']['properties']['items']['items'])
CROSSWALK_COLUMNS = ['adm_cd'] + _columns(SCHEMAS['area_crosswalks.schema.json']['properties']['items']['items'])


def csv_name(name, speed, radius):
    """정적 묶음 파일 이름과 같다: areas_0.8_300.csv"""
    return f'{name}_{speed:.1f}_{radius}.csv'


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return value


def _flatten(row, prefix=''):
    flat = {}
    for key, value in row.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f'{prefix}{key}.'))
        else:
            flat[prefix + key] = value
    return flat


def to_csv(columns, rows):
    """UTF-8(BOM) CSV. 엑셀에서 한글이 깨지지 않게 BOM을 붙인다. 스키마에 없는 키는 넣지 않는다."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(columns)
    for row in rows:
        flat = _flatten(row)
        writer.writerow([_cell(flat.get(c)) for c in columns])
    return '﻿' + out.getvalue()


def csv_responses():
    error = {'description': '오류', 'content': {'application/json': {'schema': inline(SCHEMAS['error.schema.json'])}}}
    return {200: {'description': 'UTF-8(BOM) CSV', 'content': {'text/csv': {'schema': {'type': 'string'}}}},
            400: error, 500: error}
