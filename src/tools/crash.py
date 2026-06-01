"""Crash diagnostic tools: vmcore analysis, dmesg diagnosis, task management."""

from ..utils.system import run_cmd, run_shell, check_command, detect_os_family

# In-memory task storage (ephemeral - persists only while server runs)
_diagnosis_tasks: dict[str, dict] = {}
_task_counter = 0


def _check_kdump_enabled() -> bool:
    """Check if kdump/crash dump is configured."""
    for cmd in [
        ["systemctl", "is-active", "kdump"],
        ["service", "kdump", "status"],
    ]:
        out = run_cmd(cmd)
        if "active" in out.lower():
            return True
    cmdline = run_cmd(["cat", "/proc/cmdline"])
    if "crashkernel=" in cmdline:
        return True
    return False


def _check_vmcore_files() -> list[str]:
    """Check for existing vmcore files."""
    vmcore_files = []
    for path in ["/var/crash", "/dump"]:
        out = run_cmd(["find", path, "-name", "vmcore*", "-type", "f"], timeout=10)
        if not out.startswith("[ERROR") and out.strip():
            vmcore_files.extend(out.strip().split("\n"))
    return vmcore_files


def create_vmcore_diagnosis_task(vmcore_path: str | None = None) -> str:
    """Create a kernel crash diagnosis task from VMCORE file."""
    global _task_counter
    _task_counter += 1
    task_id = f"vmcore-{_task_counter}"

    parts = [f"=== VMCORE DIAGNOSIS TASK {task_id} ==="]

    # Check if kdump is enabled
    kdump_ok = _check_kdump_enabled()
    parts.append(f"\nKdump status: {'ENABLED' if kdump_ok else 'NOT CONFIGURED'}")

    # Find vmcore files
    if vmcore_path and vmcore_path != "auto":
        files = [vmcore_path]
    else:
        files = _check_vmcore_files()

    if not files:
        parts.append("\nNo vmcore files found.")
        parts.append("\nTo enable kdump on Amazon Linux:")
        parts.append("  1. Add crashkernel=256M to /etc/default/grub GRUB_CMDLINE_LINUX")
        parts.append("  2. sudo grub2-mkconfig -o /boot/grub2/grub.cfg")
        parts.append("  3. sudo yum install -y kexec-tools")
        parts.append("  4. sudo systemctl enable kdump && sudo systemctl start kdump")
        parts.append("  5. Reboot to apply")
        parts.append("\nUse create_dmesg_diagnosis_task() for log-based analysis instead.")
        _diagnosis_tasks[task_id] = {
            "status": "completed", "result": parts,
            "type": "vmcore", "files_found": False,
        }
        return "\n".join(parts)

    crash_available = check_command("crash")
    parts.append(f"\nCrash analysis tool: {'AVAILABLE' if crash_available else 'NOT INSTALLED'}")
    parts.append(f"\nKernel: {run_cmd(['uname', '-r']).strip()}")

    for fpath in files[:3]:
        parts.append(f"\n{'='*60}")
        parts.append(f"VMCORE file: {fpath}")
        size = run_cmd(["ls", "-lh", fpath]).strip()
        parts.append(f"Size: {size}")
        parts.append(f"\n  File type: {run_cmd(['file', fpath]).strip()}")

        if crash_available:
            parts.append("\n  -- Basic crash analysis (log-only, non-interactive) --")
            crash_script = "bt -a; log; ps; vm; foreach bt"
            script_path = f"/tmp/crash_cmds_{task_id}.txt"
            with open(script_path, "w") as f:
                f.write(crash_script)
            crash_out = run_cmd([
                "crash", "-i", script_path, fpath,
                "/usr/lib/debug/lib/modules/$(uname -r)/vmlinux"
            ], timeout=120)
            parts.append(crash_out[:2000] if len(crash_out) > 2000 else crash_out)
        else:
            parts.append("\n  (crash tool not installed. To install:)")
            parts.append("    sudo yum install -y crash")
            parts.append("    sudo yum install -y kernel-debuginfo-$(uname -r)")

    _diagnosis_tasks[task_id] = {
        "status": "completed", "result": parts,
        "type": "vmcore", "files_found": True,
    }
    return "\n".join(parts)


