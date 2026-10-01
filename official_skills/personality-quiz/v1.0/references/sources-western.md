# 西洋占星来源

| source_id | 书目/资料 | 主要用途 | 使用提醒 | review_status |
|---|---|---|---|---|
| WEST-EPHEM-01 | [Astronomy Engine 官方仓库](https://github.com/cosinekitty/astronomy)，Don Cross | 当前随包 `2.1.19` 的天体位置与坐标计算口径 | 当前运行时事实来源；MIT 许可，不提供人格或事件解释 | reviewed-scope |
| WEST-EPHEM-02 | Swiss Ephemeris / Astrodienst 技术文档 | 独立历表口径对照 | 仅作可选交叉核验，不得写成当前运行时引擎 | seeded |
| WEST-GEO-01 | [GeoNames](https://www.geonames.org/about.html)，`geonamescache 2.0.0` 数据快照 | 50 个现有规范城市标签的 WGS84 参考坐标，仅用于准确时间的上升计算 | CC BY 4.0；记录 GeoNames ID、提取方式和许可；不把区域坐标或设备位置充当出生地 | reviewed-scope |
| WEST-UX-01 | [CHANI 入门指南](https://www.chani.com/astro-education/your-guide-to-sun-moon-and-rising-signs)、[Co–Star FAQ](https://www.costarastrology.com/faq)、[TimePassages 手册](https://support.astrograph.com/support/solutions/articles/66000476614-desktop-manual-timepassages) | 五项结果的主题选择与信息层级参考 | 产品方资料不证明科学效度；60 组中文文案为原创，不复制产品正文 | reviewed-scope |
| WEST-CLASSIC-01 | Ptolemy, *Tetrabiblos* | 古典占星历史和基本框架 | 需区分古典语境与现代心理占星 | seeded |
| WEST-CLASSIC-02 | William Lilly, *Christian Astrology* | 传统占星方法与术语考据 | 不直接套用于当前只覆盖本命行星和主要相位的引擎 | seeded |
| WEST-MODERN-01 | Sue Tompkins, *Aspects in Astrology* | 相位的心理动力和矛盾表现 | 现代版权书；只保留团队归纳和版本指针 | seeded |
| WEST-MODERN-02 | Stephen Arroyo, *Astrology, Psychology, and the Four Elements* | 元素与心理取向的现代解释 | 不把心理语言写成临床结论 | seeded |
| WEST-MODERN-03 | Liz Greene, *The Astrology of Fate* | 心理占星的复杂性与象征解释 | 不用于保证具体命运事件 | seeded |
| WEST-MODERN-04 | Robert Hand, *Planets in Transit* | 行运解释方法 | 当前引擎未计算行运时不得使用 | seeded |
| WEST-MODERN-05 | Howard Sasportas, *The Twelve Houses* | 宫位的心理主题 | 当前引擎未计算宫位时不得使用 | seeded |
