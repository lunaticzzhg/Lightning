"""Check methods, media, wire schemas and models against committed HTTP contract.

Run: PYTHONPATH=. .venv/bin/python scripts/check_routes.py
"""
import json
from pathlib import Path
from sqlalchemy import create_engine
from backend.app.api import create_app

root = Path(__file__).resolve().parents[1]
contract = json.loads((root / 'contracts/http/openapi.json').read_text())
actual_doc = create_app(create_engine('sqlite://')).openapi()
actual = actual_doc['paths']
expected = contract['paths']


def shape(schema, components):
    if '$ref' in schema:
        name = schema['$ref'].split('/')[-1]
        return shape(components[name], components)
    if 'anyOf' in schema:
        return tuple(sorted((shape(s, components) for s in schema['anyOf']), key=str))
    kind = schema.get('type')
    if isinstance(kind, list):
        return tuple(sorted((shape({'type': k}, components) for k in kind), key=str))
    if kind == 'object':
        return ('object', tuple(sorted(schema.get('required', []))),
                tuple((k, shape(v, components)) for k, v in sorted(schema.get('properties', {}).items())),
                schema.get('additionalProperties') is True)
    if kind == 'array':
        return ('array', shape(schema['items'], components))
    return (kind, schema.get('format'))


for path, methods in expected.items():
    if path not in actual:
        raise SystemExit(f'missing path: {path}')
    for method, operation in methods.items():
        route = actual[path].get(method)
        if route is None or route['operationId'] != operation['operationId']:
            raise SystemExit(f'operation mismatch: {method.upper()} {path}')
        for status, definition in operation['responses'].items():
            response = route['responses'].get(status)
            if response is None:
                raise SystemExit(f'response status mismatch: {method.upper()} {path} {status}')
            for media, entry in definition.get('content', {}).items():
                target = response.get('content', {}).get(media)
                if target is None or shape(entry['schema'], contract['components']['schemas']) != shape(target.get('schema', {}), actual_doc['components']['schemas']):
                    raise SystemExit(f'response schema mismatch: {method.upper()} {path} {media}')
        for media, entry in operation.get('requestBody', {}).get('content', {}).items():
            target = route.get('requestBody', {}).get('content', {}).get(media)
            if target is None or shape(entry['schema'], contract['components']['schemas']) != shape(target.get('schema', {}), actual_doc['components']['schemas']):
                raise SystemExit(f'request schema mismatch: {method.upper()} {path} {media}')
extra = {(p, m) for p, methods in actual.items() for m in methods if m in ('get', 'post', 'put', 'patch', 'delete')} - {(p, m) for p, methods in expected.items() for m in methods}
if extra:
    raise SystemExit(f'undocumented routes: {extra}')
print('HTTP routes and wire schemas match contract')
