#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
史衡 · 五链决策模型 —— 共享的处境编码与距离（engine.py 与 retriever.py 共用）

从 engine.py 抽离出来，避免 engine.py 与 retriever.py 相互导入造成循环依赖。
单一来源（single source of truth）：处境向量的序数映射、判别权重、归一化、
加权距离都只在此定义一次。
"""

from __future__ import annotations

from typing import Any, Dict


# 枚举 -> 序数，便于距离计算
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
