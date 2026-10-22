#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
史衡 · 五链决策模型 —— 命令行入口

零依赖（仅标准库），无需安装即可运行：

    python scripts/cli.py decide -i my_situation.json
    python scripts/cli.py decide --interactive
    python scripts/cli.py cases --search 粮道
    python scripts/cli.py validate

设计原则：CLI 是 Skill 的「无 Agent 模式」。Agent 读 SKILL.md 走五层链，
人直接敲命令走同一个引擎 —— 两者共用 scripts/engine.py，不会产生行为漂移。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from engine import (  # noqa: E402
    ARCHETYPES,
    DATA,
    ORDINAL,
    WEIGHTS,
    ShihengEngine,
    encode_sv,
    render,
)

PROG = "shiheng"

# 12 维处境向量的取值域，供交互式输入校验与 sv-template 输出
SV_SCHEMA = {
    "power_ratio": (["very_weak", "weak", "even", "strong", "very_strong"],
                    "相对实力：谈崩了谁先扛不住"),
    "stakes": (["low", "medium", "high", "existential"],
               "赌注：最坏是亏钱，还是没有以后"),
    "reversibility": ("float01", "可逆性 0..1：后悔时撤销代价多大"),
    "info_asym": ("float_pm1", "信息优势 -1..1：正数=你更懂，负数=对方更懂"),
    "time_pressure": (["low", "medium", "high"], "时间压力"),
    "horizon": (["single", "repeated"], "视野：一次性，还是长期共处"),
    "actors": ("int2", "参与方数量：2 或 3+"),
    "third_party": ("bool", "是否存在第三方（裁判/盟友/观众）"),
    "resource_slack": (["low", "medium", "high"], "资源余量：还有多少腾挪空间"),
    "opponent_rationality": (["myopic", "rational", "vindictive"],
                             "对手类型：短视/理性/记仇"),
    "moral_constraint": (["low", "medium", "high"], "道德约束强度"),
}

FOUR_DECISIVE = ("power_ratio", "stakes", "horizon", "reversibility")


# ---------------------------------------------------------------------------
# 输出工具
# ---------------------------------------------------------------------------

