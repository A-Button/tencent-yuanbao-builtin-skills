# 预订单链接与二维码

用于展示 `prepare_shipment_order` 结果、解释跳转原理，以及区分图片显示失败和扫码失效。

## 一、读取真实返回值

1. 先处理JSON-RPC `error` 和Tool Result的 `isError=true`，失败时不按成功预订单输出。
2. 若宿主交付原始JSON-RPC响应，先取外层 `result` 得到Tool Result。
3. 当前服务优先读取 `structuredContent.url` 和 `structuredContent.qrCode`。不要固定读取 `structuredContent.result`，它是旧字符串结果的包装方式。
4. 仅当结构化结果缺失、为空或只含旧版字符串包装时再兼容：旧版 `structuredContent.result` 为 `weixin://` 字符串则只使用该链接；仅有 `content` 文本时，解析其中的JSON对象获取 `url`、`qrCode`，或接受旧版纯Scheme文本。
5. 非空的新结构化对象若缺少字段，只展示已有的有效非空字符串，并说明哪个入口未返回；不从其他文本块补齐、不拼接不同响应、不自行生成二维码URL。无法解析的文本不当作链接。

`url` 应为服务端返回的小程序Scheme；`qrCode`应为HTTP(S)图片地址。保留原始字符串，不截断、不额外编码或解码、不把 `weixin://` 改成 `https://`。

## 二、同时展示可操作入口

默认在主对话中展示“去小程序确认并支付”文字链接和内嵌二维码图片，不附加“打开二维码”入口，不主动创建网页、浏览器标签页或侧边预览。支付入口的可见文字固定为“去小程序确认并支付”，真实地址只放在链接目标中，禁止输出裸链接，也不得把完整地址放进正文、表格、行内代码或代码块。以下是展示模板，必须用同一次成功响应的实际字段替换花括号占位内容；实际回答直接渲染Markdown，不将模板放进代码块：

```markdown
已生成预订单，请进入快递100小程序确认最终订单、价格并支付。

[去小程序确认并支付]({url})

![扫码进入小程序确认订单]({qrCode})
```

- 宿主将Scheme渲染为不可点击的文字时，提示扫描主对话中的二维码图片；禁止以裸Scheme或原始URL代码块作为兜底。
- 图片不支持内嵌或加载失败时，在主对话中如实说明并保留支付文字链接；不自动新建网页、浏览器标签页或侧边图片预览。仅在用户另行明确要求浏览器打开二维码时，才使用宿主相应能力，不把“展示二维码”理解为授权新开页面。
- 只展示或打开已有结果时，不再次调用 `prepare_shipment_order`。二维码和跳转链接必须来自同一条预订单。
- HTTP 200、PNG格式、图片显示、二维码解码、小程序跳转、预订单可用性是不同检查层级。只报告实际验证的层级，不将图片占位符判成订单失效。

## 三、当前服务端实现原理

以下说明用于理解当前服务实现，不是要求Agent自行拼接链接或调用额外接口。下面的原始URL示例仅用于技术说明，不得作为寄件结果的展示模板；寄件结果仍必须使用前述文字链接格式。

### 1. 保存预订单

`ConnectorShipmentToolProvider.prepareShipmentTool()`中的 `prepare_shipment_order` 调用 `PreShipmentOrderServiceImpl.collectShipmentOrderInfo()`。
服务端保存预订单并产生 `orderNo`；Connector用 `extractPreparedOrderNo()`读取编号，再构造小程序入口。此步骤不创建支付交易码，也不完成正式下单。

### 2. 构造微信明文 URL Scheme

`buildWechatMiniProgramScheme(orderNo)`当前拼接的格式：

```text
weixin://dl/business/?appid=wx6885acbedba59c14&path=pages/dispatch/index&query=orderNo%3Dexample&env_version=release
```

| 部分 | 当前用途 |
| --- | --- |
| `weixin://dl/business/` | 微信处理的小程序跳转协议入口，不是普通HTTPS网页 |
| `appid` | 目标快递100小程序标识 |
| `path=pages/dispatch/index` | 目标小程序页面路径 |
| `query=orderNo%3Dexample` | 页面参数；内层原文为 `orderNo=example` |
| `env_version=release` | 当前代码选择正式版小程序 |

代码先用 `URLEncoder.encode("orderNo=" + orderNo, "UTF-8")` 编码页面参数，再把它放入Scheme的 `query`。当前Connector直接拼接明文Scheme，不调用微信 `generatescheme` 接口，也不调用旧的 `ckd.im` 短链服务。

支持该协议的入口把Scheme交给微信，微信按小程序标识、页面及参数打开目标页面。`orderNo`用于关联服务端预订单，避免把寄收件人信息和完整地址直接放进链接。页面如何加载订单及处理有效期需以小程序实际实现为准；Skill不能保证所有宿主、浏览器或扫码入口都支持这种跳转。

### 3. 构造二维码图片URL

当前Java实现：

```java
String url = buildWechatMiniProgramScheme(orderNo);
String qrCode = "https://www.kuaidi100.com/twoCode.do?&w=400&h=400&code="
        + URLEncodeUtil.encodeAll(url);
```

Tool返回两个字符串 `url` 和 `qrCode`。MCP文本内容块序列化同一对象，`structuredContent`保留两个字段；服务端在这个方法里不下载PNG，也没有返回Base64或MCP `image`内容块。

宿主加载 `qrCode` 时向快递100的 `twoCode.do` 图片服务发起HTTP请求。该服务将 `code` 参数还原为完整Scheme，并将它编码成普通二维码图片。扫描图片得到的是Scheme本身，不是图片地址。它是小程序跳转二维码，不是微信官方小程序码接口生成的码，也不是微信支付交易码。

`w=400&h=400`是请求尺寸，实际返回像素由图片服务决定，不能仅看参数就声称图片一定是400×400。

### 4. 为什么需要两层URL编码

```text
页面参数原文：       orderNo=example
放进Scheme的query： orderNo%3Dexample
整个Scheme再放进图片URL的code：其中变为 orderNo%253Dexample
```

第二层将内层的 `%` 编为 `%25`，同时把Scheme里的 `&`、`?`、`=`编码，避免它们被图片服务当成外层参数。图片服务按URL参数解码一次后应得到原始Scheme；微信解析Scheme的 `query` 后再得到页面参数。

这里使用 `URLEncodeUtil.encodeAll(url)`。项目当前Hutool版本的普通 `encode(url)`会保留 `&`，直接照搬旧短链接场景可能把完整Scheme拆成多个图片接口参数。二维码图片里的文本必须与返回的 `url` 完全一致。

## 四、展示失败和失效的区别

- 图片加载失败：可能是宿主图片加载、网络或图片服务问题。在主对话中说明显示失败，保留支付文字链接；不裸露URL，不自动打开新页面，不推断订单已失效。
- 图片能显示且可解码，但扫码不能跳转：检查扫码入口是否支持Scheme，以及微信与小程序侧的实际提示，不能仅凭图片正确就保证跳转成功。
- 进入小程序后提示订单不存在或失效：需要检查预订单数据及小程序读取逻辑。当前Tool未返回有效期，也没有在生成方法中设置过期参数，不得编造“几分钟有效”或“永久有效”。
- 重新画同一条Scheme的二维码不会改变 `orderNo`，也不会延长预订单有效期。用户明确要求重新创建时按已确认寄件信息发起一次新预下单，使用同一次新返回的两个入口；失败或结果未知时不自动重试。
