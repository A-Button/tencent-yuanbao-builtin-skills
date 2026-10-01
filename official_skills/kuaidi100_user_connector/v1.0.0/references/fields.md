# 快递100 Connector字段映射

## 默认寄件人

`get_default_sender`常用返回字段：

| 返回字段 | 预下单字段 |
| --- | --- |
| `name` | `senderName` |
| `mobile` | `senderPhone` |
| `province` | `senderProvince` |
| `city` | `senderCity` |
| `district` | `senderDistrict` |
| `addr` | `senderAddress` |
| `id` | `saddrid`（可选） |

## 地址簿

`search_address_book`返回寄件或收件地址对象，常用字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 地址簿记录ID；设置默认寄件人时作为`addressId` |
| `name` | 联系人姓名 |
| `mobile` | 手机号；收件时映射为`receiverPhone` |
| `province` | 省份；收件时映射为`receiverProvince` |
| `city` | 城市；收件时映射为`receiverCity` |
| `district` | 区县；收件时映射为`receiverDistrict` |
| `addr` | 详细地址；收件时映射为`receiverAddress` |
| `tag` | 地址类型：1为寄件地址，2为收件地址 |
| `isDefault` | 是否默认地址：1是，0否 |

手机号和地址可能包含隐私信息，只能在确认时脱敏展示。写操作只向
`set_default_sender`传递服务端返回的`id`，不得把完整地址重新作为修改参数提交。

地址分类映射：

| Agent参数 | 下游`tag` | 含义 |
| --- | --- | --- |
| `sender` | `1` | 寄件地址 |
| `receiver` | `2` | 收件地址 |

`add_address_book_entry`使用上述分类，并固定`isDefault=0`。`update_address_book_entry`
不接受分类或默认状态参数，只合并用户明确提供的地址字段。`delete_address_book_entry`
只需要`addressId`，下游网页请求中的`guid`不得要求用户提供。

## 地址解析

`parse_address`返回：

| 字段 | 说明 |
| --- | --- |
| `resultCode` | 是否解析成功 |
| `message` | 解析说明 |
| `province` | 省份 |
| `city` | 城市 |
| `district` | 区县 |
| `subArea` | 不含省市区的详细地址 |

## 物品寄递知识与重量

`query_item_weight`常用返回：

| 字段 | 说明 |
| --- | --- |
| `itemName` / `item_name` | 物品名称 |
| `specWeight` / `spec_weight` | 参考重量（公斤） |
| `category` | 分类 |
| `restrictionLevel` / `restriction_level` | 寄递限制 |
| `matchSource` / `match_source` | 匹配来源：`SYNONYM`同义词、`EXACT`精确、`FUZZY_CATEGORY`品类匹配、`FUZZY_AGGREGATED`动态聚合、`DEFAULT`未匹配兜底 |
| `weightSource` / `weight_source` | 返回数据记录的重量来源；为空时不自行声称来源 |
| `tags`、`categoryPath` / `category_path` | 物品标签与分类路径 |
| `deliveryRequirements` / `delivery_requirements` | 寄递特殊要求 |
| `carrierRules` / `carrier_rules` | 匹配到的运输规则数组，可能为空或缺失 |
| `packagingAdvice` / `packaging_advice` | 匹配到的包装及保价建议数组，可能为空或缺失 |

字段可能使用驼峰或下划线形式，按实际响应读取，不要求两种形式同时存在。

运输规则常用字段（同样兼容下划线命名）：

| 字段 | 说明 |
| --- | --- |
| `transportMode` | `LAND`陆运、`AIR`空运、`ALL`全部；限制只适用于对应运输方式 |
| `restrictionLevel` | `ALLOWED`可寄递、`CONDITIONAL`有条件收寄、`FORBIDDEN`禁运；这些枚举用于嵌套规则，顶层字段可能直接返回中文 |
| `conditionDesc`、`transportCondition` | 收寄条件与运输条件摘要；回答时保留适用条件 |
| `ruleSource` | `REGULATION`、`CARRIER`、`MANUAL`等来源标识，不等于具体法规链接或实时验证 |
| `shippingRemark` | 面向用户的寄递说明 |

包装建议常用字段（同样兼容下划线命名）：

| 字段 | 说明 |
| --- | --- |
| `adviceTitle` | 建议标题 |
| `packingMaterials`、`packingDesc` | 推荐材料与详细包装说明 |
| `insuranceRecommend`、`insuranceDesc` | 是否建议保价及说明；缺失时不推断为不推荐，不扩展为赔付承诺 |

`DEFAULT`表示未匹配，不得使用该结果推断重量或可寄结论；旧版默认重量也不能直接进入查价。已匹配但重量缺失时保留知识结果。只有继续查价或预下单时，才要求用户提供或确认重量，并转换为有限且大于0的数值。

## 快递方案

`list_shipping_options`结果到`prepare_shipment_order`的映射：

| 查价字段 | 预下单字段 |
| --- | --- |
| `name` | `kuaidiName` |
| `com` | `kuaidiCom` |
| `sign` | `companySign` |
| `serviceType` | `serviceType`（可选） |
| `totalprice` | `estimatedAmount`（可选） |
| `firstPrice` | `firstPrice`（可选） |
| `overPrice` | `overPrice`（可选） |
| `overWeight` | `overWeight`（可选） |

不得根据名称自行推测公司编码或品牌标识，必须使用本次查价结果。

## 预下单必填字段

```text
senderName, senderPhone, senderProvince, senderCity, senderDistrict, senderAddress
receiverName, receiverPhone, receiverProvince, receiverCity, receiverDistrict, receiverAddress
itemName, weightKg
kuaidiName, kuaidiCom, companySign
confirmed=true
```

可选字段：

```text
saddrid, raddrid, serviceType, estimatedAmount
firstPrice, overPrice, overWeight
remark, expectedPickupTimeDesc
```

## 预下单结果

`prepare_shipment_order`当前返回对象，字段直接位于MCP Tool Result的 `structuredContent` 下：

| 返回字段 | 含义 | 展示方式 |
| --- | --- | --- |
| `structuredContent.url` | 携带预订单编号的微信明文 URL Scheme | 固定渲染为“去小程序确认并支付”文字链接；禁止裸链接，无法点击时引导使用二维码 |
| `structuredContent.qrCode` | `twoCode.do`二维码图片URL，图片内容是同一个 `url` | 在主对话中内嵌二维码图片；不默认附加“打开二维码”入口或新开页面 |

`qrCode`不是Base64图片、微信支付交易码或正式订单号。当前结果不单独返回 `orderNo`、金额或有效期字段，不得自行补造。

原始JSON-RPC响应外层还有 `result`，完整路径为 `result.structuredContent.url` 和 `result.structuredContent.qrCode`。宿主已解包时直接读取 `structuredContent`。

完整示例见[Tool契约](tool-contracts.md#prepare_shipment_order)；文本与旧版结果兼容、展示模板和编码原理见[链接与二维码](link-and-qrcode.md)。
