# 快递100 Connector Tool契约

运行时`tools/list`是Tool名称和输入Schema的权威来源。本文件记录Agent编排所需的稳定语义和返回包络。

## 通用返回包络

成功结果：

```json
{
  "content": [{"type": "text", "text": "..."}],
  "structuredContent": {},
  "isError": false
}
```

业务失败：

```json
{
  "content": [{"type": "text", "text": "可读错误信息"}],
  "structuredContent": {"error": "可读错误信息"},
  "isError": true
}
```

`isError=true`时不得将`content`描述为成功结果。

## get_default_sender

- 属性：只读。
- 参数：无。
- 用途：获取当前OAuth用户的默认寄件人。
- 返回：`structuredContent.result`为寄件人对象，常用字段见[字段映射](fields.md)。
- 约束：向用户展示前必须脱敏并要求确认；无数据时改为人工收集。

## search_address_book

- 属性：只读。
- 参数：
  - `keyword`可选，联系人姓名或地址关键字；省略时列出对应类型的地址。
  - `addressType`可选，只能为`receiver`或`sender`，默认`receiver`。
  - `limit`可选，默认10，范围1～20。
- 返回：`structuredContent.items`为当前OAuth用户的地址数组。
- 约束：唯一匹配才可进入确认；同名多条必须让用户选择。不得把完整手机号和地址直接展示在对话中。

## set_default_sender

- 属性：写操作，会修改服务端默认寄件地址。
- 必填参数：`addressId`、`confirmed`。
- 约束：`addressId`必须来自本轮`search_address_book(addressType=sender)`结果；只有用户明确确认候选地址后才能传`confirmed=true`。
- 返回：`structuredContent.result`为写后查询验证通过的新默认寄件人。
- 重试：失败、超时、断网或结果未知时禁止自动重复调用；可以重新调用`get_default_sender`检查当前状态。
- 安全：Agent不传Token、用户ID或完整地址；服务端依据认证上下文重新读取整条地址并校验归属。

## add_address_book_entry

- 属性：写操作。
- 必填参数：`addressType`、`name`、`phone`、`province`、`city`、`district`、`address`、`confirmed`。
- 可选参数：`fixedPhone`、`postcode`。
- 分类：`addressType=sender`为寄件地址，`receiver`为收件地址；调用前必须询问用户，Agent不得猜测。
- 默认状态：新增固定为非默认；如需设置默认寄件人，再调用`set_default_sender`。
- 重试：超时、断网或结果未知时禁止自动重试，避免重复地址。

## update_address_book_entry

- 属性：写操作。
- 必填参数：`addressId`、`confirmed`，并至少提供一个需要修改的地址字段。
- 可修改字段：`name`、`phone`、`province`、`city`、`district`、`address`、`fixedPhone`、`postcode`。
- 约束：`addressId`必须来自本轮地址簿查询；未传字段保留原值；不得改变地址分类和默认状态。
- 重试：超时、断网或结果未知时禁止自动重试。

## delete_address_book_entry

- 属性：写操作。
- 必填参数：`addressId`、`confirmed`。
- 约束：目标必须来自本轮地址簿查询；当前默认寄件地址禁止删除，必须先设置另一条默认寄件地址。
- 安全：服务端按当前OAuth用户重新查询目标；Agent不传`guid`、Token或用户ID。
- 返回：成功时`structuredContent.deleted=true`。
- 重试：超时、断网或结果未知时禁止自动重试，可以重新查询地址簿确认状态。

## aiserviceapiquery4agent_get

- 属性：只读。
- 必填参数：`kuaidiNum`。
- 可选参数：`phone`（手机号或后四位）、`comName`（快递公司名称或编码）。
- 返回：现有`queryForModel`物流查询结果，包括适合Agent展示的物流状态和轨迹信息。
- 展示：有真实轨迹时必须整理为Markdown表格，至少包含“时间”和“物流轨迹”两列；不以原始长文本、段落或列表替代。无数据时如实说明，不补造轨迹行。
- 约束：查询结果要求手机号验证时再询问；不得臆造快递公司、物流轨迹或预计送达时间。

## list_my_shipment_orders

- 属性：只读。
- 参数：`limit`可选，整数，范围1～200；接口省略参数时仍默认10，本Skill默认显式传`limit=200`。50是模型的默认明细展示上限：先统计状态，再展示包含已取消在内的所有订单，≤50条全部展示、>50条只展示前50条；只有用户明确指定状态才做筛选。接口没有状态筛选或分页参数，不自行添加。
- 返回：`structuredContent`包含`success`、`total`、`count`和`orders`。
- 约束：仅返回当前OAuth用户订单，不接受身份参数。

```json
{
  "success": true,
  "total": 2,
  "count": 2,
  "orders": [
    {
      "orderId": 123,
      "trackingNumber": "YT123",
      "carrierName": "圆通",
      "statusName": "待接单",
      "senderCity": "深圳市",
      "receiverCity": "杭州市"
    }
  ]
}
```

