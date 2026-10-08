# rpgmaker-mz-translation

给 AI Agent 使用的 **RPG Maker MV/MZ 游戏汉化技能包**，包含文本定位、翻译与术语管理流程，以及路径补丁、审计、图片加解密和存档编解码脚本。当前已验证的语言对是日语 → 中文。

按 [Agent Skills](https://agentskills.io/specification) 的目录形式组织：[SKILL.md](SKILL.md) 是 Agent 的流程入口，参考文档和脚本按任务调用。翻译和插件语义判断由 Agent 完成，脚本负责确定性的写入、编解码和校验。

## 功能

RPG Maker 游戏的文本分散在多种载体中，需要分别定位和处理：

| 载体 | 处理内容 |
| --- | --- |
| `data/*.json` | 事件对话、选项、数据库名称与描述，以及嵌套的插件指令参数 |
| `js/plugins.js` | 插件参数，包括多层 JSON 字符串 |
| `js/plugins/*.js` | 插件源码中硬编码的界面文字 |
| `img/` | 图片上的文字，包括需要先解密的图片 |
| `save/` | 存档中保留的旧文本 |

- **按路径修改数据**：修改清单绑定源文件摘要、精确路径和预期旧值；先预检，再生成独立工作副本，避免相同文本出现在显示字段和程序字段时被一起替换。
- **独立核对修改**：检查实际差异是否与清单一致，核对结构、类型、选项分支和未修改字节；`note`、`meta`、标识符等程序字段默认保护。未知插件字段需要检查实际消费者。
- **按需翻译图片文字**：先检查并询问用户是否处理；范围确认后提供原图与翻译预览的 **compare**，样张确认后才批量处理和回写。标题美术字可单独决定。本包未内置 OCR 引擎或通用重绘脚本。
- **统一验收流程**：结合候选文本审计、语义复核和游戏内检查，处理遗漏、控制字符、字体和插件参数等问题。

JSON 路径补丁工具只处理 `data/*.json`；插件参数、源码、图片和存档使用各自的处理与验收流程。

## 安装与使用

将**整个技能目录**放入客户端配置的技能目录，保留 `SKILL.md`、`references/`、`scripts/` 和 `assets/`。具体路径与启用方式以客户端文档为准；例如本项目的 WorkBuddy 使用路径为：

```text
%USERPROFILE%\.workbuddy\skills\rpgmaker-mz-translation\
```

脚本使用 Python 3 标准库；`verify_plugins_js.js` 需要 Node.js。图片识别和重绘所需工具按具体任务选择。

技能安装后，向 Agent 提供游戏目录和目标语言即可：

```text
使用 rpgmaker-mz-translation，把「<游戏绝对路径>」汉化成简体中文。
```

Agent 会在游戏旁建立 `<游戏目录名>_translation_work`，将备份、译文、术语表、图片预览、报告和补丁集中在那里；再次执行会检查并恢复已有任务。也可直接指定其他工作目录。图片处理由 Agent 主动询问，先确认 compare 样张；原游戏回写前另行确认。

也可以只做定位或审计：

```text
检查这个 RPG Maker 游戏的文本分布和插件，列出可翻译字段与需要保护的字段。
游戏目录：<路径>
```

Agent 从 [SKILL.md](SKILL.md) 开始执行：备份 → 定位与分类 → 按上下文翻译 → 在工作副本中应用修改 → 校验与复核 → 游戏内验收。

## 使用边界

- **先备份，再修改**。保留原始数据和各载体的备份，校验通过后再安装工作副本。
- **图片翻译单独确认**。用户同意处理范围和 compare 样张后，才进行批量处理与回写。
- **静态校验不等于翻译或玩法验收**。它不能证明译文准确、文本全部覆盖，也不能证明插件行为和游戏画面正常；仍需上下文复核与实机检查。
- **插件需按实际实现判断**。`note` 可能同时承载程序标签和可见文本；确需翻译其中内容时走专项处理，不绕过默认保护进行全局替换。
- **其他语言对需要适配**。引擎处理流程可复用，但候选文本识别、特殊文本规则和字体要求需另行验证，日语模块见 [scripts/lang/ja.py](scripts/lang/ja.py)。
- **游戏数据留在游戏工作目录**。本仓库提供空术语表模板和最小测试案例，不包含游戏资产或完整译文。

## 文档

| 文档 | 用途 |
| --- | --- |
| [Agent 主流程](SKILL.md) | 从备份到验收的操作步骤 |
| [工作区与任务命令](references/workspace.md) | 默认目录、任务恢复、产物边界及外部工具调用 |
| [文本地图](references/text-map.md) | 字段、事件指令码与程序字段的区分 |
| [安全补丁流程](references/safe-patching.md) | 修改清单、路径写入与独立校验命令 |
| [图片文字翻译](references/image-redraw.md) | 范围询问、compare、重绘和视觉验收 |
| [证据与验收边界](references/validation.md) | 审计契约、验证依据与尚需人工检查的部分 |
| [常见问题](references/pitfalls.md) | 引擎规则、插件差异与游戏案例 |
| [日语 → 中文](references/lang-pair-ja-zh.md) | 注音、纯汉字日文词与字体 |
| [插件参数修复](references/plugin-param-repair.md) | 参数体检与损坏修复 |
| [补丁分发前清理](references/release.md) | 打包清理与必须保留的文件 |
| [术语表模板](assets/glossary.template.json) | 每个游戏的术语表起点 |

## 开发验证

在仓库根目录运行：

```sh
python -B -m unittest discover -s tests -v
node --check scripts/verify_plugins_js.js
```

测试覆盖路径写入、独立差异校验、文本审计和编解码回归；图片 compare 与游戏内验收需另行完成。

## 交流与支持

欢迎交流工具使用、AI 与 Agent 技术问题：[爱发电 · 笨蛋歪](https://afdian.com/a/dummywayne)。

## License

[MIT](LICENSE)
