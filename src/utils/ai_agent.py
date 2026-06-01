"""AI Agent module - DeepSeek API integration for intelligent diagnosis analysis.

Uses DeepSeek's OpenAI-compatible API to interpret raw diagnostic output
and provide human-readable analysis with recommendations.
"""

import os
import json
from typing import Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def _build_system_prompt(diagnosis_type: str) -> str:
    """Build system prompt for the diagnostic type."""
    base = """You are an expert Linux systems administrator / SRE engineer with deep knowledge of:
- Linux kernel internals (memory management, IO subsystem, networking, scheduler)
- System performance analysis and tuning
- AWS EC2 and EBS troubleshooting
- Container runtimes (Docker, containerd)
- Java application diagnostics

Your task is to analyze raw system diagnostic output and provide:
1. A concise summary of the current state
2. Any issues or anomalies detected (be specific with numbers/thresholds)
3. Root cause analysis of problems found
4. Actionable recommendations (specific commands to run, config changes to make)

Be concise but thorough. Use technical precision. If everything looks healthy, say so clearly.
If critical issues exist, flag them with CRITICAL or WARNING prefixes.
"""
    return base


def _build_user_prompt(diagnosis_type: str, raw_output: str, context: str = "") -> str:
    """Build the user prompt with diagnostic output."""
    prompt = f"""Analyze the following {diagnosis_type} diagnostic output from an EC2 instance.

{context}

--- RAW DIAGNOSTIC OUTPUT ---
{raw_output}

--- END OUTPUT ---

Provide: summary, issues found, root cause analysis, and actionable recommendations."""
    return prompt


def analyze_with_deepseek(
    diagnosis_type: str,
    raw_output: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    context: str = "",
) -> str:
    """Send diagnostic output to DeepSeek for AI-powered analysis.

    Args:
        diagnosis_type: Type of diagnosis (memory, IO, network, etc.)
        raw_output: Raw diagnostic command output
        api_key: DeepSeek API key (defaults to DEEPSEEK_API_KEY env var)
        model: Model name (default: deepseek-chat)
        base_url: API base URL (default: https://api.deepseek.com)
        context: Additional context about the system

    Returns:
        AI analysis text
    """
    if not HAS_OPENAI:
        return (
            "[ERROR] openai package not installed.\n"
            "Install with: pip install openai\n"
            "Or: uv add openai"
        )

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return (
            "[ERROR] DeepSeek API key not provided.\n"
            "Pass api_key parameter or set DEEPSEEK_API_KEY environment variable.\n"
            "Get a key at: https://platform.deepseek.com/api_keys"
        )

    if not raw_output or raw_output.startswith("[ERROR"):
        return f"[SKIP] No valid diagnostic data to analyze (raw output was empty or errored)"

    try:
        client = OpenAI(api_key=key, base_url=base_url)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_system_prompt(diagnosis_type)},
                {"role": "user", "content": _build_user_prompt(diagnosis_type, raw_output[:15000], context)},
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"[ERROR] DeepSeek API call failed: {e}"
