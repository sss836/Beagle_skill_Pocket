# 按交付物选择技能

以下是匹配提示，不是安装清单。只选择当前会话提供的技能，名称以其清单为准。

| 目标 | 优先检查 | 区分相近需求 |
| --- | --- | --- |
| 主 agent 带队 | agent-team | 普通导航不自动组队；严格审计才考虑 supervisor |
| 学术初稿 | nature-writing | 已有文字润色或翻译优先 nature-polishing |
| 论文语句找支撑文献 | nature-citation | 大范围文献调查或引用指标优先 nature-academic-search |
| 模拟审稿 | nature-reviewer | 回复真实审稿意见优先 nature-response |
| 论文中文汇报 | nature-paper2ppt | 一般演示优先 presentations |
| 科研数据图 | nature-figure / scipilot-figure-skill | 按数据、期刊和既有流程选一个主技能 |
| 技术架构图 | drawio-diagram-builder | 可编辑结构图与 AI 位图插画分开选择 |
| Word / PDF / 表格 | documents / pdf / spreadsheets | 以格式和版面要求决定 |
| Google 文件 | google-drive 及其格式子技能 | 需要已连接工具；本地文件不依赖云连接 |
| 网站 / 交互解释 | sites / visualize | 持久站点与会话内解释按目标区分 |
| 图片 | imagegen | SVG 或代码原生图标按原生格式编辑 |
| 跨来源调查 | deep-research / research | 按深度和输出要求选择 |
| 查找可安装技能 | find-skills | 授权安装时再读取 skill-installer |
| 制作技能 | skill-creator | 重复内容模板优先适用的 template-creator |
| Codex 产品问题 | openai-docs | 按其要求核实当前行为 |

多 agent 是组织方式，领域技能决定专业做法。互盲和数据完整性等要求不能因组合而丢弃。
