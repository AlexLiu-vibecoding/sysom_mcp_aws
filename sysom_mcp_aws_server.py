#!/usr/bin/env python3
"""
SysOM MCP for AWS - System Diagnostic MCP Server
=================================================
An MCP server providing system diagnostic tools for Amazon EC2 instances.
Runs locally on the EC2 instance and diagnoses the local system.

Usage:
  # stdio mode (for AI assistants like Claude Desktop, Cline, etc.)
  python sysom_mcp_aws_server.py --stdio

  # SSE mode (HTTP server)
  python sysom_mcp_aws_server.py --sse --host 0.0.0.0 --port 7140
"""

import sys
import argparse

from mcp.server.fastmcp import FastMCP

# Import all diagnostic tool modules
from src.tools import memory, io, network, sched, crash, other, aws_ebs

# Import system utilities
from src.utils.system import detect_os, detect_os_family, get_kernel_version, get_instance_id

# Create MCP server
mcp = FastMCP("SysOM-AWS")


@mcp.resource("sysom://env")
def get_env_info() -> str:
    """Get current environment info (OS, kernel, instance ID)."""
    return (
        f"OS: {detect_os()}\n"
        f"Kernel: {get_kernel_version()}\n"
        f"Instance: {get_instance_id()}"
    )


# ===== Memory Diagnostics =====

@mcp.tool()
def memgraph() -> str:
    """Memory panorama analysis: scan memory usage, slab, fragmentation, swap, top consumers."""
    return memory.memgraph()


@mcp.tool()
def javamem() -> str:
    """Java memory diagnosis: analyze Java heap, GC stats, native memory in containers.
    Detects container runtime (docker/containerd) and execs into Java containers."""
    return memory.javamem()


@mcp.tool()
def oomcheck() -> str:
    """OOM check: scan for OOM killer events, memory pressure, watermarks, low memory conditions."""
    return memory.oomcheck()


# ===== IO Diagnostics =====

@mcp.tool()
def iofsstat() -> str:
    """IO filesystem statistics: analyze mount points, disk usage, block devices, IO scheduler."""
    return io.iofsstat()


@mcp.tool()
def iodiagnose() -> str:
    """IO diagnosis: analyze IO latency, queue depth, top IO processes, disk throughput."""
    return io.iodiagnose()


# ===== Network Diagnostics =====

@mcp.tool()
def packetdrop() -> str:
    """Network packet drop diagnosis: interface drops, qdisc drops, conntrack, driver stats."""
    return network.packetdrop()


@mcp.tool()
def netjitter() -> str:
    """Network jitter diagnosis: latency variance, RTT measurements, buffer sizes, IRQ distribution."""
    return network.netjitter()


# ===== Scheduler Diagnostics =====

@mcp.tool()
def delay() -> str:
    """Scheduler delay diagnosis: scheduling latency, context switches, RCU stalls, softirq delays."""
    return sched.delay()


@mcp.tool()
def loadtask() -> str:
    """Load/task diagnosis: analyze CPU hot processes, run queue, D-state tasks, load average."""
    return sched.loadtask()


# ===== Crash/Diagnosis Task Management =====

@mcp.tool()
def create_vmcore_diagnosis_task(vmcore_path: str = "auto") -> str:
    """Create a kernel crash diagnosis task from VMCORE file.
    Args:
        vmcore_path: Path to vmcore file, or 'auto' to search /var/crash/
    """
    return crash.create_vmcore_diagnosis_task(vmcore_path)


@mcp.tool()
def create_dmesg_diagnosis_task(hours: int = 24) -> str:
    """Create a diagnosis task based on dmesg/kernel log analysis.
    Args:
        hours: Look back period in hours (default: 24)
    """
    return crash.create_dmesg_diagnosis_task(hours)


@mcp.tool()
def query_diagnosis_task(task_id: str) -> str:
    """Query the status and result of a diagnosis task by task ID.
    Args:
        task_id: Task ID from create_vmcore_diagnosis_task or create_dmesg_diagnosis_task
    """
    return crash.query_diagnosis_task(task_id)


@mcp.tool()
def list_history_tasks() -> str:
    """List all historical diagnosis tasks."""
    return crash.list_history_tasks()


# ===== Other Diagnostics =====

@mcp.tool()
def vmcore(vmcore_path: str = "") -> str:
    """VMCORE analysis: analyze kernel crash dump file.
    Args:
        vmcore_path: Path to vmcore file (optional, auto-search if empty)
    """
    return other.vmcore(vmcore_path or None)


@mcp.tool()
def diskanalysis() -> str:
    """Disk analysis: disk usage, block devices, EBS volume mapping with CloudWatch metrics."""
    return other.diskanalysis()


# ===== AWS-specific Diagnostics =====

@mcp.tool()
def ebs_performance() -> str:
    """EBS volume performance: CloudWatch metrics (IOPS, throughput, burst balance, queue length)."""
    return aws_ebs.ebs_performance()


@mcp.tool()
def ec2_metadata() -> str:
    """Display detailed EC2 instance metadata including VPC/subnet/security group info."""
    return aws_ebs.ec2_metadata()


def main():
    parser = argparse.ArgumentParser(description="SysOM MCP for AWS - System Diagnostic Server")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode (for AI clients)")
    parser.add_argument("--sse", action="store_true", help="Run in SSE/HTTP mode")
    parser.add_argument("--host", default="0.0.0.0", help="SSE host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7140, help="SSE port (default: 7140)")
    args = parser.parse_args()

    if args.sse:
        print(f"Starting SysOM-AWS MCP server (SSE mode) on {args.host}:{args.port}", file=sys.stderr)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        # Default: stdio mode
        print("Starting SysOM-AWS MCP server (stdio mode)", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
