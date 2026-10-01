# 人格结果页图片规则

本参考只在维护或诊断人格结果页图片时读取。图片是结果的视觉层，不参与计分，也不把四字母近似包装成正式 MBTI 诊断。

## 当前映射

`assets/report-illustrations.json` 是当前结果页的图片映射。`mascots.default_file` 指向用户提供的 `assets/report-art/enfj.png`；其余 15 型暂共用这张人物图。后续收到其他类型人物图后，在 `mascots.type_files` 中逐型指定，不改计分或复制格式。

报告的 communication、decision、growth、reflection 四栏分别使用 `assets/report-art/` 下的同名 PNG。构建器按映射把图片内联进离线 HTML，并校验文件路径、格式、实际解码和大小。人物图和四栏插画当前都使用空 alt，不把 ENFJ 图错误描述成其他类型的专属形象。

计分质量通过且四轴均非 X 时，页面才显示类型人物图；含 X 或全同作答时不强行选择类型或展示人物图。报告图片也只使用同一份当前映射。替换图片后须重新验证 20／50 题产物及宿主 2 MiB 附件上限。


## 交接边界

图片、称呼、资源哈希和角色选择不得写入 `PERSONALITY_RESULT_V1`；复制交接只包含四轴连续值与大五原始均值。
