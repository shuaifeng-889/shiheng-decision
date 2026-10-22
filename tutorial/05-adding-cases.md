# 05 · 扩展案例库

**目标**：从零加一条 T1 级史决策案例，并通过全部防退化测试。

---

## 什么时候该加案例

不是"想到一个有趣的典故就加"。该加的信号有三种：

1. **命中率不够**。某个反复出现的处境类型，检索出来的 Top-5 相似度都只有 60% 出头——
   说明库里没有真正对得上的先例，是硬凑的。
2. **原型空缺**。九类博弈原型里，某一类的案例数量明显偏少，导致该类场景的检索质量差。
3. **时代盲区**。现有案例集中在某些朝代，某一时期的决策模式没有覆盖。

**不该加的情况**：只是想多凑几条。案例库的价值在每条的质量，不在数量。
一条用错的案例，比没有这条案例危害更大。

---

## 三条硬标准

### 1. 必须是正史确载（T1）

| 等级 | 定义 | 能否作为决策依据 |
|---|---|---|
| **T1** | 正史确载 | ✅ 可以 |
| **T2** | 早期文献有载但源流有瑕（晚出、史官本人存疑、关键细节仅见别传注引） | ⚠️ 仅作旁证，不可单独承重 |
| **T3** | 小说敷衍（演义系统虚构） | ❌ 禁止 |

**这个库目前 100% 是 T1。** 加 T2/T3 不是不可以，但会拉低整库质量，
而且 `test_corpus.py` 里有一条断言是「全部为 T1 正史确载」，加进去测试就挂了。

### 2. 必须有结构化出处

`source` 是自由文本（给人看），`sources` 是结构化字段（给机器校验）。两个都要填。

```json
"source": "《宋史·寇准传》",
"sources": [{"book": "宋史", "juan": "寇准传", "canonical": true, "category": "正史"}]
```

- `book` 只能是**书名**，不能写成篇名（"寇准传"不是书）
- `canonical` 表示是否属二十四史；《左传》《国语》《资治通鉴》都是 `false`
- `category` 取值：`正史` / `编年` / `经部史书`

### 3. 必须有反事实与失效条件

`counterfactual`（不这么做会怎样）和 `failure_if`（什么情况下这招不灵）是**强制字段**。
缺了它们，这条案例就退化成"成功学故事"，而本项目存在的意义就是反对这个。

---

## 史料核验流程

不要凭记忆写。三步走：

**第一步，找原文。** 两个可靠来源：

- **中国哲学书电子化计划**（ctext.org）：3 万部古籍，但史书部分只到《三国志》
- **维基文库**（zh.wikisource.org）：二十四史全文齐全，含中华书局点校本文字

**第二步，核对篇目。** 最常见的错误是把列传名当书名。写 `《史记·淮阴侯列传》` 是对的，
写成 `book: "淮阴侯列传"` 就错了——`validate` 会把它算成一部不存在的史书，
二十四史覆盖率统计会失真。

**第三步，标注存疑。** 如果关键细节只在注引里（比如裴松之注）、或史官本人已表怀疑
（比如司马迁对某些传闻的处理），如实降级为 T2 并在 `source` 里写明。
**宁可标 T2，不要为了凑 T1 而隐去存疑。**

---

## `sv_tags` 怎么填

这是最需要判断力的一步。**`sv_tags` 不是"这个故事里主角的处境"，而是"这个决策节点上，
决策者面对的结构"。**

以 C003 长勺之战为例：

```json
"sv_tags": {
  "power_ratio": "very_weak",      // 齐强鲁弱，正面会战必不胜
  "stakes": "existential",         // 输了就亡国
  "reversibility": 0.2,            // 会战一旦开始无法中止
  "info_asym": 0.2,                // 曹刿看出齐军锐气可耗，齐方没看出鲁军意图
  "time_pressure": "high",         // 齐师已列阵挑战，不能无限等
  "horizon": "single",             // 这一战打完就结束
  "actors": 2,                     // 鲁、齐
  "third_party": false,            // 无第三方可借力
  "resource_slack": "low",         // 鲁军资源有限，经不起消耗
  "opponent_rationality": "myopic",// 齐军恃强轻敌，三鼓而气衰
  "moral_constraint": "high"       // 春秋战礼约束
}
```

填法要点：

- **站在决策者当时的信息条件下判断**，不用后世才知道的结果
- `horizon` 填这一**战**是一次性还是长期：长勺之战本身是 `single`，
  但齐鲁之间的关系是 `repeated`。填哪个取决于你建模的是哪个决策
- `opponent_rationality` 要基于当时对手的实际表现，不是他的历史评价
- 拿不准的维度填中间值（`medium` / `0.5` / `0`），不要瞎猜极端值