def create_dmesg_diagnosis_task(hours: int = 24) -> str:
    """Create a diagnosis task based on dmesg/kernel log analysis."""
    global _task_counter
    _task_counter += 1
    task_id = f"dmesg-{_task_counter}"

    parts = [f"=== DMESG DIAGNOSIS TASK {task_id} ==="]
    parts.append(f"Analyzing kernel log for the last {hours} hours\n")

    os_family = detect_os_family()

    # 1. Raw dmesg
    parts.append("--- Recent Kernel Messages ---")
    if os_family == "amazonlinux2023":
        dmesg_out = run_cmd(["dmesg", "--level=alert,crit,err,warn", "--since",
                             f"{hours}h ago"], timeout=10)
    else:
        dmesg_out = run_cmd(["dmesg"], timeout=10)
    parts.append(dmesg_out[:2000] if len(dmesg_out) > 2000 else dmesg_out)

    # 2. Error/Warning classification
    parts.append("\n\n--- Message Classification ---")
    error_categories = {
        "OOM / Memory": ["oom", "out of memory", "low memory", "allocation failure"],
        "IO Errors": ["i/o error", "buffer I/O", "end_request", "device error"],
        "Network Errors": ["NETDEV", "net_ratelimit", "TX timeout", "link down"],
        "Hardware Errors": ["mce", "machine check", "PCIe", "EDAC", "AER"],
        "FS Errors": ["ext4", "xfs", "btrfs", "nfs", "corruption", "fs error"],
        "Scheduler/RCU": ["rcu", "stall", "softlockup", "hardlockup", "hung_task"],
        "Kernel Panic": ["panic", "kernel BUG", "Oops", "segfault"],
        "NVMe/Storage": ["nvme", "ata", "scsi", "disk", "drive"],
    }

    for category, keywords in error_categories.items():
        found = []
        for kw in keywords:
            for line in dmesg_out.split("\n"):
                if kw.lower() in line.lower():
                    found.append(line.strip())
                    break
        if found:
            parts.append(f"\n  [{category}] {len(found)} related messages:")
            for msg in found[:5]:
                parts.append(f"    - {msg}")
            if len(found) > 5:
                parts.append(f"    ... ({len(found) - 5} more)")

    # 3. System health indicators
    parts.append("\n\n--- System Health ---")
    parts.append(f"  Uptime: {run_cmd(['uptime']).strip()}")
    parts.append(f"  Memory: {run_cmd(['free', '-h']).strip()}")
    parts.append(f"  Disk: {run_cmd(['df', '-h', '/']).strip()}")

    _diagnosis_tasks[task_id] = {
        "status": "completed",
        "result": parts,
        "type": "dmesg",
        "message_count": len(dmesg_out.split("\n")) if dmesg_out else 0,
    }

    return "\n".join(parts)


def query_diagnosis_task(task_id: str) -> str:
    """Query the status and result of a diagnosis task by task ID."""
    if task_id in _diagnosis_tasks:
        task = _diagnosis_tasks[task_id]
        result = [
            f"=== TASK {task_id} ===",
            f"Status: {task['status']}",
            f"Type: {task['type']}",
        ]
        result_lines = "\n".join(task.get("result", []))
        result.append(f"\nResult:\n{result_lines}")
        return "\n".join(result)
    else:
        return (f"[ERROR] Task '{task_id}' not found. "
                f"Use list_history_tasks() to see all available tasks.")


def list_history_tasks() -> str:
    """List all historical diagnosis tasks."""
    if not _diagnosis_tasks:
        return "No diagnosis tasks have been created yet."

    parts = [f"=== DIAGNOSIS TASK HISTORY ({len(_diagnosis_tasks)} tasks) ==="]
    for task_id, task in _diagnosis_tasks.items():
        parts.append(f"\n  [{task['status'].upper()}] {task_id}")
        parts.append(f"    Type: {task['type']}")
        parts.append(f"    Result: use query_diagnosis_task('{task_id}') to view details")
    return "\n".join(parts)
