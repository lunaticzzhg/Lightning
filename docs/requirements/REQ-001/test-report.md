# REQ-001 阶段一测试报告

- 日期：2026-10-23
- 环境：Apple Silicon Mac、Docker Desktop（Engine `arm64`）、MySQL 8.4、Python 3.13 容器、React/TypeScript 构建。
- 验证环境：使用 `lightning-req001-verify` Compose 项目、独立 MySQL 卷和 `127.0.0.1:18000`，结果代表新空库安装。

## 已执行

| 范围 | 步骤与结果 |
| --- | --- |
| 合同与构建 | `scripts/generate_contracts.py --check`、`scripts/check_routes.py`、`npm run build --prefix web` 均通过；路由与管理接口合同一致。 |
| 后端行为 | `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_strategy_flow.py tests/test_deploy_data.py`：6 项通过。覆盖无效包、名称冲突、原包重复、并发重复、不同版本参数、无参数版本、原包字节下载、写入令牌、数据库故障及备份失败后的应用恢复。失败上传未留策略或版本记录。 |
| 策略样例 | `valid`、`no-parameters` 通过静态校验；`invalid` 因不支持市场被拒绝。 |
| MySQL 并发 | 对同一新策略包同时发起 5 次 HTTP 上传，结果为 1 次 201、4 次 409，库中只有一条策略记录。 |
| 默认项目 | `docker compose -f deploy/local/compose.yaml config --format json` 显示项目 `lightning-req001`，使用独立数据卷。 |
| 空库部署 | 独立 Compose 从空卷启动，`migrate` 完成，MySQL 仅有 `alembic_version`、`strategies`、`versions`。API 上传与下载成功；应用重启后版本、原包仍可读，SHA-256 不变。 |
| 浏览器 | Playwright 在真实页面完成策略列表→策略→版本详情，以及新策略 ZIP 上传→成功反馈→参数定义展示；390 像素窗口详情可读。页面无参数值填写与保存入口。Review 后模拟 `/api/status` 首次失败，点“重试”再次获取启动令牌并加载列表；模拟上传已保存但版本详情首次读取失败，页面明确提示已保存并提供“重试查看版本”，重试后进入详情。 |
| 备份恢复 | 停写备份到 `/tmp/lightning-req001-verify.sql`，在 `lightning-restore` 独立卷恢复；恢复前后指纹相同，策略数 1、版本数 1。 |

## 尚未验证及边界

- 断开公网后的冷启动、上传和查看尚未实测；已构建镜像并不等于完整离线验收。
- 非本机设备直接访问的网络试验尚未执行；Compose 配置仅发布到 `127.0.0.1`，数据库未发布端口。
- 策略包只做静态校验，Python 依赖安装、策略运行和交易输出未验证，符合阶段一范围。
