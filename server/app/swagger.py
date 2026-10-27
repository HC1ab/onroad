"""Bundled contract snapshot for standalone Docker Swagger documentation."""
import json
from pathlib import Path

SCHEMAS = json.loads(Path(__file__).with_name('api_schemas.json').read_text(encoding='utf-8'))


def inline(value):
    if isinstance(value, list):
        return [inline(v) for v in value]
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if '$ref' in value:
        file, _, fragment = value.pop('$ref').partition('#')
        target = SCHEMAS[file]
        for part in fragment.strip('/').split('/') if fragment else []:
            target = target[part]
        return {**inline(target), **inline(value)}
    return {k: inline(v) for k, v in value.items() if k not in ('$id', '$schema')}


def responses(kind, not_found=False):
    result = {200: {'description': '성공', 'content': {'application/json': {
        'schema': inline(SCHEMAS[f'{kind}.schema.json'])}}}}
    for status in [400, 500] + ([404] if not_found else []):
        result[status] = {'description': '오류', 'content': {'application/json': {
            'schema': inline(SCHEMAS['error.schema.json'])}}}
    return result
