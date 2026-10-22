#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
史衡 · 五链决策模型 —— L2 层博弈求解内核
SHIHENG Five-Chain Decision Model / Layer 2: Game-Theoretic Verifier

纯标准库实现。提供的能力：
  1. pure_nash        —— 纯策略纳什均衡枚举（通用 n x m）
  2. mixed_nash_2x2   —— 2x2 混合策略纳什均衡闭式解
  3. classify_2x2     —— 博弈原型识别（囚徒困境/斗鸡/猎鹿/智猪/死锁/一般）
  4. stackelberg      —— 序贯博弈逆向归纳，量化先动优势/后动优势
  5. signaling        —— 信号博弈：贝叶斯更新 + 分离/混同均衡判据
  6. repeated         —— 重复博弈合作临界折现因子 δ*
  7. shapley_and_core —— 三方联盟博弈：Shapley 值 + 核（core）非空判据

约定：所有 payoff 矩阵 A[i][j] 表示【行玩家】在「行选 i、列选 j」时的收益；
      B[i][j] 表示【列玩家】在同一情形下的收益。零和非对称均可。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Dict, List, Optional, Sequence, Tuple

EPS = 1e-9


# ----------------------------------------------------------------------------
# 1. 纯策略纳什均衡
# ----------------------------------------------------------------------------

def best_responses_row(A: Sequence[Sequence[float]], q: int) -> List[int]:
    """行玩家在列玩家固定选 q 时的最优反应集合。"""
    vals = [A[i][q] for i in range(len(A))]
    best = max(vals)
    return [i for i, v in enumerate(vals) if abs(v - best) < EPS]


def best_responses_col(B: Sequence[Sequence[float]], p: int) -> List[int]:
    """列玩家在行玩家固定选 p 时的最优反应集合。"""
    n_cols = len(B[0])
    vals = [B[p][j] for j in range(n_cols)]
    best = max(vals)
    return [j for j, v in enumerate(vals) if abs(v - best) < EPS]


def pure_nash(A: Sequence[Sequence[float]],
              B: Sequence[Sequence[float]]) -> List[Tuple[int, int]]:
    """枚举全部纯策略纳什均衡，返回 [(row_idx, col_idx), ...]。"""
    return [(i, j)
            for i in range(len(A))
            for j in range(len(B[0]))
            if i in best_responses_row(A, j) and j in best_responses_col(B, i)]


def dominates(A: Sequence[Sequence[float]], a: int, b: int,
              strict: bool = True) -> bool:
    """行玩家策略 a 是否（严格/弱）占优策略 b。"""
    cmp = (lambda x, y: x > y + EPS) if strict else (lambda x, y: x >= y - EPS)
    return all(cmp(A[a][j], A[b][j]) for j in range(len(A[0])))


def iterated_elimination(A: Sequence[Sequence[float]],
                         B: Sequence[Sequence[float]]
                         ) -> Tuple[List[int], List[int]]:
    """迭代剔除严格劣势策略，返回幸存的行/列策略索引。"""
    rows = list(range(len(A)))
    cols = list(range(len(B[0])))
    changed = True
    while changed and len(rows) > 1 and len(cols) > 1:
        changed = False
        for i in list(rows):
            for k in list(rows):
                if i != k and all(A[i][j] > A[k][j] + EPS for j in cols):
                    rows.remove(k)
                    changed = True
        for j in list(cols):
            for k in list(cols):
                if j != k and all(B[i][j] > B[i][k] + EPS for i in rows):
                    cols.remove(k)
                    changed = True
    return rows, cols


# ----------------------------------------------------------------------------
# 2. 2x2 混合策略纳什均衡（闭式解）
# ----------------------------------------------------------------------------

