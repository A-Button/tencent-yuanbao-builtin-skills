# RollingGo 酒店连接器 API 对接参考手册

> **文档版本**：v2.6  
> **服务节点**：`https://mcp.rollinggo.cn/mcp`  
> **鉴权方式**：`Authorization: Bearer {{access_token}}`（由连接器网关自动注入）  

本文档供连接器 (Connector) 工程人员与 Agent 在需要深入查阅字段级契约与响应报文样例时使用。

---

## 目录

1. [通用协议规范](#通用协议规范)
2. [接口 1：searchHotels (搜索酒店)](#1-searchhotels-搜索酒店)
3. [接口 2：getHotelDetail (查询房型报价)](#2-gethoteldetail-查询房型报价)
4. [接口 3：hotelPriceConfirm (锁定实时价格)](#3-hotelpriceconfirm-锁定实时价格)
5. [接口 4：createHotelBookingWithPaymentURL (创建订单)](#4-createhotelbookingwithpaymenturl-创建订单)
6. [接口 5：searchHotelOrders (查询订单列表)](#5-searchhotelorders-查询订单列表)
7. [接口 6：getHotelOrderDetail (查询订单详情)](#6-gethotelorderdetail-查询订单详情)
8. [接口 7：getHotelSearchTags (获取搜索标签)](#7-gethotelsearchtags-获取搜索标签)

---

## 通用协议规范

- **通信协议**：HTTPS
- **数据格式**：`application/json`
- **字符编码**：UTF-8
- **鉴权 Header**：
  ```http
  Authorization: Bearer <access_token>
  Content-Type: application/json
  ```
- **通用错误响应格式**：
  ```json
  {
    "success": false,
    "code": 4000,
    "message": "参数错误原因说明"
  }
  ```

---

## 1. searchHotels (搜索酒店)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hotelsearch`
- **功能**：根据多维条件进行酒店列表初筛及首夜最低参考价展示。

### 请求参数字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| `originQuery` | string | ✅ | — | 针对多轮会话提炼出的完整住宿意图文本 |
| `place` | string | ✅ | — | 目标搜索名称。**针对景点/机场/车站/地铁站/详细地址等局部 POI，必须完整包含城市前缀**（例如 `杭州西湖` 而非单个 `西湖`、`上海虹桥火车站` 而非 `虹桥火车站`），避免全球同名地点定位歧义 |
| `placeType` | string | ✅ | — | 地点类型，严格匹配中文枚举：`城市`、`机场`、`景点`、`火车站`、`地铁站`、`酒店`、`区/县`、`详细地址` |
| `size` | integer | ❌ | 5 | 返回数量限制（最大 20） |
| `checkInParam.checkInDate` | string | ❌ | 明天 | 入住开始时间，格式 `YYYY-MM-DD` |
| `checkInParam.stayNights` | integer | ❌ | 1 | 入住晚数（1~28） |
| `checkInParam.adultCount` | integer | ❌ | 2 | 每间房成人数 |
| `filterOptions.starRatings` | float[] | ❌ | — | 星级范围 `[min, max]`，取值 0.0~5.0，步长 0.5 |
| `filterOptions.distanceInMeter` | integer | ❌ | 2000 | 直线距离限制（米），景点/机场时生效 |
| `hotelTags.requiredTags` | string[] | ❌ | — | 硬性过滤标签列表，如 `["含早餐", "游泳池"]` |
| `hotelTags.preferredBrands` | string[] | ❌ | — | 连锁品牌名称偏好列表，如 `["亚朵", "全季"]` |
| `hotelTags.maxPricePerNight` | number | ❌ | — | 每房每晚预算上限（人民币） |

### 请求体示例 (Request JSON)
```json
{
  "originQuery": "帮我找杭州西湖附近酒店，明晚入住1晚2人",
  "place": "杭州西湖",
  "placeType": "景点",
  "size": 5,
  "checkInParam": {
    "checkInDate": "2026-06-10",
    "stayNights": 1,
    "adultCount": 2
  },
  "filterOptions": {
    "starRatings": [4.0, 5.0],
    "distanceInMeter": 3000
  },
  "hotelTags": {
    "requiredTags": ["含早餐"],
    "preferredBrands": ["全季", "亚朵"],
    "maxPricePerNight": 800
  }
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "message": "查询成功",
  "hotelInformationList": [
    {
      "hotelId": 1109562,
      "name": "杭州西湖湖滨亚朵酒店",
      "nameEn": "Atour Hotel West Lake Hangzhou",
      "brand": "亚朵",
      "address": "杭州市上城区延安路123号",
      "destinationId": "100021",
      "starRating": 4.5,
      "distanceInMeters": 850,
      "latitude": 30.2541,
      "longitude": 120.1652,
      "imageUrl": "https://img.rollinggo.cn/hotel/1109562/main.jpg",
      "bookingUrl": "https://rollinggo.cn/pages/hotel/detail?hotelId=1109562",
      "areaCode": "CN",
      "description": "酒店紧邻西湖风景名胜区，交通便利...",
      "hotelAmenities": ["免费WiFi", "健身房", "免费行李寄存"],
      "price": {
        "hasPrice": true,
        "currency": "CNY",
        "lowestPrice": 539.0,
        "message": "参考价"
      },
      "tags": ["含早餐", "近地铁", "免费WiFi"]
    }
  ]
}
```

---

## 2. getHotelDetail (查询房型报价)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hoteldetail`
- **功能**：根据 hotelId 查询选定酒店的全部可售房型、床型、餐食与取消政策。

### 请求体示例 (Request JSON)
```json
{
  "hotelId": 1109562,
  "dateParam": {
    "checkInDate": "2026-06-10",
    "checkOutDate": "2026-06-11"
  },
  "occupancyParam": {
    "roomCount": 1,
    "adultCount": 2,
    "childCount": 0
  },
  "filter": {
    "cancelPolicy": "CANCELABLE",
    "mealType": "WITH_BREAKFAST"
  }
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "hotelId": 1109562,
  "name": "杭州西湖湖滨亚朵酒店",
  "roomRatePlans": [
    {
      "ratePlanId": "RP_ATOUR_889201",
      "ratePlanName": "Superior King Bed with Breakfast",
      "roomName": "高级大床房",
      "bedTypeDescription": "1张特大床2米",
      "averagePrice": 539.0,
      "currency": "CNY",
      "mealAmount": 1,
      "mealTypeStr": "含单份早餐",
      "cancelPolicy": "2026-06-09 18:00 前可免费取消",
      "cancelable": true,
      "isOnRequest": false,
      "roomInfo": {
        "area": "30-35㎡",
        "floor": "3-8层",
        "window": "有窗",
        "wifi": "免费客房WIFI"
      }
    }
  ]
}
```

---

## 3. hotelPriceConfirm (锁定实时价格)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hotelpriceconfirm`
- **功能**：下单前锁定房态与价格，换取凭证号 `referenceNo`（15~30分钟内有效）。

### 请求体示例 (Request JSON)
```json
{
  "hotelID": 1109562,
  "ratePlanID": "RP_ATOUR_889201",
  "numOfRooms": 1,
  "dateParam": {
    "checkInDate": "2026-06-10",
    "checkOutDate": "2026-06-11"
  },
  "occupancyDetails": [
    {
      "roomNum": 1,
      "adultCount": 2,
      "childCount": 0
    }
  ]
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "message": "价格确认成功",
  "priceDetailsInfo": {
    "referenceNo": "REF_20260610_HZ_991823",
    "checkInDate": "2026-06-10",
    "checkOutDate": "2026-06-11",
    "priceConfirmTime": "2026-09-04 11:30:00",
    "hotelList": [
      {
        "hotelName": "杭州西湖湖滨亚朵酒店",
        "roomName": "Superior King Bed",
        "roomNameCn": "高级大床房",
        "bedTypeStr": "1张特大床2米",
        "cancelPolicy": "免费取消截止至 2026-06-09 18:00:00",
        "currency": "CNY",
        "totalPrice": 539.0,
        "isOnRequest": false
      }
    ]
  },
  "guestProfile": {
    "contactDefault": {
      "firstName": "SAN",
      "lastName": "ZHANG",
      "email": "zhangsan@example.com"
    }
  },
  "note": null
}
```

---

## 4. createHotelBookingWithPaymentURL (创建订单)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hotelbook`
- **功能**：提交入住人信息生成正式预订，返回收银台安全支付链接 `paymentUrl`。

### 请求体示例 (Request JSON)
```json
{
  "referenceNo": "REF_20260610_HZ_991823",
  "contact": {
    "firstName": "SAN",
    "lastName": "ZHANG",
    "email": "zhangsan@example.com"
  },
  "guestList": [
    {
      "roomNum": 1,
      "guestInfo": [
        {
          "firstName": "SAN",
          "lastName": "ZHANG",
          "isAdult": true
        },
        {
          "firstName": "SI",
          "lastName": "LI",
          "isAdult": true
        }
      ]
    }
  ],
  "customerRequest": "尽量安排高楼层"
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "bookingResult": {
    "orderNo": "RG_ORDER_20260610008891",
    "paymentType": "URL",
    "paymentUrl": "https://cashier.rollinggo.cn/pay?orderNo=RG_ORDER_20260610008891&token=sec_token_xxx"
  }
}
```

---

## 5. searchHotelOrders (查询订单列表)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hotelorders`
- **功能**：查询当前用户的历史与待支付订单。

### 请求体示例 (Request JSON)
```json
{
  "status": "ALL",
  "dateRange": {
    "startDate": "2026-01-01",
    "endDate": "2026-06-10"
  }
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "code": 2000,
  "message": "Order query successful",
  "orderList": [
    {
      "orderNo": "RG_ORDER_20260610008891",
      "hotelName": "杭州西湖湖滨亚朵酒店",
      "roomName": "高级大床房",
      "numOfRooms": 1,
      "checkInDate": "2026-06-10",
      "checkOutDate": "2026-06-11",
      "mealDesc": "含单份早餐",
      "cancelPolicyDesc": "免费取消截止至 2026-06-09 18:00:00",
      "orderStatus": "Pending",
      "totalPrice": 539.0,
      "currency": "CNY",
      "orderDate": "2026-06-05 14:22:10",
      "orderDetailUrl": "https://rollinggo.cn/pages/order/detail?orderNo=RG_ORDER_20260610008891"
    }
  ]
}
```

---

## 6. getHotelOrderDetail (查询订单详情)

- **URL**：`POST https://mcp.rollinggo.cn/mcp/hotelorderdetail`
- **功能**：根据订单号获取单笔订单完整履约明细（5 大模块划分）。

### 请求体示例 (Request JSON)
```json
{
  "orderNo": "RG_ORDER_20260610008891"
}
```

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "code": 2000,
  "message": "Order query successful",
  "orderDetail": {
    "baseInfo": {
      "orderNo": "RG_ORDER_20260610008891",
      "referenceNo": "REF_20260610_HZ_991823",
      "orderStatus": "Pending",
      "orderDate": "2026-06-05 14:22:10",
      "orderDetailUrl": "https://rollinggo.cn/pages/order/detail?orderNo=RG_ORDER_20260610008891"
    },
    "hotelInfo": {
      "hotelName": "杭州西湖湖滨亚朵酒店",
      "hotelImageUrl": "https://img.rollinggo.cn/hotel/1109562/main.jpg",
      "hotelPhone": "0571-88888888",
      "platformSupportPhone": "400-820-8820",
      "hotelAddress": "杭州市上城区延安路123号",
      "latitude": 30.2541,
      "longitude": 120.1652
    },
    "stayInfo": {
      "roomName": "高级大床房",
      "bedTypeStr": "1张特大床2米",
      "checkInDate": "2026-06-10",
      "checkOutDate": "2026-06-11",
      "checkInTime": "14:00以后",
      "checkOutTime": "12:00以前",
      "numOfRooms": 1,
      "nights": 1,
      "mealDesc": "含单份早餐",
      "contact": {
        "name": "ZHANG SAN",
        "phone": "13800138000",
        "email": "zhangsan@example.com"
      },
      "guestNames": ["ZHANG SAN", "LI SI"]
    },
    "priceInfo": {
      "totalPrice": 539.0,
      "currency": "CNY"
    },
    "policyInfo": {
      "freeCancelDeadline": "2026-06-09 18:00:00",
      "cancelPolicyDesc": "免费取消截止至 2026-06-09 18:00:00",
      "cancelable": true
    }
  }
}
```

---

## 7. getHotelSearchTags (获取搜索标签)

- **URL**：`GET https://mcp.rollinggo.cn/mcp/hoteltags`
- **功能**：获取系统当前启用的全量特色设施、品牌与服务标签字典。

### 请求体
无（GET 请求，无需入参）。

### 响应体示例 (Response JSON)
```json
{
  "success": true,
  "code": 2000,
  "tags": [
    { "name": "含早餐", "category": "餐饮服务" },
    { "name": "游泳池", "category": "核心设施" },
    { "name": "免费WiFi", "category": "核心设施" },
    { "name": "近地铁", "category": "交通便利" },
    { "name": "亲子家庭", "category": "特色主题" }
  ],
  "usageGuide": {
    "tagUsage": "将标签名称放入 hotelTags.requiredTags（必须满足）或 preferredBrands（偏好品牌）列表中",
    "exampleRequest": "{\"place\": \"杭州西湖\", \"placeType\": \"景点\", \"hotelTags\": {\"requiredTags\": [\"含早餐\"]}}"
  }
}
```
