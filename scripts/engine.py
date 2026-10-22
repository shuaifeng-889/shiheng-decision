#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
史衡 · 五链决策模型 —— 主控引擎
SHIHENG Five-Chain Decision Model / Orchestrator

五层链在这一个文件里串起来：
    L0 ENCODE    处境编码   自然语言线索 -> 12 维处境向量 SV
    L1 RETRIEVE  史案检索   SV -> 加权结构化相似度 -> Top-K 史案与兵计（CBR 引擎）
    L2 VERIFY    博弈校验   局面 -> 9 类博弈原型 -> 纳什/精炼均衡求解（数学引擎）
    L3 MAP       兵计映射   三十六计 x 失效条件 x 红线
    L4 ARBITER   裁决输出   融合排序 + 影子谏官 + 反事实 + 红灯清单

用法：
    from engine import ShihengEngine
    eng = ShihengEngine()
    report = eng.decide(sv, payoffs=(A, B), delta=0.6)
    print(render(report))

命令行：
    python engine.py --demo          跑内置演示
    python engine.py --selftest      跑引擎自检
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from nash_core import (ARCHETYPES, ARCHETYPE_STRATAGEMS, classify_2x2,
                       diagnose, infer_archetype_from_sv)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


# ---------------------------------------------------------------------------
# L0 处境编码：枚举 -> 序数，便于距离计算
# ---------------------------------------------------------------------------

ORDINAL = {
    "power_ratio": {"very_weak": -2, "weak": -1, "even": 0, "strong": 1, "very_strong": 2},
    "stakes":      {"low": 0, "medium": 1, "high": 2, "existential": 3},
    "time_pressure": {"low": 0, "medium": 1, "high": 2},
    "resource_slack": {"low": 0, "medium": 1, "high": 2},
    "moral_constraint": {"low": 0, "medium": 1, "high": 2},
    "opponent_rationality": {"myopic": 0, "rational": 1, "vindictive": 2},
    "horizon":    {"single": 0, "repeated": 1},
}

# 各维度的判别权重。取值理由写进注释，便于后续按场景重标定。
WEIGHTS = {
    "power_ratio": 3.0,           # 强弱对比决定攻守的基本取向
    "stakes":      2.0,           # 赌注决定可接受的风险敞口
    "reversibility": 2.5,         # 不可逆性决定能否用一次性激烈手段
    "info_asym":   2.0,           # 信息差是所有信号的燃料
    "time_pressure": 1.5,         # 时间压力压制谋略空间
    "horizon":     2.5,           # 单次/重复决定信誉是否计息，影响最大
    "actors":      2.0,           # 参与方数决定是否需要考虑第三方
    "third_party": 1.5,
    "resource_slack": 1.5,        # 冗余决定能否打持久消耗
    "opponent_rationality": 2.0,  # 对手类型决定信号能否被解读
    "moral_constraint": 2.0,      # 红线约束，直接参与风险折扣
}

NUMERIC_RANGE = {"reversibility": (0.0, 1.0), "info_asym": (-1.0, 1.0),
                 "actors": (2.0, 3.0)}
MAX_DIST = sum(WEIGHTS.values())  # 归一化上界（各维最大偏离时的加权和）


def normalize_sv(sv: Dict[str, Any]) -> Dict[str, float]:
    """把混合类型的 SV 统一映射到 [0,1] 区间的可比向量。"""
    out: Dict[str, float] = {}
    for dim, w in WEIGHTS.items():
        v = sv.get(dim)
        if dim in ORDINAL:
            table = ORDINAL[dim]
            lo = min(table.values())
            hi = max(table.values())
            out[dim] = (table[str(v)] - lo) / (hi - lo) if v in table else 0.5
        elif dim == "third_party":
            out[dim] = 1.0 if v else 0.0
        else:
            lo, hi = NUMERIC_RANGE[dim]
            out[dim] = (float(v) - lo) / (hi - lo)
    return out


def sv_distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """加权曼哈顿距离，返回 0..1 的相似度（1 表示完全契合）。"""
    na, nb = normalize_sv(a), normalize_sv(b)
    raw = sum(WEIGHTS[d] * abs(na[d] - nb[d]) for d in WEIGHTS)
    return 1.0 - raw / MAX_DIST


