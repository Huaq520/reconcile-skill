# Reconcile（重归于好）

> An agent skill for rehearsing the conversation you're afraid to have.
> 一个把聊天记录变成「排练室」的 skill：复刻对方的语气，陪你把最难的那句话练到不发抖。

- **English name / repo:** `reconcile`（建议仓库名 `reconcile-skill`）
- **中文名:** 重归于好-skill
- **Skill id:** `reconcile`（kebab-case，符合 agent skill 规范）
- **类型:** 纯本地 skill：Markdown 指令 + Python 标准库脚本，无外部依赖

---

## What it does

| Mode | 说明 |
|---|---|
| **排练 Rehearse** | 用聊天记录复刻 TA 的句长、标点、口头禅和反应模式；你说一句，它用 TA 的语气回，并给一行「想法 / 提示」 |
| **点评 Coach** | 随时切换出戏：哪句有效、哪句踩雷、下一句怎么改 |
| **复盘 Review** | 回到整段关系：时间线、矛盾类型、可修复性、双方视角 |

试错是核心：`重来`、`存档/读档`、`换个走向`、`关提示`、`结束`，重来不扣分。

## Quick start

```bash
# 1) 把记录整理成统一 JSONL（QQ txt / 微信 CSV / 粘贴）
python3 scripts/normalize.py chat.txt -o chat.jsonl --me 我的昵称

# 2) 抽取语气指纹，生成人设卡草稿
python3 scripts/persona.py chat.jsonl --name 阿澈 -o persona-draft.md

# 3) 按 references/persona-sheet.md 补全人设卡，存到 .reconcile/persona.md

# 4) 记录处境（A 刚吵完 / B 冷战 / C 分手想复合 / D 断联 / E 修复中）
python3 scripts/state.py init --persona .reconcile/persona.md --stage C --goal "让她愿意回我一句"
```

然后在对话里说「开始排练」，或直接说你想练的那句话。

## Install

把本目录放到 agent 的 skill 搜索路径下：

```bash
# 项目级
<project>/.agents/skills/reconcile/
# 或用户级
~/.agents/skills/reconcile/
```

支持的运行时：任何读取 `SKILL.md` + YAML frontmatter 的 agent（dsh、Claude Code 等）。
脚本只依赖 Python 3.9+ 标准库。

## Structure

```
reconcile/
├── SKILL.md                     # 主流程：先问处境 → 建人设 → 排练 → 点评/复盘
├── references/
│   ├── roleplay.md              # 反应引擎、温度规则、试错机制、失败模式
│   ├── persona-sheet.md         # 人设卡模板
│   ├── framework.md             # 六阶段复盘
│   ├── scripts-library.md       # 道歉 / 邀约 / 边界 / 告别
│   ├── safety.md                # 红线与危机应对
│   └── platform-import.md       # QQ / 微信 导出与隐私
└── scripts/
    ├── normalize.py             # 任意导出 → 统一 JSONL
    ├── persona.py               # 语气统计 + 典型台词
    ├── state.py                 # 存档 / 读档 / 温度
    └── stats.py                 # 消息量、延迟、主动性
```

## Design notes

- **只分析用户主动提供的材料**；不抓取、不解密、不上传。
- 对方想法以「假设 + 证据 + 置信度」给出，不读心、不承诺复合。
- 不生成 PUA / 煤气灯 / 冷暴力话术；暴力、跟踪、威胁、未成年、对方明确拒绝 → 停止排练。
- 模拟不是本人：排练不能替代真实对话。

## Before publishing

- [ ] 选一个 LICENSE（MIT / Apache-2.0）
- [ ] 补 1–2 个脱敏示例（`examples/`）
- [ ] 录一段 10s demo（可选）
- [ ] 确认仓库里没有真实聊天记录

## License

未指定。上传前请自行添加 LICENSE 文件。
