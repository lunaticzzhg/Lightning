# 技术方案：macOS 平台与策略管理

- 需求编号：REQ-001
- 状态：草稿，待评审
- 依据：[PRD](./prd.md) · [交互原型](./prototype.html)
- 调研日期：2026-10-23

## 1. 方案概览

用户启动本机应用后，在浏览器管理策略。浏览器把操作交给本机服务；服务校验策略包、生成版本号、保存数据。**只有保存完成才显示“已导入，未运行验证”。**

策略、原始 ZIP 和参数配置保存在应用安装目录之外。后续回测、模拟和实盘引用确切的“代码版本 + 配置修订”，不会因用户再次上传或修改参数而改变。阶段一只管理这些记录，不运行策略。

## 2. 技术选择

当前仓库没有应用代码。以下为实施选择，尚未在目标 Mac 上实测。

| 选择 | 理由与代价 |
| --- | --- |
| React + TypeScript 页面、FastAPI 本机服务 | 便于以后增加回测和交易页面；前端需要单独构建。[Vite 可构建静态页面](https://vite.dev/guide/build)，[FastAPI 支持文件上传](https://fastapi.tiangolo.com/tutorial/request-files/)。 |
| MySQL 8.4 数据库 | 本机和服务器使用同一种数据库，迁移时无需转换数据库格式；阶段一需额外安装并运行 MySQL。[MySQL 提供 macOS 安装包](https://dev.mysql.com/doc/refman/8.4/en/macos-installation-pkg.html)，[Alembic 管理数据库版本升级](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。 |
| 捆绑 Python 的 macOS `.app` | 用户无需自行配置 Python；首次安装还需配置本机 MySQL。安装包、签名和启动体验需实测。[PyInstaller 支持 macOS 应用包](https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles)。 |

页面和接口由同一个本机地址提供。应用只监听 `127.0.0.1`；写入操作需要本次启动的随机令牌，并检查请求来源，防止其他网页借浏览器修改本机数据。这个做法参考 [OWASP 的跨站请求防护说明](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。

首次安装先用 MySQL 官方安装包装好本机服务，再由 Lightning 的初始化步骤创建业务数据库和专用账号。初始化时临时输入管理员凭证，不保存；应用日常只用专用账号，连接密码存入 macOS 钥匙串。启动时检查连接，未安装或未启动时给出处理提示。服务器阶段将数据库导出后导入服务器上的 MySQL，再核对策略版本、原始包和配置修订。[MySQL Shell 提供导出与导入工具](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-shell-utilities.html)。同一种数据库能省去格式转换，但仍需搬迁、核对数据和调整连接配置。

## 3. 策略包怎么定义

上传一个 ZIP，根目录至少有 `strategy.json` 和 `strategy.py`。清单示例：

```json
{
  "schema_version": 1,
  "interface_version": 1,
  "name": "双均线策略",
  "description": "根据分钟线调整目标仓位",
  "markets": ["US"],
  "bar_interval": "1m",
  "required_fields": ["open", "high", "low", "close", "volume"],
  "entrypoint": "strategy:on_bar",
  "python": "3.13",
  "dependencies": [],
  "parameters": [
    {"name": "fast_window", "type": "integer", "required": true, "default": 5, "min": 1}
  ]
}
```

首期市场只接受 `CN`（A 股）和 `US`（美股），周期只接受 `1m`。名称、说明、市场和所需数据不能为空。参数类型为整数、小数、布尔值、文本和枚举；可声明必填、默认值、数字范围或枚举选项。默认值也要通过校验，配置不能包含清单之外的参数。配置不设密钥类型，也不提供券商凭证入口。首期使用捆绑的 Python 3.13，不接受第三方依赖；以后增加依赖时明确支持的版本，不在上传时安装软件。

未来运行器调用 `strategy.py` 的 `on_bar(event)`。版本 1 约定 `event` 是字典：`timestamp` 为 UTC 分钟时间；`bars` 按“市场:标的”索引，提供截至该分钟按时间排序的开、高、低、收、成交量；`parameters` 是所选配置修订的完整参数值；`account` 提供只读的基准币种、账户净值、各币种现金和持仓数量。函数返回 `None` 表示不调仓；返回列表表示本策略的完整目标持仓，每项含 `market`、`symbol`、`target_weight`（占账户净值的比例），未列出的本策略持仓目标为零。平台负责校验、风控和下单。行情调整、币种换算和交易限制等细则留到回测阶段；若改变上述字段的含义，须提高 `interface_version`。阶段一只检查入口和 Python 语法，不执行代码。

上传时先限制 ZIP 大小（暂定 10 MiB）、文件数（100）和解压总量（50 MiB）；拒绝损坏、加密、重复路径、绝对路径、`..` 和符号链接。再检查清单与入口文件，计算原包的 SHA-256 校验值。静态检查无法保证代码实际可运行；运行验证留到后续阶段。

## 4. 数据与主要流程

| 记录 | 保存规则 |
| --- | --- |
| 策略 | 平台生成固定 ID；名称去掉首尾空格后不区分大小写，不能重名。新建时取包内名称；向已有策略上传时，包内名称必须与该策略一致，文件名不决定归属。 |
| 代码版本 | 固定归属一个策略；保存原始 ZIP、清单、校验值、时间和“未运行验证”状态；保存后不可覆盖。相同原包再次上传时返回已有版本。 |
| 参数配置 | 固定归属一个代码版本。 |
| 配置修订 | 每次保存新建一条，记录当时的名称、全部参数值、时间和固定 ID；旧修订不变。 |

这四类记录都用平台生成的全局唯一 ID 关联，迁移后 ID 不变。原始 ZIP 作为二进制字段与版本记录在同一次数据库提交中保存，失败时都不留下；上传大小限制须同时符合 MySQL 的传输配置。展示给用户的“版本 1”“修订 2”只是便于阅读；将来的运行引用固定 ID。所有参数都由服务端按所属代码版本校验，报错时页面保留输入。

主要接口分四组：创建/查看策略、上传/下载代码版本、创建/查看配置、保存/查看修订。新建策略与向已有策略上传版本用不同入口；上传用文件表单，其余操作用 JSON。服务端处理重名、重复上传和并发保存，返回明确错误；浏览器不自行分配版本号。

业务数据由本机 MySQL 保存；`~/Library/Application Support/Lightning/` 只放应用配置，`~/Library/Logs/Lightning/` 放日志。应用关闭或替换时不删除数据库。启动器打开浏览器并避免重复启动；页面提供关闭入口。数据库不可连接等启动失败时显示原因和日志位置。

升级前先停止旧版。新版首次启动时，用 [MySQL 导出工具](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)复制旧库，在临时库上升级并核对记录；通过后才让新版应用连接新库，旧库暂留供回退。升级失败则继续使用未改动的旧库。[MySQL 的建表、改表等语句可能隐式提交](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)，不能把“事务回滚”当成升级保护。导出文件只用于升级回退，阶段一不提供备份恢复页面。

以上升级与恢复流程需用真实旧版数据演练。MySQL 在当前 Apple Silicon Mac 上的安装和初始化、钥匙串读取、应用签名与关闭体验，以及 10 MiB 上传限制，都需实测。服务器迁移还需演练导出、导入和数据核对。
