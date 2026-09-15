# rpgmaker-mz-translation

给 AI Agent 用的 **RPG Maker MV/MZ 游戏汉化技能包**。它把"游戏文本在哪、统一去哪改、怎么安全地批量替换、翻完怎么验收、发布前怎么清干净"整理成一套可执行的流程 + 脚本。

遵循 [Agent Skills 开放标准](https://agentskills.io/)，`SKILL.md` 单文件即全部必需内容，任何兼容该标准的 Agent 客户端都能直接加载。

---

## 它解决什么

RPG Maker 游戏的文本**不在一个地方**——这是汉化最容易踩的坑。实际分布在五类载体：

| 载体 | 内容 |
|---|---|
| `data/*.json` | 剧情对话、选项、插件指令、数据库名称与描述（**量最大**） |
| `js/plugins.js` | 插件参数（值是**嵌套 JSON 字符串**，要递归穿透） |
| `js/plugins/*.js` | 插件源码里硬编码的界面文字 |
| `img/*.png_` | 加密图片上烤进去的字 |
| `save/*.rmmzsave` | 存档里冻结的旧文本 |

其中 `data/` 内部还要按**事件指令码**区分（`401/405` 对话、`102` 选项、`402` 分支、`657` 插件指令、`108/408` 注释…），并且要跳过标识符、`note` 元数据、资源名——否则一译就坏功能。

本技能把这些全部写成可查的**文本地图**，并把确定性的部分（遍历、编解码、审计）做成脚本，判断性的部分（翻什么、哪些可见、术语怎么定）留给 Agent。

---

## 安装

本包是标准 Agent Skills 目录，安装 = 把它放进你所用的 Agent 的技能目录。

| 客户端 | 放这里 |
|---|---|
| **WorkBuddy** | `%USERPROFILE%\.workbuddy\skills\rpgmaker-mz-translation\` |
| Claude Code | `~/.claude/skills/rpgmaker-mz-translation/` |
| 其他兼容 Agent Skills 的客户端 | 见各自文档的技能目录 |

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
│   ├── pitfalls.md                 # 通用踩坑清单
│   ├── lang-pair-ja-zh.md          # 日→中 专属：注音、纯汉字日文词、字体
│   ├── plugin-param-repair.md      # 插件参数写坏后的修复
│   └── release.md                  # 发布前清理（含"绝不删"清单）
├── scripts/                        # 确定性代码，执行即可，不占上下文
│   ├── audit_visible_jp.py         # 全载体扫描 + 按可见性分类 + 与备份比对
│   ├── fix_plugin_params.py        # 插件参数体检 / 修复
│   ├── verify_plugins_js.js        # 复刻插件参数解析器做只读校验
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

- **不要跳过备份**。所有步骤都依赖"与原始备份逐条比对"来判定漏译，没有备份无法工作。
- **本仓库不含任何游戏文本、译文表或术语表**。术语表只提供空模板——每个游戏的译文与术语都是该游戏独有的，不属于本工具。
- 脚本只做"确定性且通用"的部分：遍历、编解码、比对、校验。**翻译内容与可见性判断由 Agent 完成**，不写死在脚本里。

## License

MIT
