# 健康报告数据契约与生成规则

## 1. 通用输入

```json
{
  "report_type": "daily|weekly",
  "profile": {
    "height_cm": 175,
    "weight_kg": 70,
    "age": 30,
    "sex": "male|female|unknown",
    "goal": "fat_loss|maintain|gain|unknown",
    "target_kcal": 2100,
    "target_protein_g": 90,
    "target_fat_g": 70,
    "target_carb_g": 250
  }
}
```

未知字段填 `null`，不要填一个看似合理的默认值。

## 2. 日报输入

```json
{
  "report_type": "daily",
  "date": "2026-09-21",
  "weekday": "周一",
  "day_complete_confirmed": true,
  "profile": {},
  "meals": [
    {
      "meal_type": "早餐|午餐|晚餐|加餐",
      "time": "08:10",
      "photo_url": null,
      "foods": [{"name":"水煮蛋","portion":"2个"}],
      "totals": {"kcal":240,"protein_g":18,"fat_g":12,"carb_g":15,"sodium_mg":320},
      "scene": "只基于记录写场景",
      "signal": "只基于数据写关键信号",
      "source": "user_photo|user_text|connector|estimate",
      "confidence": "high|medium|low"
    }
  ],
  "exercises": [
    {
      "name":"傍晚快走",
      "time":"18:20",
      "duration_min":40,
      "distance_km":4.2,
      "pace":"9分31秒/公里",
      "kcal":168,
      "source":"connector|user_text|estimate"
    }
  ],
  "daily_activity_kcal": 300,
  "daily_activity_source": "connector|steps_estimate|unknown"
}
```

计算：

```text
intake_kcal = sum(meals[].totals.kcal)
active_kcal = sum(exercises[].kcal)
bmr_male = 10*weight_kg + 6.25*height_cm - 5*age + 5
bmr_female = 10*weight_kg + 6.25*height_cm - 5*age - 161
total_burn_kcal = bmr_kcal + daily_activity_kcal + active_kcal
balance_kcal = intake_kcal - total_burn_kcal
```

只在所有项可用时计算 `total_burn_kcal` 和 `balance_kcal`。

## 3. 周报输入

```json
{
  "report_type": "weekly",
  "week_start": "2026-09-14",
  "week_end": "2026-09-20",
  "profile": {},
  "days": [
    {
      "date": "2026-09-14",
      "weekday": "周一",
      "is_valid_day": true,
      "meals": {
        "breakfast": {"summary":"水煮蛋2个、无糖豆浆250ml","kcal":420},
        "lunch": {"summary":"鸡胸肉饭、西兰花","kcal":760},
        "dinner": {"summary":"清蒸鱼1条、青菜2小碗、米饭半小碗","kcal":720}
      },
      "nutrition": {"protein_g":90,"fat_g":60,"carb_g":230},
      "exercise_slots": {
        "noon": null,
        "commute": null,
        "evening": {"summary":"快走40分钟，4.2km","kcal":168}
      },
      "intake_kcal": 1900,
      "bmr_kcal": 1649,
      "daily_activity_kcal": 300,
      "active_kcal": 168,
      "total_burn_kcal": 2117
    }
  ],
  "next_week_plan": {
    "days": [
      {
        "weekday":"周一",
        "breakfast":"鸡蛋2个、无糖酸奶200g、全麦面包2片",
        "lunch":"鸡胸肉150g、糙米饭1小碗约150g、西兰花2小碗约300g",
        "dinner":"清蒸鱼1条约250g、青菜2小碗约300g、米饭半小碗约80g",
        "movement":"午饭后快走15分钟",
        "target_balance_kcal":-250
      }
    ]
  }
}
```

## 4. 有效天定义

满足以下任一条件可计为有效记录日：

- 至少 2 个餐次有记录；
- 至少 1 个餐次且有 1 条运动记录；
- 用户明确确认该日记录已经完整。

未记录日不是 0 摄入、0 消耗。周累计只加总口径一致的有效日，并在页脚写明有效天数。

## 5. 周历表格

三张表固定为：

1. 饮食周历：行是早餐、午餐、晚餐、当日摄入。
2. 运动周历：行是午间、通勤/下班、晚间、运动消耗。
3. 下周执行表：行是早餐、午餐、晚餐、顺手运动、目标差值。

CSS 必须保留：

```css
.matrix-wrap{max-width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;touch-action:pan-x}
.week-matrix .corner,.week-matrix tbody th{position:sticky;left:0}
.week-matrix td.empty{text-align:center;vertical-align:middle}
```

移动端 390px 视口下，除固定首列外约显示 3 个日期列。历史缺失值渲染：

```html
<td class="empty">暂无记录</td>
```

## 6. 份量单位

允许：

- 自然个数：1 条鱼、2 个鸡蛋、半个红薯；
- 常见容器：1 小碗米饭、2 小碗熟蔬菜；
- 标准计量：150g、250ml；
- 最佳写法：`1 小碗（约150g）`。

禁止：一掌、一掌心、一拳、两拳、半拳。

## 7. HTML 外正文

日报信息不完整时，在 HTML 后输出追问。周报完整时，在 HTML 后输出“要不要一键帮你同步到日历？”。这些内容不得写入 HTML 文件。