def mixed_nash_2x2(A: Sequence[Sequence[float]],
                   B: Sequence[Sequence[float]]) -> Optional[Dict[str, float]]:
    """
    2x2 混合策略纳什均衡闭式解。

    行玩家以概率 p 选 row0；列玩家以概率 q 选 col0。
    无差异条件：
        q* = (A11 - A01) / (A00 - A01 - A10 + A11)
        p* = (B11 - B10) / (B00 - B10 - B01 + B11)
    分母为 0 表示该玩家不存在无差异混合（非完全混合），返回 None。
    返回概率越界（<0 或 >1）时同样返回 None。
    """
    if len(A) != 2 or len(A[0]) != 2:
        raise ValueError("mixed_nash_2x2 仅支持 2x2 矩阵")

    den_q = A[0][0] - A[0][1] - A[1][0] + A[1][1]
    den_p = B[0][0] - B[1][0] - B[0][1] + B[1][1]
    if abs(den_q) < EPS or abs(den_p) < EPS:
        return None

    q = (A[1][1] - A[0][1]) / den_q
    p = (B[1][1] - B[1][0]) / den_p
    if not (-EPS <= p <= 1 + EPS and -EPS <= q <= 1 + EPS):
        return None

    p, q = min(max(p, 0.0), 1.0), min(max(q, 0.0), 1.0)
    return {
        "p_row0": p,
        "q_col0": q,
        "payoff_row": p * q * A[0][0] + p * (1 - q) * A[0][1]
                      + (1 - p) * q * A[1][0] + (1 - p) * (1 - q) * A[1][1],
        "payoff_col": p * q * B[0][0] + p * (1 - q) * B[0][1]
                      + (1 - p) * q * B[1][0] + (1 - p) * (1 - q) * B[1][1],
    }


# ----------------------------------------------------------------------------
# 3. 博弈原型识别
# ----------------------------------------------------------------------------

@dataclass
class GameArchetype:
    key: str
    name: str
    name_en: str
    sunzi_ref: str
    stratagem_ref: str
    structural_logic: str
    failure_mode: str


