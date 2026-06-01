"""Memory diagnostic tools: memgraph, javamem, oomcheck."""

from ..utils.system import run_cmd, run_shell, detect_os_family, check_command
from ..utils.container import detect_container_runtime, list_java_containers, exec_in_container, get_java_pid_in_container


def memgraph() -> str:
    """Memory panorama analysis: scan memory usage, slab, fragmentation, swap."""
    parts = ["=== MEMORY PANORAMA ANALYSIS ==="]

    # 1. Overall memory usage
    parts.append("\n--- Overall Memory (free -h) ---")
    parts.append(run_cmd(["free", "-h"]))

    # 2. Detailed meminfo
    parts.append("\n--- /proc/meminfo (key fields) ---")
    meminfo = run_cmd(["cat", "/proc/meminfo"])
    key_fields = [
        "MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
        "SwapTotal", "SwapFree", "SwapCached", "Active", "Inactive",
        "Dirty", "Writeback", "AnonPages", "Mapped", "Shmem",
        "Slab", "SReclaimable", "SUnreclaim", "PageTables",
        "KernelStack", "VmallocUsed", "Committed_AS",
        "HugePages_Total", "HugePages_Free",
    ]
    for line in meminfo.split("\n"):
        for field in key_fields:
            if line.startswith(field + ":") or line.startswith(field + "\t"):
                parts.append(f"  {line.strip()}")
                break

    # 3. Memory fragmentation
    parts.append("\n--- Memory Fragmentation (buddyinfo) ---")
    buddy = run_cmd(["cat", "/proc/buddyinfo"])
    parts.append(buddy if len(buddy) < 500 else buddy[:500] + "\n...(truncated)")

    # 4. Slab info
    parts.append("\n--- Top Slab Caches (slabinfo) ---")
    if check_command("slabtop"):
        parts.append(run_cmd(["slabtop", "-o", "-s", "c", "--once"], timeout=10))
    else:
        # Raw /proc/slabinfo - top 15
        slab = run_cmd(["bash", "-c", "cat /proc/slabinfo | awk 'NR>1 {print $1, $2, $3, $4}' | sort -k2 -rn | head -15"])
        parts.append(slab)

    # 5. Top memory processes
    parts.append("\n--- Top Memory Consumers (ps) ---")
    ps_out = run_cmd(["ps", "axo", "pid,ppid,user,%mem,rss,vsz,comm", "--sort=-%mem"])
    lines = ps_out.split("\n")
    parts.append("\n".join(lines[:12]))  # header + top 10

    # 6. Kernel memory details
    parts.append("\n--- Kernel Memory (vmstat -s) ---")
    parts.append(run_cmd(["vmstat", "-s"]))

    # 7. IPC shared memory
    parts.append("\n--- Shared Memory (ipcs -m) ---")
    parts.append(run_cmd(["ipcs", "-m"]))

    # 8. numa (if available)
    if check_command("numastat"):
        parts.append("\n--- NUMA Stats ---")
        parts.append(run_cmd(["numastat"], timeout=10))

    return "\n".join(parts)


