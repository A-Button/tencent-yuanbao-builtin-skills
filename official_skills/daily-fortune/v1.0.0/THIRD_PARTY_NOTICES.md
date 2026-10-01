# 第三方声明 · 八字大师

本 Skill 使用以下开源组件与数据：

- lunar-javascript（MIT）：历法、干支、节气。
- 八字大师专用依赖：见各 Skill 的 `vendor/node_modules` 内 LICENSE 文件。
- Kangxi stroke snapshot（MIT, Kawai Lo）：仅用于 `name-analysis`。
- iztro（MIT）：仅用于 `ziwei-master`。
- astronomy-engine（MIT）：仅用于 `western-astrology`。
- qimendunjia-standalone（MIT）：仅用于 `qimen-divination`。

所有依赖离线打包在 `vendor/node_modules`，运行时不联网。
