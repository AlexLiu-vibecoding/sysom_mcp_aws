"""Network diagnostic tools: packetdrop, netjitter."""

from ..utils.system import run_cmd, run_shell, check_command, detect_os_family


def get_primary_interfaces() -> list[str]:
    """Get primary network interfaces (exclude loopback)."""
    out = run_cmd(["ip", "-o", "link", "show"])
    interfaces = []
    for line in out.split("\n"):
        if "LOOPBACK" not in line.upper():
            iface = line.split(":")[1].strip() if ": " in line else ""
            if iface:
                interfaces.append(iface)
    return interfaces


def packetdrop() -> str:
    """Network packet drop diagnosis: check drops at interface, qdisc, conntrack, driver levels."""
    parts = ["=== NETWORK PACKET DROP DIAGNOSIS ==="]

    interfaces = get_primary_interfaces()
    if not interfaces:
        parts.append("\nNo non-loopback interfaces found.")
        return "\n".join(parts)

    # 1. Interface-level drops (netstat -i / ip -s)
    parts.append("\n--- Interface Statistics (ip -s link) ---")
    for iface in interfaces:
        parts.append(f"\n  Interface: {iface}")
        parts.append(run_cmd(["ip", "-s", "link", "show", iface]))

    # 2. Qdisc drops
    parts.append("\n--- Qdisc (queue discipline) Drops ---")
    parts.append(run_cmd(["tc", "-s", "qdisc", "show"]))

    # 3. Softnet drops (softirq processing)
    parts.append("\n--- Softnet Statistics (/proc/net/softnet_stat) ---")
    softnet = run_cmd(["cat", "/proc/net/softnet_stat"])
    # Parse: cpu, processed, dropped, time_squeeze, ...
    parts.append(softnet)
    if not softnet.startswith("[ERROR"):
        parts.append("\n  (columns: cpu, processed, dropped, time_squeeze, cpu_collision, ...)")
        total_dropped = 0
        for line in softnet.split("\n"):
            fields = line.strip().split()
            if len(fields) >= 3:
                try:
                    total_dropped += int(fields[2], 16)  # hex values
                except ValueError:
                    pass
        parts.append(f"  Total softnet drops: {total_dropped}")

    # 4. Conntrack table
    parts.append("\n--- Conntrack Table Status ---")
    ct_count = run_cmd(["cat", "/proc/net/nf_conntrack"], timeout=5)
    ct_count_lines = len(ct_count.split("\n")) if not ct_count.startswith("[ERROR") else 0
    ct_max = run_cmd(["sysctl", "-n", "net.netfilter.nf_conntrack_max"])
    ct_current = run_cmd(["sysctl", "-n", "net.netfilter.nf_conntrack_count"])
    parts.append(f"  Current entries: {ct_current.strip() or ct_count_lines}")
    parts.append(f"  Max entries: {ct_max.strip()}")
    if ct_current.strip().isdigit() and ct_max.strip().isdigit():
        ratio = int(ct_current.strip()) / int(ct_max.strip()) * 100 if int(ct_max.strip()) > 0 else 0
        parts.append(f"  Utilization: {ratio:.1f}%")
        if ratio > 90:
            parts.append("  WARNING: Conntrack table nearly full! Risk of packet drops.")

    # 5. Driver-level drops via ethtool
    parts.append("\n--- Driver Statistics (ethtool -S) ---")
    for iface in interfaces:
        if check_command("ethtool"):
            stats = run_cmd(["ethtool", "-S", iface], timeout=10)
            if not stats.startswith("[ERROR"):
                drop_related = []
                for line in stats.split("\n"):
                    if any(kw in line.lower() for kw in ["drop", "error", "fifo", "miss", "overrun", "queue", "busy"]):
                        drop_related.append(line)
                if drop_related:
                    parts.append(f"\n  {iface} (drop/error related counters):")
                    for dl in drop_related[:15]:
                        parts.append(f"    {dl.strip()}")
                else:
                    parts.append(f"\n  {iface}: no drop/error counters found")
            else:
                parts.append(f"\n  {iface}: ethtool not supported")

    # 6. Network errors (netstat -i)
    parts.append("\n--- Interface Errors (netstat -i) ---")
    if check_command("netstat"):
        parts.append(run_cmd(["netstat", "-i"]))
    else:
        parts.append("  netstat not available")

    # 7. Listen queue drops
    parts.append("\n--- TCP Listen Queue Overflows ---")
    parts.append(run_shell(
        "nstat -az 2>/dev/null | grep -E 'ListenOverflows|ListenDrops|TCPBacklogDrop' || "
        "echo '(nstat not available, try installing iproute package)'"
    ))

    return "\n".join(parts)


