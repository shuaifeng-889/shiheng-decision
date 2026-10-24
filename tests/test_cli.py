#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CLI 端到端测试 —— 保证「无 Agent 模式」与引擎行为一致。

用 subprocess 真跑命令行，而不是导入函数，因为要验证的正是
argparse 解析、编码输出、退出码这些只有真进程才暴露的东西。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile


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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
CLI = os.path.join(ROOT, "scripts", "cli.py")

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print("  %s  %-46s got=%r" % ("PASS" if ok else "FAIL", name, got))


def check_true(name, cond, note=""):
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if cond else (PASS, FAIL + 1)
    print("  %s  %-46s %s" % ("PASS" if cond else "FAIL", name, note))


def run(*args, stdin: str | None = None):
    """跑 CLI，返回 (returncode, stdout, stderr)。

    stdin 必须显式设为 DEVNULL，否则子进程会继承父进程 stdin 并阻塞等待。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs = dict(
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=60,
    )
    if stdin is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin

    proc = subprocess.run([sys.executable, CLI, *args], **kwargs)
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    global PASS, FAIL
    PASS = FAIL = 0

    print("\n=== 1. 基础命令 ===")
    code, out, _ = run("--help")
    check("--help 退出码", code, 0)
    check_true("--help 列出 decide", "decide" in out)
    check_true("--help 列出 validate", "validate" in out)

    code, out, _ = run()
    check("无参数时打印帮助并正常退出", code, 0)

    print("\n=== 2. template 输出可作为输入 ===")
    code, out, _ = run("template")
    check("template 退出码", code, 0)
    try:
        tpl = json.loads(out)
        ok_json = True
    except json.JSONDecodeError:
        tpl, ok_json = {}, False
    check_true("template 是合法 JSON", ok_json)
    check_true("template 含全部 12 维", len([k for k in tpl if not k.startswith("_")]) == 11,
               note="（11 个可填维度，actors 与 third_party 各计一维）")

    print("\n=== 3. decide 三种输出格式 ===")
    sv = {
        "power_ratio": "weak", "stakes": "high", "reversibility": 0.3,
        "info_asym": -0.2, "time_pressure": "high", "horizon": "repeated",
        "actors": 3, "third_party": True, "resource_slack": "low",
        "opponent_rationality": "rational", "moral_constraint": "high",
    }
    with tempfile.TemporaryDirectory() as td:
        sv_path = os.path.join(td, "sv.json")
        with open(sv_path, "w", encoding="utf-8") as f:
            json.dump(sv, f, ensure_ascii=False)

        code, out, _ = run("decide", "-i", sv_path, "-f", "md")
        check("decide md 退出码", code, 0)
        check_true("md 含五层链标题", "L0 ENCODE" in out and "L1 RETRIEVE" in out)
        check_true("md 含正史检索式（历史主通道）", "正史检索式" in out)
        check_true("md 的本地样本已标注兜底", "本地精简样本" in out)
        check_true("md 含影子谏官", "影子谏官" in out)
        check_true("md 含执行前三项自检", "自检" in out)

        code, out, _ = run("decide", "-i", sv_path, "-f", "brief")
        check("decide brief 退出码", code, 0)
        check_true("brief 含史案 Top", "史案 Top-" in out)
        check_true("brief 含策略排序", "策略排序" in out)
        check_true("brief 比 md 短", len(out) < 4000, note="(%d 字符)" % len(out))

        code, out, _ = run("decide", "-i", sv_path, "-f", "json")
        check("decide json 退出码", code, 0)
        try:
            data = json.loads(out)
            ok = True
        except json.JSONDecodeError:
            data, ok = {}, False
        check_true("json 可解析", ok)
        check_true("json 含八个顶层键（含三层检索）",
                   set(data) == {"sv", "game", "cases", "stratagems", "shadow",
                                 "corpus_hits", "model_hits", "web_queries"})
        check_true("json 的 sv 回显一致", data.get("sv") == sv)
        check("json 返回 5 条史案", len(data.get("cases", [])), 5)

        print("\n=== 4. 收益矩阵与重复博弈 ===")
        mat_path = os.path.join(td, "m.json")
        with open(mat_path, "w", encoding="utf-8") as f:
            json.dump({"A": [[5, 1], [8, 2]], "B": [[5, 8], [1, 2]]}, f)

        code, out, _ = run("decide", "-i", sv_path, "-m", mat_path,
                           "--delta", "0.55", "-f", "json")
        check("带矩阵退出码", code, 0)
        d = json.loads(out)
        check("原型判定为囚徒困境", d["game"]["archetype"], "PRISONERS_DILEMMA")
        check("纯策略均衡坐标", d["game"]["pure_nash"], [[1, 1]])
        check_true("收益序 R>T>P>S 正确",
                   d["game"]["payoffs"] == {"R": 5, "T": 8, "S": 1, "P": 2})
        check_true("δ* 计算正确（=0.5）",
                   abs(d["game"]["repeated"]["delta_star"] - 0.5) < 1e-9)
        check_true("δ=0.55 判为可持续", d["game"]["repeated"]["sustainable"] is True)

        print("\n=== 5. 错误处理 ===")
        code, _, err = run("decide", "-i", os.path.join(td, "missing.json"))
        check("缺文件退出码非零", code != 0, True)
        check_true("缺文件有中文错误提示", "找不到文件" in err)

        bad_path = os.path.join(td, "bad.json")
        with open(bad_path, "w", encoding="utf-8") as f:
            json.dump({"power_ratio": "超强"}, f, ensure_ascii=False)
        code, _, err = run("decide", "-i", bad_path)
        check("非法取值退出码非零", code != 0, True)
        check_true("非法取值提示可选项", "very_strong" in err)

        broken = os.path.join(td, "broken.json")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("{not json")
        code, _, err = run("decide", "-i", broken)
        check("坏 JSON 退出码非零", code != 0, True)

        code, _, err = run("decide")  # 无输入且非 tty
        check("无输入时不崩", code != 0, True)

    print("\n=== 6. 检索类命令 ===")
    code, out, _ = run("cases", "--search", "粮道")
    check("cases --search 退出码", code, 0)
    check_true("检索到粮道相关史案", "C014" in out or "C018" in out)

    code, out, _ = run("cases", "--show", "C037")
    check("cases --show 退出码", code, 0)
    check_true("C037 含澶渊", "澶渊" in out)
    check_true("C037 标注 T1", "T1" in out)

    code, out, _ = run("cases", "--show", "C999")
    check("不存在的案例退出码非零", code != 0, True)

    code, out, _ = run("stratagem", "--show", "S19")
    check("stratagem --show 退出码", code, 0)
    check_true("S19 是釜底抽薪", "釜底抽薪" in out)
    check_true("S19 输出适用前提", "适用前提" in out)
    check_true("S19 输出失效条件", "失效条件" in out)
    check_true("S19 输出红线", "红线" in out)

    code, out, _ = run("stratagem")
    check("stratagem 列表退出码", code, 0)
    check_true("列表含 36 计", out.count("S") >= 36)

    print("\n=== 7. 自检与原型表 ===")
    code, out, _ = run("validate")
    check("validate 退出码", code, 0)
    check_true("validate 全通过", "FAIL=0" in out)

    code, out, _ = run("archetypes")
    check("archetypes 退出码", code, 0)
    for arch in ("PRISONERS_DILEMMA", "CHICKEN", "STAG_HUNT", "BOXED_PIGS",
                 "DEADLOCK", "SIGNALING", "STACKELBERG", "REPEATED", "COALITION"):
        check_true("列出原型 %s" % arch, arch in out)

    print("\n" + "=" * 62)
    print("  PASS=%d  FAIL=%d" % (PASS, FAIL))
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
