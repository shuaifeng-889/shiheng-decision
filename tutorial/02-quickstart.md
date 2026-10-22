# 02 · 五分钟上手

**目标**：从一句大白话的处境描述，走到一份完整报告。

---

## 先理解一件事

这个模型**不预测未来，也不给你标准答案**。它做三件事：

1. 把这个局面里**真正决定胜负的那几个变量**挑出来（多数人一开始抓错了）
2. 找出**历史上结构相同的先例**，看当时的结构、选项、后果
3. 检查**你中意的那个办法，失效条件会不会已经在你身上发生了**

所以用法不是"输入问题、索取答案"，而是"输入结构、获取对照"。

---

## 方法 A：交互式（第一次用推荐这个）

```bash
python scripts/cli.py decide --interactive
```

它会问你 11 个问题。每个都给默认值，**不知道怎么填就直接回车**：

```
power_ratio        相对实力（悬殊弱/弱/相当/强/绝对优势） [相当]：
stakes             赌注多大（很低/一般/大/生死存亡） [一般]：
reversibility      可逆性 0..1，做错了能撤回多少 [0.5]：
info_asym          信息优势 -1..1（负数=对方比你更懂内情） [0]：
time_pressure      时间压力（充裕/一般/紧迫） [一般]：
horizon            这事之后还要跟对方打交道吗（一次性/长期共处） [长期共处]：
actors             涉及几方（2 / 3） [2]：
third_party        有没有第三方（裁判、盟友、观众）y/n [n]：
resource_slack     你的资源余量（紧张/一般/充裕） [一般]：
opponent_rationality 对手类型（短视/理性/记仇） [理性]：
moral_constraint   道德约束强度（低/中/高） [中]：
```

填完会先回显一遍编码结果，然后直接出完整报告。

> **别急着按默认值走完全程。** 四个带 `<-- 决定性` 标记的维度
> （`power_ratio` / `stakes` / `horizon` / `reversibility`）如果填错，
> 后面的推荐方向就整体歪了。它们怎么判断见 [教程 03](03-encoding.md)。

---

## 方法 B：从文件读（适合反复调参）

先拿一个模板：

```bash
python scripts/cli.py template > my_situation.json
```

模板长这样（`_comment` 和 `_notes` 是给你看的，引擎会忽略以 `_` 开头的键）：

```json
{
  "power_ratio": "even",
  "stakes": "medium",
  "reversibility": 0.5,
  "info_asym": 0.0,
  "time_pressure": "medium",
  "horizon": "repeated",
  "actors": 3,
  "third_party": true,
  "resource_slack": "medium",
  "opponent_rationality": "rational",
  "moral_constraint": "medium"
}
```

改完之后跑：

```bash
python scripts/cli.py decide -i my_situation.json            # 完整报告
python scripts/cli.py decide -i my_situation.json -f brief   # 只要结论
```

---

## 一个完整的例子

假设处境是：**你是乙方小团队，甲方坚持要你们先交完整方案再谈价格；你判断这可能是
拿了方案找别人做。**

第 1 步，编码。**不要想"我希望是什么"，只想"事实上是什么"**：

```json
{
  "power_ratio": "weak",
  "stakes": "high",
  "reversibility": 0.3,
  "info_asym": -0.2,
  "time_pressure": "high",
  "horizon": "repeated",
  "actors": 3,
  "third_party": true,
  "resource_slack": "low",
  "opponent_rationality": "rational",
  "moral_constraint": "high"
}
```

每一条的理由：

| 维度 | 取值 | 理由 |
|---|---|---|
| `power_ratio` | weak | 谈崩了是你没生意，不是他没供应商 |
| `stakes` | high | 方案交出去等于把核心资产交出去，影响后面几年 |
| `reversibility` | 0.3 | 方案一旦交付基本收不回，但还没签排他条款 |
| `info_asym` | -0.2 | 你知道自己方案的细节，但不知道对方同时在谈几家 |
| `horizon` | repeated | 同一行业，以后还会碰到 |
| `actors` | 3 | 你、甲方、可能存在的第三方供应商 |
| `resource_slack` | low | 小团队，经不起白做一轮 |

第 2 步，跑：

```bash
python scripts/cli.py decide -i my_situation.json -f brief
```

第 3 步，看输出。会得到类似：

```
博弈结构：囚徒困境 / 序贯博弈（取决于是否给矩阵）
史案 Top-5：
  1. [C030] 郭子仪单骑退回纥·诚信号的极限使用
  2. [C044] 石敬瑭割燕云·儿皇帝（反面基准）
  ...
策略排序：
  1. 借刀杀人  ...
  2. 借尸还魂  ...
```

第 4 步（关键），**去看首推策略的失效条件**：

```bash
python scripts/cli.py stratagem --show S03
```

会打出这一计的**适用前提 / 失效条件 / 红线**。如果失效条件里有一条已经在你身上成立，
这一计就作废，不管它综合分多高。这是整个模型最反常识、也最有用的一条纪律。

---

## 想更严格：给它收益矩阵

如果你能判断出四种结局的**相对好坏**，就能从"类比"升级到"求解"：

```bash
cat > matrix.json <<'EOF'
{
  "A": [[5, 1], [8, 2]],
  "B": [[5, 8], [1, 2]]
}
EOF

python scripts/cli.py decide -i my_situation.json -m matrix.json --delta 0.55 -f brief
```

矩阵怎么填：

- `A` = 对方（行）的收益，`B` = 你（列）的收益
- `A[0][0]` = 双方都合作时对方的收益；`A[1][0]` = 对方背叛、你合作时对方的收益
- 数字只表示**相对大小**，不必是真实金额。重要的是顺序
- `--delta` 是重复博弈折现因子：你觉得"未来还重要"的程度，0.9 = 非常看重长期关系

这次输出会多出几行真正的数学结论：

```
  收益序  ：R=5 T=8 S=1 P=2（对称）
  纯策略均衡：[(1, 1)]
  重复博弈：δ=0.55，δ*=0.50，可持续
            δ=0.55 ≥ δ*=0.50，长期关系足以抑制背叛。
```

**`δ*` 是这个模型里最值钱的数字之一**：它是"维持合作所需的最低耐心"。你的 `δ` 高于它，
长期合作就是稳定的；低于它，背叛在数学上就是理性的——跟你人品无关。

---

## 三种输出格式怎么选

| 格式 | 命令 | 用途 |
|---|---|---|
| `md`（默认） | `-f md` | 完整报告，六节结构，给人读 |
| `brief` | `-f brief` | 只要结论，调参时反复跑 |
| `json` | `-f json` | 喂给别的程序，字段稳定 |

---

## 接下来

- 编码填不准 → [03 处境编码怎么填](03-encoding.md)（**这一篇最重要**）
- 报告看不懂 → [04 读懂报告](04-reading-report.md)
- 想加史案 → [05 扩展案例库](05-adding-cases.md)
- 想改权重或做成自己的 Skill → [06 标定权重与接入 Agent](06-weighting-and-agent.md)