def encode_sv(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    L0 入口：把粗粒度的问答结果转成 SV。

    answers 接受可读字符串，容忍中英混合与自然表述：
        power_ratio        : 悬殊弱/弱/相当/强/绝对优势
        stakeholders n      : 两方/三方及以上
    """
    mapping = {
        "power_ratio": {"悬殊弱": "very_weak", "很弱": "very_weak", "very_weak": "very_weak",
                        "弱": "weak", "weak": "weak", "劣势": "weak",
                        "相当": "even", "均势": "even", "even": "even",
                        "强": "strong", "strong": "strong", "优势": "strong",
                        "绝对优势": "very_strong", "very_strong": "very_strong"},
        "stakes": {"很低": "low", "low": "low", "一般": "medium", "medium": "medium",
                   "大": "high", "high": "high", "生死存亡": "existential",
                   "existential": "existential"},
        "time_pressure": {"充裕": "low", "low": "low", "一般": "medium", "medium": "medium",
                          "紧迫": "high", "high": "high"},
        "resource_slack": {"紧张": "low", "low": "low", "一般": "medium", "medium": "medium",
                           "充裕": "high", "high": "high"},
        "moral_constraint": {"低": "low", "low": "low", "中": "medium", "medium": "medium",
                             "高": "high", "high": "high"},
        "opponent_rationality": {"短视": "myopic", "myopic": "myopic",
                                 "理性": "rational", "rational": "rational",
                                 "记仇": "vindictive", "vindictive": "vindictive"},
        "horizon": {"一次性": "single", "single": "single",
                    "长期共处": "repeated", "repeated": "repeated"},
    }
    sv: Dict[str, Any] = {}
    for dim, table in mapping.items():
        sv[dim] = table.get(str(answers.get(dim, "")), "even" if dim == "power_ratio"
                            else list(table.values())[1])
    sv["reversibility"] = float(answers.get("reversibility", 0.5))
    sv["info_asym"] = float(answers.get("info_asym", 0.0))
    sv["actors"] = 3 if str(answers.get("actors", "2")) in ("3", "3+", "三方") else 2
    sv["third_party"] = bool(answers.get("third_party", False))
    return sv


# ---------------------------------------------------------------------------
# L2 博弈校验的风险折扣
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """一个候选策略：既可以是史案，也可以是兵计。"""
    kind: str                      # 'case' | 'stratagem'
    id: str
    name: str
    similarity: float
    archetype: str
    detail: Dict[str, Any] = field(default_factory=dict)
    game_fit: float = 0.0
    risk_penalty: float = 0.0
    red_flags: List[str] = field(default_factory=list)
    score: float = 0.0

    def as_row(self) -> Tuple[float, str, str]:
        return (self.score, self.kind, self.name)


RISK_KEYWORDS = ("高危", "禁忌", "违法", "欺诈", "侵略", "违约")


def risk_profile(item: Dict[str, Any]) -> Tuple[float, List[str]]:
    """从 redline / evidence_warning / failure_conditions 提取风险等级与标记。"""
    penalty, flags = 0.0, []
    redline = item.get("redline", "") or ""
    warn = item.get("evidence_warning", "") or ""
    if any(k in redline for k in RISK_KEYWORDS):
        penalty += 0.55
        flags.append("红线警告：%s" % redline.split("：")[0].strip("*"))
    if warn:
        penalty += 0.15
        flags.append("史料支撑不足，仅可作旁证")
    return min(penalty, 0.9), flags


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------

class ShihengEngine:
    def __init__(self, data_dir: str = DATA):
        with open(os.path.join(data_dir, "cases.json"), encoding="utf-8") as f:
            self.cases = json.load(f)["cases"]
        with open(os.path.join(data_dir, "stratagems.json"), encoding="utf-8") as f:
            self.stratagems = json.load(f)["stratagems"]
        self.case_by_id = {c["id"]: c for c in self.cases}
        self.strat_by_id = {s["id"]: s for s in self.stratagems}

    # -- L1 检索 ------------------------------------------------------------
    def retrieve_cases(self, sv: Dict[str, Any], top_k: int = 5
                       ) -> List[Candidate]:
        scored = []
        for c in self.cases:
            sim = sv_distance(sv, c["sv_tags"])
            # 正史权重：T1 满权重，T2/T3 依可信度递减
            cred = {"T1": 1.0, "T2": 0.75, "T3": 0.4}.get(c["tier"], 0.5)
            scored.append(Candidate(kind="case", id=c["id"], name=c["title"],
                                    similarity=sim * cred, archetype=c["archetype"],
                                    detail=c))
        scored.sort(key=lambda x: -x.similarity)
        return scored[:top_k]

    def retrieve_stratagems(self, sv: Dict[str, Any], top_k: int = 6
                            ) -> List[Candidate]:
        scored = []
        for s in self.stratagems:
            sim = sv_distance(sv, s["sv_profile"])
            penalty, flags = risk_profile(s)
            cand = Candidate(kind="stratagem", id=s["id"], name=s["name"],
                             similarity=sim, archetype=s["archetype"], detail=s,
                             risk_penalty=penalty, red_flags=flags)
            scored.append(cand)
        scored.sort(key=lambda x: -x.similarity)
        return scored[:top_k]

    # -- L2 校验与融合 ------------------------------------------------------
    def verify(self, payoffs: Optional[Tuple[Sequence[Sequence[float]],
                                             Sequence[Sequence[float]]]],
               delta: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if payoffs is None:
            return None
        A, B = payoffs
        return diagnose(A, B, delta=delta)

    def arbitrate(self, sv: Dict[str, Any], case_top: List[Candidate],
                  stra_top: List[Candidate],
                  game: Optional[Dict[str, Any]],
                  moral_floor: str = "medium") -> List[Candidate]:
        """
        L4 融合裁决。

        打分公式（透明可复现）：
            score = 0.45 * 处境相似度
                  + 0.25 * 博弈原型契合度
                  - 0.30 * 风险折扣
        对超出道德基线的策略追加硬折扣。
        """
        # 无收益矩阵时，用处境反推最可能的原型
        if game:
            target_arch = game["archetype"]["key"]
        else:
            target_arch = infer_archetype_from_sv(sv)
        target_group = set(ARCHETYPE_STRATAGEMS.get(target_arch, []))

        fused: List[Candidate] = []
        for cand in stra_top:
            # 契合度三档：被列入目标原型的参考兵计 > 主原型相同 > 其他
            if cand.id in target_group and cand.archetype == target_arch:
                fit = 1.0
            elif cand.id in target_group:
                fit = 0.85
            elif cand.archetype == target_arch:
                fit = 0.70
            else:
                fit = 0.30
            cand.game_fit = fit
            penalty = cand.risk_penalty
            # 道德基线硬折扣：约束越高，高危计越不可用
            if moral_floor == "high" and penalty >= 0.55:
                penalty = min(0.9, penalty + 0.2)
                cand.red_flags.append("超出你设定的道德/合规基线，本模型不建议采用")
            # 重复博弈环境：一次性失信类策略额外计息
            if sv.get("horizon") == "repeated" and cand.archetype == "SIGNALING":
                penalty = min(0.9, penalty + 0.1)
                cand.red_flags.append("重复博弈环境下，信号类策略失效后会被对方长期记账")
            cand.risk_penalty = penalty
            cand.score = round(0.45 * cand.similarity + 0.25 * fit
                               - 0.30 * penalty, 4)
            fused.append(cand)
        fused.sort(key=lambda c: -c.score)
        return fused

    # -- 影子谏官 -----------------------------------------------------------
    def shadow_advisor(self, sv: Dict[str, Any],
                       ranked: List[Candidate],
                       game: Optional[Dict[str, Any]]) -> List[str]:
        """
        专门挑刺的一环。

        设立理由：C014/C019/C028 三条史案共同指向同一个失败模式——
        不是算力不足，而是决策者身边失去了报坏消息的人。此环节把负反馈制度化。
        """
        notes: List[str] = []
        if sv.get("horizon") == "repeated" and ranked and \
                ranked[0].archetype in ("SIGNALING", "STACKELBERG"):
            notes.append("你与对方是长期关系。首推策略依赖对方不识破，一旦被识破，"
                         "损失的不止这一轮，而是此后所有轮次的信任折价。请确认："
                         "这一轮的收益是否真的值得把它折现掉。")
        if sv.get("stakes") == "existential" and \
                float(sv.get("reversibility", 0.5)) < 0.3 and ranked:
            notes.append("赌注为生死存亡且决策基本不可逆。此类局面下，任何依赖"
                         "「对方会按我预期反应」的策略都应当有一个撤退预案——"
                         "没有预案的孤注一掷，与赌博没有区别。")
        if game and game.get("repeated") and game["repeated"].get("sustainable"):
            notes.append("这是一个可以自持的重复博弈（δ≥δ*）。既然未来阴影足够重，"
                         "你就拥有了单轮牺牲换长期收益的空间——此时最划算的动作往往"
                         "不是赢下这一轮，而是让对方看清你愿意长期合作，从而把他从"
                         "「这一轮必须榨取最大值」的心态里拉出来。")
        if float(sv.get("info_asym", 0)) <= -0.35:
            notes.append("你的处境向量显示信息严重不对称且对你不利（info_asym=%.2f）。"
                         "白登之围（C012）的前提正是如此：十余批使者都报可击，"
                         "唯独一人说不可，而那人被囚。请先回答：你听到过反对意见吗？"
                         "如果从未听到，问题不在敌人的强大，而在你的信息通道。"
                         % sv.get("info_asym", 0))
        if sv.get("moral_constraint") == "low":
            notes.append("你设定的道德/合规约束很低。请注意这不是免费选项："
                         "低约束在短期内扩大策略集，长期会缩小愿意与你合作的对象集合。")
        if sv.get("opponent_rationality") == "vindictive":
            notes.append("对手被判定为记仇型。此类对手不按收益表行事，"
                         "囚徒困境/斗鸡等模型的预测会失真，需以其情绪目标函数重新建模。")
        if game and game.get("stackelberg") and \
                game["stackelberg"].get("commitment_value", 0) > 2:
            notes.append("局面存在显著承诺价值（%.1f）。这意味着先动方能通过自缚获利。"
                         "若你尚未行动，请评估抢先做出不可逆承诺的可行性——"
                         "这正是破釜沉舟的数学来源。"
                         % game["stackelberg"]["commitment_value"])
        if not notes:
            notes.append("未触发结构性风险标记。仍需自问一句："
                         "你有可以当面告诉你「你错了」的人吗？")
        return notes

    # -- 主入口 -------------------------------------------------------------
    def decide(self, sv: Dict[str, Any],
               payoffs: Optional[Tuple[Sequence[Sequence[float]],
                                       Sequence[Sequence[float]]]] = None,
               delta: Optional[float] = None,
               top_k: int = 5, moral_floor: str = "medium") -> Dict[str, Any]:
        cases = self.retrieve_cases(sv, top_k=top_k)
        stratagems = self.retrieve_stratagems(sv, top_k=top_k + 1)
        game = self.verify(payoffs, delta=delta)
        ranked = self.arbitrate(sv, cases, stratagems, game,
                                moral_floor=moral_floor)
        return {
            "sv": sv,
            "game": game,
            "cases": cases,
            "stratagems_ranked": ranked,
            "shadow": self.shadow_advisor(sv, ranked, game),
        }


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

def render(report: Dict[str, Any]) -> str:
    sv, game = report["sv"], report["game"]
    L: List[str] = []
    L.append("# 史衡 · 决策报告\n")

    L.append("## 一、处境向量 (L0 ENCODE)\n")
    for k, v in sv.items():
        L.append("- **%s**：%s" % (k, v))
    L.append("")

    if game:
        a = game["archetype"]
        L.append("## 二、博弈体检 (L2 VERIFY)\n")
        L.append("**原型判定**：%s（%s）\n" % (a["name"], a["name_en"]))
        L.append("- 结构：%s" % a["structural_logic"])
        L.append("- 孙子映射：%s" % a["sunzi_ref"])
        L.append("- 兵计映射：%s" % a["stratagem_ref"])
        L.append("- **典型失效**：%s" % a["failure_mode"])
        p = game["payoffs"]
        L.append("- 收益参数：R=%.1f T=%.1f S=%.1f P=%.1f" %
                 (p["R"], p["T"], p["S"], p["P"]))
        L.append("- 纯策略均衡：%s" % game["pure_nash"])
        if game["mixed_nash"]:
            m = game["mixed_nash"]
            L.append("- 混合均衡：我方 %.0f%% / 对方 %.0f%%" %
                     (m["p_row0"] * 100, m["q_col0"] * 100))
        st = game["stackelberg"]
        L.append("- 先动溢价：%s｜承诺价值：%.1f" %
                 (st["first_mover_premium_row"], st["commitment_value"]))
        if game["repeated"]:
            L.append("- %s" % game["repeated"]["reason"])
        L.append("")
    else:
        # 未提供收益矩阵时仍保留本节，说明降级方式，避免报告编号断档
        L.append("## 二、博弈体检 (L2 VERIFY)\n")
        L.append("**未提供收益矩阵**，本节降级为「由处境反推原型」，性质是类比而非求解。\n")
        L.append("- 推断原型：%s" % infer_archetype_from_sv(sv))
        L.append("- 若要得到严格结论（纳什均衡 / 先动溢价 / 承诺价值 / 临界折现因子），"
                 "请用 `-m` 传入 2x2 收益矩阵")
        L.append("- 缺少矩阵时，下方的策略排序中「博弈契合度」一项按原型近似计，"
                 "**可信度低于有矩阵的情形**")
        L.append("")

    L.append("## 三、史案对标 (L1 RETRIEVE)\n")
    for i, c in enumerate(report["cases"], 1):
        d = c.detail
        L.append("### %d. %s  （相似度 %.0f%%，%s）" %
                 (i, c.name, c.similarity * 100, d["tier"]))
        L.append("- **出处**：%s" % d["source"])
        L.append("- **决策点**：%s" % d["decision_point"])
        L.append("- **行动**：%s" % d["action"])
        L.append("- **结果**：%s" % d["outcome"])
        L.append("- **迁移**：%s" % d["lesson"])
        L.append("- **反事实**：%s" % d["counterfactual"])
        L.append("")

    L.append("## 四、策略排序 (L4 ARBITER)\n")
    L.append("| 排名 | 计策 | 处境契合 | 博弈契合 | 风险折扣 | 综合 |")
    L.append("|---|---|---|---|---|---|")
    for i, s in enumerate(report["stratagems_ranked"], 1):
        L.append("| %d | **%s** | %.2f | %.2f | %.2f | **%.3f** |" %
                 (i, s.name, s.similarity, s.game_fit, s.risk_penalty, s.score))
    L.append("")

    top = report["stratagems_ranked"][0]
    L.append("### 首推：%s\n" % top.name)
    L.append("- **要义**：%s" % top.detail["essence"])
    L.append("- **适用前提**：%s" % top.detail["premise"])
    L.append("- **现代迁移**：%s" % top.detail["modern"])
    L.append("- **失效条件**：%s" % "；".join(top.detail["failure_conditions"]))
    L.append("- **红线**：%s" % top.detail["redline"])
    L.append("")

    L.append("## 五、影子谏官（强制负反馈）\n")
    for n in report["shadow"]:
        L.append("- %s" % n)
    L.append("")

    L.append("## 六、执行前三项自检\n")
    L.append("> 这三项来自 C014（周亚夫）、C019（袁绍杀田丰）、C028（哥舒翰）、"
             "C031（于谦）四条史案的共同教训："
             "失败极少源于算力不足，而源于信息通道闭塞、只看有利证据、以及没有退路。\n")
    L.append("1. **我的反对意见通道在哪里？** "
             "我最近一次听到「你这样不对」是什么时候？若答不出，"
             "本报告的排序建立在我的自我认知之上，而那正是最不可靠的输入。")
    L.append("2. **失效条件里有几条正在发生？** "
             "回到首推策略的失效条件逐条对照。若已有任一条件成立，"
             "该策略此刻就不成立，无论处境契合度多高。")
    L.append("3. **失败时我从哪里退出？** "
             "在动手之前写下退出线与退出方式。不可逆 + 无预案 = 赌博，不是决策。")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 内置演示：一个现实的职场/商业决策场景
# ---------------------------------------------------------------------------

DEMO = {
    "title": "公司核心方案被强势方低价索取，要不要草签授权",
    "answers": {
        "power_ratio": "weak",
        "stakes": "existential",
        "reversibility": 0.2,
        "info_asym": -0.4,
        "time_pressure": "high",
        "horizon": "repeated",
        "actors": "3",
        "third_party": True,
        "resource_slack": "low",
        "opponent_rationality": "rational",
        "moral_constraint": "high",
    },
    # 对方（行）与我方（列）：合作=公平授权；背叛=低价索取/拒绝
    # 对方背叛诱惑高（T=8 > R=5），P=2，我方最差 S=1
    "payoffs": ([[5, 1], [8, 2]], [[5, 8], [1, 2]]),
    "delta": 0.55,
}


def run_demo() -> str:
    eng = ShihengEngine()
    sv = encode_sv(DEMO["answers"])
    report = eng.decide(sv, payoffs=DEMO["payoffs"], delta=DEMO["delta"],
                        moral_floor="high")
    head = "> 演示场景：**%s**\n\n" % DEMO["title"]
    return head + render(report)


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        print(run_demo())
    else:
        print("engine.py 是库模块，一般不直接运行。")
        print("  看内置演示：  python engine.py --demo")
        print("  命令行入口：  python scripts/cli.py --help")
