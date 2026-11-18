# 荣浩燃气 Home Assistant 集成

`ronghao_gas` 是一个 Home Assistant 自定义集成，用于读取荣浩能源燃气云平台的数据。

## 功能

- 账户余额和气量余额
- 燃气表读数与累计用气量
- 最近购气金额
- 最新用气量和金额
- 最近 30 天、12 个月用气统计
- 最近一次用气时间和刷新时间
- 手动刷新服务 `ronghao_gas.refresh`
- 可配置轮询间隔：6、8、10、12 或 24 小时

## 安装

将 `ronghao_gas` 目录复制到 Home Assistant 配置目录的：

```text
custom_components/ronghao_gas/
```

然后在 Home Assistant 中通过“设置 → 设备与服务 → 添加集成”搜索“荣浩燃气”，按表单填写平台账号参数。

## 安全说明

Bearer Token、用户 ID 和 AES 密钥只在 Home Assistant 的配置流程中填写，不要提交到 Git 仓库、截图或公开讨论中。仓库中的代码不包含个人账号凭据。

## 版本

当前代码版本：`3.2.2`

## 免责声明

本项目由用户社区维护，与荣浩能源官方无关。接口或平台行为变化可能导致集成失效。

