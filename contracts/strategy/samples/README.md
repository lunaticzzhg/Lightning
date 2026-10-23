# 策略包样例

每个目录的 `strategy.json` 和 `strategy.py` 是 ZIP 根目录文件。例如：

```sh
cd contracts/strategy/samples/valid
zip /tmp/lightning-valid.zip strategy.json strategy.py
```

`valid` 可导入且声明两个参数；`no-parameters` 可导入但没有参数；`invalid` 声明不支持的市场，上传应拒绝且不留记录。样例代码只演示静态合同，不代表策略已通过运行验证。
