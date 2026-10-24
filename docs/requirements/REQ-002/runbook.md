# REQ-002 本机运行与数据保护

历史行情由 MySQL 目录和 `market_data` 文件卷共同组成。只复制数据库无法恢复行情。以下命令从仓库根目录执行；首次启动、数据库凭证和策略包操作见 [REQ-001 运行手册](../REQ-001/runbook.md)。

## 启动与检查

```sh
python3 scripts/create_local_secrets.py
docker compose -f deploy/local/compose.yaml up -d --build
curl -f http://127.0.0.1:8000/api/status
```

浏览器进入“历史数据”，用股票、周期和日期范围查找；分钟线还可选盘中时段。首期只接收 UTF-8 CSV：必填 `symbol,open,high,low,close,volume`，日线另填 `date`，分钟线另填带时区的 `timestamp`。`exchange` 可选，填写时使用 `SH`、`SZ`、`BJ`、`NYSE`、`NASDAQ` 或 `AMEX`。能从 A 股代码确定交易所时自动识别；如美股文件没有交易所，上传后须选择。代码与交易所明显矛盾的文件会被拒绝。同代码在不同交易所的记录要在文件中分别填写交易所。文件大小和行数暂有保护上限 30 MB、20 万行；这些是防止一次请求耗尽资源的临时边界，待真实样本实测后调整。分钟时间需确认“开始”或“结束”。A 股成交量可选“股”或“手（100 股）”，美股只接受“股”。

价格或成交量变化提示的比率阈值尚未由真实样本确认。需要试验时，可以给应用容器配置 `LIGHTNING_MARKET_PRICE_ALERT_RATIO`、`LIGHTNING_MARKET_VOLUME_ALERT_RATIO`，值须大于 1。比如价格比率为 2 时，当前收盘价达到前一条的两倍才提示。每版保存当时使用的阈值。未配置时，系统仍会标记修正旧值的时点，但不会声称已识别一般行情异常。

## 联合备份与隔离恢复

先停应用再备份。若启动时设置了 `LIGHTNING_PORT_BIND` 等 Compose 环境变量，备份时也要设置相同的值，以便工具恢复应用。命令生成同名前缀的 `.sql`、`.sql.market.tar`、`.sql.json`；三者必须一起保留在 Docker 卷以外。`.sql.market.tar` 含原始 CSV 和 Parquet 行情文件。校验会读取全部已发布版本引用的文件、核对 SHA-256 和记录数。旧版仅有 SQL 与 JSON 的备份仍可按旧结构隔离恢复。

```sh
python3 scripts/deploy_data.py backup --compose deploy/local/compose.yaml /path/outside/docker/lightning-YYYYMMDD.sql
python3 scripts/deploy_data.py restore /path/outside/docker/lightning-YYYYMMDD.sql --image lightning-app:local
```

恢复默认使用独立的 `lightning-restore` 数据库和行情卷。若该隔离项目已有数据，可使用 `--project 新项目名` 建立另一套隔离卷。校验失败时不要开放该恢复结果；原运行环境不受影响。核对后才能清理这个隔离项目：

```sh
docker compose -f deploy/restore/compose.yaml down -v
# 若恢复时指定了 --project，只运行下面这条，替换成实际项目名：
docker compose -f deploy/restore/compose.yaml -p 新项目名 down -v
```

若版本文件缺失或校验失败，API 返回该版读取失败，不会绘制不完整 K 线。不可删除已发布文件。未发布草稿超过两天后，先停止应用，再运行下面的清理命令。它删除过期草稿目录，随后清理没有草稿或成功导入记录引用的原件，包括中断上传留下的孤立原件；相同内容被已发布版本引用时保留。应用停止期间不能上传新文件，清理结束后再启动。

```sh
docker compose -f deploy/local/compose.yaml stop app
docker compose -f deploy/local/compose.yaml run --rm --no-deps -e LIGHTNING_MARKET_APP_STOPPED=1 migrate python scripts/prune_market.py
docker compose -f deploy/local/compose.yaml up -d --no-deps app
```

如使用自定义 Compose 项目名或端口，三条命令都传相同的 `-p` 和 `LIGHTNING_PORT_BIND`。清理使用迁移服务的数据库管理账号；日常应用账号没有 `DELETE` 权限。MySQL 首次建卷时从 `deploy/mysql-init/01-app-grants.sql` 设置应用账号的最小权限，迁移和维护由管理账号执行。