ARCHETYPES: Dict[str, GameArchetype] = {
    "PRISONERS_DILEMMA": GameArchetype(
        key="PRISONERS_DILEMMA", name="囚徒困境", name_en="Prisoner's Dilemma",
        sunzi_ref="伐谋 / 伐交：《谋攻篇》「必以全争于天下」，改写对方收益结构优于直接对抗",
        stratagem_ref="趁火打劫、上屋抽梯、借刀杀人、远交近攻",
        structural_logic="T>R>P>S：个体理性导致集体最差。破局点在改变对方收益或通过重复博弈引入未来阴影，而非指望对方觉悟。",
        failure_mode="误判为单次博弈而施诱导，实则对方具备长期记忆，造成信誉锚定反噬。",
    ),
    "CHICKEN": GameArchetype(
        key="CHICKEN", name="斗鸡博弈", name_en="Game of Chicken",
        sunzi_ref="《九地篇》：「投之亡地然后存，陷之死地然后生」——通过自我承诺剥夺自己的退路",
        stratagem_ref="背水一战、破釜沉舟、置之死地",
        structural_logic="T>R>S>P：谁先示弱谁得次好，双方硬顶则同毁。胜点是抢先做出不可逆承诺（烧掉退路），而非比谁更强。",
        failure_mode="对手同样烧了退路，或对手根本不在乎共同毁灭（非理性/无知），承诺即自杀。",
    ),
    "STAG_HUNT": GameArchetype(
        key="STAG_HUNT", name="猎鹿博弈", name_en="Stag Hunt",
        sunzi_ref="《计篇》「上下同欲者胜」——协同需要共同信念而非强制",
        stratagem_ref="合纵连横、远交近攻（结盟侧）",
        structural_logic="R>T>P>S：存在两个均衡，合作均衡更优但需信任。关键变量是「我相不相信对方会合作」。",
        failure_mode="在信任未建立时抢先进攻（改出合作均衡），把最优结果彻底锁死。",
    ),
    "BOXED_PIGS": GameArchetype(
        key="BOXED_PIGS", name="智猪博弈", name_en="Boxed Pigs",
        sunzi_ref="《军争篇》「以迂为直，以患为利」——让强者承担成本，弱者享受溢出",
        stratagem_ref="借尸还魂、树上开花、假道伐虢、顺手牵羊",
        structural_logic="小猪的占优策略是等待。弱者的正确姿势是搭便车并守住自身不可替代性，而非争着踩踏板。",
        failure_mode="大猪识破后停止踩踏板（改规则），弱者连同 entitlement 一起失去；或弱者被判定无价值而被踢出猪圈。",
    ),
    "DEADLOCK": GameArchetype(
        key="DEADLOCK", name="死锁博弈", name_en="Deadlock",
        sunzi_ref="《形篇》「胜兵先胜而后求战」——优势已定时无需谋略，直接兑现",
        stratagem_ref="以逸待劳、先发制人",
        structural_logic="T>P>R>S：背叛无条件占优，不存在合作空间。此时不要指望关系，按实力兑现。",
        failure_mode="把死锁当 PD 去感化对方，白白错失兑现窗口。",
    ),
    "SIGNALING": GameArchetype(
        key="SIGNALING", name="信号博弈", name_en="Signaling Game",
        sunzi_ref="《计篇》「兵者，诡道也…远而示之近，近而示之远」",
        stratagem_ref="瞒天过海、空城计、声东击西、无中生有、示弱骄敌",
        structural_logic="信息不对称下，行动同时是目的与信号。分离均衡要求「伪装成本高到低能者可承受不起」，否则塌缩为混同均衡而失效。",
        failure_mode="信号成本太低（可低成本模仿），对方按先验而非信号行动，计策当场失效并暴露意图。",
    ),
    "STACKELBERG": GameArchetype(
        key="STACKELBERG", name="序贯博弈/斯塔克尔伯格", name_en="Stackelberg Game",
        sunzi_ref="《虚实篇》「致人而不致于人」——抢先定义战场即定义对手的反应集",
        stratagem_ref="围魏救赵、暗度陈仓、釜底抽薪、反客为主",
        structural_logic="先动者可选择让对方的最优反应恰好对自己最有利。核心不是「快」，而是「让对方不得不那样做」。",
        failure_mode="对方不受制于被改变的成本结构（如对方可承受损失或另有退路），抢先播种的反应反而反过来成为你的枷锁。",
    ),
    "REPEATED": GameArchetype(
        key="REPEATED", name="重复博弈", name_en="Repeated Game",
        sunzi_ref="《作战篇》「兵闻拙速，未睹巧之久也」之外，另有长期共处的定额考虑",
        stratagem_ref="以义待人、取信于民（君子协定）、以直报怨",
        structural_logic="当 δ ≥ δ* 时合作可自持。δ* = (T-R)/(T-P)。要把「未来阴影」拉长：增加交互频率、提高透明度、降低背叛一次性收益。",
        failure_mode="把重复博弈当末局博弈打：在最后一次交割时背叛，一次性耗尽累积的信誉资本。",
    ),
    "COALITION": GameArchetype(
        key="COALITION", name="联盟博弈", name_en="Coalition Game",
        sunzi_ref="《谋攻篇》「上兵伐谋，其次伐交」",
        stratagem_ref="远交近攻、连横、假道伐虢",
        structural_logic="三方及以上要看「关键加入者」：Shapley 值低于其单独行动收益者不会被纳入稳定联盟。核心(core)为空则任何分配方案都会被推翻。",
        failure_mode="联盟收益大于成本但核心为空（各方都不满足分配），组建当下即崩；或忽略关键第三方而谈双边。",
    ),
}


def classify_2x2(A: Sequence[Sequence[float]],
                 B: Sequence[Sequence[float]]) -> Dict[str, object]:
    """
    识别 2x2 博弈原型。

    玩家策略序约定为 [合作/克制, 背叛/强硬]。
    先判定是否对称；对称时按 T/R/P/S 排序判型；非对称时按支配结构降级判型。
    """
    symmetric = all(abs(A[i][j] - B[j][i]) < 1e-6
                    for i in range(2) for j in range(2))
    R = A[0][0]          # 双方合作
    T = A[1][0]          # 己背叛、彼合作（诱惑）
    S = A[0][1]          # 己合作、彼背叛（被出卖）
    P = A[1][1]          # 双方背叛

    if symmetric:
        if T > R > P > S:
            key = "PRISONERS_DILEMMA"
        elif T > R > S > P:
            key = "CHICKEN"
        elif R > T > P > S:
            key = "STAG_HUNT"
        elif T > P > R > S:
            key = "DEADLOCK"
        elif R > S > T > P or R > S > P > T:
            key = "BOXED_PIGS"
        else:
            key = "SIGNALING"
    else:
        # 「搭便车」结构判据：一方有严格占优策略，另一方没有，且均衡收益严重不对称
        row_strict_dom = (all(A[1][j] > A[0][j] + EPS for j in range(2)) or
                          all(A[0][j] > A[1][j] + EPS for j in range(2)))
        col_strict_dom = (all(B[i][1] > B[i][0] + EPS for i in range(2)) or
                          all(B[i][0] > B[i][1] + EPS for i in range(2)))
        if (row_strict_dom or col_strict_dom) and not (row_strict_dom and col_strict_dom):
            key = "BOXED_PIGS"
        elif row_strict_dom and col_strict_dom:
            key = "DEADLOCK"
        elif T > R > P > S:
            key = "PRISONERS_DILEMMA"
        else:
            key = "STACKELBERG"
    return {
        "key": key,
        "symmetric": symmetric,
        "payoffs": {"R": R, "T": T, "S": S, "P": P},
        "delta_star": repeated_threshold(T, R, P) if key in
                      ("PRISONERS_DILEMMA", "DEADLOCK") else None,
    }


