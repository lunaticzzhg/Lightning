"""Exercise the running local Compose stack using its browser-facing HTTP API."""
import hashlib
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile

BASE = os.environ.get('LIGHTNING_SMOKE_BASE', 'http://127.0.0.1:8000')
COMPOSE = ['docker', 'compose', '-f', 'deploy/local/compose.yaml']
if os.environ.get('LIGHTNING_COMPOSE_PROJECT'):
    COMPOSE.extend(['-p', os.environ['LIGHTNING_COMPOSE_PROJECT']])


def call(path, method='GET', data=None, headers=None):
    request = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def pack(name):
    body = io.BytesIO()
    manifest = {'schema_version': 1, 'interface_version': 1, 'name': name,
                'description': '容器验证', 'markets': ['US'], 'bar_interval': '1m',
                'required_fields': ['close'], 'entrypoint': 'strategy:on_bar',
                'python': '3.13', 'dependencies': [],
                'parameters': [{'name': 'window', 'type': 'integer', 'required': True,
                                'default': 5, 'min': 1, 'max': 20}]}
    with zipfile.ZipFile(body, 'w') as archive:
        archive.writestr('strategy.json', json.dumps(manifest, ensure_ascii=False))
        archive.writestr('strategy.py', 'def on_bar(event):\n    return None\n')
    return body.getvalue()


def upload(path, content, token):
    boundary = uuid.uuid4().hex
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="demo.zip"\r\n'
            'Content-Type: application/zip\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    return call(path, 'POST', data, {'Content-Type': f'multipart/form-data; boundary={boundary}', 'X-Lightning-Token': token})


def main():
    for attempt in range(30):
        try:
            if call('/api/status')[0] == 200:
                break
        except OSError:
            pass
        if attempt == 29:
            raise RuntimeError('本地应用未就绪')
        time.sleep(0.2)
    status, data = call('/api/status')
    assert status == 200, (status, data)
    token = json.loads(data)['token']
    original = pack('容器验证_' + uuid.uuid4().hex[:8])
    assert upload('/api/strategies', original, 'wrong')[0] == 403
    status, data = upload('/api/strategies', original, token)
    assert status == 201, (status, data)
    version = json.loads(data)
    assert version['sha256'] == hashlib.sha256(original).hexdigest()
    assert upload('/api/strategies', original, token)[0] == 409
    assert call(f"/api/versions/{version['id']}/download")[1] == original
    subprocess.run([*COMPOSE, 'restart', 'app'], check=True, capture_output=True)
    for _ in range(20):
        try:
            if call('/api/status')[0] == 200:
                break
        except OSError:
            time.sleep(0.2)
    status, data = call(f"/api/versions/{version['id']}")
    assert status == 200 and json.loads(data)['version']['id'] == version['id']
    assert call(f"/api/versions/{version['id']}/download")[1] == original
    print(json.dumps({'version_id': version['id'], 'sha256': version['sha256']}))


if __name__ == '__main__':
    main()
