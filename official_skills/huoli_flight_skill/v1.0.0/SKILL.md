---
name: huoli_flight_skill
version: v1.0.0
description: 航班管家机票与出行服务。支持机票查询和预订、订单与售后、值机指引，以及航班动态、机场信息、执飞机型和我的航班行程查询。用户提到机票、订票、退改签、抢票、值机、选座、登机牌、发票、航班状态、机场或我的行程时使用。
---

# 航班管家机票与出行服务

通过已注册在 Hbgj MCP Server 的工具处理机票、航班动态和个人行程业务。

## 文件地图

| 文件 | 用途 | 何时读取 |
|---|---|---|
| `SKILL.md` | 触发条件、意图路由与工具清单 | 每次触发时**必须**读取 |
| `references/booking_workflow.md` | 查询机票、查询舱位、普通购票、低价抢票、普通订单与抢票订单流程 | 用户要查票、购票、查询或取消普通订单及抢票订单时**必须**读取 |
| `references/after_sales_workflow.md` | 退票、改期、值机、开票和凭证管理流程 | 用户要退改机票、办理值机、报销或管理凭证时**必须**读取 |
| `references/dynamic_query_workflow.md` | 航班动态、机场信息、机场大屏和执飞机型查询 | 用户要查航班状态、机场信息、登机口、值机柜台或机型时**必须**读取 |
| `references/trip_workflow.md` | 我的近期、历史及指定范围航班行程查询 | 用户要查“我的航班”“我的行程”或出行记录时**必须**读取 |

## 执行方式

直接调用对应 MCP 工具，并传入 JSON 对象参数。不要使用本地脚本包装工具调用。

例如，查询航班时调用 `search_flights`，参数示例：

```json
{
  "date": "2026-10-01",
  "departureCityCode": "BJS",
  "arrivalCityCode": "SHA",
  "cabinPreference": "Y",
  "onlyDirect": "true",
  "sortBy": "totalPrice",
  "sortOrder": "asc"
}
```

## 意图路由

| 用户意图 | 执行流程 |
|---|---|
| 查询机票 | `search_flights` → 展示航班列表 |
| 查询舱位或价格 | `search_flights` → `get_flight_offers` |
| 订票 | `search_flights` → `get_flight_offers` → `uni_query_flight_confirm`（查询乘机人）→ `uni_query_flight_confirm`（行程确认）→ 用户明确确认 → `uni_order_create` |
| 查询订单 | `uni_order_query` |
| 取消订单 | `uni_order_query` → 用户明确确认 → `uni_order_cancel` |
| 退票 | `uni_order_query` → `refund_query_fee` → 用户明确确认 → `refund_submit` |
| 改期 | `uni_order_query` → `reroute_query_flight_filter` → `reroute_query_fee` → 用户明确确认 → `reroute_submit` |
| 报销开票 | `query_invoiceable` → 用户明确确认 → `submit_invoice` |
| 查询或管理凭证 | `query_invoices` → 必要时确认 → `manage_invoice` |
| 低价抢票 | `grab_low_confirm` → `grab_low_price_calculate` → 用户明确确认 → `grab_low_create_order` |
| 查询或取消抢票订单 | `grab_low_order_list` / `grab_low_order_detail` → 用户明确确认 → `grab_low_cancel` |
| 值机指引 | `trip_query` → `dynamic_flight_query` → `checkin_window` |
| 航班动态或航线班次 | `dynamic_flight_query_yb`；地点不明确时先用 `dynamic_airport_search_yb` 解析 |
| 机场信息或机场大屏 | `dynamic_airport_search_yb` → 按需调用 `dynamic_airport_screen_yb` |
| 执飞机型 | `dynamic_plane_type_yb`；缺少必要航班信息时先按动态流程查询或向用户追问 |
| 我的航班、我的行程或历史行程 | `trip_query_yb` |
| 我的航班现在什么状态 | `trip_query_yb` 定位唯一行程 → `dynamic_flight_query_yb` 查询该航班实时动态；无法唯一定位时先让用户选择 |

“我的航班”即使未提供航班号也走行程流程；指定航班号的状态查询走动态流程。查询登机口、值机柜台等现场信息走动态流程；办理值机、选座、登机牌等业务仍走现有值机指引流程。`dynamic_flight_query` 和 `dynamic_flight_query_yb` 都只查询航班信息；现有值机流程的值机窗口与办理入口以 `checkin_window` 的结果为准。跨流程查询时，只能用行程结果中已确认的航班号和日期查询动态，不猜测航班身份。按上述路由读取对应工作流；涉及行程加动态时两份新增工作流都要读取。

## 工具清单

| 工具 | 说明 |
|---|---|
| `search_flights` | 查询机票列表 |
| `get_flight_offers` | 查询航班舱位、价格、余票和退改规则 |
| `uni_query_flight_confirm` | 查询乘机人及行程确认信息 |
| `uni_order_create` | 创建机票订单 |
| `uni_order_query` | 查询订单列表或详情 |
| `uni_order_cancel` | 取消机票订单 |
| `refund_query_fee` | 计算退票费用 |
| `refund_submit` | 提交退票申请 |
| `reroute_query_flight_filter` | 查询改期可选航班 |
| `reroute_query_fee` | 计算改期费用 |
| `reroute_submit` | 提交改期申请 |
| `query_invoiceable` | 查询可报销订单 |
| `submit_invoice` | 提交报销凭证或开票申请 |
| `query_invoices` | 查询已提交凭证 |
| `manage_invoice` | 取消、修改或重发凭证 |
| `grab_low_confirm` | 生成低价抢票填单方案 |
| `grab_low_price_calculate` | 计算低价抢票订单总价 |
| `grab_low_create_order` | 创建低价抢票订单 |
| `grab_low_order_list` | 查询低价抢票订单列表 |
| `grab_low_order_detail` | 查询低价抢票订单详情 |
| `grab_low_cancel` | 取消低价抢票订单 |
| `trip_query` | 查询用户待出行行程 |
| `dynamic_flight_query` | 查询航班基础信息 |
| `checkin_window` | 查询值机开放、截止时间和在线入口 |
| `dynamic_airport_search_yb` | 搜索机场、城市和国家，解析真实查询编码 |
| `dynamic_airport_screen_yb` | 查询机场进港或出港实时大屏 |
| `dynamic_flight_query_yb` | 查询指定航班或航线的实时动态 |
| `dynamic_plane_type_yb` | 查询已确认航班的执飞机型信息 |
| `trip_query_yb` | 查询当前用户的航班行程 |

## 全局约束

- 不伪造参数或复用已失效的上游结果。所有 ID、价格、订单号、透传字段和乘机人数据必须来自用户输入或当前流程的工具响应。
- 创建、取消、退票、改期、开票以及修改凭证等有外部影响的操作，必须先展示关键信息并取得用户对当前动作的明确确认。
- 用户表示“停止”“算了”或撤销意图时，立即停止未执行的操作。
- 工具失败时停止当前链路，说明失败原因和可行的下一步；不伪造结果或盲目重复调用。
