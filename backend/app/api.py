"""FastAPI transport boundary. Business decisions live in strategies.service."""
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.app.transport import (Error, Status, Strategy, StrategyDetail, Version, VersionDetail)
from backend.features.strategies import service
from backend.features.strategies.package import PackageError, MAX_ZIP


ERROR_RESPONSES = {code: {'model': Error} for code in (400, 403, 404, 409, 422, 503)}


def error_response(code, message, status):
    return Response(content=Error(code=code, message=message).model_dump_json(), media_type='application/json', status_code=status)


def create_app(engine: Engine, static_dir: Path | None = None):
    token = secrets.token_urlsafe(32)
    app = FastAPI(title='Lightning management API', version='1.0.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token

    allowed_hosts = {host.strip().lower() for host in os.environ.get('LIGHTNING_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if host.strip()}
    if not allowed_hosts or '*' in allowed_hosts:
        raise RuntimeError('LIGHTNING_ALLOWED_HOSTS 必须列出实际域名，不能使用通配符')

    @app.middleware('http')
    async def request_guard(request: Request, call_next):
        host = request.url.hostname
        if host is None or host.lower() not in allowed_hosts:
            return error_response('forbidden', '访问域名无效', 403)
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            expected = f'{request.url.scheme}://{request.headers.get("host")}'
            if origin and origin != expected:
                return error_response('forbidden', '请求来源无效', 403)
            if request.headers.get('x-lightning-token') != token:
                return error_response('forbidden', '本次启动令牌无效', 403)
        return await call_next(request)

    @app.exception_handler(PackageError)
    async def package_error(_request, exc):
        return error_response('invalid_input', str(exc), 400)

    @app.exception_handler(service.NotFound)
    async def not_found(_request, _exc):
        return error_response('not_found', '记录不存在', 404)

    @app.exception_handler(service.Conflict)
    async def conflict(_request, exc):
        return error_response('conflict', str(exc), 409)

    @app.exception_handler(RequestValidationError)
    async def request_validation(_request, _exc):
        return error_response('invalid_request', '请求格式无效', 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request, _exc):
        logging.exception('Database request failed')
        return error_response('database_unavailable', '数据服务暂不可用', 503)

    async def package_bytes(file: UploadFile):
        contents = await file.read(MAX_ZIP + 1)
        if not file.filename:
            raise PackageError('请选择 ZIP 策略包')
        return contents

    @app.get('/health/live', include_in_schema=False)
    def live():
        return {'ok': True}

    @app.get('/api/status', response_model=Status, operation_id='status', responses=ERROR_RESPONSES)
    def status():
        with engine.connect() as connection:
            connection.exec_driver_sql('SELECT 1')
        return {'ok': True, 'token': token}

    @app.get('/api/strategies', response_model=list[Strategy], operation_id='list_strategies', responses=ERROR_RESPONSES)
    def list_strategies():
        return service.list_strategies(engine)

    @app.post('/api/strategies', response_model=Version, status_code=201, operation_id='create_strategy', responses=ERROR_RESPONSES)
    async def create_strategy(file: UploadFile = File(...)):
        return service.upload(engine, file.filename or '', await package_bytes(file))

    @app.get('/api/strategies/{strategy_id}', response_model=StrategyDetail, operation_id='get_strategy', responses=ERROR_RESPONSES)
    def get_strategy(strategy_id: str):
        return service.get_strategy(engine, strategy_id)

    @app.post('/api/strategies/{strategy_id}/versions', response_model=Version, status_code=201, operation_id='upload_version', responses=ERROR_RESPONSES)
    async def upload_version(strategy_id: str, file: UploadFile = File(...)):
        return service.upload(engine, file.filename or '', await package_bytes(file), strategy_id)

    @app.get('/api/versions/{version_id}', response_model=VersionDetail, operation_id='get_version', responses=ERROR_RESPONSES)
    def get_version(version_id: str):
        return service.get_version(engine, version_id)

    @app.get('/api/versions/{version_id}/download', operation_id='download_version', response_class=Response, responses={**ERROR_RESPONSES, 200: {'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def download_version(version_id: str):
        name, data = service.download(engine, version_id)
        return Response(data, media_type='application/octet-stream', headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name, safe='')}"})

    static = static_dir or (Path(__file__).resolve().parents[2] / 'web/dist')
    if static.is_dir():
        assets = static / 'assets'
        if assets.is_dir():
            app.mount('/assets', StaticFiles(directory=assets), name='assets')

        @app.get('/{path:path}', include_in_schema=False, responses=ERROR_RESPONSES)
        def index(path: str):
            if path.startswith(('api/', 'health/')):
                return error_response('not_found', '接口不存在', 404)
            candidate = (static / path).resolve()
            if path and candidate.is_relative_to(static.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static / 'index.html')
    return app
