#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
史料语料库验收 —— 防止扩容时退化。

判据：
  1. 二十四史覆盖不低于基线（记录当前值，允许上升不允许下降）
  2. 每条案例字段完整、T1 分级、结构化出处合法
  3. 兵计 <-> 史案双向索引零失效
  4. 博弈原型归属合法
  5. 处境向量维度与 meta 声明一致
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

ERSHISI = ['史记', '汉书', '后汉书', '三国志', '晋书', '宋书', '南齐书', '梁书', '陈书', '魏书',
           '北齐书', '周书', '隋书', '南史', '北史', '旧唐书', '新唐书', '旧五代史', '新五代史',
           '宋史', '辽史', '金史', '元史', '明史']

VALID_ARCH = {'PRISONERS_DILEMMA', 'CHICKEN', 'STAG_HUNT', 'BOXED_PIGS', 'DEADLOCK',
              'SIGNALING', 'STACKELBERG', 'REPEATED', 'COALITION'}

# 覆盖基线：不得低于此值
BASELINE_COVERAGE = 22

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s  %-48s got=%s" % ("PASS" if ok else "FAIL", name, got))


def check_ge(name, got, floor):
    global PASS, FAIL
    ok = got >= floor
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s  %-48s got=%s (>=%s)" % ("PASS" if ok else "FAIL", name, got, floor))


def main() -> int:
    global PASS, FAIL
    PASS = FAIL = 0

    cases_d = json.load(open(os.path.join(DATA, "cases.json"), encoding="utf-8"))
    stra_d = json.load(open(os.path.join(DATA, "stratagems.json"), encoding="utf-8"))
    cases = cases_d["cases"]
    stras = stra_d["stratagems"]

    print("\n=== 1. 史料覆盖 ===")
    hit = Counter(s["book"] for c in cases for s in c.get("sources", [])
                  if s.get("canonical"))
    covered = [b for b in ERSHISI if b in hit]
    missing = [b for b in ERSHISI if b not in hit]
    print("  已覆盖 %d/24：%s" % (len(covered), "、".join(covered)))
    print("  未覆盖：%s" % ("、".join(missing) or "无"))
    check_ge("二十四史覆盖不低于基线", len(covered), BASELINE_COVERAGE)
    check("覆盖书目均属二十四史", len([b for b in covered if b not in ERSHISI]), 0)

    print("\n=== 2. 案例字段完整性 ===")
    req = ("title", "era", "protagonist", "source", "tier", "archetype", "sv_tags",
           "sources", "situation", "decision_point", "action", "outcome", "lesson",
           "counterfactual", "failure_if")
    check("字段缺失为 0", len([c["id"] for c in cases if not all(k in c for k in req)]), 0)
    check("全部为 T1 正史确载",
          sum(1 for c in cases if c["tier"] == "T1"), len(cases))
    check("结构化出处非空",
          len([c["id"] for c in cases if not c.get("sources")]), 0)
    check("博弈原型合法",
          len([c["id"] for c in cases if c["archetype"] not in VALID_ARCH]), 0)

    print("\n=== 3. 处境向量一致性 ===")
    keys = set(cases_d["meta"]["sv_legend"])
    check("sv_tags 维度与 meta 一致",
          len([c["id"] for c in cases if set(c["sv_tags"]) != keys]), 0)

    print("\n=== 4. 双向索引 ===")
    case_ids = {c["id"] for c in cases}
    stra_ids = {s["id"] for s in stras}
    bad_ref = sorted({cid for s in stras for cid in s.get("case_ids", [])
                      if cid not in case_ids})
    check("兵计->史案 无效引用为 0", len(bad_ref), 0)
    bad_sid = sorted({sid for c in cases for sid in c.get("stratagem", [])
                      if sid not in stra_ids})
    check("史案->兵计 无效引用为 0", len(bad_sid), 0)
    unreferenced = sorted(case_ids -
                          {cid for s in stras for cid in s.get("case_ids", [])})
    check("孤立史案为 0（每条都被至少一计引用）", len(unreferenced), 0)

    print("\n=== 5. 兵计法典 ===")
    check("三十六计齐全", len(stras), 36)
    sreq = ("name", "group", "essence", "sunzi_ref", "archetype", "sv_profile",
            "premise", "case_ids", "modern", "failure_conditions", "redline", "counter")
    check("兵计字段缺失为 0",
          len([s["id"] for s in stras if not all(k in s for k in sreq)]), 0)
    check("兵计原型合法",
          len([s["id"] for s in stras if s["archetype"] not in VALID_ARCH]), 0)
    print("  已知留空史案（因史料不可靠刻意留白）：%s"
          % "、".join(s["id"] for s in stras if not s.get("case_ids")))

    print("\n" + "=" * 62)
    print("  PASS=%d  FAIL=%d   案例 %d 条 / 兵计 %d 条 / 二十四史 %d/24"
          % (PASS, FAIL, len(cases), len(stras), len(covered)))
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
