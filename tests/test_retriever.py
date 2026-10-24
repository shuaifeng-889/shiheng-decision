#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
三层检索器验收（retriever.py）—— 证明检索是「按处境语义检索」而非「固定案例复用」。

判据：
  1. 处境文本能把标签处境翻译成中文白话（不是英文标签拼接）；
  2. 两个结构迥异的处境，兵书判据检索结果必须不同（判别力）；
  3. 两个结构迥异的处境，博弈机制检索结果必须不同（判别力）；
  4. 联网查询构造器按 scope 生成三条查询（博弈论/兵书/正史），且带来源限定词；
  5. 来源校验能识别演义/小说层并降级，能识别权威来源。
"""

from __future__ import annotations

import os
import sys


def _force_utf8() -> None:
    for _name in ("stdout", "stderr"):
        _stream = getattr(sys, _name, None)
        try:
            if _stream is not None and hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


_force_utf8()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from retriever import (HybridRetriever, build_history_queries,  # noqa: E402
                       build_web_queries, validate_history_source,
                       validate_web_source, text_score)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s  %-52s got=%s" % ("PASS" if ok else "FAIL", name, got))


# 两个结构迥异的处境
SV_EXISTENTIAL = {
    "power_ratio": "weak", "stakes": "existential", "reversibility": 0.2,
    "info_asym": -0.4, "time_pressure": "high", "horizon": "repeated",
    "actors": 3, "third_party": True, "resource_slack": "low",
    "opponent_rationality": "rational", "moral_constraint": "high",
}
SV_LOWSTAKES = {
    "power_ratio": "even", "stakes": "low", "reversibility": 0.9,
    "info_asym": 0.0, "time_pressure": "medium", "horizon": "repeated",
    "actors": 2, "third_party": False, "resource_slack": "medium",
    "opponent_rationality": "rational", "moral_constraint": "medium",
}


def _ids(hits):
    return tuple(h.id for h in hits)


if __name__ == "__main__":
    r = HybridRetriever(data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))

    print("\n=== 1. 处境文本构造 ===\n")
    q_exist = r.situation_text(SV_EXISTENTIAL)
    q_low = r.situation_text(SV_LOWSTAKES)
    print("  生死存亡处境文本: %s" % q_exist)
    print("  低赌注处境文本:   %s" % q_low)
    check("处境文本含中文白话而非英文标签",
          ("实力" in q_exist and "弱" in q_exist and "even" not in q_exist), True)
    check("生死存亡处境含「不可逆」",
          "不可逆" in q_exist, True)
    check("低赌注处境含「可逆/反悔」",
          ("可逆" in q_low or "反悔" in q_low), True)
    check("两个处境文本不同", q_exist != q_low, True)

    print("\n=== 2. 兵书判据检索判别力 ===\n")
    c_exist = r.retrieve_corpus(SV_EXISTENTIAL, q_exist, top_k=5)
    c_low = r.retrieve_corpus(SV_LOWSTAKES, q_low, top_k=5)
    print("  生死存亡判据 Top-5: %s" % [h.id for h in c_exist])
    print("  低赌注判据 Top-5:   %s" % [h.id for h in c_low])
    check("判据检索非空（生死存亡）", len(c_exist) > 0, True)
    check("判据检索非空（低赌注）", len(c_low) > 0, True)
    check("两个处境的判据 Top-5 不完全相同", _ids(c_exist) != _ids(c_low), True)
    check("判据命中带原文（可回源）", all(h.quote for h in c_exist[:3]), True)

    print("\n=== 3. 博弈机制检索判别力 ===\n")
    m_exist = r.retrieve_models(SV_EXISTENTIAL, q_exist, top_k=5)
    m_low = r.retrieve_models(SV_LOWSTAKES, q_low, top_k=5)
    print("  生死存亡机制 Top-5: %s" % [h.id for h in m_exist])
    print("  低赌注机制 Top-5:   %s" % [h.id for h in m_low])
    check("机制检索非空（生死存亡）", len(m_exist) > 0, True)
    check("机制检索非空（低赌注）", len(m_low) > 0, True)
    check("两个处境的机制 Top-5 不完全相同", _ids(m_exist) != _ids(m_low), True)
    check("机制命中带失效条件", all(h.failure for h in m_exist[:3]), True)

    print("\n=== 4. 联网查询构造器 ===\n")
    qs = build_web_queries(SV_EXISTENTIAL, q_exist, archetype="PRISONERS_DILEMMA")
    scopes = [q["scope"] for q in qs]
    print("  scopes: %s" % scopes)
    check("生成三条查询", len(qs), 3)
    check("覆盖博弈论/兵书/正史原文三个范围",
          set(scopes) == {"博弈论", "兵书", "正史原文"}, True)
    check("博弈论查询带原型术语",
          "囚徒困境" in qs[0]["query"], True)
    check("正史查询带来源限定词",
          ("二十四史" in qs[2]["query"] or "资治通鉴" in qs[2]["query"]), True)

    print("\n=== 5. 来源校验 ===\n")
    ok_fiction, tier_fiction = validate_web_source("《三国演义》里诸葛亮空城计……")
    ok_canon, tier_canon = validate_web_source("《资治通鉴·唐纪三十九》载郭子仪单骑退回纥……")
    ok_bing, tier_bing = validate_web_source("《孙子兵法·计篇》：兵者国之大事……")
    check("演义来源判为不可用", ok_fiction, False)
    check("演义来源判为 T3", tier_fiction, "T3-小说敷衍")
    check("正史来源判为可用", ok_canon, True)
    check("正史来源落在正史范围", tier_canon, "正史")
    check("兵书来源落在兵书范围", tier_bing, "兵书")

    print("\n=== 6. 文本打分基本性质 ===\n")
    s_same = text_score("长期共处 对手理性会算账", "长期共处 对手理性会算账")
    s_diff = text_score("长期共处 对手理性会算账", "生死存亡 破釜沉舟")
    check("相同文本打分高于不同文本", s_same > s_diff, True)
    check("打分在 0..1 区间", 0.0 <= s_same <= 1.0 and 0.0 <= s_diff <= 1.0, True)

    print("\n=== 7. 正史检索（历史部分主通道）===\n")
    hq = build_history_queries(SV_EXISTENTIAL, q_exist, archetype="PRISONERS_DILEMMA")
    check("生成正史检索式", len(hq) >= 2, True)
    check("正史检索式均标记为正史原文",
          all(q["scope"] == "正史原文" for q in hq), True)
    check("优先检索史记与资治通鉴",
          ("史记" in hq[0]["query"] and "资治通鉴" in hq[0]["query"]), True)
    check("按处境结构检索而非固定典故名",
          not any(k in " ".join(q["query"] for q in hq)
                  for k in ("田忌赛马", "破釜沉舟", "空城计")), True)
    # 不同原型应生成不同的结构检索词
    hq2 = build_history_queries(SV_EXISTENTIAL, q_exist, archetype="COALITION")
    check("不同原型的结构检索词不同",
          hq[0]["query"] != hq2[0]["query"], True)

    print("\n=== 8. 正史来源定级 ===\n")
    cases = [
        ("《史记·项羽本纪》载沛公…", True, "T1-正史原文"),
        ("《资治通鉴·唐纪三十九》…", True, "T1-正史原文"),
        ("《汉书·食货志》…", True, "T1-正史原文"),
        ("《国语·晋语》…", True, "T2-史部其他"),
        ("《三国演义》诸葛亮…", False, "T3-小说敷衍"),
        ("某自媒体解读", False, "未知来源"),
    ]
    for text, want_ok, want_tier in cases:
        ok, tier, book = validate_history_source(text)
        check("来源定级 %s" % text[:14], (tier == want_tier and ok == want_ok), True)

    print("\n" + "=" * 64)
    print("  PASS=%d  FAIL=%d" % (PASS, FAIL))
    print("=" * 64)
    sys.exit(1 if FAIL else 0)
