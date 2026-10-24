#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
案例库覆盖面审计测试 —— 把 references/03-corpus-coverage.md 的审计固化为断言。

为什么需要这一套：test_corpus.py 保证的是「数据没坏」，这套保证的是
「数据没跑偏」。前者查字段与索引，后者查分布——一个案例库可以字段全对、
索引全通，却在 84% 是军事案例、80% 是 existential 赌注的状态下稳定运行，
而用户问「要不要接这个 offer」时永远得不到同构的史案。

判据（均为下限，允许上升不允许下降）：
  1. 二十四史覆盖 >= 22
  2. stakes=low 至少 2 条（2026-10-24 扩容后的基线）
  3. stakes=medium 至少 2 条
  4. PRISONERS_DILEMMA / DEADLOCK 各至少 1 条
  5. 非军事主题域至少 8 条（人事 / 制度 / 经济 / 仕途 合计）
  6. 宋元明清（近世）至少 6 条
  7. 孤立史案为 0、原型合法、字段齐全（与 test_corpus 同源，防回归）
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter


def _force_utf8() -> None:
    for _name in ("stdout", "stderr"):
        _stream = getattr(sys, _name, None)
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


_force_utf8()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
ERSHISI = ['史记', '汉书', '后汉书', '三国志', '晋书', '宋书', '南齐书', '梁书', '陈书',
           '魏书', '北齐书', '周书', '隋书', '南史', '北史', '旧唐书', '新唐书',
           '旧五代史', '新五代史', '宋史', '辽史', '金史', '元史', '明史']
VALID_ARCH = {'PRISONERS_DILEMMA', 'CHICKEN', 'STAG_HUNT', 'BOXED_PIGS', 'DEADLOCK',
              'SIGNALING', 'STACKELBERG', 'REPEATED', 'COALITION'}

PASS = FAIL = 0


def check_ge(name, got, floor):
    global PASS, FAIL
    ok = got >= floor
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s %-46s got=%s (>=%s)" % ("PASS" if ok else "FAIL", name, got, floor))


def check(name, cond, detail=""):
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if cond else (PASS, FAIL + 1)
    print("  %s %-46s %s" % ("PASS" if cond else "FAIL", name, detail))


def main() -> int:
    global PASS, FAIL
    PASS = FAIL = 0

    cd = json.load(open(os.path.join(DATA, "cases.json"), encoding="utf-8"))
    sd = json.load(open(os.path.join(DATA, "stratagems.json"), encoding="utf-8"))
    cases, stras = cd["cases"], sd["stratagems"]

    print("\n=== 1. 二十四史覆盖 ===")
    hit = Counter(s["book"] for c in cases for s in c.get("sources", [])
                  if s.get("canonical"))
    covered = [b for b in ERSHISI if b in hit]
    check_ge("二十四史覆盖", len(covered), 22)

    print("\n=== 2. 赌注分布（最易被忽视的盲区）===")
    st = Counter(c["sv_tags"]["stakes"] for c in cases)
    print("  分布：%s" % dict(st))
    check_ge("stakes=low", st.get("low", 0), 2)
    check_ge("stakes=medium", st.get("medium", 0), 2)
    # existential 占比不设上限但要点名：这是来源性质，不是缺陷
    ex_pct = 100.0 * st.get("existential", 0) / max(1, len(cases))
    print("  [告知] stakes=existential 占 %.0f%%（正史来源性质，靠匹配度机制降级，"
          "不设上限）" % ex_pct)

    print("\n=== 3. 原型覆盖 ===")
    ar = Counter(c["archetype"] for c in cases)
    print("  分布：%s" % dict(ar))
    check_ge("PRISONERS_DILEMMA", ar.get("PRISONERS_DILEMMA", 0), 1)
    check_ge("DEADLOCK", ar.get("DEADLOCK", 0), 1)
    check("原型取值合法", all(c["archetype"] in VALID_ARCH for c in cases))

    print("\n=== 4. 非军事主题域（2026-10-24 扩容基线 9）===")
    # 按 id 段判定，比关键词筛更稳：C051-C052 制度、C053-C055 人事、
    # C056-C057 仕途进退、C061-C062 经济制度
    nonmil = [c for c in cases if c["id"] in
              {"C051", "C052", "C053", "C054", "C055", "C056", "C057",
               "C061", "C062"}]
    print("  命中：%s" % "、".join(c["title"][:12] for c in nonmil))
    check_ge("人事/制度/仕途/经济 合计", len(nonmil), 9)

    print("\n=== 5. 近世覆盖（宋元明清，制度最接近现代组织）===")
    # 两个坑都踩过，别再踩：
    #  1) 不能用裸「元」——"汉元年"含"元"；不能用裸「宋」——"南朝宋元嘉八年"含"宋"
    #  2) 不能用「明」子串——"陈·祯明二年"含"祯明"。明代须用前缀匹配。
    NEAR_KEYS = ("北宋", "南宋", "宋·", "辽", "元·")
    near = [c for c in cases
            if any(k in c["era"] for k in NEAR_KEYS) or c["era"].startswith("明")]
    print("  命中 %d 条：%s" % (len(near), "、".join(
        "%s(%s)" % (c["id"], c["era"][:10]) for c in near)))
    check_ge("宋元明清合计", len(near), 6)

    print("\n=== 6. 完整性回归（防扩容改坏）===")
    req = ("title", "era", "protagonist", "source", "tier", "archetype", "sv_tags",
           "sources", "situation", "decision_point", "action", "outcome", "lesson",
           "counterfactual", "failure_if", "stratagem")
    check("字段缺失为 0", not [c["id"] for c in cases if not all(k in c for k in req)])
    check("全部 T1", all(c["tier"] == "T1" for c in cases))
    keys = set(cd["meta"]["sv_legend"])
    check("sv_tags 维度与 meta 一致",
          not [c["id"] for c in cases if set(c["sv_tags"]) != keys])
    sids = {s["id"] for s in stras}
    check("史案->兵计 零失效",
          not sorted({x for c in cases for x in c["stratagem"]} - sids))
    check("孤立史案为 0",
          not sorted({c["id"] for c in cases} -
                     {x for s in stras for x in s.get("case_ids", [])}))

    print("\n" + "=" * 62)
    print("  PASS=%d  FAIL=%d   案例 %d 条 / 兵计 %d 条 / 二十四史 %d/24"
          % (PASS, FAIL, len(cases), len(stras), len(covered)))
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
