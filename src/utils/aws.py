"""AWS-specific utilities: EC2 metadata, EBS metrics via CloudWatch."""

import json
from .system import run_cmd, run_shell


def get_ec2_metadata() -> dict:
    """Fetch EC2 instance metadata."""
    metadata = {}
    paths = [
        ("instance_id", "instance-id"),
        ("instance_type", "instance-type"),
        ("availability_zone", "placement/availability-zone"),
        ("region", "placement/region"),
        ("ami_id", "ami-id"),
        ("hostname", "hostname"),
        ("local_ipv4", "local-ipv4"),
        ("public_ipv4", "public-ipv4"),
    ]
    for key, path in paths:
        val = run_cmd(["curl", "-s", "--connect-timeout", "2",
                       f"http://169.254.169.254/latest/meta-data/{path}"])
        if not val.startswith("[ERROR"):
            metadata[key] = val
    out = run_cmd(["curl", "-s", "--connect-timeout", "2",
                   "http://169.254.169.254/latest/meta-data/block-device-mapping/"])
    if not out.startswith("[ERROR") and out != "(no output, exit code 0)":
        metadata["block_devices"] = out.split()
    return metadata


def get_ebs_volume_info() -> list[dict]:
    """Get EBS volume IDs mapped to local devices."""
    volumes = []
    out = run_cmd(["lsblk", "-o", "NAME,SERIAL,SIZE,TYPE,MOUNTPOINT", "-J"])
    try:
        data = json.loads(out)
        for dev in data.get("blockdevices", []):
            children = dev.get("children", [dev])
            for child in children:
                serial = child.get("serial", "") or ""
                if "vol" in serial:
                    volumes.append({
                        "device": f"/dev/{child.get('name', '')}",
                        "volume_id": serial,
                        "size": child.get("size", ""),
                        "mountpoint": child.get("mountpoint", ""),
                    })
    except (json.JSONDecodeError, KeyError):
        pass
    return volumes


def _build_metric_script(volume_id: str, region: str) -> str:
    """Build the Python script for fetching CloudWatch metrics."""
    import textwrap
    script = textwrap.dedent(f"""\
    import json, boto3
    from datetime import datetime, timedelta, timezone

    cw = boto3.client("cloudwatch", region_name="{region}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=1)

    metrics = {{}}
    for metric in [
        "VolumeReadOps", "VolumeWriteOps",
        "VolumeReadBytes", "VolumeWriteBytes",
        "VolumeQueueLength", "BurstBalance",
        "VolumeThroughputPercentage",
        "VolumeConsumedReadWriteOps",
    ]:
        try:
            resp = cw.get_metric_statistics(
                Namespace="AWS/EBS",
                MetricName=metric,
                Dimensions=[{{"Name": "VolumeId", "Value": "{volume_id}"}}],
                StartTime=start,
                EndTime=end,
                Period=300,
                Statistics=["Average", "Maximum"],
            )
            datapoints = resp.get("Datapoints", [])
            if datapoints:
                avg = [d for d in datapoints if "Average" in d]
                mx = [d for d in datapoints if "Maximum" in d]
                avg_val = round(avg[0]["Average"], 2) if avg else "N/A"
                mx_val = round(mx[0]["Maximum"], 2) if mx else "N/A"
                metrics[metric] = {{"avg_5min": avg_val, "max_5min": mx_val}}
            else:
                metrics[metric] = "no data in last hour"
        except Exception as e:
            metrics[metric] = f"error: {{e}}"

    print(json.dumps(metrics, indent=2))
    """)
    # Escape for shell
    return script.replace('"', '\\"')


def get_ebs_cloudwatch_metrics(volume_id: str, region: str | None = None) -> dict:
    """Get EBS performance metrics from CloudWatch for the last hour."""
    if not region:
        md = get_ec2_metadata()
        region = md.get("region", "us-east-1")

    py_script = _build_metric_script(volume_id, region)
    cmd = f"python3 -c \"{py_script}\""
    result = run_shell(cmd, timeout=30)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"raw_output": result}


def check_ebs_burst_balance(volume_id: str, region: str | None = None) -> str:
    """Check if EBS burst balance is running low."""
    data = get_ebs_cloudwatch_metrics(volume_id, region)
    bb = data.get("BurstBalance", {})
    if isinstance(bb, dict) and "avg_5min" in bb:
        avg_bb = bb["avg_5min"]
        if isinstance(avg_bb, (int, float)):
            if avg_bb < 20:
                return (
                    f"CRITICAL: EBS Burst Balance at {avg_bb}% — "
                    f"performance will throttle soon! Consider gp3 migration."
                )
            elif avg_bb < 50:
                return (
                    f"WARNING: EBS Burst Balance at {avg_bb}% — "
                    f"low headroom, consider gp3 with higher baseline IOPS"
                )
            else:
                return f"Burst Balance is healthy: {avg_bb}%"
    return f"Burst Balance data:\n{json.dumps(data, indent=2)}"
