"""AWS-specific diagnostic tools: EBS performance, EC2 metadata."""

from ..utils.aws import (
    get_ec2_metadata,
    get_ebs_volume_info,
    get_ebs_cloudwatch_metrics,
    check_ebs_burst_balance,
)
from ..utils.system import run_cmd, check_command
import json


def ebs_performance() -> str:
    """EBS volume performance analysis: CloudWatch metrics, burst balance, throughput."""
    parts = ["=== EBS PERFORMANCE ANALYSIS ==="]

    # 1. EC2 metadata
    parts.append("\n--- Instance Info ---")
    md = get_ec2_metadata()
    parts.append(f"  Instance: {md.get('instance_id', 'N/A')}")
    parts.append(f"  Type: {md.get('instance_type', 'N/A')}")
    parts.append(f"  AZ: {md.get('availability_zone', 'N/A')}")
    parts.append(f"  Region: {md.get('region', 'N/A')}")

    # 2. EBS volume mapping
    parts.append("\n--- EBS Volume Mapping ---")
    volumes = get_ebs_volume_info()

    if not volumes:
        parts.append("  No EBS volumes detected (Nitro instance with NVMe required)")
        parts.append("\n  Alternative: check block devices manually:")
        parts.append(run_cmd(["lsblk", "-o", "NAME,SERIAL,SIZE,TYPE,MOUNTPOINT"]))
        return "\n".join(parts)

    for vol in volumes:
        parts.append(f"\n  Device: {vol['device']}")
        parts.append(f"  Volume ID: {vol['volume_id']}")
        parts.append(f"  Size: {vol['size']}")
        parts.append(f"  Mount: {vol['mountpoint']}")

    # 3. CloudWatch metrics per volume
    region = md.get("region", "us-east-1")
    for vol in volumes:
        vol_id = vol["volume_id"]
        parts.append(f"\n{'='*60}")
        parts.append(f"CloudWatch Metrics - {vol_id} ({vol['device']})")
        parts.append(f"  Period: last 1 hour, 5-min intervals")

        metrics = get_ebs_cloudwatch_metrics(vol_id, region)
        if isinstance(metrics, dict) and metrics.get("raw_output"):
            parts.append(f"  (error fetching metrics: {metrics['raw_output']})")
            continue

        if isinstance(metrics, dict):
            # Burst Balance
            bb = metrics.get("BurstBalance", {})
            if isinstance(bb, dict):
                parts.append(f"\n  Burst Balance:")
                parts.append(f"    Avg (5min): {bb.get('avg_5min', 'N/A')}%")
                parts.append(f"    Max (5min): {bb.get('max_5min', 'N/A')}%")
                avg_bb = bb.get("avg_5min")
                if isinstance(avg_bb, (int, float)):
                    if avg_bb < 20:
                        parts.append("    STATUS: CRITICAL - throttling imminent!")
                    elif avg_bb < 50:
                        parts.append("    STATUS: WARNING - low burst headroom")

            # Queue Length
            ql = metrics.get("VolumeQueueLength", {})
            if isinstance(ql, dict):
                parts.append(f"\n  Queue Length:")
                parts.append(f"    Avg: {ql.get('avg_5min', 'N/A')}")
                parts.append(f"    Max: {ql.get('max_5min', 'N/A')}")

            # IOPS
            reads = metrics.get("VolumeReadOps", {})
            writes = metrics.get("VolumeWriteOps", {})
            if isinstance(reads, dict) and isinstance(writes, dict):
                avg_reads = reads.get("avg_5min", 0)
                avg_writes = writes.get("avg_5min", 0)
                if isinstance(avg_reads, (int, float)) and isinstance(avg_writes, (int, float)):
                    total_iops = round((avg_reads + avg_writes) / 300, 1)  # 300s period
                    parts.append(f"\n  IOPS (avg):")
                    parts.append(f"    Read: {avg_reads} ops/5min ({round(avg_reads/300, 1)}/s)")
                    parts.append(f"    Write: {avg_writes} ops/5min ({round(avg_writes/300, 1)}/s)")
                    parts.append(f"    Total: ~{total_iops} IOPS")

            # Throughput
            rbytes = metrics.get("VolumeReadBytes", {})
            wbytes = metrics.get("VolumeWriteBytes", {})
            if isinstance(rbytes, dict) and isinstance(wbytes, dict):
                avg_r = rbytes.get("avg_5min", 0)
                avg_w = wbytes.get("avg_5min", 0)
                if isinstance(avg_r, (int, float)) and isinstance(avg_w, (int, float)):
                    mb_s_read = round(avg_r / (300 * 1024 * 1024), 2)
                    mb_s_write = round(avg_w / (300 * 1024 * 1024), 2)
                    parts.append(f"\n  Throughput (avg):")
                    parts.append(f"    Read: {mb_s_read} MB/s")
                    parts.append(f"    Write: {mb_s_write} MB/s")

            # Idle Time
            idle = metrics.get("VolumeIdleTime", {})
            if isinstance(idle, dict):
                parts.append(f"\n  Idle Time: {idle.get('avg_5min', 'N/A')} seconds")

        # 4. Local disk stats
        parts.append(f"\n  Local /proc/diskstats for {vol['device'].replace('/dev/', '')}:")
        dev_name = vol["device"].replace("/dev/", "")
        distats = run_cmd(["cat", "/proc/diskstats"])
        for line in distats.split("\n"):
            if dev_name in line and line.strip():
                parts.append(f"    {line.strip()}")

    return "\n".join(parts)


def ec2_metadata() -> str:
    """Display detailed EC2 instance metadata."""
    parts = ["=== EC2 INSTANCE METADATA ==="]

    md = get_ec2_metadata()
    if not md:
        parts.append("  Not running on EC2 or metadata endpoint unreachable.")
        return "\n".join(parts)

    for key, val in md.items():
        if isinstance(val, list):
            parts.append(f"  {key}:")
            for item in val:
                parts.append(f"    - {item}")
        else:
            parts.append(f"  {key}: {val}")

    # Additional network metadata
    parts.append("\n--- Network ---")
    macs = run_cmd(["curl", "-s", "--connect-timeout", "2",
                    "http://169.254.169.254/latest/meta-data/network/interfaces/macs/"])
    if not macs.startswith("[ERROR") and macs.strip():
        for mac in macs.strip().split("\n")[:5]:
            mac = mac.strip("/")
            vpc_id = run_cmd(["curl", "-s", "--connect-timeout", "2",
                              f"http://169.254.169.254/latest/meta-data/network/interfaces/macs/{mac}/vpc-id"])
            subnet_id = run_cmd(["curl", "-s", "--connect-timeout", "2",
                                 f"http://169.254.169.254/latest/meta-data/network/interfaces/macs/{mac}/subnet-id"])
            security_groups = run_cmd(["curl", "-s", "--connect-timeout", "2",
                                        f"http://169.254.169.254/latest/meta-data/network/interfaces/macs/{mac}/security-groups"])
            parts.append(f"  MAC: {mac}")
            parts.append(f"    VPC: {vpc_id}")
            parts.append(f"    Subnet: {subnet_id}")
            parts.append(f"    Security Groups: {security_groups}")

    return "\n".join(parts)
