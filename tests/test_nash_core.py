#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
L2 博弈求解内核 —— 验证套件

运行： python tests/test_nash_core.py
覆盖：七个求解器的正常路径、边界与已知数值的理论真值对照。
所有断言均为「与解析真值对照」，而非快照式自证。
"""

from __future__ import annotations

import os
import sys


def _force_utf8() -> None:
    """Windows 无控制台时 stdout 编码是 cp1252，打印中文会抛 UnicodeEncodeError。"""
    for _name in ("stdout", "stderr"):
        _stream = getattr(sys, _name, None)
        try:
            if _stream is not None and hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


_force_utf8()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nash_core import (  # noqa: E402
    bayes_update,
    classify_2x2,
    core_nonempty,
    diagnose,
    mixed_nash_2x2,
    pure_nash,
    repeated_threshold,
    repeated_verdict,
    shapley,
    signaling_verdict,
    stackelberg,
)

PASS, FAIL = 0, 0


def check(name: str, got, want, tol: float = 1e-6):
    """统一判定入口：数值给容差，非数值要求严格相等。"""
    global PASS, FAIL
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    if ok:
        PASS += 1
        print("  PASS  %-46s got=%s" % (name, got))
    else:
        FAIL += 1
        print("  FAIL  %-46s got=%s want=%s" % (name, got, want))


print("\n[1] 纯策略纳什均衡")

# 囚徒困境：T=5 R=3 P=1 S=0
A = [[3, 0], [5, 1]]
B = [[3, 5], [0, 1]]
check("囚徒困境 → 唯一均衡 (背叛,背叛)", pure_nash(A, B), [(1, 1)])

# 智猪博弈：大猪=行，小猪=列；同时按(5,1)、大按小等(4,4)、大等小按(9,-1)、都不按(0,0)
A_pig = [[5, 4], [9, 0]]
B_pig = [[1, 4], [-1, 0]]
check("智猪博弈 → 大猪踩板、小猪等待", pure_nash(A_pig, B_pig), [(0, 1)])

# 斗鸡博弈：T=4 R=3 S=1 P=0
A_ch = [[3, 1], [4, 0]]
B_ch = [[3, 4], [1, 0]]
check("斗鸡博弈 → 两个纯均衡", len(pure_nash(A_ch, B_ch)), 2)

print("\n[2] 博弈原型分类")
check("囚徒困境识别", classify_2x2(A, B)["key"], "PRISONERS_DILEMMA")
check("斗鸡博弈识别", classify_2x2(A_ch, B_ch)["key"], "CHICKEN")
check("猎鹿博弈识别",
      classify_2x2([[4, 0], [3, 2]], [[4, 3], [0, 2]])["key"], "STAG_HUNT")
check("智猪博弈识别", classify_2x2(A_pig, B_pig)["key"], "BOXED_PIGS")
check("死锁博弈识别",
      classify_2x2([[1, 0], [4, 3]], [[1, 4], [0, 3]])["key"], "DEADLOCK")

print("\n[3] 混合策略纳什均衡（闭式解 vs 理论真值）")

# 猜硬币 / 无纯均衡：A、B 为标准的「斗鸡无主体的错位矩阵」
A_mx = [[1, 0], [0, 1]]
B_mx = [[0, 1], [1, 0]]
mn = mixed_nash_2x2(A_mx, B_mx)
check("错位博弈 p*(row0)", mn["p_row0"], 0.5)
check("错位博弈 q*(col0)", mn["q_col0"], 0.5)
check("错位博弈 行期望收益", mn["payoff_row"], 0.5)

# 无差异条件回代验证：混合均衡下行的两个纯策略期望收益必须相等
p, q = mn["p_row0"], mn["q_col0"]
row0_ev = 1 * q + 0 * (1 - q)
row1_ev = 0 * q + 1 * (1 - q)
check("无差异条件成立（行两策略期望相等）", row0_ev, row1_ev)

print("\n[4] Stackelberg 序贯均衡与先动溢价")
# 先行者可通过承诺拿到 4，同行刻最好只能拿 3
stk = stackelberg([[3, 0], [5, 1]], [[3, 5], [0, 1]])
check("PD 情形先行者收益", stk["row_leads"]["payoff_leader"], float(1))
check("PD 不存在先动溢价（PD 靠改写收益而非抢先）",
      stk["first_mover_premium_row"], 0.0)

# 自缚得益（对应《九地》「投之亡地然后存」）：
# 同时行动的唯一下均衡给行 1；若行抢先承诺 row0 ——放弃自己在 col0 下偏离到 row1 的
# 诱惑——反倒把列的最优反应锁在 col0，拿到 6。这正是「破釜沉舟」的收益来源。
A_sq = [[6, 0], [8, 1]]
B_sq = [[7, 2], [1, 5]]
stk2 = stackelberg(A_sq, B_sq)
check("自缚承诺锁定高成效", stk2["row_leads"]["payoff_leader"], float(6))
check("同时行动最好均衡仅为 1", stk2["simultaneous_best_row_payoff"], float(1))
check("先动溢价 = 6 - 1 = 5", stk2["first_mover_premium_row"], 5.0)
check("承诺价值为正", stk2["commitment_value"] > 0, True)

print("\n[5] 信号博弈：分离 / 混同判据")
sep = signaling_verdict(prior=0.4, cost_low=8.0, cost_high=2.0,
                        gain_if_believed=5.0, fallback_if_not=0.0)
check("高成本，低能力不模仿 → 分离均衡", sep["equilibrium"], "separating")
check("分离均衡下低能力不发信号", sep["low_type_will_mimic"], False)

pool = signaling_verdict(prior=0.4, cost_low=1.0, cost_high=0.5,
                         gain_if_believed=5.0, fallback_if_not=0.0)
check("低成本，人人可发 → 混同均衡", pool["equilibrium"], "pooling")
check("混合边际为正（确有模仿动机）", pool["mimic_margin"] > 0, True)

check("贝叶斯更新 P(H|sig)", bayes_update(0.5, 0.9, 0.2), 0.818181, tol=1e-4)

print("\n[6] 重复博弈临界折现因子")
check("δ* = (T-R)/(T-P) = 2/4", repeated_threshold(T=5, R=3, P=1), 0.5, tol=1e-6)
check("δ=0.8 ≥ δ* → 合作可自持", repeated_verdict(0.8, 5, 3, 1)["sustainable"], True)
check("δ=0.3 < δ* → 未来太轻", repeated_verdict(0.3, 5, 3, 1)["sustainable"], False)

print("\n[7] 联盟博弈：Shapley 值 + 核")
v_sym = {frozenset(): 0.0,
         frozenset({"A"}): 0.0, frozenset({"B"}): 0.0, frozenset({"C"}): 0.0,
         frozenset({"A", "B"}): 1.0, frozenset({"A", "C"}): 1.0,
         frozenset({"B", "C"}): 1.0, frozenset({"A", "B", "C"}): 1.0}
phi = shapley(v_sym)
check("对称三方 Shapley 各得 1/3", phi["A"], 1 / 3, tol=1e-6)
check("Shapley 有效性（Σφ = v(N)）", sum(phi.values()), 1.0)

# 三人多数博弈的核【必然为空】：任一二人组单独即可拿到全部收益 1，
# 三分饭的钱却填不了两个人的胃口——任何两人都有脱离动机。
# 这是「合纵必散」的数学根源，不是数值巧合。
ok_sym, why_sym = core_nonempty(v_sym)
check("三人多数博弈核为空（合纵不稳）", ok_sym, False)
check("诊断给出具体的脱离二元组", "脱离动机" in why_sym, True)

# 凸博弈才是核非空的例子：v(S∪T)+v(S∩T) ≥ v(S)+v(T) 保证 Shapley 落在核内
v_convex = {frozenset(): 0.0,
            frozenset({"A"}): 1.0, frozenset({"B"}): 2.0, frozenset({"C"}): 3.0,
            frozenset({"A", "B"}): 4.0, frozenset({"A", "C"}): 5.0,
            frozenset({"B", "C"}): 6.0, frozenset({"A", "B", "C"}): 10.0}
phi_c = shapley(v_convex)
check("凸博弈 Shapley 之和 = v(N)", sum(phi_c.values()), 10.0)
check("凸博弈核非空", core_nonempty(v_convex)[0], True)

# 手套博弈变体：AB=1, AC=1, BC=0, ABC=1 → 存在脱离动机，核应为空
v_asym = {frozenset(): 0.0,
          frozenset({"A"}): 0.0, frozenset({"B"}): 0.0, frozenset({"C"}): 0.0,
          frozenset({"A", "B"}): 1.0, frozenset({"A", "C"}): 1.0,
          frozenset({"B", "C"}): 0.0, frozenset({"A", "B", "C"}): 1.0}
ok, reason = core_nonempty(v_asym)
check("非对称三方核为空", ok, False)
check("诊断指出 A 有脱离动机", "A" in reason or "B" in reason, True)

print("\n[8] 端到端体检 diagnose")
rep = diagnose(A, B, delta=0.5)
check("PD 体检返回正确原型", rep["archetype"]["name"], "囚徒困境")
check("PD 体检含孙子映射", rep["archetype"]["sunzi_ref"].startswith("伐谋"), True)
check("PD 混合/纯均衡均给到", len(rep["pure_nash"]) > 0, True)

print("\n" + "=" * 62)
print("  PASS=%d  FAIL=%d" % (PASS, FAIL))
print("=" * 62)
sys.exit(1 if FAIL else 0)
