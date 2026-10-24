#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
史衡 · 五链决策模型 —— 三层检索器（L1 扩展）
SHIHENG Five-Chain / Layer 1: Hybrid Retriever

设计动机（踩坑后固化）：
    旧版 L1 只扫 cases.json 的 64 条史案 + stratagems.json 的 36 条兵计，
    用 11 维向量距离排序。结果是「田忌赛马」「破釜沉舟」这类典型案例反复命中，
    与用户具体处境脱节——因为检索源是死的、封闭的，且只有「结构距离」这一个信号。

本模块把检索升级为三层 + 一个联网出口，统一由 ShihengEngine 调用：

    层 1  文本判据检索    corpus_bing.json 的 45 条兵书原文判据
                         （孙子 31 / 吴子 3 / 六韬 3 / 三略 2 / 尉缭子 2 /
                           司马法 1 / 问对 1 / 孙膑 1 / 三十六计 1）
                         —— 回答「经典文本对这类结构说了什么判据」
    层 2  结构史案检索    cases.json 的 64 条史案（保留原有向量距离）
                         —— 回答「历史上有谁遇到过同构局面」
    层 3  博弈机制检索    game_models.json 的 34 个博弈模型
                         —— 回答「这个局靠哪条机制运行、判据是什么、什么条件下反转」

    联网检索              通过外部 WebSearch 实时查史料/兵书/博弈论文献，
                         本地三层作为兜底与「来源等级」校验。检索动作由上层
                         （Agent）执行，本模块只提供「该搜什么」的查询构造器。

核心原则（对应 SKILL.md 的诉求）：
    - 不要复用固定典型案例，要在「史料+兵书+博弈论」范围内按处境检索
    - 每个结论都要能落到用户的具体处境（谁、对谁、筹码、退路）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine_common import normalize_sv, sv_distance  # 复用引擎的编码与距离

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


# ---------------------------------------------------------------------------
# 文本检索的轻量分词与打分（纯标准库，无第三方依赖）
# ---------------------------------------------------------------------------

# 常见中英文停用词，避免虚词主导匹配
_STOP = set("的了是在和与或于对为就被把但从而及以其所者之也都不没有又很更最这那一个些我你他她它我们你们他们它们什么怎么如何因为所以如果那么已经正在可以需要应该".split())


def _tokenize(text: str) -> List[str]:
    """极简中文分词：单字为最小单位，连续字母/数字并为词。"""
    toks: List[str] = []
    buf = ""
    for ch in str(text).lower():
        if ch.isalnum() and ord(ch) < 128:
            buf += ch
        else:
            if buf:
                toks.append(buf)
                buf = ""
            if '\u4e00' <= ch <= '\u9fff':
                toks.append(ch)
    if buf:
        toks.append(buf)
    return [t for t in toks if t not in _STOP and len(t) <= 32]


