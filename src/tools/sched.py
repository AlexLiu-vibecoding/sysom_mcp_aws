"""Scheduler diagnostic tools: delay, loadtask."""

from ..utils.system import run_cmd, run_shell, check_command


def delay() -> str:
    """Scheduler/delay diagnosis: analyze scheduling latency, preemption, softirq delays."""
    parts = ["=== SCHEDULER DELAY DIAGNOSIS ==="]

    # 1. Scheduler stats
    parts.append("\n--- Scheduler Statistics (/proc/schedstat) ---")
    schedstat = run_cmd(["cat", "/proc/schedstat"])
    if not schedstat.startswith("[ERROR"):
        # Parse: domain-specific and CPU-level stats
        lines = schedstat.split("\n")
        parts.append(f"  Total lines: {len(lines)}")
        # Show scheduler domain summary
        domain_lines = [l for l in lines if not l.startswith("version") and not l.startswith("timestamp")]
        for dl in domain_lines[:5]:
            parts.append(f"  {dl.strip()}")
        if len(domain_lines) > 5:
            parts.append(f"  ... ({len(domain_lines) - 5} more)")

    # 2. Scheduler debug info
    parts.append("\n--- Scheduler Debug (/proc/sched_debug) ---")
    sched_debug = run_cmd(["cat", "/proc/sched_debug"], timeout=5)
    if not sched_debug.startswith("[ERROR"):
        # Just grab key summary lines
        for line in sched_debug.split("\n"):
            if any(kw in line.lower() for kw in [
                "nr_running", "nr_switches", "nr_load_updates",
                "nr_uninterruptible", "next_balance", "curr->pid",
                "average load", ".nr_running",
            ]):
                parts.append(f"  {line.strip()}")
    else:
        parts.append("  (sched_debug not available - need CONFIG_SCHED_DEBUG)")

    # 3. Load average and CPU utilization
    parts.append("\n--- CPU Load & Utilization ---")
    parts.append(f"  Load average: {run_cmd(['cat', '/proc/loadavg']).strip()}")
    if check_command("mpstat"):
        parts.append(run_cmd(["mpstat", "-P", "ALL", "1", "3"], timeout=10))

    # 4. Softirq/hardirq breakdown
    parts.append("\n--- SoftIRQ Times (/proc/softirqs) ---")
    parts.append(run_cmd(["cat", "/proc/softirqs"]))

    parts.append("\n--- HardIRQ Counts (/proc/interrupts, summary) ---")
    parts.append(run_cmd(["cat", "/proc/interrupts"]))

    # 5. Preemption / voluntary context switches
    parts.append("\n--- Context Switch Rate ---")
    cs = run_cmd(["cat", "/proc/stat"])
    for line in cs.split("\n"):
        if line.startswith("ctxt") or line.startswith("processes") or line.startswith("procs_running") or line.startswith("procs_blocked"):
            parts.append(f"  {line.strip()}")

    parts.append("\n--- Top Processes by Preemption/Voluntary Switches ---")
    parts.append(run_shell(
        "for pid in $(ls /proc/*/sched 2>/dev/null | head -30); do "
        "  p=$(echo $pid | cut -d/ -f3); "
        "  c=$(cat /proc/$p/comm 2>/dev/null); "
        "  cs=$(grep 'nr_switches' /proc/$p/sched 2>/dev/null | awk '{print $3}'); "
        "  vs=$(grep 'nr_voluntary_switches' /proc/$p/sched 2>/dev/null | awk '{print $3}'); "
        "  iv=$(grep 'nr_involuntary_switches' /proc/$p/sched 2>/dev/null | awk '{print $3}'); "
        "  echo \"$cs|PID=$p|COMM=$c|vol=$vs|invol=$iv\"; "
        "done | sort -t'|' -k1 -rn | head -10 | tr '|' ' '"
    ))

    # 6. RCU stall detection
    parts.append("\n--- RCU Stall / Lockup Detection ---")
    rcu = run_shell(
        "dmesg --level=err,warn 2>/dev/null | grep -iE 'rcu|stall|lockup|hung_task|softlockup|hardlockup' | tail -10 || "
        "dmesg 2>/dev/null | grep -iE 'rcu|stall|lockup|hung_task' | tail -10"
    )
    if rcu and not rcu.startswith("[ERROR"):
        parts.append(rcu if rcu.strip() else "  No RCU stall or lockup events found")
    else:
        parts.append("  No RCU/softlockup events found in kernel log")

    return "\n".join(parts)


