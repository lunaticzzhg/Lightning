# 数据源脚本

这里放从外部获取数据、转成 Lightning 导入格式的脚本。脚本只生成本地文件，不会自动导入或发布数据版本。

| 脚本 | 输入 | 输出 |
| --- | --- | --- |
| [Tushare A 股日线](./tushare_daily.py) | Tushare Token、股票代码、起止日期 | UTF-8 CSV；每行一交易日，包含股票、交易所、日期、开高低收价和成交量 |

## 拉取 Tushare 免费日线

账号需有 Tushare [`daily` 接口](https://tushare.pro/document/1?doc_id=27)权限。按[当前权限表](https://tushare.pro/document/2?doc_id=290)，免费档需 120 积分，只能取未复权日线。安装依赖后，在项目目录运行：

```bash
python3 -m pip install tushare
python3 data_sources/tushare_daily.py --symbol 600519.SH --start 20260101 --end 20260930
```

运行时输入 Token，脚本不会将其写进文件。也可预先设置 `TUSHARE_TOKEN` 环境变量。默认输出到 `data_sources/exports/`；用 `--output 路径` 可指定位置。已有同名文件不会被覆盖；默认输出目录不会提交到 Git。

生成的是**未复权日线**。在数据管理页面上传 CSV 时，来源填“Tushare Pro／A 股日线”，价格处理选“未复权”，成交量单位选“手”。停牌日通常没有日线记录，不能仅凭日期空白判断拉取失败。