def _ngrams(tokens: List[str], n: int = 2) -> List[str]:
    """生成字符 n-gram（对中文，2-gram 能抓住双字词）。"""
    if len(tokens) < n:
        return tokens[:]
    return ["".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def text_score(query: str, text: str) -> float:
    """
    文本相似度打分，返回 0..1。

    采用 n-gram 重叠（Jaccard）+ 关键词命中加权，对中文短文本足够稳定，
    且无需任何第三方依赖。数值只作相对排序，不声称语义精确。
    """
    if not query or not text:
        return 0.0
    q_tok = _tokenize(query)
    t_tok = _tokenize(text)
    if not q_tok or not t_tok:
        return 0.0

    q1, t1 = set(_ngrams(q_tok, 1)), set(_ngrams(t_tok, 1))
    q2, t2 = set(_ngrams(q_tok, 2)), set(_ngrams(t_tok, 2))

    uni = len(q1 & t1) / len(q1 | t1) if (q1 | t1) else 0.0
    bi = len(q2 & t2) / len(q2 | t2) if (q2 | t2) else 0.0

    # 2-gram 命中权重更高（双字词更具体）
    return round(0.4 * uni + 0.6 * bi, 4)


# ---------------------------------------------------------------------------
# 结果容器
# ---------------------------------------------------------------------------

@dataclass
class CorpusHit:
    """一条兵书原文判据的检索命中。"""
    id: str
    book: str
    juan: str
    quote_type: str
    quote: str
    plain: str
    mechanism: List[str]
    use: str
    failure_if: str
    score: float
    game_models: List[str] = field(default_factory=list)
    tier: str = "T1"


@dataclass
class ModelHit:
    """一个博弈模型的检索命中。"""
    id: str
    name: str
    en: str
    family: str
    archetype: str
    structure: str
    diagnosis: List[str]
    conclusion: str
    failure: List[str]
    modern: List[str]
    counter: str
    score: float
    matched_diagnosis: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 三层检索器
# ---------------------------------------------------------------------------

class HybridRetriever:
    """
    三层检索器。数据惰性加载，构造时传入 data_dir。

    使用方式（引擎内部）：
        r = HybridRetriever(data_dir)
        hits = r.retrieve_corpus(sv, situation_text, top_k=5)     # 层1 判据
        models = r.retrieve_models(sv, situation_text, top_k=5)   # 层3 模型
    """

    def __init__(self, data_dir: str = DATA):
        self.data_dir = data_dir
        self._corpus: Optional[List[Dict[str, Any]]] = None
        self._models: Optional[List[Dict[str, Any]]] = None

    # -- 数据加载 ----------------------------------------------------------
    @property
    def corpus(self) -> List[Dict[str, Any]]:
        if self._corpus is None:
            with open(os.path.join(self.data_dir, "corpus_bing.json"),
                      encoding="utf-8") as f:
                self._corpus = json.load(f).get("entries", [])
        return self._corpus

    @property
    def models(self) -> List[Dict[str, Any]]:
        if self._models is None:
            with open(os.path.join(self.data_dir, "game_models.json"),
                      encoding="utf-8") as f:
                self._models = json.load(f).get("models", [])
        return self._models

    # -- 处境文本构造 ------------------------------------------------------
    # 每个维度取值 -> 中文白话，用于把标签处境翻译成可检索的自然语言。
    # 这是「语义检索」的关键：不是拿英文标签去比，而是拿「处境描述」去比。
    _DIM_PHRASES = {
        "power_ratio": {
            "very_weak": "实力悬殊处于劣势", "weak": "实力较弱处于下风",
            "even": "双方实力相当", "strong": "实力占优", "very_strong": "占绝对优势",
        },
        "stakes": {
            "low": "赌注很小输了也没关系", "medium": "赌注一般",
            "high": "赌注很大", "existential": "生死存亡的赌注没有退路",
        },
        "horizon": {
            "single": "一锤子买卖以后不再来往",
            "repeated": "长期共处以后还要打交道",
        },
        "opponent_rationality": {
            "myopic": "对手短视只看眼前", "rational": "对手理性会算账",
            "vindictive": "对手记仇会报复",
        },
        "time_pressure": {
            "low": "时间充裕", "medium": "时间一般", "high": "时间紧迫必须尽快决定",
        },
        "resource_slack": {
            "low": "资源紧张没有余量", "medium": "资源一般",
            "high": "资源充裕有腾挪空间",
        },
        "moral_constraint": {
            "low": "道德约束低", "medium": "道德约束中等",
            "high": "道德约束高不能越线",
        },
    }

    @classmethod
    def situation_text(cls, sv: Dict[str, Any],
                       extra_text: str = "") -> str:
        """
        把处境向量转成一段中文白话，供文本检索使用。
        extra_text 是用户对处境的具体描述（谁、对谁、筹码、退路），优先级最高。
        """
        parts = [extra_text.strip()] if extra_text and extra_text.strip() else []
        for dim in ("power_ratio", "stakes", "horizon",
                    "opponent_rationality", "time_pressure",
                    "resource_slack", "moral_constraint"):
            v = str(sv.get(dim, ""))
            phrase = cls._DIM_PHRASES.get(dim, {}).get(v)
            if phrase:
                parts.append(phrase)
        rev = float(sv.get("reversibility", 0.5))
        if rev < 0.35:
            parts.append("不可逆做错了无法回头")
        elif rev > 0.65:
            parts.append("高度可逆随时可以反悔")
        ia = float(sv.get("info_asym", 0.0))
        if ia < -0.3:
            parts.append("信息不对称对我不利对方更懂内情")
        elif ia > 0.3:
            parts.append("信息优势我更了解内情")
        if int(sv.get("actors", 2)) >= 3:
            parts.append("多方参与涉及第三方")
        if bool(sv.get("third_party", False)):
            parts.append("存在第三方裁判盟友或观众")
        return " ".join(parts)

    # -- 层1：文本判据检索 -------------------------------------------------
    def retrieve_corpus(self, sv: Dict[str, Any],
                        situation_text: str = "",
                        top_k: int = 5) -> List[CorpusHit]:
        """
        在兵书原文判据库中检索。匹配信号 = 原文 + 白话 + 机制名 + 使用场景
        + 标签 的文本重叠度，与处境文本比对。tags 关键词命中额外加权，
        因为它是最具区分度的结构化信号。
        """
        q = situation_text or self.situation_text(sv)
        q_toks = set(_ngrams(_tokenize(q), 2)) | set(_tokenize(q))
        scored: List[CorpusHit] = []
        for e in self.corpus:
            hay = " ".join([
                e.get("quote", ""),
                e.get("plain", ""),
                " ".join(e.get("mechanism", [])),
                e.get("use", ""),
            ])
            s = text_score(q, hay)
            # tags 关键词命中加权：每个命中的 tag 词 +0.12，封顶 +0.6
            tag_bonus = 0.0
            for t in e.get("tags", []):
                if t and t in q:
                    tag_bonus += 0.12
            tag_bonus = min(tag_bonus, 0.6)
            s = round(min(1.0, s + tag_bonus), 4)
            if s <= 0.0:
                continue
            scored.append(CorpusHit(
                id=e.get("id", "?"),
                book=e.get("book", ""),
                juan=e.get("juan", ""),
                quote_type=e.get("quote_type", ""),
                quote=e.get("quote", ""),
                plain=e.get("plain", ""),
                mechanism=e.get("mechanism", []),
                use=e.get("use", ""),
                failure_if=e.get("failure_if", ""),
                game_models=e.get("game_models", []),
                tier=e.get("tier", "T1"),
                score=s,
            ))
        scored.sort(key=lambda x: -x.score)
        return scored[:top_k]

    # -- 层3：博弈机制检索 -------------------------------------------------
    def retrieve_models(self, sv: Dict[str, Any],
                        situation_text: str = "",
                        top_k: int = 5,
                        min_diagnosis_hits: int = 1) -> List[ModelHit]:
        """
        在博弈模型库中检索。用两条信号：
          1. 文本重叠（structure/conclusion/modern/tags 与处境文本）
          2. diagnosis 判据命中数（把判据里的关键词拆出来，看处境文本是否命中）
        命中 >= 2 条判据视为强适用；只命中 1 条标注为弱相关。
        """
        q = situation_text or self.situation_text(sv)
        q_toks = set(_ngrams(_tokenize(q), 2))

        scored: List[ModelHit] = []
        for m in self.models:
            hay = " ".join([
                m.get("structure", ""),
                m.get("conclusion", ""),
                " ".join(m.get("modern", [])),
                " ".join(m.get("tags", [])),
            ])
            s = text_score(q, hay)

            # 判据命中：用 2-gram 实义双字词（去掉单字噪声）与处境文本重叠。
            # 要求重叠至少 1 个双字词，避免「对手理性会算账」中的单字「算」
            # 误命中「先算后动」这类判据。
            matched: List[str] = []
            for diag in m.get("diagnosis", []):
                d_2g = set(_ngrams(_tokenize(diag), 2))
                overlap = d_2g & q_toks
                if overlap:
                    matched.append(diag)
            # 综合分：文本 0.5 + 判据命中 0.5（每命中一条 +0.25，封顶 0.5）
            diag_score = min(0.5, 0.25 * len(matched))
            score = round(0.5 * s + diag_score, 4)

            if score <= 0.0 and not matched:
                continue
            scored.append(ModelHit(
                id=m.get("id", "?"),
                name=m.get("name", ""),
                en=m.get("en", ""),
                family=m.get("family", ""),
                archetype=m.get("archetype", ""),
                structure=m.get("structure", ""),
                diagnosis=m.get("diagnosis", []),
                conclusion=m.get("conclusion", ""),
                failure=m.get("failure", []),
                modern=m.get("modern", []),
                counter=m.get("counter", ""),
                score=score,
                matched_diagnosis=matched,
            ))

        # 强适用优先（判据命中 >= 2），再按综合分
        def sort_key(h: ModelHit) -> Tuple[int, float]:
            strong = 1 if len(h.matched_diagnosis) >= 2 else 0
            return (strong, h.score)

        scored.sort(key=sort_key, reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# 联网检索查询构造器
# ---------------------------------------------------------------------------

# 联网检索的权威来源白名单。检索必须在「史料+兵书+博弈论」范围内，
# 防止检索漂移到营销号或二手解读。
WEB_SOURCES = {
    "正史": ["二十四史", "史记", "资治通鉴", "汉书", "后汉书", "三国志",
             "晋书", "宋史", "明史", "旧唐书", "新唐书", "元史"],
    "兵书": ["孙子兵法", "孙膑兵法", "吴子", "六韬", "三略", "尉缭子",
             "司马法", "李卫公问对", "三十六计", "武经七书"],
    "博弈论": ["博弈论", "纳什均衡", "囚徒困境", "信号博弈", "重复博弈",
               "序贯博弈", "斗鸡博弈", "斯塔克尔伯格"],
}


# 处境结构 → 正史里常见的结构性表述（按结构检索，不按典故名，
# 避免又回到「复用田忌赛马/破釜沉舟这类典型案例」的老路）
STRUCT_TERMS = {
    "PRISONERS_DILEMMA": "相疑 相攻 俱败 盟约 背约",
    "CHICKEN": "相持 不退 死地 决战 对峙",
    "STAG_HUNT": "合纵 约从 连横 共击 会盟",
    "BOXED_PIGS": "坐观 承弊 附庸 借力",
    "DEADLOCK": "必取 势成 兼并 既定",
    "SIGNALING": "示弱 疑兵 伪遁 遣使 觇",
    "STACKELBERG": "先发 制人 袭其后 断其粮 攻其所必救",
    "REPEATED": "世好 岁贡 约为兄弟 累世 通好",
    "COALITION": "连和 约盟 三分 犄角 并力",
}


def build_web_queries(sv: Dict[str, Any],
                      situation_text: str = "",
                      archetype: str = "") -> List[Dict[str, str]]:
    """
    构造联网检索查询。返回 [(scope, query), ...]，由上层（Agent）逐条 WebSearch。

    scope 决定检索落在哪个范围：正史 / 兵书 / 博弈论。
    每条查询都带上来源限定词，确保结果可回源核验。
    """
    q = situation_text or HybridRetriever.situation_text(sv)
    queries: List[Dict[str, str]] = []

    # 博弈论：按推断原型锁定术语
    arch = archetype or _infer_archetype(sv)
    arch_terms = {
        "PRISONERS_DILEMMA": "囚徒困境 博弈论",
        "CHICKEN": "斗鸡博弈 承诺 博弈论",
        "STAG_HUNT": "猎鹿博弈 信任 博弈论",
        "BOXED_PIGS": "智猪博弈 搭便车",
        "DEADLOCK": "死锁博弈 博弈论",
        "SIGNALING": "信号博弈 分离均衡 博弈论",
        "STACKELBERG": "序贯博弈 先动优势 博弈论",
        "REPEATED": "重复博弈 触发策略 博弈论",
        "COALITION": "联盟博弈 夏普利值",
    }
    queries.append({
        "scope": "博弈论",
        "query": "%s %s" % (arch_terms.get(arch, "博弈论 纳什均衡"), q),
    })

    # 兵书：检索经典原文判据
    queries.append({
        "scope": "兵书",
        "query": "%s 原文 谋略 出处" % q,
    })

    # 正史原文：历史部分的主通道，按处境结构检索并回源到篇目
    arch = archetype or _infer_archetype(sv)
    queries.append({
        "scope": "正史原文",
        "query": "史记 资治通鉴 %s %s" % (STRUCT_TERMS.get(arch, "谋 策 议 计"), q),
    })

    return queries


def _infer_archetype(sv: Dict[str, Any]) -> str:
    """轻量原型推断，供查询构造器用（不依赖 nash_core，避免循环导入）。"""
    if int(sv.get("actors", 2)) >= 3 and bool(sv.get("third_party", False)):
        return "COALITION"
    if str(sv.get("horizon", "single")) == "repeated":
        return "REPEATED"
    if float(sv.get("info_asym", 0.0)) >= 0.4:
        return "SIGNALING"
    if str(sv.get("stakes", "medium")) in ("existential", "high") \
            and float(sv.get("reversibility", 0.5)) < 0.35:
        return "CHICKEN"
    return "STACKELBERG"


# ---------------------------------------------------------------------------
# 正史检索：历史部分的主通道（优先于本地 64 条精简样本）
# ---------------------------------------------------------------------------

# 二十四史 + 《资治通鉴》：命中即 T1 正史原文
CANONICAL_HISTORY = [
    "史记", "汉书", "后汉书", "三国志", "晋书", "宋书", "南齐书", "梁书",
    "陈书", "魏书", "北齐书", "周书", "隋书", "南史", "北史", "旧唐书",
    "新唐书", "旧五代史", "新五代史", "宋史", "辽史", "金史", "元史", "明史",
    "资治通鉴",
]
# 其他史部/政书/子部史著：T2
SEMI_HISTORY = ["国语", "战国策", "左传", "春秋", "通典", "文献通考",
                "贞观政要", "史通", "清史稿", "竹书纪年", "世说新语"]
# 小说/演义层：T3，禁止当决策依据
FICTION = ["演义", "小说", "三国志通俗", "封神", "西游记", "水浒", "说唐",
           "杨家将", "岳飞传（评书）"]


def build_history_queries(sv: Dict[str, Any],
                          situation_text: str = "",
                          archetype: str = "",
                          limit: int = 3) -> List[Dict[str, str]]:
    """
    构造「正史原文」检索式——历史部分的主通道。

    与 build_web_queries 的区别：这里**按处境结构检索正史原文**，
    不去搜固定典故名（如「田忌赛马」「破釜沉舟」），
    以免又回到「复用典型案例」的老路。

    返回 [{scope, query, purpose}]，由上层（Agent）逐条 WebSearch。
    """
    q = situation_text or HybridRetriever.situation_text(sv)
    arch = archetype or _infer_archetype(sv)

    # 处境结构 → 正史里常见的结构性表述（按结构检索，不按典故名）
    struct_terms = {
        "PRISONERS_DILEMMA": "相疑 相攻 俱败 盟约 背约",
        "CHICKEN": "相持 不退 死地 决战 对峙",
        "STAG_HUNT": "合纵 约从 连横 共击 会盟",
        "BOXED_PIGS": "坐观 承弊 附庸 借力",
        "DEADLOCK": "必取 势成 兼并 既定",
        "SIGNALING": "示弱 疑兵 伪遁 遣使 觇",
        "STACKELBERG": "先发 制人 袭其后 断其粮 攻其所必救",
        "REPEATED": "世好 岁贡 约为兄弟 累世 通好",
        "COALITION": "连和 约盟 三分 犄角 并力",
    }
    st = struct_terms.get(arch, "谋 策 议 计")

    queries: List[Dict[str, str]] = []
    # 1) 史记 + 通鉴 优先（叙事最完整、最易回源核验）
    queries.append({
        "scope": "正史原文",
        "query": "史记 资治通鉴 %s %s" % (st, q),
        "purpose": "在《史记》《资治通鉴》中找同构史事，回源到篇目",
    })
    # 2) 二十四史原文
    queries.append({
        "scope": "正史原文",
        "query": "二十四史 %s %s 原文 本纪 列传" % (st, q),
        "purpose": "扩大到二十四史本纪/列传原文",
    })
    # 3) 具体决策动作（看当时实际怎么做的，便于迁移）
    if limit >= 3:
        queries.append({
            "scope": "正史原文",
            "query": "%s 决策 应对 结果 %s 汉书 后汉书 三国志" % (st, q),
            "purpose": "定位史事中的具体决策动作与结局",
        })
    return queries[:max(1, limit)]


def validate_history_source(text: str) -> Tuple[bool, str, str]:
    """
    正史来源定级。返回 (是否可用, 等级, 命中的书名)。

    等级：
        T1-正史原文   二十四史 / 《资治通鉴》原文 —— 可作决策依据
        T2-史部其他   其他史部、政书 —— 可作旁证
        T3-小说敷衍   演义/小说 —— 仅作反面参照，禁止当依据
        未知来源      不可核验
    """
    if not text:
        return (False, "未知来源", "")
    for f in FICTION:
        if f in text:
            return (False, "T3-小说敷衍", f)
    for b in CANONICAL_HISTORY:
        if b in text:
            return (True, "T1-正史原文", b)
    for b in SEMI_HISTORY:
        if b in text:
            return (True, "T2-史部其他", b)
    return (False, "未知来源", "")


def validate_web_source(text: str) -> Tuple[bool, str]:
    """
    校验一段联网检索结果的来源等级。
    返回 (是否落在白名单范围, 来源等级)。用于把联网结果与本地库对齐，
    防止把小说、演义、营销号解读当作可复用依据。
    """
    if not text:
        return (False, "empty")
    lowered = text
    # 演义/小说层标记：命中即降级
    fiction = ("演义", "小说", "三国志通俗", "封神", "西游记", "水浒")
    for f in fiction:
        if f in lowered:
            return (False, "T3-小说敷衍")
    # 权威来源标记
    for scope, terms in WEB_SOURCES.items():
        for t in terms:
            if t in lowered:
                return (True, scope)
    return (False, "未知来源")


if __name__ == "__main__":
    # 自检：一个低赌注、可逆、长期共处的处境，应命中「田忌赛马」而非生死案例
    sv = {"power_ratio": "even", "stakes": "low", "reversibility": 0.9,
          "info_asym": 0.0, "time_pressure": "medium", "horizon": "repeated",
          "actors": 2, "third_party": False, "resource_slack": "medium",
          "opponent_rationality": "rational", "moral_constraint": "medium"}
    r = HybridRetriever()
    q = r.situation_text(sv)
    print("处境文本:", q)
    print()
    print("== 层1 兵书判据 Top-5 ==")
    for h in r.retrieve_corpus(sv, q, top_k=5):
        print("  %s 《%s·%s》 %.3f  %s" % (h.id, h.book, h.juan, h.score, h.plain[:30]))
    print()
    print("== 层3 博弈模型 Top-5 ==")
    for h in r.retrieve_models(sv, q, top_k=5):
        flag = "强" if len(h.matched_diagnosis) >= 2 else "弱"
        print("  %s %s(%.3f)[%s] %s" % (h.id, h.name, h.score, flag, h.structure[:30]))
    print()
    print("== 联网查询构造 ==")
    for qq in build_web_queries(sv, q):
        print("  [%s] %s" % (qq["scope"], qq["query"]))
