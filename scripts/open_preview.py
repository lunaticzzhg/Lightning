"""Replace the local preview containers and open the ready Web page."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "deploy/local/compose.yaml"
PROJECT = "lightning-browser-check"
IMAGE = "lightning-browser-check:local"
DEFAULT_STATE_DIR = Path.home() / ".local/share/lightning/preview"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def volume_exists() -> bool:
    result = subprocess.run(
        ["docker", "volume", "inspect", f"{PROJECT}_mysql_data"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def prepare_secrets(state_dir: Path) -> Path:
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths = [state_dir / name for name in ("root_password", "app_password")]
    present = [path.is_file() for path in paths]
    if not all(present):
        if any(present) or volume_exists():
            raise RuntimeError(
                f"预览数据库可能已有数据，但凭证不完整：{state_dir}。"
                "请恢复原凭证后重试，脚本不会覆盖数据库。"
            )
        for path in paths:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
                secret_file.write(secrets.token_urlsafe(36) + "\n")
    for path in paths:
        path.chmod(0o600)

    override = state_dir / "compose.override.yaml"
    body = (
        "secrets:\n"
        "  root_password:\n"
        f"    file: {json.dumps(str(paths[0].resolve()))}\n"
        "  app_password:\n"
        f"    file: {json.dumps(str(paths[1].resolve()))}\n"
    )
    descriptor = os.open(override, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as override_file:
        override_file.write(body)
    override.chmod(0o600)
    return override


def is_ready(base_url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in (
        "/",
        "/api/status",
        "/api/market/search?symbol=600000&period=day&from_date=2026-10-23&to_date=2026-10-23",
    ):
        try:
            with opener.open(base_url + path, timeout=2) as response:
                if response.status != 200:
                    return False
                if path == "/api/status" and not json.load(response).get("ok"):
                    return False
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False
    return True


def wait_until_ready(base_url: str, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if is_ready(base_url):
            return
        time.sleep(2)
    raise RuntimeError(f"预览服务启动后未通过检查：{base_url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="更新本地预览容器，检查服务后打开浏览器")
    parser.add_argument("--port", type=int, default=18002, help="本机访问端口，默认 18002")
    parser.add_argument("--no-browser", action="store_true", help="只部署并检查，不打开浏览器")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")

    state_dir = Path(os.environ.get("LIGHTNING_PREVIEW_STATE_DIR", DEFAULT_STATE_DIR)).expanduser().resolve()
    base_url = f"http://127.0.0.1:{args.port}"
    environment = os.environ.copy()
    environment["LIGHTNING_PORT_BIND"] = str(args.port)
    environment["LIGHTNING_IMAGE"] = IMAGE
    deployment_started = False
    compose: list[str] = []
    try:
        run(["docker", "info", "--format", "{{.ServerVersion}}"])
        run(["docker", "compose", "version"])
        override = prepare_secrets(state_dir)
        compose = [
            "docker", "compose", "-f", str(COMPOSE_FILE), "-f", str(override), "-p", PROJECT
        ]
        run(compose + ["config", "--quiet"], env=environment)
        print("正在构建最新代码…", flush=True)
        run(compose + ["build", "app"], env=environment)
        print("正在替换旧预览容器…", flush=True)
        deployment_started = True
        run(compose + ["down", "--remove-orphans"], env=environment)
        run(compose + ["up", "-d", "--no-build"], env=environment)
        wait_until_ready(base_url)
        print(f"预览服务已就绪：{base_url}", flush=True)
        if not args.no_browser and not webbrowser.open(base_url):
            print(f"浏览器未自动打开，请访问：{base_url}", file=sys.stderr)
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"预览失败：{error}", file=sys.stderr)
        if deployment_started and compose:
            subprocess.run(compose + ["ps"], cwd=ROOT, env=environment, check=False)
            subprocess.run(
                compose + ["logs", "--tail=80", "app", "migrate", "db"],
                cwd=ROOT, env=environment, check=False,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