# ----------------------------------------------------------------------------
# 4. Stackelberg：序贯博弈与先动溢价
# ----------------------------------------------------------------------------

def stackelberg(A: Sequence[Sequence[float]],
                B: Sequence[Sequence[float]]) -> Dict[str, object]:
    """
    分别计算「行先动」与「列先动」的子博弈精炼均衡，量化先动/后动优势。

    领导者承诺一个纯策略，跟随者观察后最优反应；领导者预期到这一点做最优选。
    """
    def solve(leader_first: bool) -> Dict[str, object]:
        if leader_first:
            options = []
            for i in range(len(A)):
                br = best_responses_col(B, i)
                vals = [(j, B[i][j]) for j in br]
                j_hat = max(vals, key=lambda x: x[1])[0]
                options.append((A[i][j_hat], i, j_hat))
            payoff, lead, follow = max(options, key=lambda x: x[0])
            return {"leader": "row", "payoff_leader": payoff,
                    "action": (lead, follow)}
        options = []
        for j in range(len(B[0])):
            br = best_responses_row(A, j)
            vals = [(i, A[i][j]) for i in br]
            i_hat = max(vals, key=lambda x: x[0])[0]
            options.append((B[i_hat][j], j, i_hat))
        payoff, lead, follow = max(options, key=lambda x: x[0])
        return {"leader": "col", "payoff_leader": payoff,
                "action": (follow, lead)}

    row_first = solve(True)
    col_first = solve(False)
    # 同刻 simultaneous 对照：取各纯均衡中的最好收益
    eq = pure_nash(A, B)
    nash_row_payoff = max((A[i][j] for i, j in eq), default=None)

    return {
        "row_leads": row_first,
        "col_leads": col_first,
        "simultaneous_best_row_payoff": nash_row_payoff,
        "first_mover_premium_row": (row_first["payoff_leader"] - nash_row_payoff)
                                   if nash_row_payoff is not None else None,
        "commitment_value": abs(row_first["payoff_leader"]
                                - col_first["payoff_leader"]),
    }


# ----------------------------------------------------------------------------
# 5. 信号博弈：贝叶斯更新 + 均衡类型判据
# ----------------------------------------------------------------------------

def bayes_update(prior: float, likelihood_h: float, likelihood_l: float) -> float:
    """P(Type=High | signal) —— 单次信号后的后验。"""
    num = prior * likelihood_h
    den = num + (1 - prior) * likelihood_l
    if abs(den) < EPS:
        raise ValueError("信号发生的总概率为 0，先验与似然不自洽")
    return num / den


