# 史衡 · 五链决策模型

[![CI](https://github.com/shuaifeng-889/shiheng-decision/actions/workflows/ci.yml/badge.svg)](https://github.com/shuaifeng-889/shiheng-decision/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.10%20%7C%203.12%20%7C%203.13-blue)](https://github.com/shuaifeng-889/shiheng-decision)
[![License](https://img.shields.io/badge/license-MIT%20%2B%20CC%20BY--NC--SA%204.0-green)](LICENSE)

**把博弈论当骨架，把正史当案例库，给现实决策一套可证伪的结构化推理。**

不是"孙子兵法读后感"。是一套能跑、能测、能被推翻的决策工具。

```bash
git clone https://github.com/shuaifeng-889/shiheng-decision.git ~/.workbuddy/skills/shiheng-decision
cd ~/.workbuddy/skills/shiheng-decision
python scripts/cli.py decide --interactive
```

零依赖、零配置、纯标准库。Python 3.8+ 即可。

---

## 为什么做这个

市面上的「兵法 × 谋略」类内容，几乎都栽在两个坑里：

**一、把演义当史实。** 诸葛亮空城计（裴松之早已辨其妄）、蒋干盗书、献西施、打黄盖——这些最广为流传的"史例"，正史里都没有。拿虚构情节当决策依据，等于用错误的训练集调参。

**二、只讲成功，不讲失效。** "背水一战"被引用了两千年，但没人告诉你陈馀如果按李左车之计先断韩信粮道，背水就是全军覆没。任何策略都有它的失效条件，不写失效条件的策略库是有毒的。

这个项目针对这两点做了三个强制设计：

| 设计 | 做法 | 效果 |
|---|---|---|
| **史料分级** | 每条案例标注 T1 正史确载 / T2 源流有瑕 / T3 小说敷衍。**T3 禁止作为决策依据** | 64 条案例 100% 为 T1，全部有结构化出处（书名/篇目/是否正史） |
| **失效条件优先** | 每条史案强制 `failure_if`，每计强制 `failure_conditions`。**若失效条件当下已成立，再高的匹配度也作废** | 决策前先自证"这一计在你这儿其实不能用" |
| **影子谏官** | 专设一环反驳前面的推荐，把负反馈制度化 | 灵感来自 C019 袁绍杀田丰——处理掉报坏消息的人，等于销毁组织的纠错能力 |

---

## 它长什么样

```
========================================================================
处境：实力=weak 赌注=high 可逆=0.30 视野=repeated 余量=low
========================================================================
博弈结构：囚徒困境（PRISONERS_DILEMMA）
  结构    ：T>R>P>S：个体理性导致集体最差。破局点在改变对方收益或通过重复
            博弈引入未来阴影，而非指望对方觉悟。
  孙子对照：伐谋 / 伐交：《谋攻篇》「必以全争于天下」，改写对方收益结构
            优于直接对抗
  失效模式：误判为单次博弈而施诱导，实则对方具备长期记忆，造成信誉锚定反噬。
  收益序  ：R=5 T=8 S=1 P=2（对称）
  纯策略均衡：[(1, 1)]
  重复博弈：δ=0.55，δ*=0.50，可持续
            δ=0.55 ≥ δ*=0.50，长期关系足以抑制背叛。

史案 Top-5：
  1. [C030] 郭子仪单骑退回纥·诚信号的极限使用（相似度 91%，T1）
  2. [C040] 岳飞郾城大捷与十二金牌（相似度 86%，T1）
  3. [C044] 石敬瑭割燕云·儿皇帝（反面基准，相似度 85%，T1）
  4. [C037] 澶渊之盟·寇准促真宗亲征（相似度 84%，T1）
  5. [C031] 于谦北京保卫战·主战不迁都（相似度 83%，T1）

策略排序：
  1. 借刀杀人   综合 0.566（处境 0.78 / 博弈 0.85 / 风险 -0.00）  <-- 首推
  2. 借尸还魂   综合 0.477（处境 0.89 / 博弈 0.30 / 风险 -0.00）
  ...
```

完整报告还会输出：每条史案的决策点/行动/结果/**迁移**/**反事实**/**失效条件**、首推策略的**前提/失效/红线**三件套、**影子谏官**诤言、**执行前三项自检**。

---

## 五层链

```
L0 ENCODE    处境编码   现实处境 ──→ 12 维处境向量 SV
L1 RETRIEVE  史案检索   SV ──→ 加权结构化相似度 ──→ Top-5 史案 / 六计候选
L2 VERIFY    博弈校验   局面 ──→ 9 类博弈原型 ──→ 纳什 / Stackelberg / 信号 / 重复 / Shapley
L3 MAP       兵计映射   三十六计 × 适用前提 × 失效条件 × 红线
L4 ARBITER   裁决输出   策略排序 + 影子谏官 + 执行前三项自检
```

**12 维处境向量**（`power_ratio` / `stakes` / `reversibility` / `info_asym` / `time_pressure` / `horizon` / `actors` / `third_party` / `resource_slack` / `opponent_rationality` / `moral_constraint`）。

其中四个是决定性的，必须明确：`power_ratio`（谈崩了谁先扛不住）、`stakes`（最坏是亏钱还是没有以后）、`horizon`（五年后还在同一圈子吗）、`reversibility`（后悔时撤销代价多大）。

**打分公式完全透明：**

```
score = 0.45 × 处境相似度 + 0.25 × 博弈契合度 − 0.30 × 风险折扣
```

---

## 三种用法

### 1. 命令行（不需要任何 Agent）

```bash
python scripts/cli.py decide --interactive          # 交互式录入，出完整报告
python scripts/cli.py decide -i sv.json -f brief    # 从文件读，只要结论
python scripts/cli.py cases --search 粮道            # 检索史案
python scripts/cli.py cases --show C037             # 看单条史案全文
python scripts/cli.py stratagem --show S19          # 看单计的前提/失效/红线
python scripts/cli.py template                      # 拿一个处境向量模板
python scripts/cli.py archetypes                    # 九类原型 + 权重表
python scripts/cli.py validate                      # 数据完整性自检
```

### 2. Python API

```python
import sys; sys.path.insert(0, "scripts")
from engine import ShihengEngine, render

eng = ShihengEngine(data_dir="data")
sv = {
    "power_ratio": "weak", "stakes": "high", "reversibility": 0.3,
    "info_asym": -0.2, "time_pressure": "high", "horizon": "repeated",
    "actors": 3, "third_party": True, "resource_slack": "low",
    "opponent_rationality": "rational", "moral_constraint": "high",
}
# 可选：传入 2x2 收益矩阵做严格博弈体检
A = [[5, 1], [8, 2]]
B = [[5, 8], [1, 2]]
print(render(eng.decide(sv, payoffs=(A, B), delta=0.55, moral_floor="high")))
```

### 3. 作为 Agent Skill

`SKILL.md` 是给 AI Agent 读的执行协议。把整个目录放进 skills 目录即可：

```bash
# WorkBuddy / Claude Code 等遵循 SKILL.md 约定
git clone https://github.com/shuaifeng-889/shiheng-decision.git ~/.workbuddy/skills/shiheng-decision
```

Agent 会按五层链逐层推进，用 `scripts/engine.py` 做检索与求解，再负责把结果翻译成人话。

---

## 快速验证

```bash
python scripts/cli.py validate        # 数据完整性（13 项断言）
python tests/test_nash_core.py        # 求解内核（37 项，全部对照解析真值）
python tests/test_discrimination.py   # 判别力（10 项）
python tests/test_cli.py              # 命令行端到端（57 项）
```

判别力测试是最关键的一组：它要求三个结构迥异的场景必须推出**三条不同策略**，防止模型退化成"什么场景都推荐同一计"。

```
囚徒困境场景 → 借刀杀人
死锁场景     → 趁火打劫
猎鹿场景     → 指桑骂槐
```

---

## 内容规模

- **64 条史决策节点**，全部 T1 正史确载，覆盖春秋至明
  ——**定位为离线兜底的精简样本，非权威史源**；历史部分以《史记》《资治通鉴》二十四史
  **原文检索为主通道**（`build_history_queries` 按处境结构检索 + `validate_history_source` 定级）
- **二十四史覆盖 22/24**（暂缺《南齐书》《北史》）
- 每条含结构化出处（`sources`：书名／篇目／是否正史／类别）、决策点、行动、结果、迁移、**反事实**、**失效条件**
- **三十六计全谱**，每计含：博弈原型、处境适配向量、史案引用、现代迁移、失效条件、红线、破法
- **9 类博弈原型**：囚徒困境、斗鸡、猎鹿、智猪、死锁、信号、序贯、重复、联盟
- **45 条兵书原文判据**（孙子/吴子/六韬/三略/尉缭子/司马法/问对/孙膑/三十六计）＋ **34 个博弈模型**，已接入三层检索
- **166 项自动化断言**（含案例库覆盖面审计、三层检索判别力与正史检索定级）

关于刻意留白：`S31 美人计` 与 `S34 苦肉计` 的经典案例（献西施、打黄盖）都出自小说层，正史无载，因此这两计的 `case_ids` **刻意置空**并附 `evidence_warning`。宁可留白，不为凑数牺牲准确性。

---

## 教程

| 篇目 | 内容 |
|---|---|
| [01 安装与验证](tutorial/01-install.md) | 三种安装方式，5 分钟确认环境可用 |
| [02 五分钟上手](tutorial/02-quickstart.md) | 从一句处境描述到一份完整报告 |
| [03 处境编码怎么填](tutorial/03-encoding.md) | 12 维逐个讲透，含最常见的四个误判陷阱 |
| [04 读懂报告](tutorial/04-reading-report.md) | 五层链逐层解读，哪些能信、哪些要打问号 |
| [05 扩展案例库](tutorial/05-adding-cases.md) | 加一条史案的全流程，含史料核验与防退化 |
| [06 标定权重与接入 Agent](tutorial/06-weighting-and-agent.md) | 改权重、做领域特化、写成自己的 Skill |

---

## 目录

```
SKILL.md                      Agent 执行协议（五层链 + 五条核心纪律）
README.md                     本文件
scripts/
  cli.py                      命令行入口（零依赖）
  engine.py                   五层链主控：编码 / 三层检索调度 / 裁决 / 渲染
  engine_common.py            处境编码与距离的共享实现（单一来源）
  retriever.py                三层检索器：判据检索 + 机制检索 + 联网查询构造
  nash_core.py                L2 求解内核（纳什 / Stackelberg / 信号 / 重复 / Shapley）
data/
  cases.json                  64 条史决策案例（全部 T1）
  stratagems.json             三十六计全谱
  corpus_bing.json            45 条兵书原文判据（已接入检索）
  game_models.json            34 个博弈模型（已接入检索）
references/
  01-situation-encoding.md    12 维处境向量字典与提问话术
  02-anti-patterns.md         史料陷阱与类比失真防呆手册
tests/
  test_nash_core.py           求解内核（37 项）
  test_discrimination.py      判别力（10 项）
  test_corpus.py              语料库防退化（13 项）
  test_cli.py                 命令行端到端（57 项）
  test_coverage.py            覆盖面审计（13 项）
  test_retriever.py           三层检索判别力（23 项）
```

---

## 已知局限（请先读这一节再决定要不要信它）

这个项目**不声称能算出最优解**。理由不是谦虚，是数学：

1. **复旦 CCDA（唐世平）的论证**：《孙子兵法》所处理的是「非常规博弈」（ill-defined game），**不存在完整的数学均衡解**。因此本项目采用「结构化类比 + 局部形式化验证」的混合路线。L2 只在能给出 2×2 收益矩阵时做严格求解，其余情况是**由处境反推原型**，性质是类比，不是求解。

2. **相似度权重是先验设定**，不是从数据学习得到的。`WEIGHTS` 里的数字是设计判断，不同场景应重新标定（见 [教程 06](tutorial/06-weighting-and-agent.md)）。

3. **时代错置风险**。战国之君不是 CEO，古代臣僚不是职业经理人。制度背景差异会造成类比失真。`references/02-anti-patterns.md` 系统列了六类失真。

4. **不是全史覆盖，且存在结构性偏斜**。64 条案例、22/24 部正史；
   其中 45 条是 existential 赌注（正史只记录国家级存亡决策，日常尺度不留痕）。
   命中率低时应如实说明，不要硬套——SKILL.md 的「史案匹配度」机制就是为此设计。

5. **它是计算器，不是参谋**。最值钱的部分——追问你"真正的目标函数是哪一个"、指出你的偏好排序可能只是"最容易启动的那个"——依赖使用者的自我诚实。工具不能替代这个。

---

## 贡献

欢迎补充史案、修正史实、新增领域标定。**但史料标准不放宽**：新增案例必须是 T1（正史确载），必须有结构化出处、原文引文、反事实与失效条件。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

提交前请跑：

```bash
python scripts/cli.py validate
python tests/test_nash_core.py && python tests/test_discrimination.py && python tests/test_cli.py
```

---

## 引用

如果这个模型对你的研究或写作有帮助：

```
史衡·五链决策模型（SHIHENG Five-Chain Decision Model）, v1.0.
https://github.com/shuaifeng-889/shiheng-decision
```

## 许可

代码 MIT，数据（`data/`、`references/`、`tutorial/`）CC BY 4.0。史书原文属公有领域，本项目的整理、分级与结构化标注为原创贡献。
