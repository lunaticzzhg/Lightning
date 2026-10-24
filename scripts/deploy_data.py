"""Backup and isolated restore for a Docker Compose Lightning environment."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from secrets import token_urlsafe

ROOT = Path(__file__).resolve().parents[1]
RESTORE_COMPOSE = ROOT / 'deploy/restore/compose.yaml'
MARKET_TAR_SUFFIX = '.market.tar'
MYSQL_CLIENT = 'MYSQL_PWD="$(cat /run/secrets/root_password)" exec mysql -uroot lightning'
MYSQL_DUMP = 'MYSQL_PWD="$(cat /run/secrets/root_password)" exec mysqldump -uroot --single-transaction --hex-blob --no-tablespaces lightning'


def compose(file, *args, input_file=None, output_file=None, env=None):
    command = ['docker', 'compose', '-f', str(file)]
    project = (env or os.environ).get('LIGHTNING_RESTORE_PROJECT') if file.resolve() == RESTORE_COMPOSE.resolve() else (env or os.environ).get('LIGHTNING_COMPOSE_PROJECT')
    if project:
        command.extend(['-p', project])
    command.extend(args)
    with (input_file.open('rb') if input_file else open(os.devnull, 'rb')) as source:
        with (output_file.open('wb') if output_file else open(os.devnull, 'wb')) as output:
            result = subprocess.run(command, stdin=source, stdout=output if output_file else subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f'{" ".join(command[:5])} 失败: {result.stderr.decode(errors="replace")[-2000:]}')
    return result.stdout.decode() if not output_file else None


def source_snapshot(file, env=None):
    return json.loads(compose(file, 'run', '--rm', '--no-deps', 'migrate', 'python', 'scripts/snapshot.py', env=env))


def backup(file, destination, env=None):
    destination = destination.resolve()
    market_archive = destination.with_suffix(destination.suffix + MARKET_TAR_SUFFIX)
    if destination.exists() or market_archive.exists() or destination.with_suffix(destination.suffix + '.json').exists():
        raise RuntimeError('备份目标已存在，拒绝覆盖')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + '.partial')
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(handle)
    market_temp = market_archive.with_suffix(market_archive.suffix + '.partial')
    was_running = 'app' in compose(file, 'ps', '--status', 'running', '--services', env=env).splitlines()
    compose(file, 'stop', 'app', env=env)
    try:
        before = source_snapshot(file, env)
        compose(file, 'exec', '-T', 'db', 'sh', '-c', MYSQL_DUMP, output_file=temp, env=env)
        if temp.stat().st_size == 0:
            raise RuntimeError('备份文件为空')
        if 'market_versions' in before['counts']:
            compose(file, 'run', '--rm', '--no-deps', 'migrate', 'tar', '-C', '/srv/market', '-cf', '-', '.', output_file=market_temp, env=env)
            if market_temp.stat().st_size == 0:
                raise RuntimeError('行情文件备份为空')
        after = source_snapshot(file, env)
        if before != after:
            raise RuntimeError('备份期间数据发生变化')
        temp.replace(destination)
        if market_temp.exists():
            market_temp.replace(market_archive)
            market_archive.chmod(0o600)
        fingerprint = destination.with_suffix(destination.suffix + '.json')
        fingerprint.write_text(json.dumps(before, ensure_ascii=False, indent=2) + '\n')
        fingerprint.chmod(0o600)
    finally:
        temp.unlink(missing_ok=True)
        market_temp.unlink(missing_ok=True)
        if was_running:
            compose(file, 'up', '-d', '--no-deps', 'app', env=env)
    return before


def prepare_restore_secrets():
    folder = ROOT / 'deploy/restore/secrets'
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('app_password', 'root_password'):
        path = folder / name
        if not path.exists():
            path.write_text(token_urlsafe(36) + '\n')
            path.chmod(0o600)


def restore(backup_file, image='lightning-app:local', project='lightning-restore'):
    backup_file = backup_file.resolve()
    expected = json.loads(backup_file.with_suffix(backup_file.suffix + '.json').read_text())
    prepare_restore_secrets()
    env = {**os.environ, 'LIGHTNING_IMAGE': image, 'LIGHTNING_RESTORE_PROJECT': project}
    # New isolated volume each run; an existing restore is never overwritten.
    volumes = subprocess.run(['docker', 'volume', 'inspect', f'{project}_mysql_data'], capture_output=True)
    if volumes.returncode == 0 or subprocess.run(['docker', 'volume', 'inspect', f'{project}_market_data'], capture_output=True).returncode == 0:
        raise RuntimeError('隔离恢复项目已存在；请先人工核对，再执行 docker compose -f deploy/restore/compose.yaml down -v')
    compose(RESTORE_COMPOSE, 'up', '-d', '--wait', 'db', env=env)
    compose(RESTORE_COMPOSE, 'exec', '-T', 'db', 'sh', '-c', MYSQL_CLIENT, input_file=backup_file, env=env)
    archive = backup_file.with_suffix(backup_file.suffix + MARKET_TAR_SUFFIX)
    if 'market_versions' in expected['counts']:
        if not archive.is_file(): raise RuntimeError('缺少同行情文件备份')
        compose(RESTORE_COMPOSE, 'run', '--rm', '--no-deps', '-T', 'verify', 'tar', '-C', '/srv/market', '-xf', '-', input_file=archive, env=env)
    actual = json.loads(compose(RESTORE_COMPOSE, 'run', '--rm', 'verify', env=env))
    if actual != expected:
        raise RuntimeError(f'隔离恢复校验不一致: {actual} != {expected}')
    return actual


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    backup_parser = sub.add_parser('backup')
    backup_parser.add_argument('--compose', type=Path, required=True)
    backup_parser.add_argument('destination', type=Path)
    restore_parser = sub.add_parser('restore')
    restore_parser.add_argument('backup_file', type=Path)
    restore_parser.add_argument('--image', default='lightning-app:local')
    restore_parser.add_argument('--project', default='lightning-restore')
    args = parser.parse_args()
    try:
        if args.action == 'backup':
            result = backup(args.compose, args.destination)
        else:
            result = restore(args.backup_file, args.image, args.project)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