def signaling_verdict(prior: float,
                      cost_low: float,
                      cost_high: float,
                      gain_if_believed: float,
                      fallback_if_not: float = 0.0) -> Dict[str, object]:
    """
    判定时运低保真型是否会模仿高能力型发信号 —— 即昭示诚意的信号可否维持分离均衡。
    判据（分离均衡的激励相容约束）：
        高能力型发信号：    gain_if_believed - cost_high   >= fallback_if_not
        低能力型不发信号：  gain_if_believed - cost_low    <= fallback_if_not
    """
    high_ok = (gain_if_believed - cost_high) >= fallback_if_not
    low_det = (gain_if_believed - cost_low) <= fallback_if_not
    margin = (gain_if_believed - cost_low) - fallback_if_not  # >0 表示低也愿意模仿

    if high_ok and low_det:
        kind = "separating"
        verdict = "分离均衡成立：信号只被真正具备实力的一方发出，接收方可据此更新信念。"
    elif high_ok and not low_det:
        kind = "pooling"
        verdict = ("混同均衡：低能力型也会模仿（模仿边际 %.2f），"
                   "信号失去甄别功能，接收方只能按先验 %.2f 行事。" % (margin, prior))
    elif not high_ok and not low_det:
        kind = "none"
        verdict = "信号成本高于收益，无人发信号，信道坍缩。"
    else:
        kind = "reverse"
        verdict = "信号反而由弱者独发（逆向选择），强者退出该信号场，接收方应反向解读。"

    return {
        "equilibrium": kind,
        "verdict": verdict,
        "high_type_will_signal": high_ok,
        "low_type_will_mimic": not low_det,
        "mimic_margin": margin,
    }


# ----------------------------------------------------------------------------
# 6. 重复博弈：合作自持的临界折现因子
# ----------------------------------------------------------------------------

def repeated_threshold(T: float, R: float, P: float, S: float | None = None) -> Optional[float]:
    """
    以牙还牙（Tit-for-Tat）下合作可自持的临界折现因子：
        δ* = (T - R) / (T - P)
    δ ≥ δ* 表示未来阴影足够重，合作能自我维持。
    """
    den = T - P
    if abs(den) < EPS:
        return None
    return (T - R) / den


def repeated_verdict(delta: float, T: float, R: float, P: float) -> Dict[str, object]:
    d_star = repeated_threshold(T, R, P)
    if d_star is None:
        return {"sustainable": False, "reason": "参数退化，无法判定"}
    sustainable = delta >= d_star - EPS
    return {
        "delta": delta,
        "delta_star": d_star,
        "sustainable": sustainable,
        "reason": ("δ=%.2f ≥ δ*=%.2f，长期关系足以抑制背叛。" % (delta, d_star))
                  if sustainable else
                  ("δ=%.2f < δ*=%.2f，未来太轻，理性计算出卖更有利——此时勿以道义期待替代制度约束。"
                   % (delta, d_star)),
    }


# ----------------------------------------------------------------------------
# 7. 联盟博弈：Shapley 值 + 核非空判据
# ----------------------------------------------------------------------------

def shapley(values: Dict[frozenset, float]) -> Dict[str, float]:
    """三方联盟博弈的 Shapley 值（参与者默认从 values 的单人 key 反推）。"""
    players = sorted({p for s in values for p in s})
    n = len(players)
    result = {p: 0.0 for p in players}
    for p in players:
        others = [o for o in players if o != p]
        for size in range(len(others) + 1):
            for subset in combinations(others, size):
                s = frozenset(subset)
                w = len(s) + 1
                weight = (_fact(w - 1) * _fact(n - w)) / _fact(n)
                result[p] += weight * (values.get(s | {p}, 0.0) - values.get(s, 0.0))
    return result


def _fact(k: int) -> int:
    r = 1
    for i in range(2, k + 1):
        r *= i
    return r


def core_nonempty(values: Dict[frozenset, float]) -> Tuple[bool, str]:
    """
    核非空判据（简化版）：
      1) 个体理性：φ_i ≥ v({i})
      2) 有效性：  Σφ_i = v(N)
      3) 联盟理性：任一真子集 S，Σ_{i∈S} φ_i ≥ v(S)
    返回是否非空与诊断。
    """
    players = sorted({p for s in values for p in s})
    grand = values.get(frozenset(players), 0.0)
    phi = shapley(values)

    if sum(phi.values()) < grand - 1e-6:
        return False, "总产出不足，Shapley 分配总额 %.2f < 联盟总收益 %.2f" % (
            sum(phi.values()), grand)
    for p in players:
        if phi[p] < values.get(frozenset({p}), 0.0) - 1e-6:
            return False, "参与者 %s 的 Shapley 分配 %.2f 低于其单独行动收益 %.2f" % (
                p, phi[p], values.get(frozenset({p}), 0.0))
    for size in range(2, len(players)):
        for subset in combinations(players, size):
            s = frozenset(subset)
            if sum(phi[i] for i in s) < values.get(s, 0.0) - 1e-6:
                return False, "子集 {%s} 可分得 %.2f < 其自组收益 %.2f，有脱离动机" % (
                    ",".join(s), sum(phi[i] for i in s), values.get(s, 0.0))
    return True, "核非空：存在任何子集都无脱离动机的稳定分配方案。"


