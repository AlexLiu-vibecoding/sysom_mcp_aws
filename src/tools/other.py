"""Other diagnostic tools: vmcore standalone analysis, diskanalysis."""

from ..utils.system import run_cmd, run_shell, check_command
from ..utils.aws import get_ebs_volume_info, get_ebs_cloudwatch_metrics


def vmcore(vmcore_path: str | None = None) -> str:
    """VMCORE standalone analysis: analyze kernel crash dump."""
    parts = ["=== VMCORE ANALYSIS ==="]

    kdump_ok = False
    out = run_cmd(["systemctl", "is-active", "kdump"])
    if "active" in out.lower():
        kdump_ok = True

    parts.append(f"Kdump status: {'ACTIVE' if kdump_ok else 'INACTIVE'}")

    if not kdump_ok:
        cmdline = run_cmd(["cat", "/proc/cmdline"])
        if "crashkernel=" in cmdline:
            parts.append("  (crashkernel parameter present but service not running)")

    # Find vmcore files
    files = []
    if vmcore_path:
        files = [vmcore_path]
    else:
        for path in ["/var/crash", "/dump"]:
            found = run_cmd(["find", path, "-name", "vmcore*", "-type", "f"], timeout=10)
            if not found.startswith("[ERROR") and found.strip():
                files.extend(found.strip().split("\n"))

    if not files:
        parts.append("\nNo vmcore files found.")
        parts.append("\nNote: EC2 instances don't have kdump enabled by default.")
        parts.append("To use this feature, you need to:")
        parts.append("  1. Launch EC2 with 'crashkernel=auto' kernel parameter")
        parts.append("  2. Install kexec-tools")
        parts.append("  3. Configure /etc/kdump.conf")
        parts.append("  4. Start kdump service")
        return "\n".join(parts)

    for fpath in files[:3]:
        parts.append(f"\n{'='*60}")
        parts.append(f"File: {fpath}")
        parts.append(f"Size: {run_cmd(['ls', '-lh', fpath]).strip()}")

        if check_command("crash"):
            parts.append(f"\n  First 200 bytes analysis:")
            parts.append(f"  {run_cmd(['xxd', fpath, '-l', '200']).strip()}")
            parts.append("\n  To analyze interactively:")
            parts.append(f"    crash {fpath} /usr/lib/debug/lib/modules/$(uname -r)/vmlinux")
        else:
            parts.append("\n  crash tool not installed. Install with:")
            parts.append("    sudo yum install -y crash")
            parts.append("    sudo yum install -y kernel-debuginfo-$(uname -r)")

    return "\n".join(parts)


def diskanalysis() -> str:
    """Disk analysis: analyze disk usage, performance, and EBS health."""
    parts = ["=== DISK ANALYSIS ==="]

    # 1. Overall disk usage
    parts.append("\n--- Disk Usage ---")
    parts.append(run_cmd(["df", "-h", "--total"]))
    parts.append("\n--- Inode Usage ---")
    parts.append(run_cmd(["df", "-i", "--total"]))

    # 2. Block device layout
    parts.append("\n--- Block Device Layout ---")
    parts.append(run_cmd(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,PKNAME,ROTA"]))

    # 3. EBS Volume info (if on EC2)
    parts.append("\n--- EBS Volume Mapping ---")
    ebs_volumes = get_ebs_volume_info()
    if ebs_volumes:
        for vol in ebs_volumes:
            parts.append(f"  Device: {vol['device']}")
            parts.append(f"  Volume ID: {vol['volume_id']}")
            parts.append(f"  Size: {vol['size']}")
            parts.append(f"  Mount: {vol['mountpoint']}")
            parts.append("")
    else:
        parts.append("  No EBS volumes detected (may not be on EC2 Nitro)")

    # 4. Disk performance (iostat)
    parts.append("\n--- Disk Performance (iostat -x 1 3) ---")
    if check_command("iostat"):
        io = run_cmd(["iostat", "-x", "1", "3"], timeout=10)
        io_lines = io.split("\n")
        parts.append("\n".join(io_lines[-15:]))
    else:
        parts.append(run_cmd(["cat", "/proc/diskstats"]))

    # 5. Largest directories
    parts.append("\n--- Top 20 Largest Directories (/) ---")
    parts.append(run_cmd(["du", "-x", "-d", "1", "/", "--exclude=/proc",
                          "--exclude=/sys", "--exclude=/dev"], timeout=15))

    parts.append("\n--- Top 20 Largest Files in /var ---")
    parts.append(run_cmd(["find", "/var", "-type", "f", "-size", "+100M",
                          "-exec", "ls", "-lh", "{}", "+"], timeout=15))

    # 6. EBS CloudWatch metrics
    if ebs_volumes:
        parts.append("\n--- EBS CloudWatch Metrics (last 1 hour) ---")
        for vol in ebs_volumes:
            vol_id = vol["volume_id"]
            parts.append(f"\n  Volume: {vol_id} ({vol['device']})")
            metrics = get_ebs_cloudwatch_metrics(vol_id)
            if isinstance(metrics, dict):
                for metric_name, data in metrics.items():
                    if isinstance(data, dict):
                        parts.append(f"    {metric_name}: avg={data.get('avg_5min')}, max={data.get('max_5min')}")
                    else:
                        parts.append(f"    {metric_name}: {data}")
            else:
                parts.append(f"    {metrics}")

    # 7. Disk mount options
    parts.append("\n--- Mount Options ---")
    parts.append(run_cmd(["cat", "/proc/mounts"]))

    # 8. Swap files
    parts.append("\n--- Swap ---")
    parts.append(run_cmd(["swapon", "--show"]))

    return "\n".join(parts)