## parse_address

- 属性：只读。
- 必填参数：`address`字符串。
- 返回：`province`、`city`、`district`、`subArea`、`resultCode`和`message`。
- 约束：关键地址字段缺失时只追问缺失部分。

## query_item_weight

- 属性：查询类，不创建寄件订单；未匹配词可能由服务端记录到新词库用于后续维护。
- 必填参数：`itemName`非空字符串，为具体物品名称；不传订单、地址、重量或身份参数。
- 用途：独立咨询物品寄递限制、运输条件、包装或保价建议，以及寄件前估重；无需先进入完整寄件流程。
- 返回：`structuredContent.result`为物品对象。除`itemName`、`specWeight`、`category`、`restrictionLevel`外，可包含`matchSource`、`weightSource`、`carrierRules`、`packagingAdvice`等；字段映射和嵌套语义见[字段映射](fields.md)。扩展信息取决于匹配数据，数据库降级分支可能不返回规则和建议。
- 已匹配但没有重量：保留已匹配物品及其规则、包装信息，重量为空；不改成默认物品。
- 未匹配：`matchSource=DEFAULT`，保留输入物品名，重量与寄递限制为空或省略，不代表可寄。兼容旧版返回：`DEFAULT`伴随的“1.0公斤、可寄递”也只能视为历史兜底值，不能作为查询依据。
- 约束：知识咨询无需确认重量；继续查价或预下单前，实际重量或有效参考重量必须由用户确认。明确禁寄物不得进入查价或预下单；运输方式特定的限制按其适用范围解释。
- 缺少或空白`itemName`：返回Tool错误，不执行物品查询。工具失败或信息未覆盖问题时，按Skill路由规则补充查询，不编造知识结果。

## list_shipping_options

- 属性：只读。
- 必填参数：`senderCity`、`receiverCity`、`weightKg`。
- 返回：`structuredContent.items`为快递方案数组。
- 约束：公司编码、`companySign`和价格字段必须来自本轮结果，不得自行猜测。

## prepare_shipment_order

- 属性：写操作，会保存一条`PENDING`预订单。
- 必填参数：以运行时Schema为准，核心字段见[字段映射](fields.md)。
- 返回：`structuredContent.url`为小程序URL Scheme，`structuredContent.qrCode`为对应的二维码图片URL。两个字段位于 `structuredContent` 顶层，不包在 `result` 中。
- 重试：失败、超时、断网或结果未知时禁止自动重试。
- 业务结果：仅保存预订单，不代表正式订单已提交或支付完成。

以下为Tool Result示例，`example`仅用于说明格式，不是真实可用的预订单：

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"url\":\"weixin://dl/business/?appid=wx6885acbedba59c14&path=pages/dispatch/index&query=orderNo%3Dexample&env_version=release\",\"qrCode\":\"https://www.kuaidi100.com/twoCode.do?&w=400&h=400&code=weixin%3A%2F%2Fdl%2Fbusiness%2F%3Fappid%3Dwx6885acbedba59c14%26path%3Dpages%2Fdispatch%2Findex%26query%3DorderNo%253Dexample%26env_version%3Drelease\"}"
    }
  ],
  "structuredContent": {
    "url": "weixin://dl/business/?appid=wx6885acbedba59c14&path=pages/dispatch/index&query=orderNo%3Dexample&env_version=release",
    "qrCode": "https://www.kuaidi100.com/twoCode.do?&w=400&h=400&code=weixin%3A%2F%2Fdl%2Fbusiness%2F%3Fappid%3Dwx6885acbedba59c14%26path%3Dpages%2Fdispatch%2Findex%26query%3DorderNo%253Dexample%26env_version%3Drelease"
  },
  "isError": false
}
```

如果直接读取HTTP JSON-RPC响应，上述Tool Result位于外层 `result` 中。Agent优先读取结构化字段；宿主仅暴露 `content` 文本时解析JSON，不把整段JSON当作跳转地址。仅当结构化结果缺失、为空或只有旧版字符串包装时才走兼容分支；已有非空结构化对象缺少某字段时保留可用字段并说明缺失，不拼接不同来源的数据。`isError=true`或JSON-RPC `error`必须先处理，不把其中的URL视为成功下单结果。

展示完整规则及旧版字符串兼容见[链接与二维码](link-and-qrcode.md)。Agent在主对话中提供支付文字链接和内嵌二维码图片：支付链接固定显示为“去小程序确认并支付”，禁止输出裸链接或完整URL代码块；不默认附加“打开二维码”入口，不主动新开网页或侧边预览。旧版字符串也须转换为同样的支付文字链接，缺少二维码时不编造。用户仍需在小程序确认最终订单、价格及支付。