# ----------------------------------------------------------------------------
# 诊断总入口
# ----------------------------------------------------------------------------

# 博弈原型 -> 兵计反向索引。
# 单一来源（single source of truth）：stratagems.json 里每计的 archetype 是它的主原型，
# 但多数兵计天然横跨多个原型（例如「远交近攻」既是联盟博弈也是时序对抗）。
# 因此在这里建立反向索引，仲裁层据此计算「博弈契合度」，避免两处维护导致漂移。
ARCHETYPE_STRATAGEMS: Dict[str, List[str]] = {
    "PRISONERS_DILEMMA": ["S05", "S28", "S03", "S23", "S33"],
    "CHICKEN":           ["S34", "S13", "S31"],
    "STAG_HUNT":         ["S23", "S30", "S09", "S35"],
    "BOXED_PIGS":        ["S14", "S29", "S24", "S12"],
    "DEADLOCK":          ["S04", "S18", "S22"],
    "SIGNALING":         ["S01", "S06", "S07", "S10", "S20", "S21",
                          "S25", "S27", "S29", "S32", "S33"],
    "STACKELBERG":       ["S02", "S04", "S05", "S08", "S11", "S15", "S16",
                          "S17", "S18", "S19", "S22", "S30", "S36"],
    "REPEATED":          ["S09", "S26", "S27", "S30"],
    "COALITION":         ["S03", "S09", "S14", "S23", "S24", "S35"],
}


def infer_archetype_from_sv(sv: Dict[str, Any]) -> str:
    """
    无收益矩阵时，用处境向量反推最可能的博弈原型。

    优先次序取决于处境的决定性特征：
      参与方 >= 3 且可由第三方借力 -> 联盟博弈
      长期共处                      -> 重复博弈
      信息优势显著且存在出奇空间    -> 信号博弈
      其余                          -> 序贯博弈（攻其必救的通用结构）
    """
    horizon = str(sv.get("horizon", "single"))
    actors = int(sv.get("actors", 2))
    third = bool(sv.get("third_party", False))
    info = float(sv.get("info_asym", 0.0))
    pressure = str(sv.get("time_pressure", "medium"))

    if actors >= 3 and third:
        return "COALITION"
    if horizon == "repeated":
        return "REPEATED"
    if info >= 0.4 and pressure != "low":
        return "SIGNALING"
    return "STACKELBERG"


def diagnose(A: Sequence[Sequence[float]],
             B: Sequence[Sequence[float]],
             delta: Optional[float] = None) -> Dict[str, object]:
    """对一个局面做完整的博弈体检，返回结构化结论。"""
    cls = classify_2x2(A, B)
    arch = ARCHETYPES[cls["key"]]
    eq_pure = pure_nash(A, B)
    mixed = mixed_nash_2x2(A, B) if len(A) == 2 and len(A[0]) == 2 else None
    stk = stackelberg(A, B)
    rep = repeated_verdict(delta, cls["payoffs"]["T"], cls["payoffs"]["R"],
                           cls["payoffs"]["P"]) if delta is not None else None

    return {
        "archetype": {"key": arch.key, "name": arch.name, "name_en": arch.name_en,
                      "sunzi_ref": arch.sunzi_ref,
                      "stratagem_ref": arch.stratagem_ref,
                      "structural_logic": arch.structural_logic,
                      "failure_mode": arch.failure_mode},
        "payoffs": cls["payoffs"],
        "symmetric": cls["symmetric"],
        "pure_nash": eq_pure,
        "mixed_nash": mixed,
        "stackelberg": stk,
        "repeated": rep,
    }


if __name__ == "__main__":
    # 自检：囚徒困境
    A = [[3, 0], [5, 1]]
    B = [[3, 5], [0, 1]]
    print("[PD]", diagnose(A, B, delta=0.5)["archetype"]["name"],
          diagnose(A, B)["pure_nash"])