def javamem() -> str:
    """Java memory diagnostics: analyze Java heap/memory usage in containers."""
    parts = ["=== JAVA MEMORY DIAGNOSIS ==="]

    runtime = detect_container_runtime()
    if not runtime:
        parts.append("[INFO] No container runtime detected (docker or containerd)")
        # Try to find Java directly on host
        ps_out = run_cmd(["ps", "-ef", "--no-headers"])
        java_lines = [l for l in ps_out.split("\n") if "java" in l.lower() and "grep" not in l.lower()]
        if java_lines:
            parts.append("\nJava processes found on host (not in container):")
            for jl in java_lines[:10]:
                parts.append(f"  {jl}")
            parts.append("\nNote: jcmd/jmap may need to be run as the same user as the Java process.")
        else:
            parts.append("No Java processes detected.")
            parts.append("\nTroubleshooting: Java applications are running in containers.")
            parts.append("Container detection result: no runtime found.")
        return "\n".join(parts)

    parts.append(f"\nContainer runtime detected: {runtime}")

    containers = list_java_containers(runtime)
    if not containers:
        parts.append("\nNo Java containers found.")
        parts.append("Tips:")
        parts.append("  - Make sure containers are running (docker ps / crictl ps)")
        parts.append("  - Container image name should contain: java/jdk/spring/tomcat/etc.")
        return "\n".join(parts)

    for c in containers:
        parts.append(f"\n{'='*60}")
        parts.append(f"Container: {c['name']} ({c['id']})")
        parts.append(f"Image: {c['image']}")

        # Get Java PID
        pid = get_java_pid_in_container(c["id"], runtime)
        if not pid:
            parts.append("  [WARN] Could not find Java PID")
            continue
        parts.append(f"Java PID: {pid}")

        # Check available tools
        has_jcmd = exec_in_container(c["id"], ["which", "jcmd"], runtime)
        has_jmap = exec_in_container(c["id"], ["which", "jmap"], runtime)
        has_jstat = exec_in_container(c["id"], ["which", "jstat"], runtime)
        has_java = exec_in_container(c["id"], ["which", "java"], runtime)

        parts.append(f"  Tools available: jcmd={'yes' if 'jcmd' in has_jcmd else 'no'}, "
                     f"jmap={'yes' if 'jmap' in has_jmap else 'no'}, "
                     f"jstat={'yes' if 'jstat' in has_jstat else 'no'}")

        # Java version
        if "java" in has_java:
            java_ver = exec_in_container(c["id"], ["java", "-version"], runtime)
            ver_line = java_ver.split("\n")[0] if java_ver else "N/A"
            parts.append(f"  Java Version: {ver_line.strip()}")

        # 1. jcmd VM info
        if "jcmd" in has_jcmd:
            parts.append(f"\n  -- jcmd VM.uptime --")
            parts.append(exec_in_container(c["id"], ["jcmd", pid, "VM.uptime"], runtime))
            parts.append(f"\n  -- jcmd GC.heap_info --")
            parts.append(exec_in_container(c["id"], ["jcmd", pid, "GC.heap_info"], runtime))
            parts.append(f"\n  -- jcmd VM.native_memory (summary) --")
            nm = exec_in_container(c["id"], ["jcmd", pid, "VM.native_memory", "summary"], runtime)
            if "Native memory tracking is not enabled" in nm or "No such diagnostic command" in nm:
                parts.append("  [INFO] Native Memory Tracking not enabled (add -XX:NativeMemoryTracking=summary to JVM args)")
                parts.append(nm)
            else:
                parts.append(nm)
            parts.append(f"\n  -- jcmd GC.class_histogram (top 20) --")
            hist = exec_in_container(c["id"], ["jcmd", pid, "GC.class_histogram"], runtime)
            hist_lines = hist.split("\n")
            parts.append("\n".join(hist_lines[:24]))
            if len(hist_lines) > 24:
                parts.append(f"  ... ({len(hist_lines) - 24} more lines)")

        # 2. jstat -gc
        if "jstat" in has_java:
            parts.append(f"\n  -- jstat -gcutil (GC stats) --")
            parts.append(exec_in_container(c["id"], ["jstat", "-gcutil", pid, "250", "4"], runtime))

        # 3. Container memory limits (cgroup)
        parts.append(f"\n  -- Container Memory Limits --")
        cg_mem = exec_in_container(c["id"], ["cat", "/sys/fs/cgroup/memory/memory.limit_in_bytes"], runtime)
        parts.append(f"  Memory limit: {cg_mem} bytes")
        cg_usage = exec_in_container(c["id"], ["cat", "/sys/fs/cgroup/memory/memory.usage_in_bytes"], runtime)
        parts.append(f"  Memory usage: {cg_usage} bytes")

    return "\n".join(parts)


