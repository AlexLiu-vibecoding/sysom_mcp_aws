"""AI-powered diagnostic tools that run system diagnostics then analyze with DeepSeek."""

from ..utils.ai_agent import analyze_with_deepseek
from ..utils.system import get_instance_id, detect_os, get_kernel_version
from . import memory, io, network, sched, other, aws_ebs


def _system_context() -> str:
    """Build system context string."""
    return (
        f"System: {detect_os()}\n"
        f"Kernel: {get_kernel_version()}\n"
        f"Instance: {get_instance_id()}"
    )


def ai_memory_analysis(api_key: str = "") -> str:
    """Run full memory diagnostics and analyze with DeepSeek AI.
    Args:
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append("STEP 1: Collecting memory diagnostics...")
    parts.append("=" * 60)

    raw = []
    raw.append("--- memgraph output ---")
    raw.append(memory.memgraph())
    raw.append("\n--- oomcheck output ---")
    raw.append(memory.oomcheck())
    raw.append("\n--- javamem output ---")
    raw.append(memory.javamem())

    combined = "\n".join(raw)
    parts.append(f"Collected {len(combined)} characters of diagnostic data\n")
    parts.append("=" * 60)
    parts.append("STEP 2: DeepSeek AI analysis")
    parts.append("=" * 60)

    analysis = analyze_with_deepseek(
        "memory",
        combined,
        api_key=api_key or None,
        context=f"Full memory diagnostics including memgraph, oomcheck, and javamem.\n{_system_context()}",
    )
    parts.append(analysis)

    return "\n".join(parts)


def ai_io_analysis(api_key: str = "") -> str:
    """Run full IO diagnostics and analyze with DeepSeek AI.
    Args:
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append("STEP 1: Collecting IO diagnostics...")
    parts.append("=" * 60)

    raw = []
    raw.append("--- iofsstat output ---")
    raw.append(io.iofsstat())
    raw.append("\n--- iodiagnose output ---")
    raw.append(io.iodiagnose())

    combined = "\n".join(raw)
    parts.append(f"Collected {len(combined)} characters of diagnostic data\n")
    parts.append("=" * 60)
    parts.append("STEP 2: DeepSeek AI analysis")
    parts.append("=" * 60)

    analysis = analyze_with_deepseek(
        "IO/filesystem",
        combined,
        api_key=api_key or None,
        context=f"Full IO diagnostics including filesystem stats and IO performance.\n{_system_context()}",
    )
    parts.append(analysis)

    return "\n".join(parts)


def ai_network_analysis(api_key: str = "") -> str:
    """Run full network diagnostics and analyze with DeepSeek AI.
    Args:
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append("STEP 1: Collecting network diagnostics...")
    parts.append("=" * 60)

    raw = []
    raw.append("--- packetdrop output ---")
    raw.append(network.packetdrop())
    raw.append("\n--- netjitter output ---")
    raw.append(network.netjitter())

    combined = "\n".join(raw)
    parts.append(f"Collected {len(combined)} characters of diagnostic data\n")
    parts.append("=" * 60)
    parts.append("STEP 2: DeepSeek AI analysis")
    parts.append("=" * 60)

    analysis = analyze_with_deepseek(
        "network",
        combined,
        api_key=api_key or None,
        context=f"Full network diagnostics including packet drops and jitter.\n{_system_context()}",
    )
    parts.append(analysis)

    return "\n".join(parts)


def ai_scheduler_analysis(api_key: str = "") -> str:
    """Run full scheduler diagnostics and analyze with DeepSeek AI.
    Args:
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append("STEP 1: Collecting scheduler diagnostics...")
    parts.append("=" * 60)

    raw = []
    raw.append("--- delay output ---")
    raw.append(sched.delay())
    raw.append("\n--- loadtask output ---")
    raw.append(sched.loadtask())

    combined = "\n".join(raw)
    parts.append(f"Collected {len(combined)} characters of diagnostic data\n")
    parts.append("=" * 60)
    parts.append("STEP 2: DeepSeek AI analysis")
    parts.append("=" * 60)

    analysis = analyze_with_deepseek(
        "scheduler/CPU",
        combined,
        api_key=api_key or None,
        context=f"Full scheduler diagnostics including delay analysis and load/task analysis.\n{_system_context()}",
    )
    parts.append(analysis)

    return "\n".join(parts)


