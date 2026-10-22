# 01 · 安装与验证

**目标**：5 分钟内让 `python scripts/cli.py` 跑通，并确认数据完整。

---

## 前置要求

只有一个：**Python 3.8 或更高**。

不需要 pip install，不需要虚拟环境，不需要联网。整个项目只用了标准库
（`json` / `os` / `sys` / `argparse` / `dataclasses` / `itertools` / `typing`）。

```bash
python --version     # Windows 上可能是 python3 或 py
```

如果 `python` 命令不存在，试 `python3 --version` 或 `py --version`。

---

## 方式一：装成 Agent Skill（推荐）

如果你在用支持 `SKILL.md` 约定的 Agent（WorkBuddy、Claude Code 等）：

```bash
git clone https://github.com/shuaifeng-889/shiheng-decision.git ~/.workbuddy/skills/shiheng-decision
```

Windows PowerShell：

```powershell
git clone https://github.com/shuaifeng-889/shiheng-decision.git "$env:USERPROFILE\.workbuddy\skills\shiheng-decision"
```

装完之后，你在对话里提出一个**含对抗或取舍**的问题，Agent 就会自动加载 `SKILL.md`
并按五层链执行。触发词包括：两难、取舍、谈判、竞争、跳槽、组织人事、重大投入，
或者你直接提到史书典故 / 兵法 / 博弈论 / 决策分析。

> Agent 读 `SKILL.md`，人敲 `cli.py`，两者共用 `scripts/engine.py`——所以不会出现
> "Agent 给的结论和命令行跑出来的不一样"这种漂移。

---

## 方式二：当普通项目用（不装 Skill）

只想在终端里跑：

```bash
git clone https://github.com/shuaifeng-889/shiheng-decision.git shiheng-decision
cd shiheng-decision
python scripts/cli.py decide --interactive
```

就这样，没有第二步。

---

## 方式三：不想每次敲长路径

做个别名。Linux / macOS 写进 `~/.bashrc` 或 `~/.zshrc`：

```bash
alias shiheng='python /absolute/path/to/shiheng-decision/scripts/cli.py'
```

之后：

```bash
shiheng decide --interactive
shiheng cases --search 粮道
```

Windows 可以在项目根目录放一个 `shiheng.bat`：

```bat
@echo off
python "%~dp0scripts\cli.py" %*
```

---

## 验证安装

跑两步。第一步确认代码和路径都对：

```bash
python scripts/cli.py validate
```

正常输出结尾应该是：

```
==============================================================
  PASS=13  FAIL=0   案例 50 条 / 兵计 36 条 / 二十四史 22/24
==============================================================
```

第二步确认端到端能出报告：

```bash
python scripts/cli.py decide -i examples/01-negotiation.json -m examples/01-negotiation.matrix.json --delta 0.55 -f brief
```

应该看到「博弈结构：囚徒困境」「史案 Top-5」「策略排序」三段。

### 想更彻底一点

跑全部四个测试套件（117 项断言）：

```bash
python tests/test_nash_core.py
python tests/test_discrimination.py
python tests/test_corpus.py
python tests/test_cli.py
```

四个都应该是 `FAIL=0`。如果哪个挂了，说明环境有问题，别急着用结论。

---

## 常见问题

**Q：`python` 不是内部或外部命令**

Windows 上 Python 可能只注册了 `py` 或 `python3`。用 `py scripts/cli.py validate` 试。

**Q：输出中文是乱码**

`cli.py` 已经强制把 stdout 重配为 UTF-8。如果还乱码，说明终端本身是 GBK 代码页：

```bash
chcp 65001        # Windows CMD，临时切到 UTF-8
```

PowerShell 里则可以：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
```

**Q：`validate` 报找不到 `tests/test_corpus.py`**

说明目录结构被改动过。确认 `tests/` 和 `scripts/` 是同级目录，且都在项目根下。

**Q：能 pip install 吗？**

不需要。这是有意的设计——Skill 的本质是**目录结构**，pip 装到 site-packages 反而会让
`data/` 的相对路径失效。如果你要在自己代码里用，把项目目录放进 `sys.path` 即可：

```python
import sys
sys.path.insert(0, "/path/to/shiheng-decision/scripts")
from engine import ShihengEngine
```

---

**下一步** → [02 五分钟上手](02-quickstart.md)
