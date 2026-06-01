"""Container runtime detection and exec utilities."""

import json
import os
from .system import run_cmd, check_command


def detect_container_runtime() -> str | None:
    """Detect the container runtime on this host: docker, containerd, or None."""
    if check_command("docker"):
        out = run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"])
        if not out.startswith("[ERROR"):
            return "docker"
    if check_command("crictl"):
        out = run_cmd(["crictl", "version"])
        if not out.startswith("[ERROR"):
            return "containerd"
    if os.path.isdir("/run/containerd"):
        return "containerd"  # crio also uses crictl
    return None


def list_java_containers(runtime: str) -> list[dict]:
    """List containers running Java processes."""
    containers = []
    if runtime == "docker":
        out = run_cmd(["docker", "ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}"])
        for line in out.split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                cid, name = parts[0], parts[1]
                image = parts[2] if len(parts) > 2 else ""
                # Check if it's a Java container by image name or by inspecting
                if any(kw in image.lower() for kw in ["java", "jdk", "jre", "spring",
                                                        "tomcat", "jenkins", "elastic",
                                                        "kafka", "zookeeper", "hadoop",
                                                        "smartdelivery"]):
                    # Verify by running ps inside
                    ps_out = run_cmd(["docker", "exec", cid, "ps", "-ef"])
                    if "java" in ps_out.lower():
                        containers.append({"id": cid, "name": name, "image": image, "runtime": "docker"})
        return containers
    elif runtime == "containerd":
        out = run_cmd(["crictl", "ps", "--output", "json"])
        try:
            data = json.loads(out)
            for c in data.get("containers", []):
                cid = c.get("id", "")[:12]
                name = c.get("metadata", {}).get("name", "")
                image = c.get("image", {}).get("image", "")
                if any(kw in image.lower() for kw in ["java", "jdk", "jre", "spring",
                                                        "tomcat", "jenkins", "elastic",
                                                        "kafka", "zookeeper"]):
                    ps_out = run_cmd(["crictl", "exec", cid, "ps", "-ef"])
                    if "java" in ps_out.lower():
                        containers.append({"id": cid, "name": name, "image": image, "runtime": "containerd"})
        except json.JSONDecodeError:
            pass
        return containers
    return []


def exec_in_container(container_id: str, cmd_args: list[str], runtime: str = "docker") -> str:
    """Execute a command inside a container."""
    if runtime == "docker":
        return run_cmd(["docker", "exec", container_id] + cmd_args, timeout=30)
    elif runtime == "containerd":
        return run_cmd(["crictl", "exec", container_id] + cmd_args, timeout=30)
    return "[ERROR] unknown container runtime"


def get_java_pid_in_container(container_id: str, runtime: str = "docker") -> str | None:
    """Get the Java process PID inside a container."""
    out = exec_in_container(container_id, ["ps", "-ef"], runtime)
    for line in out.split("\n"):
        if "java" in line.lower() and "grep" not in line.lower():
            parts = line.strip().split()
            if parts:
                return parts[1]  # PID is second column in ps output
    return None