def netjitter() -> str:
    """Network jitter diagnosis: latency variance, queue delays, RTT analysis."""
    parts = ["=== NETWORK JITTER DIAGNOSIS ==="]

    interfaces = get_primary_interfaces()
    if not interfaces:
        parts.append("\nNo non-loopback interfaces found.")
        return "\n".join(parts)

    # 1. Interface speed and duplex
    parts.append("\n--- Interface Speed/Duplex ---")
    for iface in interfaces:
        if check_command("ethtool"):
            speed = run_cmd(["ethtool", iface], timeout=5)
            for line in speed.split("\n"):
                if any(kw in line.lower() for kw in ["speed:", "duplex:", "auto-negotiation:", "link detected"]):
                    parts.append(f"  {iface}: {line.strip()}")

    # 2. Qdisc latency
    parts.append("\n--- Qdisc Latency (tc -s qdisc) ---")
    qdisc_out = run_cmd(["tc", "-s", "qdisc", "show"])
    for line in qdisc_out.split("\n"):
        # Show bytes dropped, backlog, and latency indicators
        if any(kw in line.lower() for kw in ["fq_codel", "fq", "pfifo", "bfifo", "red", "backlog"]):
            parts.append(f"  {line.strip()}")
        elif "throttle" in line.lower() or "overlimit" in line.lower():
            parts.append(f"  {line.strip()}")

    # 3. Ping RTT to various targets
    parts.append("\n--- RTT Measurements ---")
    # Local gateway
    gw = run_cmd(["ip", "route", "show", "default"])
    gw_ip = ""
    for line in gw.split("\n"):
        if "default via" in line:
            gw_ip = line.split()[2]
            break
    if gw_ip:
        ping_gw = run_cmd(["ping", "-c", "5", "-q", gw_ip], timeout=15)
        parts.append(f"  Gateway ({gw_ip}):")
        for line in ping_gw.split("\n"):
            if any(kw in line for kw in ["rtt", "loss", "min/avg/max"]):
                parts.append(f"    {line.strip()}")

    # DNS
    dns = run_cmd(["cat", "/etc/resolv.conf"])
    for line in dns.split("\n"):
        if "nameserver" in line:
            ns_ip = line.split()[1]
            if not ns_ip.startswith("127."):
                ping_dns = run_cmd(["ping", "-c", "3", "-q", ns_ip], timeout=10)
                for pl in ping_dns.split("\n"):
                    if any(kw in pl for kw in ["rtt", "loss"]):
                        parts.append(f"  DNS ({ns_ip}): {pl.strip()}")

    # 4. Active connections with jitter potential
    parts.append("\n--- High-Latency Connections (TCP retransmit) ---")
    if check_command("ss"):
        retrans = run_cmd(["ss", "-t", "-i"])
        retrans_lines = retrans.split("\n")
        parts.append("\n".join(retrans_lines[:20]))
        if len(retrans_lines) > 20:
            parts.append(f"  ... ({len(retrans_lines) - 20} more entries)")
    elif check_command("netstat"):
        parts.append(run_cmd(["netstat", "-s"]))
        parts.append("\n--- TCP Connections ---")
        parts.append(run_cmd(["netstat", "-tan"]))
    else:
        parts.append("  Neither ss nor netstat available")

    # 5. Interrupt distribution
    parts.append("\n--- IRQ Distribution (interrupts) ---")
    # Check interrupts for network devices
    irq_out = run_cmd(["cat", "/proc/interrupts"])
    net_irqs = []
    for line in irq_out.split("\n"):
        for iface in interfaces:
            if iface in line or (iface.replace("eth", "mlx") in line):
                net_irqs.append(line)
                break
    if net_irqs:
        parts.append("\n".join(net_irqs[:10]))
    else:
        parts.append("  (no network IRQ counter found)")

    # 6. RCV/SEND buffer usage
    parts.append("\n--- TCP Buffer Usage ---")
    for param in [
        "net.core.rmem_default", "net.core.rmem_max",
        "net.core.wmem_default", "net.core.wmem_max",
        "net.ipv4.tcp_rmem", "net.ipv4.tcp_wmem",
    ]:
        val = run_cmd(["sysctl", "-n", param])
        if not val.startswith("[ERROR"):
            parts.append(f"  {param.split('.')[-1]}: {val.strip()}")

    # 7. Ring buffer sizes
    parts.append("\n--- Ring Buffer Sizes ---")
    for iface in interfaces:
        if check_command("ethtool"):
            ring = run_cmd(["ethtool", "-g", iface], timeout=5)
            if not ring.startswith("[ERROR"):
                for line in ring.split("\n"):
                    if "RX" in line or "TX" in line:
                        parts.append(f"  {iface}: {line.strip()}")

    return "\n".join(parts)
