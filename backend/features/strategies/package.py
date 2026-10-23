"""Static ZIP and manifest validation. Uploaded Python is never imported or run."""
import ast
import hashlib
import io
import json
import stat
import zipfile

from pydantic import ValidationError
from backend.features.strategies.manifest import Manifest
MAX_ZIP = 10 * 1024 * 1024
MAX_UNPACKED = 50 * 1024 * 1024
MAX_FILES = 100


class PackageError(ValueError):
    pass


def validate_package(data: bytes):
    if not data or len(data) > MAX_ZIP:
        raise PackageError('策略包为空或超过 10 MiB')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            raise PackageError('策略包文件数超过 100')
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise PackageError('策略包解压后超过 50 MiB')
        names = set()
        for item in infos:
            name = item.filename
            normalized = name.rstrip('/')
            if (not name or name.startswith('/') or '\\' in name or ':' in name or
                    normalized in ('.', '..') or normalized.startswith('../') or
                    any(part in ('.', '..', '') for part in name.rstrip('/').split('/'))):
                raise PackageError('策略包含不安全路径')
            if normalized.casefold() in names:
                raise PackageError('策略包含重复路径')
            names.add(normalized.casefold())
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise PackageError('策略包不能含符号链接')
            if item.flag_bits & 1:
                raise PackageError('策略包不能加密')
        if not {'strategy.json', 'strategy.py'} <= names:
            raise PackageError('策略包根目录须包含 strategy.json 和 strategy.py')
        raw_manifest = archive.read('strategy.json')
        if len(raw_manifest) > 256 * 1024:
            raise PackageError('strategy.json 过大')
        manifest = json.loads(raw_manifest.decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        try:
            manifest = Manifest.model_validate(manifest).model_dump(exclude_unset=True)
        except ValidationError as exc:
            raise PackageError(f'策略声明无效：{exc.errors()[0]["msg"]}') from exc
        tree = ast.parse(archive.read('strategy.py').decode('utf-8'), filename='strategy.py')
        entry = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'on_bar'), None)
        args = (entry.args.posonlyargs + entry.args.args) if entry else []
        if (entry is None or len(args) != 1 or args[0].arg != 'event' or
                entry.args.vararg or entry.args.kwarg or entry.args.kwonlyargs or entry.args.defaults):
            raise PackageError('strategy.py 须定义 on_bar(event)')
        corrupt = archive.testzip()
        if corrupt:
            raise PackageError(f'策略包文件损坏：{corrupt}')
        return manifest, hashlib.sha256(data).hexdigest()
    except PackageError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, UnicodeError, ValueError, SyntaxError, RuntimeError, NotImplementedError, OSError) as exc:
        raise PackageError(f'策略包无法读取或解析：{exc}') from exc