def _force_utf8() -> None:
    """Windows 控制台默认 GBK，直接 print 中文会抛 UnicodeEncodeError。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _hr(char: str = "-", width: int = 72) -> str:
    return char * width


def _die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[name-defined]
    print("错误：%s" % msg, file=sys.stderr)
    raise SystemExit(code)


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        _die("找不到文件：%s" % path)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        _die("JSON 解析失败（%s 第 %d 行）：%s" % (path, e.lineno, e.msg))
    except OSError as e:
        _die("读取失败：%s" % e)


# ---------------------------------------------------------------------------
# 处境向量：校验 / 交互 / 模板
# ---------------------------------------------------------------------------

def validate_sv(sv: dict) -> tuple[dict, list[str]]:
    """校验并补全 SV。返回 (规范化后的 sv, 警告列表)。不可修复的问题直接退出。"""
    warnings: list[str] = []
    missing = [k for k in SV_SCHEMA if k not in sv]

    if missing:
        warnings.append("缺失维度已按默认值补全：%s" % "、".join(missing))

    out: dict = {}
    for dim, (spec, desc) in SV_SCHEMA.items():
        raw = sv.get(dim)
        if raw is None:
            raw = {"float01": 0.5, "float_pm1": 0.0, "int2": 2,
                   "bool": False}.get(spec if isinstance(spec, str) else "", None)
            if raw is None:
                raw = spec[0]  # 枚举取首项
        if isinstance(spec, list):
            if raw not in spec:
                _die("维度 %s 取值 %r 非法，可选：%s" % (dim, raw, " / ".join(spec)))
            out[dim] = raw
        elif spec == "float01":
            try:
                v = float(raw)
            except (TypeError, ValueError):
                _die("维度 %s 需为 0..1 的小数，收到 %r" % (dim, raw))
            if not 0.0 <= v <= 1.0:
                _die("维度 %s 需在 0..1 之间，收到 %s" % (dim, v))
            out[dim] = v
        elif spec == "float_pm1":
            try:
                v = float(raw)
            except (TypeError, ValueError):
                _die("维度 %s 需为 -1..1 的小数，收到 %r" % (dim, raw))
            if not -1.0 <= v <= 1.0:
                _die("维度 %s 需在 -1..1 之间，收到 %s" % (dim, v))
            out[dim] = v
        elif spec == "int2":
            try:
                v = int(raw)
            except (TypeError, ValueError):
                _die("维度 %s 需为整数，收到 %r" % (dim, raw))
            if v < 2:
                _die("维度 %s 至少为 2，收到 %d" % (dim, v))
            out[dim] = v
        elif spec == "bool":
            out[dim] = bool(raw)

    # 四个决定性维度不允许含糊：缺失时只警告，但明确提示
    absent = [d for d in FOUR_DECISIVE if d not in sv]
    if absent:
        warnings.append(
            "决定性维度未显式给出，已用默认值：%s（结论可靠性下降，建议补全）"
            % "、".join(absent))

    return out, warnings


def interactive_sv() -> dict:
    """一次问 11 个问题，把自然语言答案交给 encode_sv 归一。"""
    print(_hr("="))
    print("史衡 · 处境编码（直接回车 = 使用括号内默认值）")
    print(_hr("="))
    print("先想清楚一句话：这次要做的决定是什么，最坏的结果是什么。\n")

    prompts = [
        ("power_ratio", "相对实力（悬殊弱/弱/相当/强/绝对优势）", "相当"),
        ("stakes", "赌注多大（很低/一般/大/生死存亡）", "一般"),
        ("reversibility", "可逆性 0..1，做错了能撤回多少（0=完全不可逆，1=随时可撤）", "0.5"),
        ("info_asym", "信息优势 -1..1（负数=对方比你更懂内情）", "0"),
        ("time_pressure", "时间压力（充裕/一般/紧迫）", "一般"),
        ("horizon", "这事之后还要跟对方打交道吗（一次性/长期共处）", "长期共处"),
        ("actors", "涉及几方（2 / 3）", "2"),
        ("third_party", "有没有第三方（裁判、盟友、观众）y/n", "n"),
        ("resource_slack", "你的资源余量（紧张/一般/充裕）", "一般"),
        ("opponent_rationality", "对手类型（短视/理性/记仇）", "理性"),
        ("moral_constraint", "道德约束强度（低/中/高）", "中"),
    ]

    answers: dict = {}
    for key, question, default in prompts:
        try:
            raw = input("%-18s %s [%s]：" % (key, question, default)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            raise SystemExit(130)
        answers[key] = raw if raw else default

    answers["actors"] = 3 if answers["actors"].strip().startswith("3") else 2
    answers["third_party"] = answers["third_party"].strip().lower() in ("y", "yes", "是", "有", "1")
    sv = encode_sv(answers)

    print("\n" + _hr())
    print("编码结果（请核对，尤其是四个决定性维度）：")
    print(_hr())
    for dim in SV_SCHEMA:
        flag = "  <-- 决定性" if dim in FOUR_DECISIVE else ""
        print("  %-22s %s%s" % (dim, sv[dim], flag))
    print()
    return sv


def sv_template() -> dict:
    return {
        "_comment": "史衡处境向量模板。删掉 _comment 与 _notes 后可直接传给 decide -i。",
        "power_ratio": "even",
        "stakes": "medium",
        "reversibility": 0.5,
        "info_asym": 0.0,
        "time_pressure": "medium",
        "horizon": "repeated",
        "actors": 3,
        "third_party": True,
        "resource_slack": "medium",
        "opponent_rationality": "rational",
        "moral_constraint": "medium",
        "_notes": {
            "power_ratio": "very_weak | weak | even | strong | very_strong —— 问「谈崩了谁先扛不住」",
            "stakes": "low | medium | high | existential —— 问「最坏是亏钱还是没有以后」",
            "reversibility": "0..1 小数 —— 问「后悔时撤销代价多大」，1 表示随时可撤",
            "info_asym": "-1..1 小数 —— 正数=你更了解内情，负数=对方更了解",
            "time_pressure": "low | medium | high",
            "horizon": "single | repeated —— 问「五年后还在同一圈子吗」",
            "actors": "整数，2 或更多",
            "third_party": "true | false —— 是否存在裁判、盟友、观众",
            "resource_slack": "low | medium | high —— 还有多少腾挪空间",
            "opponent_rationality": "myopic | rational | vindictive",
            "moral_constraint": "low | medium | high",
        },
    }


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_decide(args: argparse.Namespace) -> int:
    eng = ShihengEngine(DATA)

    if args.interactive:
        sv = interactive_sv()
        warnings: list[str] = []
    else:
        if args.input:
            sv = _load_json(args.input)
        elif not sys.stdin.isatty():
            try:
                sv = json.load(sys.stdin)
            except json.JSONDecodeError as e:
                _die("标准输入不是合法 JSON：%s" % e.msg)
        else:
            _die("需要处境向量：用 -i FILE 指定，或 --interactive 交互输入，"
                 "或 --template 先拿一个模板")
        sv, warnings = validate_sv(sv)

    payoffs = None
    if args.matrix:
        m = _load_json(args.matrix)
        try:
            a, b = m["A"], m["B"]
        except (KeyError, TypeError):
            _die("矩阵文件需含 \"A\" 与 \"B\" 两个二维数组")
        for name, mat in (("A", a), ("B", b)):
            if len(mat) != 2 or any(len(row) != 2 for row in mat):
                _die("目前只支持 2x2 收益矩阵，%s 的维度不对" % name)
        payoffs = (a, b)

    for w in warnings:
        print("提示：%s" % w, file=sys.stderr)

    report = eng.decide(sv, payoffs=payoffs, delta=args.delta,
                        top_k=args.top, moral_floor=args.moral)

    if args.format == "json":
        game = report["game"]
        safe = {
            "sv": report["sv"],
            "game": None if not game else {
                "archetype": (game.get("archetype") or {}).get("key"),
                "archetype_name": (game.get("archetype") or {}).get("name"),
                "structural_logic": (game.get("archetype") or {}).get("structural_logic"),
                "failure_mode": (game.get("archetype") or {}).get("failure_mode"),
                "payoffs": game.get("payoffs"),
                "pure_nash": [list(x) for x in (game.get("pure_nash") or [])],
                "mixed_nash": game.get("mixed_nash"),
                "commitment_value": (game.get("stackelberg") or {}).get("commitment_value"),
                "first_mover_premium": (game.get("stackelberg") or {}).get("first_mover_premium_row"),
                "repeated": game.get("repeated"),
            },
            "cases": [
                {"id": c.id, "name": c.name, "similarity": round(c.similarity, 4),
                 "archetype": c.archetype, "tier": c.detail.get("tier"),
                 "source": c.detail.get("source")}
                for c in report["cases"]
            ],
            "stratagems": [
                {"id": c.id, "name": c.name, "score": c.score,
                 "similarity": round(c.similarity, 4),
                 "game_fit": round(c.game_fit, 4),
                 "risk_penalty": round(c.risk_penalty, 4),
                 "archetype": c.archetype,
                 "red_flags": c.red_flags}
                for c in report["stratagems_ranked"]
            ],
            "shadow": report["shadow"],
        }
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        return 0

    if args.format == "brief":
        _print_brief(report, sv)
        return 0

    print(render(report))
    return 0


def _print_brief(report: dict, sv: dict) -> None:
    """精简输出：只给结论，适合反复调参时快速查看。"""
    game = report.get("game") or {}
    cases = report["cases"]
    strats = report["stratagems_ranked"]

    print(_hr("="))
    print("处境：实力=%s 赌注=%s 可逆=%.2f 视野=%s 余量=%s"
          % (sv["power_ratio"], sv["stakes"], sv["reversibility"],
             sv["horizon"], sv["resource_slack"]))
    print(_hr("="))

    if game:
        arch = game.get("archetype") or {}
        print("博弈结构：%s（%s）" % (arch.get("name", "?"), arch.get("key", "?")))
        if arch.get("structural_logic"):
            print("  结构    ：%s" % arch["structural_logic"])
        if arch.get("sunzi_ref"):
            print("  孙子对照：%s" % arch["sunzi_ref"])
        if arch.get("failure_mode"):
            print("  失效模式：%s" % arch["failure_mode"])

        po = game.get("payoffs") or {}
        if po:
            print("  收益序  ：R=%s T=%s S=%s P=%s%s"
                  % (po.get("R"), po.get("T"), po.get("S"), po.get("P"),
                     "（对称）" if game.get("symmetric") else "（非对称）"))
        eq = game.get("pure_nash")
        if eq:
            print("  纯策略均衡：%s" % (eq,))
        else:
            print("  纯策略均衡：无（需看混合策略）")
        mx = game.get("mixed_nash")
        if mx:
            print("  混合均衡：行选第一项概率 %.3f，列选第一项概率 %.3f"
                  % (mx["p_row0"], mx["q_col0"]))
        st = game.get("stackelberg") or {}
        if st:
            cv = st.get("commitment_value")
            fm = st.get("first_mover_premium_row")
            if cv is not None:
                print("  承诺价值：%+.2f%s" % (cv, "（正值=公开自缚有超额收益）" if cv > 0 else ""))
            if fm is not None:
                print("  先动溢价：%+.2f" % fm)
        rp = game.get("repeated") or {}
        if rp:
            print("  重复博弈：δ=%.2f，δ*=%.2f，%s"
                  % (rp.get("delta", 0), rp.get("delta_star") or 0,
                     "可持续" if rp.get("sustainable") else "不可持续"))
            if rp.get("reason"):
                print("            %s" % rp["reason"])
    else:
        print("博弈结构：未提供收益矩阵，按处境反推原型（用 -m 传入矩阵可做严格求解）")

    print("\n史案 Top-%d：" % len(cases))
    for i, c in enumerate(cases, 1):
        print("  %d. [%s] %s（相似度 %.0f%%，%s）"
              % (i, c.id, c.name, c.similarity * 100,
                 c.detail.get("tier", "?")))

    print("\n策略排序：")
    for i, c in enumerate(strats, 1):
        mark = "  <-- 首推" if i == 1 else ""
        print("  %d. %-10s 综合 %.3f（处境 %.2f / 博弈 %.2f / 风险 -%.2f）%s"
              % (i, c.name, c.score, c.similarity, c.game_fit,
                 c.risk_penalty, mark))

    shadow = report.get("shadow") or []
    if shadow:
        print("\n影子谏官：")
        for line in shadow:
            print("  - %s" % line)


def cmd_cases(args: argparse.Namespace) -> int:
    eng = ShihengEngine(DATA)

    if args.show:
        c = eng.case_by_id.get(args.show.upper())
        if not c:
            _die("没有编号为 %s 的案例（用 `cases --list` 查看全部）" % args.show)
        if args.format == "json":
            print(json.dumps(c, ensure_ascii=False, indent=2))
        else:
            _print_case(c)
        return 0

    items = eng.cases
    if args.archetype:
        items = [c for c in items if c.get("archetype") == args.archetype.upper()]
    if args.tier:
        items = [c for c in items if c.get("tier") == args.tier.upper()]
    if args.search:
        kw = args.search
        items = [c for c in items
                 if any(kw in str(v) for v in c.values())]

    if args.format == "json":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    print(_hr("="))
    print("史案库：%d 条（筛选后）" % len(items))
    print(_hr("="))
    for c in items:
        print("%-5s %-4s %-14s %s"
              % (c["id"], c["tier"], c.get("archetype", "?"), c["title"]))
        print("      %s" % c.get("source", ""))
    if not items:
        print("（无匹配。试试 `cases --search 关键词` 或去掉筛选条件）")
    return 0


def _print_case(c: dict) -> None:
    print(_hr("="))
    print("%s  %s" % (c["id"], c["title"]))
    print(_hr("="))
    print("时代      ：%s" % c.get("era", ""))
    print("主角      ：%s" % c.get("protagonist", ""))
    print("出处      ：%s（可信度 %s）" % (c.get("source", ""), c.get("tier", "")))
    srcs = c.get("sources") or []
    if srcs:
        detail = "；".join(
            "《%s·%s》%s" % (s.get("book", ""), s.get("juan", ""),
                             "（正史）" if s.get("canonical") else "")
            for s in srcs)
        print("结构化出处：%s" % detail)
    if c.get("quote"):
        print("\n原文      ：%s" % c["quote"])
    print("\n决策点    ：%s" % c.get("decision_point", ""))
    print("处境      ：%s" % c.get("situation", ""))
    print("行动      ：%s" % c.get("action", ""))
    print("结果      ：%s" % c.get("outcome", ""))
    print("\n迁移      ：%s" % c.get("lesson", ""))
    print("\n反事实    ：%s" % c.get("counterfactual", ""))
    print("失效条件  ：%s" % c.get("failure_if", ""))
    if c.get("stratagem"):
        print("关联兵计  ：%s" % "、".join(c["stratagem"]))
    print("博弈原型  ：%s" % c.get("archetype", ""))
    print()


def cmd_stratagem(args: argparse.Namespace) -> int:
    eng = ShihengEngine(DATA)

    if args.show:
        s = eng.strat_by_id.get(args.show.upper())
        if not s:
            _die("没有编号为 %s 的计策（S01..S36）" % args.show)
        if args.format == "json":
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            _print_stratagem(s)
        return 0

    items = eng.stratagems
    if args.archetype:
        items = [s for s in items if s.get("archetype") == args.archetype.upper()]

    if args.format == "json":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    print(_hr("="))
    print("三十六计：%d 条" % len(items))
    print(_hr("="))
    for s in items:
        warn = " [史料支撑不足]" if s.get("evidence_warning") else ""
        print("%-4s %-6s %-14s %s%s"
              % (s["id"], s.get("group", ""), s["name"], s.get("archetype", ""), warn))
    return 0


def _print_stratagem(s: dict) -> None:
    print(_hr("="))
    print("%s  %s（%s）" % (s["id"], s["name"], s.get("group", "")))
    print(_hr("="))
    print("要义      ：%s" % s.get("essence", ""))
    print("孙子依据  ：%s" % s.get("sunzi_ref", ""))
    print("博弈原型  ：%s" % s.get("archetype", ""))
    print("\n适用前提  ：%s" % s.get("premise", ""))
    print("\n现代迁移  ：%s" % s.get("modern", ""))
    fc = s.get("failure_conditions") or []
    print("\n失效条件  ：")
    for i, f in enumerate(fc, 1):
        print("  %d. %s" % (i, f))
    print("\n红线      ：%s" % s.get("redline", ""))
    if s.get("counter"):
        print("破法      ：%s" % s["counter"])
    if s.get("evidence_warning"):
        print("\n史料警告  ：%s" % s["evidence_warning"])
    ids = s.get("case_ids") or []
    print("\n史案支撑  ：%s" % ("、".join(ids) if ids else "（刻意留空——无可信正史案例）"))
    print()


def cmd_validate(args: argparse.Namespace) -> int:
    """数据完整性自检。贡献案例前先跑这个。"""
    tests_dir = os.path.normpath(os.path.join(HERE, "..", "tests"))
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    print(_hr("="))
    print("数据完整性校验")
    print(_hr("="))
    try:
        from test_corpus import main as corpus_main
    except ImportError as e:
        _die("找不到 tests/test_corpus.py，无法自检：%s" % e)
    code = corpus_main()
    return 0 if code in (None, 0) else 1


def cmd_archetypes(args: argparse.Namespace) -> int:
    print(_hr("="))
    print("九类博弈原型")
    print(_hr("="))
    for key, a in ARCHETYPES.items():
        print("%-20s %s（%s）" % (key, a.name, a.name_en))
        print("  结构：%s" % a.structural_logic)
        print("  兵计：%s" % "、".join(
            s for s in a.stratagem_ref.split("、")[:5]))
        print("  失效：%s" % a.failure_mode)
        print()
    print("权重表（相似度计算用，可直接改 scripts/engine.py 的 WEIGHTS）：")
    total = sum(WEIGHTS.values())
    for k, v in sorted(WEIGHTS.items(), key=lambda kv: -kv[1]):
        print("  %-22s %.1f  (%.0f%%)" % (k, v, v / total * 100))
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    print(json.dumps(sv_template(), ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="史衡 · 五链决策模型：博弈论 + 正史案例 + 三十六计的结构化决策工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  shiheng decide --interactive              交互式录入处境，出完整报告
  shiheng decide -i sv.json --format brief  从文件读处境，只出结论
  shiheng decide -i sv.json -m game.json    带上收益矩阵做严格博弈体检
  shiheng cases --search 粮道               检索史案
  shiheng cases --show C037                 看单条史案全文
  shiheng stratagem --show S19              看单计的前提/失效/红线
  shiheng template                         拿一个处境向量模板
  shiheng validate                          自检数据完整性
""")

    sub = p.add_subparsers(dest="cmd", metavar="<命令>")

    d = sub.add_parser("decide", help="跑五层链，输出决策报告")
    d.add_argument("-i", "--input", metavar="FILE", help="处境向量 JSON 文件")
    d.add_argument("--interactive", action="store_true", help="交互式录入处境")
    d.add_argument("-m", "--matrix", metavar="FILE",
                   help='2x2 收益矩阵 JSON（格式 {"A": [[..],[..]], "B": [[..],[..]]}）')
    d.add_argument("--delta", type=float, default=None,
                   help="重复博弈折现因子 0..1（配合矩阵使用）")
    d.add_argument("--top", type=int, default=5, help="候选数量，默认 5")
    d.add_argument("--moral", default="medium", choices=["low", "medium", "high"],
                   help="道德底线，影响风险折扣，默认 medium")
    d.add_argument("-f", "--format", default="md", choices=["md", "brief", "json"],
                   help="md=完整报告 / brief=只要结论 / json=结构化")
    d.set_defaults(func=cmd_decide)

    c = sub.add_parser("cases", help="检索与查看史案")
    c.add_argument("--search", metavar="KW", help="关键词全文检索")
    c.add_argument("--archetype", metavar="X", help="按博弈原型筛选，如 STACKELBERG")
    c.add_argument("--tier", metavar="T", choices=["T1", "T2", "T3"],
                   help="按史料可信度筛选")
    c.add_argument("--show", metavar="ID", help="查看指定编号的完整内容")
    c.add_argument("-f", "--format", default="text", choices=["text", "json"])
    c.set_defaults(func=cmd_cases)

    s = sub.add_parser("stratagem", help="检索与查看三十六计")
    s.add_argument("--show", metavar="ID", help="查看指定计策，如 S19")
    s.add_argument("--archetype", metavar="X", help="按博弈原型筛选")
    s.add_argument("-f", "--format", default="text", choices=["text", "json"])
    s.set_defaults(func=cmd_stratagem)

    sub.add_parser("archetypes", help="列出九类博弈原型与相似度权重").set_defaults(
        func=cmd_archetypes)
    sub.add_parser("template", help="输出处境向量模板 JSON").set_defaults(
        func=cmd_template)
    sub.add_parser("validate", help="自检数据完整性（贡献案例前必跑）").set_defaults(
        func=cmd_validate)

    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
