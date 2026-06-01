#!/usr/bin/env python3
"""SysOM CLI - Interactive diagnostic tool REPL
Usage:
    uv run python sysom_cli.py          # interactive menu
    uv run python sysom_cli.py disk     # run one tool directly
    uv run python sysom_cli.py help     # list all tools
"""

import sys
import os
from datetime import datetime

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.tools import memory, io, network, sched, crash, other, aws_ebs

# Tool registry: (short_name, description, function)
TOOLS = [
    ("disk",     "磁盘与 EBS 分析",         other.diskanalysis),
    ("mem",      "内存全景分析",             memory.memgraph),
    ("oom",      "OOM 检查",                memory.oomcheck),
    ("javamem",  "Java 内存诊断",            memory.javamem),
    ("iofs",     "IO 文件系统统计",          io.iofsstat),
    ("iodiag",   "IO 性能诊断",             io.iodiagnose),
    ("pktdrop",  "网络丢包诊断",             network.packetdrop),
    ("netjit",   "网络抖动诊断",             network.netjitter),
    ("sched",    "调度延迟诊断",             sched.delay),
    ("load",     "负载/任务诊断",            sched.loadtask),
    ("ebs",      "EBS CloudWatch 性能",      aws_ebs.ebs_performance),
    ("ec2",      "EC2 实例元数据",           aws_ebs.ec2_metadata),
    ("vmcore",   "VMCORE 宕机分析",          other.vmcore),
]

# Alias mapping for quick access
ALIASES: dict[str, tuple] = {}
for short_name, desc, fn in TOOLS:
    ALIASES[short_name] = (desc, fn)
    ALIASES[str(len(ALIASES) + 1)] = (desc, fn)  # number also works


def show_banner():
    print()
    print(" ╔═══════════════════════════════════╗")
    print(" ║     SysOM EC2 Diagnostic CLI      ║")
    print(" ╠═══════════════════════════════════╣")
    print(" ║  输入编号或名称运行诊断工具       ║")
    print(" ║  输入 h 显示菜单  ·  q 退出       ║")
    print(" ╚═══════════════════════════════════╝")


def show_menu():
    print()
    print(f"  {'#':>2s}  {'命令':8s}  {'说明':<30s}")
    print(f"  {'--':>2s}  {'----':8s}  {'----':<30s}")
    for i, (short_name, desc, _) in enumerate(TOOLS, 1):
        print(f"  {i:2d}  {short_name:8s}  {desc:<30s}")
    print()


def run_tool(name: str) -> bool:
    """Run a diagnostic tool by name or number. Returns False to exit."""
    cmd = name.strip().lower()

    if cmd in ("q", "quit", "exit"):
        print("  Bye!")
        return False

    if cmd in ("h", "help", "menu", "?"):
        show_menu()
        return True

    # Try alias lookup
    if cmd in ALIASES:
        desc, fn = ALIASES[cmd]
        print(f"\n  >>> 运行: {desc} <<<")
        print(f"  {'='*50}")
        start = datetime.now()
        try:
            result = fn()
            elapsed = (datetime.now() - start).total_seconds()
            print(result)
            print(f"\n  {'='*50}")
            print(f"  [完成] 耗时 {elapsed:.1f}s")
        except Exception as e:
            print(f"\n  [错误] {e}")
        return True

    print(f"  [错误] 未知命令 '{cmd}'，输入 h 查看可用工具")
    return True


def main():
    # Direct mode: run one tool and exit
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("help", "--help", "-h"):
            print(f"用法: {sys.argv[0]} [工具名]")
            print(f"工具列表:")
            for short_name, desc, _ in TOOLS:
                print(f"  {short_name:10s}  {desc}")
            return
        run_tool(cmd)
        return

    # Interactive REPL mode
    show_banner()
    show_menu()

    while True:
        try:
            cmd = input("\n  sysom> ").strip()
            if not cmd:
                continue
            if not run_tool(cmd):
                break
        except (KeyboardInterrupt, EOFError):
            print("\n  Bye!")
            break


if __name__ == "__main__":
    main()
