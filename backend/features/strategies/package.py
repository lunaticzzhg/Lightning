"""Static ZIP and manifest validation. Uploaded Python is never imported or run."""
import ast
import hashlib
import io
import json
import math
import stat
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / 'contracts/strategy/strategy.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
MAX_ZIP = 10 * 1024 * 1024
MAX_UNPACKED = 50 * 1024 * 1024
MAX_FILES = 100


class PackageError(ValueError):
    pass


def _validate_default(parameter):
    if 'default' not in parameter:
        return
    value = parameter['default']
    kind = parameter['type']
    if kind == 'integer' and (type(value) is not int):
        raise PackageError(f"参数 {parameter['name']} 的默认值须为整数")
    if kind == 'number' and (type(value) not in (int, float)):
        raise PackageError(f"参数 {parameter['name']} 的默认值须为小数")
    if kind == 'boolean' and type(value) is not bool:
        raise PackageError(f"参数 {parameter['name']} 的默认值须为布尔值")
    if kind in ('string', 'enum') and type(value) is not str:
        raise PackageError(f"参数 {parameter['name']} 的默认值须为文本")
    if kind == 'enum' and value not in parameter.get('options', []):
        raise PackageError(f"参数 {parameter['name']} 的默认值不在选项中")
    if kind in ('integer', 'number'):
        if not math.isfinite(value):
            raise PackageError(f"参数 {parameter['name']} 的默认值须为有限数字")
        if 'min' in parameter and value < parameter['min']:
            raise PackageError(f"参数 {parameter['name']} 的默认值小于下限")
        if 'max' in parameter and value > parameter['max']:
            raise PackageError(f"参数 {parameter['name']} 的默认值大于上限")


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
        problems = sorted(VALIDATOR.iter_errors(manifest), key=lambda e: list(map(str, e.path)))
        if problems:
            raise PackageError(f'策略声明无效：{problems[0].message}')
        if not manifest['name'].strip() or not manifest['description'].strip():
            raise PackageError('策略名称和说明不能为空')
        seen = set()
        for param in manifest['parameters']:
            name = param['name'].strip()
            if not name or name.casefold() in seen:
                raise PackageError('参数名称为空或重复')
            seen.add(name.casefold())
            if any(secret in name.casefold() for secret in ('password', 'secret', 'token', 'api_key', 'credential', '密码', '密钥')):
                raise PackageError('策略参数不能保存密码或密钥')
            kind = param['type']
            if kind == 'enum' and (not param.get('options') or any(not option.strip() for option in param['options'])):
                raise PackageError(f'参数 {name} 缺少有效枚举选项')
            if kind != 'enum' and 'options' in param:
                raise PackageError(f'参数 {name} 不应声明枚举选项')
            if kind not in ('integer', 'number') and ('min' in param or 'max' in param):
                raise PackageError(f'参数 {name} 不能声明数值范围')
            if 'min' in param and 'max' in param and param['min'] > param['max']:
                raise PackageError(f'参数 {name} 的范围无效')
            _validate_default(param)
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
