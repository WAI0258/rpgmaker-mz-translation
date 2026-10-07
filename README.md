# rpgmaker-mz-translation

当前版本：**v1.1**

给 AI Agent 用的 **RPG Maker MV/MZ 游戏汉化技能包**。它把"游戏文本在哪、统一去哪改、怎么安全地批量替换、翻完怎么验收、发布前怎么清干净"整理成一套可执行的流程 + 脚本。

遵循 [Agent Skills 开放标准](https://agentskills.io/)，`SKILL.md` 单文件即全部必需内容，任何兼容该标准的 Agent 客户端都能直接加载。

## v1.1 更新

新增**按需启用的图片文字翻译流程**：先只读检查并征询用户是否处理，再根据图片选择
OCR、人工辨读或几何定位。用户同意范围后，提供原图与翻译预览的 **compare**，
确认译文、字体、排版和视觉效果后，才批量替换及回写。标题美术字与普通 UI 可分别选择。
普通文本翻译继续沿用原有流程。

同时修正文本审计与图片编解码的校验问题，详见[证据与验收边界](references/validation.md)。
本包未内置 OCR 引擎或通用图片重绘脚本。

---

## 它解决什么

RPG Maker 游戏的文本**不在一个地方**——这是汉化最容易踩的坑。实际分布在五类载体：

| 载体              | 内容                                                     |
| ----------------- | -------------------------------------------------------- |
| `data/*.json`     | 剧情对话、选项、插件指令、数据库名称与描述（**量最大**） |
| `js/plugins.js`   | 插件参数（值是**嵌套 JSON 字符串**，要递归穿透）         |
| `js/plugins/*.js` | 插件源码里硬编码的界面文字                               |
| `img/*.png_`      | 加密图片上烤进去的字                                     |
| `save/*.rmmzsave` | 存档里冻结的旧文本                                       |

其中 `data/` 内部还要按**事件指令码**区分（`401/405` 对话、`102` 选项、`402` 分支、`357` MZ 插件参数、`657` 编辑器说明、`108/408` 注释…），并且要跳过标识符、`note` 元数据、资源名——否则一译就坏功能。

本技能把这些全部写成可查的**文本地图**，并把确定性的部分（遍历、编解码、审计）做成脚本，判断性的部分（翻什么、哪些可见、术语怎么定）留给 Agent。

---

## 安装

本包是标准 Agent Skills 目录，安装 = 把它放进你所用的 Agent 的技能目录。

| 客户端                         | 放这里                                                     |
| ------------------------------ | ---------------------------------------------------------- |
| **WorkBuddy**                  | `%USERPROFILE%\.workbuddy\skills\rpgmaker-mz-translation\` |
| Claude Code                    | `~/.claude/skills/rpgmaker-mz-translation/`                |
| 其他兼容 Agent Skills 的客户端 | 见各自文档的技能目录                                       |

**Windows 上如果你把仓库放在别处开发**，可以在技能目录建一个目录联接（不占空间、自动同步）：

```bat
mklink /J "%USERPROFILE%\.workbuddy\skills\rpgmaker-mz-translation" "D:\workplace\rpgmaker-mz-translation"
```

> Windows 用 `mklink /J` 需要管理员权限；macOS / Linux 用 `ln -s`。

装好后无需配置，Agent 会在你提到「汉化 / 翻译 RPG Maker 游戏 / 游戏文本在哪」时自动加载。

---

## 目录结构

```
rpgmaker-mz-translation/
├── SKILL.md                        # 主流程（Agent 读这个）
├── README.md                       # 本文件（给人看）
├── LICENSE
├── references/                     # 细节文档，Agent 按需读
│   ├── text-map.md                 # 文本地图：精确 JSON 路径 + 指令码 + 哪些字段不能动
│   ├── pitfalls.md                 # 踩坑清单（区分引擎规则与游戏经验）
│   ├── image-redraw.md             # 可选图片翻译：询问、compare、确认、重绘及验收
│   ├── validation.md               # 证据、审计契约与验收边界
│   ├── lang-pair-ja-zh.md          # 日→中 专属：注音、纯汉字日文词、字体
│   ├── plugin-param-repair.md      # 插件参数写坏后的修复
│   └── release.md                  # 发布前清理（含"绝不删"清单）
├── scripts/                        # 确定性代码，执行即可，不占上下文
│   ├── audit_visible_jp.py         # data/plugins.js 候选清单、结构与选项校验
│   ├── fix_plugin_params.py        # 插件参数体检 / 修复
│   ├── verify_plugins_js.js        # 复刻插件参数解析器做只读校验
│   ├── encrypt_img.py             # PNG/Ogg 校验、加解密与安全写入
│   ├── saves_codec.py              # 存档 pako/zlib 编解码
│   └── lang/                       # 语言相关模块（当前：ja）
└── assets/
    └── glossary.template.json      # 术语表空模板
```

---

## 语言支持

- **引擎层与语言无关**：找文本、改文本、审计、存档、图片加解密，对任意语言对通用。
- **已实测**：日语 → 中文。
- **其他语言对**：按 `scripts/lang/ja.py` 的样子加一个模块（源语言的字形判定、特殊文本特性），
  并按目标语言确认字体要求。参考 `references/lang-pair-ja-zh.md`。

---

## 使用

对 Agent 说清楚三件事即可，其余它自己查：

```
把这个 RPG Maker 游戏汉化成中文，游戏目录 <路径>
```

或直接问：

```
这个 RPG Maker 游戏的文本都在哪些文件里？统一在哪儿改？
```

---

## 重要说明

- **不要跳过备份**。同路径比对只判断是否改动；未改动文本与改动后仍含假名的文本都需复核。
- 审计器的退出码 `0` 表示执行完成，`1` 表示输入、结构或选项校验失败；都不代表翻译质量结论。
- 用 `--json-out inventory.json` 导出完整候选上下文与路径；文本报告只展示样本。插件参数的可见性需检查实际插件。
- 插件源码、图片、存档和附带文档需分别验收，审计器不声称覆盖这些载体。
- **图片翻译需单独确认**。范围同意后先出 compare，样张确认后再批量处理与回写；不默认改图。
- **本仓库不含任何游戏文本、译文表或术语表**。术语表只提供空模板——每个游戏的译文与术语都是该游戏独有的，不属于本工具。
- 脚本只做"确定性且通用"的部分：遍历、编解码、比对、校验。**翻译内容与可见性判断由 Agent 完成**，不写死在脚本里。

## 验证

```sh
python -B -m unittest discover -s tests -v
```

测试覆盖文本审计和编解码回归，不能代替图片 compare 确认及实机视觉验收。
参阅[证据与验收边界](references/validation.md)。

## License

MIT