def ai_full_diagnosis(api_key: str = "") -> str:
    """Run ALL diagnostics and analyze everything with DeepSeek AI.
    Args:
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append("FULL SYSTEM DIAGNOSIS - Collecting all metrics...")
    parts.append("=" * 60)

    # Collect key outputs (summary only to stay under token limits)
    raw_parts = []
    collectors = [
        ("Memory (memgraph + oomcheck)", lambda: "\n".join([memory.memgraph(), memory.oomcheck()])),
        ("IO (iofsstat)", io.iofsstat),
        ("Network (packetdrop)", network.packetdrop),
        ("Scheduler (loadtask)", sched.loadtask),
        ("Disk Analysis", other.diskanalysis),
    ]

    for title, fn in collectors:
        parts.append(f"\n--- {title} ---")
        output = fn()
        # Truncate each section to avoid token limits
        truncated = output[:3000] + "\n...(truncated)" if len(output) > 3000 else output
        raw_parts.append(f"=== {title} ===\n{truncated}")

    combined = "\n\n".join(raw_parts)
    parts.append(f"\nCollected {len(combined)} characters across all subsystems\n")
    parts.append("=" * 60)
    parts.append("DeepSeek AI Full System Analysis")
    parts.append("=" * 60)

    analysis = analyze_with_deepseek(
        "full system",
        combined,
        api_key=api_key or None,
        context=(
            f"Comprehensive system health check including memory, IO, network, "
            f"scheduler, and disk subsystems.\n{_system_context()}\n"
            f"Provide an overall health assessment and priority-ordered recommendations."
        ),
        model="deepseek-chat",
    )
    parts.append(analysis)

    return "\n".join(parts)


def ai_ask_deepseek(question: str, api_key: str = "") -> str:
    """Ask DeepSeek a general question about system troubleshooting.
    Args:
        question: Your question about system diagnostics, troubleshooting, or AWS
        api_key: DeepSeek API key (or set DEEPSEEK_API_KEY env var)
    """
    parts = ["=" * 60]
    parts.append(f"Question: {question}")
    parts.append("=" * 60)

    context = (
        f"System context:\n{_system_context()}\n\n"
        f"The user is asking a system troubleshooting question on an EC2 instance."
    )

    # Run relevant diagnostics based on keywords in the question
    raw_context = ""
    q_lower = question.lower()
    if any(kw in q_lower for kw in ["memory", "oom", "mem", "swap", "java"]):
        raw_context += "\n--- Memory snapshot ---\n"
        raw_context += memory.memgraph()[:2000]
    if any(kw in q_lower for kw in ["io", "disk", "storage", "ebs", "iostat", "slow"]):
        raw_context += "\n--- IO snapshot ---\n"
        raw_context += io.iofsstat()[:2000]
    if any(kw in q_lower for kw in ["network", "net", "packet", "drop", "latency", "jitter"]):
        raw_context += "\n--- Network snapshot ---\n"
        raw_context += network.packetdrop()[:2000]
    if any(kw in q_lower for kw in ["cpu", "load", "scheduler", "process", "high"]):
        raw_context += "\n--- CPU/load snapshot ---\n"
        raw_context += sched.loadtask()[:2000]

    if raw_context:
        raw_context = f"Relevant diagnostics from the system:\n{raw_context}\n"

    analysis = analyze_with_deepseek(
        f"user question: {question}",
        raw_context or "(no auto-collected data - general question)",
        api_key=api_key or None,
        context=f"{context}\n{raw_context}",
    )
    parts.append(analysis)

    return "\n".join(parts)
