# REQ-001 本机运行与备份恢复

本手册适用于从空 MySQL 卷安装的阶段一。默认 Compose 项目为 `lightning-req001`，数据卷为 `lightning-req001_mysql_data`。以下命令从仓库根目录执行。

## 启动与停止

需要 Apple Silicon Mac、Docker Desktop（含 Compose）和空闲的 8000 端口。若端口被占用，可在启动命令前设置 `LIGHTNING_PORT_BIND=18000`，并用对应端口打开浏览器。首次运行：

```sh
python3 scripts/create_local_secrets.py

docker compose -f deploy/local/compose.yaml up -d --build
curl -f http://127.0.0.1:8000/api/status
```

浏览器打开 `http://127.0.0.1:8000`。页面、API 和原包下载同源；只绑定宿主机 `127.0.0.1:8000`，MySQL 不发布端口。数据库管理员密码仅给一次性 `migrate` 容器；应用持有日常账号密码。本机凭证在被 Git 忽略的 `deploy/local/secrets/`，不可上传或放进镜像。首次安装由 Alembic 建立 `strategies`、`versions` 表。

```sh
docker compose -f deploy/local/compose.yaml stop app
docker compose -f deploy/local/compose.yaml up -d app
docker compose -f deploy/local/compose.yaml restart app
```

启动失败时先运行 `docker compose -f deploy/local/compose.yaml ps`，再运行 `docker compose -f deploy/local/compose.yaml logs --tail=200 app migrate db`。`/health/live` 只说明进程活着；`/api/status` 会查询数据库，断库返回 503。不要对有数据的项目执行 `down -v`。

## 策略包样例

见 [策略包样例](../../../contracts/strategy/samples/README.md)。ZIP 根目录必须有 `strategy.json`、`strategy.py`。上传成功仅表示静态校验通过，不表示代码或依赖可运行。

## 备份与隔离恢复

备份会暂停应用写入，导出 SQL，并在同名 `.json` 中记录策略、版本、关联及每个原包 SHA-256 的核对指纹；完成或失败后恢复此前运行的应用。目标目录应位于 Docker 数据卷之外。建议再复制到另一块磁盘，避免整机或磁盘损坏。

```sh
python3 scripts/deploy_data.py backup --compose deploy/local/compose.yaml /path/outside/docker/lightning-YYYYMMDD.sql
python3 scripts/deploy_data.py restore /path/outside/docker/lightning-YYYYMMDD.sql --image lightning-app:local
```

恢复仅使用 `lightning-restore` 独立项目和卷，不公开端口，不覆盖现用库。工具拒绝复用已有的隔离恢复卷。核对后才可清理**该隔离项目**：

```sh
docker compose -f deploy/restore/compose.yaml down -v
```

同时保留 SQL 与 `.json` 文件，限制读取权限；两者都含业务敏感信息。备份失败若留有 `.partial`，不能将其视为完整备份。

## 离线边界

需先取得 MySQL、Node、Python 基础镜像及构建依赖，并完成应用镜像构建。运行中的应用、数据库、上传、查看和下载不调用外部服务；**断公网启动尚未实测**。本机数据卷、凭证和备份不自动带往未来服务器。
