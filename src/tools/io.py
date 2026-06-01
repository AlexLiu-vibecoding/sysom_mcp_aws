"""IO diagnostic tools: iofsstat, iodiagnose."""

from ..utils.system import run_cmd, run_shell, check_command, detect_os_family


def iofsstat() -> str:
    """IO filesystem statistics: analyze filesystem IO state and disk usage."""
    parts = ["=== IO FILESYSTEM STATISTICS ==="]

    # 1. Mount information
    parts.append("\n--- Mount Points (findmnt) ---")
    parts.append(run_cmd(["findmnt", "-D"]))  # With disk usage

    # 2. Disk usage
    parts.append("\n--- Disk Usage (df -h) ---")
    parts.append(run_cmd(["df", "-h", "--total"]))

    # 3. Block devices
    parts.append("\n--- Block Devices (lsblk) ---")
    parts.append(run_cmd(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,ROTA"]))

    # 4. IO stats (iostat)
    parts.append("\n--- IO Stats (iostat -x 1 3) ---")
    if check_command("iostat"):
        io = run_cmd(["iostat", "-x", "1", "3"], timeout=10)
        # Take the last iteration (cumulative)
        io_lines = io.split("\n")
        parts.append("\n".join(io_lines[-20:]))
    else:
        # Fallback: /proc/diskstats
        parts.append("  (iostat not installed, using /proc/diskstats)")
        parts.append(run_cmd(["cat", "/proc/diskstats"]))

    # 5. Disk scheduler
    parts.append("\n--- IO Scheduler ---")
    for dev_path in run_shell("ls /sys/block/ 2>/dev/null").split("\n"):
        dev = dev_path.strip()
        if dev and dev not in ("loop", "ram"):
            scheduler = run_cmd(["cat", f"/sys/block/{dev}/queue/scheduler"])
            if not scheduler.startswith("[ERROR"):
                parts.append(f"  {dev}: {scheduler.strip()}")
            rot = run_cmd(["cat", f"/sys/block/{dev}/queue/rotational"])
            if not rot.startswith("[ERROR"):
                parts.append(f"    rotational: {'HDD' if rot.strip() == '1' else 'SSD'}")

    # 6. Inode usage
    parts.append("\n--- Inode Usage (df -i) ---")
    parts.append(run_cmd(["df", "-i", "--total"]))

    # 7. Largest directories
    parts.append("\n--- Top 15 Largest Directories (/) ---")
    parts.append(run_cmd(["du", "-x", "-d", "1", "/"], timeout=15))

    # 8. File handles
    parts.append("\n--- File Handle Usage ---")
    parts.append(run_cmd(["cat", "/proc/sys/fs/file-nr"]))

    return "\n".join(parts)


def iodiagnose() -> str:
    """IO diagnosis: analyze IO performance issues, queue depth, latency."""
    parts = ["=== IO DIAGNOSIS ==="]

    # 1. IO latency with iostat
    parts.append("\n--- IO Latency (iostat -x 1 5) ---")
    if check_command("iostat"):
        io = run_cmd(["iostat", "-x", "1", "5"], timeout=15)
        io_lines = io.split("\n")
        parts.append("\n".join(io_lines[-15:]))
    else:
        parts.append("  iostat not installed. Install sysstat package.")
        # Fallback diskstats analysis
        parts.append("\n--- /proc/diskstats (raw) ---")
        parts.append(run_cmd(["cat", "/proc/diskstats"]))

    # 2. IO Top processes
    parts.append("\n--- Top IO Processes ---")
    if check_command("iotop"):
        parts.append(run_cmd(["iotop", "-b", "-n", "1", "-o"], timeout=10))
    elif check_command("pidstat"):
        parts.append(run_cmd(["pidstat", "-d", "1", "3"], timeout=10))
    else:
        parts.append("  Neither iotop nor pidstat available.")
        # Use /proc/<pid>/io
        parts.append(run_shell(
            "for pid in $(ls /proc/*/io 2>/dev/null | head -20 | cut -d/ -f3); do "
            "  rchar=$(grep rchar /proc/$pid/io 2>/dev/null | awk '{print $2}'); "
            "  wchar=$(grep wchar /proc/$pid/io 2>/dev/null | awk '{print $2}'); "
            "  comm=$(cat /proc/$pid/comm 2>/dev/null); "
            "  echo \"PID=$pid COMM=$comm rchar=$rchar wchar=$wchar\"; "
            "done | sort -t= -k3 -rn | head -10"
        ))

    # 3. IO queue depth
    parts.append("\n--- IO Queue Depth (inflight I/O) ---")
    parts.append(run_shell(
        "for d in /sys/block/*/inflight 2>/dev/null; do "
        "  dev=$(echo $d | cut -d/ -f4); "
        "  inflight=$(cat $d 2>/dev/null); "
        "  echo \"$dev: $inflight\"; "
        "done"
    ))

    # 4. Device mapper / LVM info
    parts.append("\n--- Device Mapper / LVM ---")
    parts.append(run_cmd(["dmsetup", "ls", "--tree"]))

    # 5. Disk wait time analysis
    parts.append("\n--- Disk Wait Time Analysis ---")
    parts.append(run_shell(
        "for pid in $(ls /proc/*/sched 2>/dev/null); do "
        "  pid=$(echo $pid | cut -d/ -f3); "
        "  comm=$(cat /proc/$pid/comm 2>/dev/null); "
        "  iowait=$(grep 'se.statistics.iowait_sum' /proc/$pid/sched 2>/dev/null | awk '{print $3}'); "
        "  if [ -n \"$iowait\" ] && [ \"$iowait\" != \"0\" ]; then "
        "    echo \"PID=$pid COMM=$comm iowait_sum=$iowait\"; "
        "  fi; "
        "done | sort -t= -k3 -rn | head -10"
    ))

    # 6. Disk throughput check
    parts.append("\n--- Disk Throughput (MB/s over 5s) ---")
    parts.append(run_shell(
        "devices=$(lsblk -ndo NAME 2>/dev/null | grep -v loop | head -5); "
        "for dev in $devices; do "
        "  before=$(cat /sys/block/$dev/stat 2>/dev/null | awk '{print $6+$10}'); "
        "  sleep 1; "
        "  after=$(cat /sys/block/$dev/stat 2>/dev/null | awk '{print $6+$10}'); "
        "  sectors=$((after - before)); "
        "  mb=$(echo \"scale=1; $sectors * 512 / 1048576\" | bc); "
        "  echo \"  $dev: ${mb}MB/s\"; "
        "done"
    ))

    # 7. Summary assessment
    parts.append("\n--- IO Health Summary ---")
    parts.append(run_shell(
        "echo \"Device  avgqu-sz  await  svctm  util%\"; "
        "iostat -x 1 2 2>/dev/null | grep -E '^[a-z]' | tail -5 | awk '{printf \"%-8s %-9s %-7s %-7s %s%%\\n\", $1, $9, $10, $11, $12}'"
    ))

    return "\n".join(parts)
