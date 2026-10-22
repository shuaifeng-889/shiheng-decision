#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
判别力验收 —— 证明模型能区分处境，而不是恒推一条计。

判据：
  1. 三个结构迥异的处境，首推策略必须互不相同；
  2. 用户自行辩出来的原型必须与引擎输出一致；
  3. 高风险策略在低道德基线场景必须被压制；
  4. 影子谏官至少触发 1 条（负反馈不可为空）。
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

from engine import ShihengEngine  # noqa: E402
from nash_core import ARCHETYPES  # noqa: E402

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s  %-52s got=%s" % ("PASS" if ok else "FAIL", name, got))


SCENES = [
    {
        "name": "弱势方被强势方索取，但双方长期共处",
        "sv": {"power_ratio": "weak", "stakes": "existential", "reversibility": 0.2,
               "info_asym": -0.4, "time_pressure": "high", "horizon": "repeated",
               "actors": 3, "third_party": True, "resource_slack": "low",
               "opponent_rationality": "rational", "moral_constraint": "high"},
        "payoffs": ([[5, 1], [8, 2]], [[5, 8], [1, 2]]),   # 囚徒困境
        "delta": 0.55,
        "expect_arch": "PRISONERS_DILEMMA",
    },
    {
        "name": "对手正陷危机，我方占优且机会转瞬即逝",
        "sv": {"power_ratio": "strong", "stakes": "high", "reversibility": 0.4,
               "info_asym": 0.4, "time_pressure": "high", "horizon": "single",
               "actors": 2, "third_party": True, "resource_slack": "high",
               "opponent_rationality": "myopic", "moral_constraint": "medium"},
        # 死锁：T>P>R>S（都背叛 4 也好过被单方出卖 0，故背叛无条件占优）
        "payoffs": ([[3, 0], [6, 4]], [[3, 6], [0, 4]]),
        "delta": None,
        "expect_arch": "DEADLOCK",
    },
    {
        "name": "长期共处的平级同事竞争，撕破脸代价高",
        "sv": {"power_ratio": "even", "stakes": "medium", "reversibility": 0.7,
               "info_asym": 0.0, "time_pressure": "low", "horizon": "repeated",
               "actors": 2, "third_party": False, "resource_slack": "medium",
               "opponent_rationality": "rational", "moral_constraint": "high"},
        "payoffs": ([[4, 0], [3, 2]], [[4, 3], [0, 2]]),   # 猎鹿：合作优但需信任
        "delta": 0.8,
        "expect_arch": "STAG_HUNT",
    },
]

if __name__ == "__main__":
    eng = ShihengEngine(data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))
    tops, arches, reports = [], [], []

    print("\n=== 判别力验收：三个结构迥异的处境 ===\n")
    for i, sc in enumerate(SCENES, 1):
        rep = eng.decide(sc["sv"], payoffs=sc["payoffs"], delta=sc["delta"],
                         moral_floor="high")
        top = rep["stratagems_ranked"][0]
        arch = rep["game"]["archetype"]["key"]
        tops.append(top.name)
        arches.append(arch)
        reports.append(rep)
        print("场景 %d：%s" % (i, sc["name"]))
        print("  原型 = %s（%s）   首推 = %s   score=%.3f"
              % (arch, rep["game"]["archetype"]["name"], top.name, top.score))
        print("  次位 = %s (%.3f)\n"
              % (rep["stratagems_ranked"][1].name, rep["stratagems_ranked"][1].score))

    print("=== 判据 ===")
    check("三个场景原型互不相同", len(set(arches)), 3)
    check("三个场景首推互不相同", len(set(tops)), 3)

    for i, (sc, a) in enumerate(zip(SCENES, arches), 1):
        check("场景%d 原型与预期一致" % i, a, sc["expect_arch"])

    # 影子谏官不得为空
    for i, rep in enumerate(reports, 1):
        check("场景%d 影子谏官非空" % i, len(rep["shadow"]) > 0, True)

    # 高危计在高道德基线下必须被打压到后段
    print("\n=== 风险压制验证：高道德基线下的高危计 ===")
    rep = reports[0]
    names = [c.name for c in rep["stratagems_ranked"]]
    scores = {c.name: c.score for c in rep["stratagems_ranked"]}
    high_risk = {"无中生有", "偷梁换柱", "美人计", "苦肉计", "反间计"}
    present = high_risk & set(names)
    if present:
        worst_rank = max(names.index(n) for n in present)
        print("  出现在候选中的高危计：%s" % "、".join(sorted(present)))
        for n in sorted(present):
            print("    %s → score=%.3f，第 %d 位" % (n, scores[n], names.index(n) + 1))
        check("高危计均未进入首推", names[0] not in high_risk, True)
        check("高危计排序落在首推之后", worst_rank >= 1, True)
    else:
        check("高危计未进入候选列表", True, True)

    print("\n" + "=" * 64)
    print("  PASS=%d  FAIL=%d" % (PASS, FAIL))
    print("  三个场景首推：%s" % " / ".join(tops))
    print("=" * 64)
    sys.exit(1 if FAIL else 0)
