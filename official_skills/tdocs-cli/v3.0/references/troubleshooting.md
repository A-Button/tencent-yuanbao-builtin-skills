# 故障排查

## 常见错误码

| 错误码 | 错误类型 | 解决方案 |
|--------|----------|----------|
| **401** | **Token 鉴权失败** | 停止并说明运行环境授权异常；不要主动登录、退出、探测或操作凭据 |
| **403** | **权限不足** | 先用 `manage get-privilege` 只读确认现状；用户明确要求分享或协作编辑时，按目标设置相应权限，否则请所有者授权或在腾讯文档前端调整 |
| **429** | **请求频率超限** | 触发速率限制，等待几秒后重试。避免紧密循环，优先使用批量命令 |
| **400006** | **Token 鉴权失败** | 停止并说明运行环境授权异常；不要主动登录、退出、探测或操作凭据 |
| **400007** | **VIP 权限不足** | ⭐ **立即升级 VIP**：访问 [https://docs.qq.com/vip?immediate_buy=1&part_aid=persnlspace_mcp](https://docs.qq.com/vip?immediate_buy=1&part_aid=persnlspace_mcp) 购买 VIP 服务 |
| **400008** | **积分不足** | ⭐ **立即购买积分**：访问 [https://docs.qq.com/vip/asset-center?tab=ai&fromPage=offsite&part_aid=offsite_claw](https://docs.qq.com/vip/asset-center?tab=ai&fromPage=offsite&part_aid=offsite_claw) 购买积分服务 |
| **-32601** | **请求接口错误** | 确认调用的命令是否在 CLI 命令列表中存在，使用 `tdocs-cli --help` 查看 |
| **-32603** | **请求参数错误** | 确认请求参数是否正确，例如 `--file-id`、`--content` 等 |
| **11607** | **请求参数错误** | 确认请求参数是否正确，例如 `--file-id`、`--content` 等 |
| **5xx** | **服务端错误**（500/502/503/504） | 后端临时故障，使用 `--debug` 重试，捕获 trace ID 后升级处理 |

## 排查步骤

1. **匹配错误码**：先查上方错误码表，按对应方案处理
2. **确认命令可用**：`tdocs-cli <service> --help` 查看可用命令列表及参数定义
3. **鉴权错误**：停止并说明运行环境授权异常；不要主动登录、退出、探测或操作凭据
4. **查阅品类参考文档**：根据场景路由表找到对应参考文档，确认命令调用规范和参数约束

## 常见场景问题

### 超时 / "context deadline exceeded"

- **原因**：HTTP 超时设置过低。
- **修复**：提高 `--timeout <秒>`（默认 30）。workflow 命令还需提高 `--poll-timeout-secs`。

### `workflow import-file` / `workflow export-file` 接近完成时超时

- **原因**：文件过大，处理时间超出轮询截止。
- **修复**：

  ```bash
  tdocs-cli workflow import-file --file ./big.xlsx \
      --poll-timeout-secs 1800 --timeout 120
  ```

### 命令找不到

- **原因**：CLI 版本过旧或本地缓存未同步。
- **修复**：

  ```bash
  tdocs-cli cache refresh
  tdocs-cli --help
  ```

### `--jq` 返回 null

- **修复**：去掉 `--jq`，查看完整 JSON 后调整表达式。或用 `--jq '.'` 美化输出。

### `--format table` 显示乱码

- **修复**：切换到 `--format json`。

## 升级处理清单

提交 bug 时请包含：

1. 完整命令（token 替换为 `<TOKEN>`）。
2. `tdocs-cli version` 输出。
3. `--debug` 打印的 trace ID。
4. 操作系统和终端类型。

**不要**在公开场合包含实际 token 或含个人数据的响应。