def loadtask() -> str:
    """Load/task diagnosis: analyze system load, CPU hot processes, run queue."""
    parts = ["=== LOAD TASK DIAGNOSIS ==="]

    # 1. System load overview
    parts.append("\n--- System Overview ---")
    parts.append(f"  Uptime: {run_cmd(['uptime']).strip()}")
    parts.append(f"  Load avg: {run_cmd(['cat', '/proc/loadavg']).strip()}")

    # 2. CPU top consumers
    parts.append("\n--- Top CPU Consumers ---")
    top_out = run_cmd(["ps", "axo", "pid,ppid,user,%cpu,%mem,rss,vsz,comm", "--sort=-%cpu"])
    lines = top_out.split("\n")
    parts.append("\n".join(lines[:16]))

    # 3. Top processes by thread count
    parts.append("\n--- Top Processes by Thread Count ---")
    parts.append(run_shell(
        "for pid in $(ls /proc/*/task 2>/dev/null); do "
        "  p=$(echo $pid | cut -d/ -f3); "
        "  c=$(cat /proc/$p/comm 2>/dev/null); "
        "  t=$(ls /proc/$p/task 2>/dev/null | wc -l); "
        "  echo \"$t $p $c\"; "
        "done | sort -rn | head -10"
    ))

    # 4. Run queue details
    parts.append("\n--- Run Queue (procs_running/blocked) ---")
    parts.append(run_shell(
        "grep -E 'procs_running|procs_blocked' /proc/stat"
    ))
    parts.append("\n--- Waiting Tasks (D-state) ---")
    d_state = run_cmd(["ps", "-eo", "pid,user,stat,comm", "--no-headers"])
    d_procs = [l for l in d_state.split("\n") if " D" in l or " D+" in l]
    if d_procs:
        parts.append("\n".join(d_procs[:20]))
        if len(d_procs) > 20:
            parts.append(f"  ... ({len(d_procs) - 20} more)")
    else:
        parts.append("  No processes in uninterruptible sleep (D state)")

    # 5. Process detail for top CPU consumers
    parts.append("\n--- Top 5 CPU Processes Detail ---")
    top5 = run_cmd(["ps", "axo", "pid,%cpu,%mem,user,comm", "--sort=-%cpu", "--no-headers"])
    for line in top5.split("\n")[:5]:
        fields = line.strip().split()
        if len(fields) >= 5:
            pid = fields[0]
            detail = run_cmd(["ps", "-p", pid, "-o", "pid,user,%cpu,%mem,rss,vsz,stat,start,time,comm"])
            parts.append(detail)

    # 6. CPU time breakdown
    parts.append("\n--- CPU Time Breakdown ---")
    if check_command("mpstat"):
        parts.append(run_cmd(["mpstat", "1", "3"], timeout=10))

    # 7. Zombie processes
    parts.append("\n--- Zombie Processes ---")
    zombies = run_cmd(["ps", "-eo", "pid,stat,comm", "--no-headers"])
    zombie_procs = [l for l in zombies.split("\n") if " Z" in l]
    if zombie_procs:
        parts.append("  Zombies found:")
        for z in zombie_procs[:10]:
            parts.append(f"    {z.strip()}")
        if len(zombie_procs) > 10:
            parts.append(f"    ... ({len(zombie_procs) - 10} more)")
    else:
        parts.append("  No zombie processes")

    return "\n".join(parts)
