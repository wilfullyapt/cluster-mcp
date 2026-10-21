"""Render a single Stronghold visibility report image from live report data."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Dark ops card palette
BG = (15, 18, 28)
CARD = (24, 28, 42)
CARD_BORDER = (45, 52, 72)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)
OK = (52, 211, 153)
WARN = (251, 191, 36)
BAD = (251, 113, 133)
ACCENT = (56, 189, 248)
LINE = (36, 42, 58)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    dejavu = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    mono = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    liberation = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/{dejavu}",
        f"/usr/share/fonts/truetype/dejavu/{mono}",
        f"/usr/share/fonts/truetype/liberation/{liberation}",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _traffic(overall: str) -> tuple[str, tuple[int, int, int]]:
    o = (overall or "unknown").lower()
    if o in ("ok", "healthy", "up"):
        return "OK", OK
    if o in ("degraded", "warn", "warning"):
        return "DEGRADED", WARN
    if o in ("down", "critical", "error"):
        return "DOWN", BAD
    return o.upper() or "UNKNOWN", MUTED


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if _text_width(draw, trial, font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def render_visibility_image(report: dict[str, Any], width: int = 1400) -> bytes:
    """Return PNG bytes for a single-page status card."""
    title_f = _font(28, bold=True)
    head_f = _font(18, bold=True)
    body_f = _font(15)
    mono_f = _font(14)
    small_f = _font(12)

    # Pre-layout content lines
    scratch = Image.new("RGB", (width, 200), BG)
    d0 = ImageDraw.Draw(scratch)

    overall = str((report.get("summary") or {}).get("overall") or report.get("overall") or "unknown")
    label, color = _traffic(overall)
    cluster = report.get("cluster") or {}
    summary = report.get("summary") or {}
    ceph = report.get("ceph") or {}
    osd_summary = ceph.get("osd_summary") or {}
    mcp = report.get("mcp") or {}
    warnings = list(report.get("warnings") or [])
    nodes = list(report.get("node_inventory") or [])
    containers = list(report.get("containers") or [])
    storage = list(report.get("storage") or [])
    osds = list(ceph.get("osds") or [])

    lines: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int], int]] = []
    # each: text, font, fill, gap_after

    def add(text: str, font=body_f, fill=TEXT, gap: int = 6) -> None:
        lines.append((text, font, fill, gap))

    add("ClusterMCP · Visibility Report", title_f, TEXT, 4)
    add(f"Generated {report.get('generated_at', '—')} · data_policy={report.get('data_policy', 'live_probes_only')}", small_f, MUTED, 14)
    add(f"Overall  ·  {label}", head_f, color, 8)

    cname = cluster.get("name") or "—"
    quorate = cluster.get("quorate")
    qtxt = "yes" if quorate is True else ("no" if quorate is False else "—")
    add(
        f"Cluster  ·  {cname}  ·  quorate={qtxt}  ·  nodes {summary.get('nodes_online', '—')}/{summary.get('total_nodes', '—')}  ·  "
        f"VMs {summary.get('total_vms', '—')}  ·  CTs {summary.get('total_containers', '—')}",
        body_f,
        TEXT,
        6,
    )

    if mcp:
        add(
            f"ClusterMCP  ·  {mcp.get('version', '—')} @ {mcp.get('commit', '—')} ({mcp.get('branch', '—')}"
            f"{', dirty' if mcp.get('dirty') else ''})  ·  PVE {mcp.get('pve_host', '—')}",
            body_f,
            MUTED,
            12,
        )

    add("Nodes", head_f, ACCENT, 8)
    if not nodes:
        add("  (no node inventory from live probes)", body_f, WARN, 8)
    for n in nodes:
        add(
            f"  {n.get('node')}  ·  {n.get('status')}  ·  {n.get('ip') or '—'}  ·  CPU {n.get('cpu_human') or '—'}  ·  "
            f"RAM {n.get('mem_human') or '—'}  ·  CTs {n.get('containers_count', 0)}  ·  up {n.get('uptime_human') or '—'}",
            mono_f,
            TEXT,
            4,
        )

    add("", body_f, TEXT, 6)
    add("Ceph", head_f, ACCENT, 8)
    pg = ceph.get("pg_states") or {}
    pg_str = ", ".join(f"{k}={v}" for k, v in sorted(pg.items(), key=lambda kv: -kv[1])[:6]) or "—"
    add(
        f"  health {ceph.get('health_status') or (ceph.get('health') or {}).get('status') or '—'}  ·  "
        f"MONs {ceph.get('mon_count') if ceph.get('mon_count') is not None else '—'}  ·  "
        f"OSDs total={osd_summary.get('total')} up={osd_summary.get('up')} in={osd_summary.get('in')}  ·  "
        f"detail={'yes' if osd_summary.get('detail_available') else 'no'} ({osd_summary.get('source') or '—'})",
        body_f,
        TEXT,
        4,
    )
    add(f"  PGs  ·  {pg_str}", body_f, MUTED, 4)
    if osds:
        for o in osds:
            usage = o.get("usage")
            usage_s = f"{usage:.1f}%" if isinstance(usage, int | float) else "—"
            add(
                f"  {o.get('name')}  ·  {o.get('status')}  ·  in={o.get('in')}  ·  use {usage_s}"
                + (f"  ·  host {o.get('node')}" if o.get("node") else ""),
                mono_f,
                TEXT,
                3,
            )
    else:
        add("  per-OSD rows omitted — live OSD tree probe returned no detail (no fabricated fill)", mono_f, WARN, 6)

    add("", body_f, TEXT, 6)
    add("Containers", head_f, ACCENT, 8)
    if not containers:
        add("  (none)", body_f, MUTED, 6)
    for c in containers:
        add(
            f"  {c.get('vmid')} {c.get('name')}  ·  {c.get('node')}  ·  {c.get('status')}  ·  "
            f"CPU {c.get('cpu_human')}  ·  RAM {c.get('mem_human')}  ·  disk {c.get('disk_human')}  ·  "
            f"up {c.get('uptime_human')}"
            + (f"  ·  {c.get('tags')}" if c.get("tags") else ""),
            mono_f,
            TEXT,
            3,
        )

    add("", body_f, TEXT, 6)
    add("Storage", head_f, ACCENT, 8)
    # compact: unique storage names with worst status across nodes
    if not storage:
        add("  (none)", body_f, MUTED, 6)
    else:
        for s in storage:
            st = str(s.get("status") or "—")
            fill = TEXT if st.lower() == "available" else WARN
            ratio = s.get("ratio")
            ratio_s = f"{ratio * 100:.1f}%" if isinstance(ratio, float) else "—"
            add(
                f"  {s.get('node')}/{s.get('storage')}  ·  {s.get('type')}  ·  {st}  ·  "
                f"{s.get('used_human')}/{s.get('total_human')} ({ratio_s})",
                mono_f,
                fill,
                3,
            )

    add("", body_f, TEXT, 8)
    add("Attention", head_f, ACCENT, 8)
    if not warnings:
        add("  No warnings from live probes.", body_f, OK, 4)
    else:
        for w in warnings:
            for wrapped in _wrap(d0, f"• {w}", body_f, width - 96):
                if wrapped.startswith("•"):
                    line = wrapped
                else:
                    line = f"  {wrapped}"
                add(line, body_f, WARN, 3)

    # measure height
    y = 36
    pad_x = 36
    for text, font, _fill, gap in lines:
        if text == "":
            y += gap
            continue
        # wrap long lines
        max_w = width - pad_x * 2
        for part in _wrap(d0, text, font, max_w):
            box = d0.textbbox((0, 0), part, font=font)
            y += int(box[3] - box[1]) + 2
        y += gap
    height = max(y + 40, 640)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    # outer card
    draw.rounded_rectangle((16, 16, width - 16, height - 16), radius=18, fill=CARD, outline=CARD_BORDER, width=2)
    # status bar
    draw.rounded_rectangle((36, 36, 36 + 14, 36 + 14), radius=7, fill=color)

    y = 36
    first = True
    for text, font, fill, gap in lines:
        if text == "":
            y += gap
            continue
        max_w = width - pad_x * 2
        parts = _wrap(draw, text, font, max_w)
        for i, part in enumerate(parts):
            x = pad_x
            if first and i == 0:
                x = pad_x + 24  # room for traffic dot
            draw.text((x, y), part, font=font, fill=fill)
            box = draw.textbbox((0, 0), part, font=font)
            y += int(box[3] - box[1]) + 2
        y += gap
        first = False

    # footer rule
    draw.line((36, height - 40, width - 36, height - 40), fill=LINE, width=1)
    draw.text((36, height - 32), "Stronghold · live PVE/Ceph probes via ClusterMCP · no recalled metrics", font=small_f, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
