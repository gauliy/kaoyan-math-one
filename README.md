# 考研数学一学习助手

`kaoyan-math-one` 是一个 Codex 学习 skill，用于拍题答疑、草稿分析、错题整理、薄弱点追踪、解题经验卡、间隔复测，以及每日和阶段复盘。教学与记录均使用中文。

## 学习方式

- 从你的最后一个正确步骤继续，重点解释卡点、方法识别信号和适用条件。
- 默认完整讲解；说“先提示”时逐级提示。
- 基于真实作答记录已表现的能力与待检查问题，区分看懂、提示后完成与独立完成。
- 为典型题提炼识别信号、关键动作、适用条件、个人易错点和回忆问题。
- 根据历史表现安排原题重做、变式与混合复测；先给题，提交后再解析。
- 学习结束时回顾当天的知识、技巧、卡点和下一步。

## 安装

需要 Codex 的本地技能支持；记录脚本需要 Python 3.9 或更高版本，仅依赖标准库。

将仓库克隆到 Codex 用户技能目录。默认目录为 `~/.codex/skills/`；自定义了 `CODEX_HOME` 时使用该目录下的 `skills/`。

```sh
git clone https://github.com/gauliy/kaoyan-math-one.git ~/.codex/skills/kaoyan-math-one
```

Windows PowerShell：

```powershell
git clone https://github.com/gauliy/kaoyan-math-one.git "$env:USERPROFILE/.codex/skills/kaoyan-math-one"
```

私有仓库需要你的 GitHub 账号具备访问权限。目标目录已存在时先检查现有安装，避免覆盖个人修改。安装后开启新会话，在技能列表选择，或使用 `$kaoyan-math-one` 明确调用。

## 首次建立学习档案

首次正式学习由助手初始化，也可以手动运行。Windows 示例：

```powershell
py -3 -X utf8 "$env:USERPROFILE/.codex/skills/kaoyan-math-one/scripts/learning_store.py" init --set-default
py -3 -X utf8 "$env:USERPROFILE/.codex/skills/kaoyan-math-one/scripts/learning_store.py" status
```

默认学习目录是 `~/Documents/Codex/math-one-learning`，设置文件是 `${CODEX_HOME 或 ~/.codex}/kaoyan-math-one-settings.json`。自定义目录用 `--root <目录> init --set-default`。数据保存在 SQLite 中，保留历史版本，并生成中文 Markdown 视图。备份时保存完整学习目录和设置文件。

本仓库只包含技能规则和记录工具，不包含个人学习档案、照片、旧对话或已完成的练习。下载仓库不会同步个人进度；手机上传 ZIP 也不等于安装本地技能或获得本机文件权限。复盘由学习对话触发，不自动安排后台提醒。

## 使用示例

- “第12题不会，这是我的草稿，从我卡住的地方继续讲。”
- “先给我提示，让我自己做。”
- “今天学完了，帮我复盘，并列出需要记住的经验卡。”
- “根据最近反复出现的问题，出三道复测题，先别给答案。”
- “这条诊断不对，重新核对我的原始作答并修正记录。”

## 文件

- `SKILL.md`：技能入口与核心规则。
- `agents/openai.yaml`：中文界面信息。
- `references/`：教学、训练复盘、历史迁移与记录协议。
- `scripts/learning_store.py`：本地学习档案读写、历史版本和可读视图。

脚本结构检查可运行 `python scripts/learning_store.py --help`；档案完整性检查使用 `python scripts/learning_store.py check`，仅在档案已初始化后执行。`check` 检查数据结构与引用，数学推导仍需辅导时核实。