def oomcheck() -> str:
    """OOM check: scan for OOM killer events, memory pressure, low-water marks."""
    parts = ["=== OOM CHECK ==="]
    os_family = detect_os_family()

    # 1. Check dmesg for OOM
    parts.append("\n--- Recent OOM killer events (dmesg) ---")
    if os_family == "amazonlinux2023":
        dmesg_oom = run_cmd(["dmesg", "--level=err,warn"])
        oom_entries = [l for l in dmesg_oom.split("\n") if "oom" in l.lower() or "OOM" in l or "out of memory" in l.lower()]
        if oom_entries:
            for e in oom_entries[-10:]:
                parts.append(f"  {e.strip()}")
        else:
            parts.append("  No OOM events found in dmesg (last boot)")

    # Also check journalctl for AL2023
    if os_family == "amazonlinux2023":
        parts.append("\n--- journalctl OOM entries ---")
        j_oom = run_cmd(["journalctl", "-k", "--no-pager", "--grep=oom|OOM|out of memory"], timeout=10)
        if not j_oom.startswith("[ERROR"):
            oom_lines = [l for l in j_oom.split("\n") if l.strip() and ("oom" in l.lower() or "OOM" in l or "out of memory" in l.lower())]
            if oom_lines:
                for l in oom_lines[-10:]:
                    parts.append(f"  {l.strip()}")
            else:
                parts.append("  No OOM events in journalctl")
        else:
            parts.append("  (journalctl grep not available)")

    # 2. Check /proc/zoneinfo for watermarks
    parts.append("\n--- Memory Watermarks (zoneinfo) ---")
    zi = run_cmd(["cat", "/proc/zoneinfo"])
    watermark_lines = []
    for line in zi.split("\n"):
        if any(kw in line for kw in ["min", "low", "high", "pages free", "managed", "present"]):
            watermark_lines.append(line)
    parts.append("\n".join(watermark_lines[:30]))
    if len(watermark_lines) > 30:
        parts.append(f"... ({len(watermark_lines) - 30} more lines)")

    # 3. Memory pressure indicators
    parts.append("\n--- Memory Pressure Indicators ---")

    # Check /proc/pressure/memory (kernel 4.20+)
    pressure = run_cmd(["cat", "/proc/pressure/memory"])
    if not pressure.startswith("[ERROR"):
        parts.append(f"  PSI Memory Pressure:\n{pressure}")
    else:
        parts.append("  PSI not available (kernel < 4.20)")

    # Check compact_*.  (compaction efficiency)
    compact = run_cmd(["cat", "/proc/sys/vm/compact_memory"])
    if not compact.startswith("[ERROR"):
        parts.append(f"  compact_memory: {compact.strip()}")

    # 4. Swap usage
    parts.append("\n--- Swap Usage ---")
    parts.append(run_cmd(["swapon", "--show"]))
    swap_total = run_cmd(["awk", "/SwapTotal/ {print $2}", "/proc/meminfo"])
    swap_free = run_cmd(["awk", "/SwapFree/ {print $2}", "/proc/meminfo"])
    parts.append(f"  Swap Total: {swap_total.strip()} kB")
    parts.append(f"  Swap Free:  {swap_free.strip()} kB")

    # 5. Top memory processes
    parts.append("\n--- Top Memory Processes (sorted by RSS) ---")
    top_mem = run_cmd(["ps", "axo", "pid,user,%mem,rss,vsz,comm", "--sort=-%mem"])
    lines = top_mem.split("\n")
    parts.append("\n".join(lines[:16]))

    # 6. OOM score
    parts.append("\n--- Process OOM Scores (top 10 highest) ---")
    oom_scores = run_shell(
        "for pid in $(ls /proc/*/oom_score 2>/dev/null); do "
        "  pid=$(echo $pid | cut -d/ -f3); "
        "  score=$(cat /proc/$pid/oom_score 2>/dev/null); "
        "  comm=$(cat /proc/$pid/comm 2>/dev/null); "
        "  echo $score $pid $comm; "
        "done | sort -rn | head -10"
    )
    parts.append(oom_scores)

    # 7. Memory cgroup limits
    parts.append("\n--- Cgroup Memory Limits ---")
    if os_family == "amazonlinux2023":
        # cgroup v2
        parts.append(run_cmd(["findmnt", "-t", "cgroup2"]))
    else:
        # cgroup v1
        parts.append(run_cmd(["findmnt", "-t", "cgroup"]))

    return "\n".join(parts)