---

## 双向索引：最容易踩的坑

案例和兵计之间是**双向引用**，两边都要改：

1. `cases.json` 里这条案例的 `stratagem` 字段 → 关联的计策编号
2. `stratagems.json` 里对应计策的 `case_ids` 字段 → 加上这条案例编号

**只改一边，`validate` 会挂：**

```
FAIL  兵计->史案 无效引用为 0
FAIL  史案->兵计 无效引用为 0
FAIL  孤立史案为 0（每条都被至少一计引用）
```

第三条最狠：**每条案例必须至少被一计引用**。所以你不能只加案例不加索引。

---

## 完整流程

### 第 1 步：确定编号

看现有最大编号：

```bash
python scripts/cli.py cases | tail -5
```

目前到 C050，新案例用 C051。

### 第 2 步：写案例条目

```json
{
  "id": "C051",
  "title": "某某之战·决策要点",
  "era": "朝代·年号（公元年份）",
  "protagonist": "决策者（阵营） — 对手",
  "source": "《某书·某传》",
  "tier": "T1",
  "archetype": "STACKELBERG",
  "sv_tags": {
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
    "moral_constraint": "medium"
  },
  "situation": "决策者面对的局面，只写客观条件。",
  "decision_point": "他必须回答的那个问题，用问句。",
  "action": "他实际做了什么。",
  "outcome": "结果如何。",
  "lesson": "结构层面的教训——不是'他真聪明'，而是'为什么这个动作在此结构下成立'。这是最重要的一段。",
  "counterfactual": "若他选了另一条路，会怎样。",
  "failure_if": "什么条件下这个策略会失效。",
  "stratagem": ["S19"],
  "sources": [
    {"book": "某书", "juan": "某传", "canonical": true, "category": "正史"}
  ]
}
```

### 第 3 步：插入数据

用脚本插，不要手改大 JSON（容易破坏格式）：

```python
import json

with open("data/cases.json", encoding="utf-8") as f:
    doc = json.load(f)

new_case = { ... }  # 上面那段

ids = {c["id"] for c in doc["cases"]}
assert new_case["id"] not in ids, "编号重复"
doc["cases"].append(new_case)

with open("data/cases.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
```

### 第 4 步：补反向索引

```python
import json

with open("data/stratagems.json", encoding="utf-8") as f:
    doc = json.load(f)

for s in doc["stratagems"]:
    if s["id"] == "S19" and "C051" not in s["case_ids"]:
        s["case_ids"].append("C051")

with open("data/stratagems.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
```

### 第 5 步：验证

```bash
python scripts/cli.py validate
```

必须全绿：

```
  PASS  二十四史覆盖不低于基线                              got=22 (>=22)
  PASS  字段缺失为 0
  PASS  全部为 T1 正史确载
  PASS  sv_tags 维度与 meta 一致
  PASS  兵计->史案 无效引用为 0
  PASS  史案->兵计 无效引用为 0
  PASS  孤立史案为 0（每条都被至少一计引用）
  PASS  三十六计齐全
```

### 第 6 步：跑全套测试

```bash
python tests/test_nash_core.py
python tests/test_discrimination.py
python tests/test_corpus.py
python tests/test_cli.py
```

**特别看 `test_discrimination`。** 它要求三个结构迥异的场景推出三条不同策略。
如果加了案例之后这个测试挂了，说明新案例破坏了判别力——通常是 `sv_tags` 填得太"居中"，
让某条案例在所有场景下都跳出来。

---

## 如果覆盖率提升了

`test_corpus.py` 里有个基线常量：

```python
BASELINE_COVERAGE = 22   # 覆盖只许升不许降
```

如果你补上了《南齐书》或《北史》的案例，覆盖率会变成 23 或 24，
**记得同步改这个常量**，否则以后退化到 22 也不会被发现。

同理，如果你新加的案例让总数变了，README 和 `SKILL.md` 里的"50 条"也要同步更新。

---

## 五个常见错误

| 错误 | 后果 | 怎么避 |
|---|---|---|
| 把篇名当书名 | 覆盖率统计失真 | `book` 只能是书名 |
| 只改单向索引 | `validate` 报孤立史案 | 两边都改 |
| `sv_tags` 填得居中 | 该案例在所有场景都跳出来，破坏判别力 | 按决策节点的真实结构填极端值 |
| `lesson` 写成人物评价 | 失去可迁移性 | 写机制，不写"他很聪明" |
| 没有 `failure_if` | 退化成成功学 | 强制字段，必须填 |

---

**下一步** → [06 标定权重与接入 Agent](06-weighting-and-agent.md)
