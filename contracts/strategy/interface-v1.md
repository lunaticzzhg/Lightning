# 策略 Python 接口 v1

上传阶段只静态检查 ZIP 根目录 `strategy.py` 定义同步函数 `on_bar(event)`，不导入或运行它。清单的 `interface_version` 为 `1`，`entrypoint` 固定为 `strategy:on_bar`。保存的版本永久保留其接口版本。

后续运行器每次调用传入一个字典 `event`：

| 字段 | 含义 |
| --- | --- |
| `timestamp` | 本次分钟结束时间，带时区的 UTC ISO 8601 字符串。 |
| `bars` | 字典，键为 `市场:标的`；值为截至该分钟按时间升序排列的行情列表。每根行情含 `timestamp`，以及清单要求的 `open`、`high`、`low`、`close`、`volume` 字段。价格和成交量为非负数字。 |
| `parameters` | 本次运行开始前固定的完整参数值字典，键为清单参数名。阶段一不保存此字段的值。 |
| `account` | 只读账户快照：`base_currency`、`equity`、`cash`（币种到金额）、`positions`（`市场:标的` 到数量）。 |

返回 `None` 表示不调仓；返回列表表示本策略完整目标持仓。每项包含 `market`（`CN` 或 `US`）、`symbol` 和 `target_weight`（占净值比例的数字）。未列出的本策略持仓目标为零。平台负责校验返回值、风控和下单。改变字段含义或返回协议须提高 `interface_version`。阶段一不承诺上述输入可用，也不保证任何上传代码可运行。
