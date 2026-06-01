"""System command utilities for running diagnostics."""

import subprocess
import shutil
import os


def run_cmd(cmd: list[str], timeout: int = 30) -> str:
    """Run a shell command and return its output. Returns error message on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr.strip()}"
        return output if output else f"(no output, exit code {result.returncode})"
    except FileNotFoundError:
        return f"[ERROR] command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"[ERROR] command timed out after {timeout}s: {' '.join(cmd)}"
    except PermissionError:
        return f"[ERROR] permission denied: {' '.join(cmd)}"
    except Exception as e:
        return f"[ERROR] {e}"


def run_shell(script: str, timeout: int = 30) -> str:
    """Run a shell script (string) and return output."""
    try:
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr.strip()}"
        return output if output else f"(no output, exit code {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"[ERROR] script timed out after {timeout}s"
    except Exception as e:
        return f"[ERROR] {e}"


def check_command(name: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(name) is not None


def detect_os() -> str:
    """Detect OS version."""
    info = {}
    for f in ["/etc/os-release", "/etc/system-release"]:
        if os.path.exists(f):
            with open(f) as fh:
                for line in fh:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip('"')
            break
    return info.get("PRETTY_NAME", info.get("NAME", os.uname().sysname))


def detect_os_family() -> str:
    """Detect OS family: amazonlinux2, amazonlinux2023, ubuntu, etc."""
    if os.path.exists("/etc/system-release"):
        content = open("/etc/system-release").read().strip()
        if "Amazon Linux release 2" in content:
            return "amazonlinux2"
        if "Amazon Linux" in content and "2023" in content:
            return "amazonlinux2023"
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    return val
    return "unknown"


def get_kernel_version() -> str:
    """Get kernel version."""
    return os.uname().release


def get_instance_id() -> str:
    """Get EC2 instance ID from metadata."""
    try:
        result = subprocess.run(
            ["curl", "-s", "--connect-timeout", "2", "http://169.254.169.254/latest/meta-data/instance-id"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return "(not on EC2 or no metadata access)"
