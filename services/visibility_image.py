"""Render a single Stronghold visibility report image from live report data.

Mobile-first high-res card: table layouts, per-row status icons, airy spacing.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Dark ops card palette
BG = (12, 14, 22)
CARD = (22, 26, 38)
CARD_BORDER = (48, 56, 78)
HEADER_BG = (30, 36, 54)
ROW_A = (26, 30, 44)
ROW_B = (22, 26, 38)
TEXT = (232, 238, 248)
MUTED = (148, 163, 184)
OK = (52, 211, 153)
WARN = (251, 191, 36)
BAD = (251, 113, 133)
ACCENT = (56, 189, 248)
LINE = (42, 50, 68)
ICON_RING = (15, 18, 28)


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
    if o in ("ok", "healthy", "up", "online", "running", "available", "health_ok"):
        return "OK", OK
    if o in ("degraded", "warn", "warning", "unknown"):
        return "WARN", WARN
    if o in ("down", "critical", "error", "offline", "stopped", "unavailable"):
        return "DOWN", BAD
    if "health_ok" in o or o == "health_ok":
        return "OK", OK
    return (o.upper() or "UNKNOWN"), MUTED


def _status_color(value: Any) -> tuple[str, tuple[int, int, int]]:
    s = str(value or "").strip().lower()
    if s in ("ok", "online", "running", "available", "up", "health_ok", "active", "active+clean", "true", "yes", "1"):
        return "ok", OK
    if s in ("degraded", "warn", "warning", "unknown", "none", ""):
        return "warn", WARN
    if s in ("down", "offline", "stopped", "error", "critical", "unavailable", "false", "no", "0"):
        return "bad", BAD
    if "health_ok" in s or s.endswith("_ok"):
        return "ok", OK
    if "health_" in s:
        return "warn", WARN
    return "muted", MUTED


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0]), int(box[3] - box[1])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        tw, _ = _text_size(draw, trial, font)
        if tw <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _draw_status_icon(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    kind: str,
    color: tuple[int, int, int],
    size: int = 18,
) -> None:
    """Draw a crisp status glyph at (x,y) top-left of the icon box."""
    r = size // 2
    cx, cy = x + r, y + r
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color, outline=ICON_RING, width=1)
    # inner mark
    if kind == "ok":
        # check
        draw.line([(cx - r // 2, cy), (cx - r // 6, cy + r // 2), (cx + r // 2, cy - r // 2)], fill=ICON_RING, width=max(2, size // 7))
    elif kind == "bad":
        # x
        o = r // 2
        draw.line([(cx - o, cy - o), (cx + o, cy + o)], fill=ICON_RING, width=max(2, size // 7))
        draw.line([(cx + o, cy - o), (cx - o, cy + o)], fill=ICON_RING, width=max(2, size // 7))
    elif kind == "warn":
        # bang
        draw.line([(cx, cy - r // 2), (cx, cy + r // 6)], fill=ICON_RING, width=max(2, size // 6))
        draw.ellipse((cx - 2, cy + r // 3, cx + 2, cy + r // 3 + 4), fill=ICON_RING)
    else:
        # dash
        draw.line([(cx - r // 2, cy), (cx + r // 2, cy)], fill=ICON_RING, width=max(2, size // 6))


def _fit_cell(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    text = str(text if text is not None else "—")
    if max_w <= 8:
        return text
    tw, _ = _text_size(draw, text, font)
    if tw <= max_w:
        return text
    # ellipsize
    ell = "…"
    lo, hi = 0, len(text)
    best = ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        cw, _ = _text_size(draw, cand, font)
        if cw <= max_w:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best


class _Canvas:
    def __init__(self, width: int, scale: int = 2):
        self.scale = max(1, scale)
        self.width = width
        # build at logical size then we already use high font sizes; keep 1:1 high res width
        self.pad = 44
        self.content_w = width - self.pad * 2
        self.y = self.pad
        self.elements: list[tuple] = []
        self.title_f = _font(34, bold=True)
        self.head_f = _font(22, bold=True)
        self.sub_f = _font(16, bold=True)
        self.body_f = _font(17)
        self.mono_f = _font(16)
        self.small_f = _font(14)
        self.scratch = Image.new("RGB", (width, 100), BG)
        self.d0 = ImageDraw.Draw(self.scratch)

    def gap(self, n: int = 16) -> None:
        self.elements.append(("gap", n))
        self.y += n

    def rule(self) -> None:
        self.elements.append(("rule", self.y))
        self.y += 14

    def title_block(self, title: str, meta: str, overall_label: str, overall_color: tuple[int, int, int]) -> None:
        self.elements.append(("title", self.y, title, meta, overall_label, overall_color))
        # estimate height
        self.y += 34 + 10 + 18 + 18 + 28 + 22

    def section_header(self, name: str, status_label: str, status_color: tuple[int, int, int], subtitle: str = "") -> None:
        h = 46 + (22 if subtitle else 0)
        self.elements.append(("section", self.y, name, status_label, status_color, subtitle, h))
        self.y += h + 10

    def kv_chips(self, items: list[tuple[str, str, tuple[int, int, int] | None]]) -> None:
        """items: (label, value, optional status color for value)."""
        self.elements.append(("chips", self.y, items))
        # 2 rows of chips roughly
        rows = max(1, (len(items) + 1) // 2)
        self.y += rows * 44 + 12

    def table(
        self,
        headers: list[str],
        col_weights: list[float],
        rows: list[tuple[str, tuple[int, int, int], list[str]]],
        row_h: int = 44,
    ) -> None:
        """
        rows: list of (status_kind, status_color, cell_values)
        First visual column is status icon (fixed), then headers.
        """
        header_h = 40
        h = header_h + max(1, len(rows)) * row_h + 8
        self.elements.append(("table", self.y, headers, col_weights, rows, row_h, header_h, h))
        self.y += h + 18

    def bullet_block(self, title_color: tuple[int, int, int], lines: list[tuple[str, tuple[int, int, int]]]) -> None:
        # each line may wrap
        total = 8
        wrapped_all: list[tuple[list[str], tuple[int, int, int]]] = []
        max_w = self.content_w - 56
        for text, color in lines:
            parts = _wrap(self.d0, text, self.body_f, max_w)
            wrapped_all.append((parts, color))
            total += len(parts) * 26 + 8
        self.elements.append(("bullets", self.y, wrapped_all, total))
        self.y += total + 8

    def footer(self, text: str) -> None:
        self.elements.append(("footer", text))
        self.y += 48

    def render(self) -> Image.Image:
        height = max(self.y + self.pad, 900)
        img = Image.new("RGB", (self.width, height), BG)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (18, 18, self.width - 18, height - 18),
            radius=22,
            fill=CARD,
            outline=CARD_BORDER,
            width=2,
        )

        for el in self.elements:
            kind = el[0]
            if kind == "gap":
                continue
            if kind == "rule":
                y = el[1]
                draw.line((self.pad, y, self.width - self.pad, y), fill=LINE, width=1)
                continue
            if kind == "title":
                _, y, title, meta, olabel, ocolor = el
                _draw_status_icon(draw, self.pad, y + 6, "ok" if olabel == "OK" else ("bad" if olabel == "DOWN" else "warn"), ocolor, size=28)
                draw.text((self.pad + 40, y), title, font=self.title_f, fill=TEXT)
                draw.text((self.pad + 40, y + 42), meta, font=self.small_f, fill=MUTED)
                # overall pill
                pill = f"OVERALL  {olabel}"
                pw, ph = _text_size(draw, pill, self.sub_f)
                px = self.pad + 40
                py = y + 70
                draw.rounded_rectangle((px, py, px + pw + 28, py + ph + 16), radius=12, fill=ocolor)
                draw.text((px + 14, py + 8), pill, font=self.sub_f, fill=ICON_RING)
                continue
            if kind == "section":
                _, y, name, slabel, scolor, subtitle, h = el
                draw.rounded_rectangle(
                    (self.pad, y, self.width - self.pad, y + h - 4),
                    radius=12,
                    fill=HEADER_BG,
                    outline=LINE,
                    width=1,
                )
                kind_icon, _ = _status_color(slabel)
                # map label to icon kind better
                if slabel.upper() in ("OK", "HEALTHY", "ONLINE"):
                    kind_icon = "ok"
                elif slabel.upper() in ("DOWN", "CRITICAL"):
                    kind_icon = "bad"
                elif slabel.upper() in ("WARN", "DEGRADED", "ATTN"):
                    kind_icon = "warn"
                _draw_status_icon(draw, self.pad + 14, y + 12, kind_icon, scolor, size=22)
                draw.text((self.pad + 46, y + 10), name, font=self.head_f, fill=ACCENT)
                # right side status tag
                tag = slabel.upper()
                tw, th = _text_size(draw, tag, self.sub_f)
                tx = self.width - self.pad - tw - 28
                draw.rounded_rectangle((tx, y + 10, tx + tw + 16, y + 10 + th + 10), radius=8, fill=scolor)
                draw.text((tx + 8, y + 14), tag, font=self.sub_f, fill=ICON_RING)
                if subtitle:
                    draw.text((self.pad + 46, y + 36), subtitle, font=self.small_f, fill=MUTED)
                continue
            if kind == "chips":
                _, y, items = el
                x = self.pad
                row_y = y
                max_x = self.width - self.pad
                for label, value, vcolor in items:
                    text = f"{label}  {value}"
                    tw, th = _text_size(draw, text, self.body_f)
                    chip_w = tw + 28
                    chip_h = th + 18
                    if x + chip_w > max_x:
                        x = self.pad
                        row_y += chip_h + 10
                    fill = (32, 38, 56)
                    draw.rounded_rectangle((x, row_y, x + chip_w, row_y + chip_h), radius=10, fill=fill, outline=LINE, width=1)
                    if vcolor:
                        _draw_status_icon(draw, x + 10, row_y + (chip_h - 16) // 2, _status_color(value)[0], vcolor, size=16)
                        draw.text((x + 32, row_y + 8), text, font=self.body_f, fill=TEXT)
                    else:
                        draw.text((x + 12, row_y + 8), text, font=self.body_f, fill=TEXT)
                    x += chip_w + 10
                continue
            if kind == "table":
                _, y, headers, weights, rows, row_h, header_h, _h = el
                icon_col = 44
                table_w = self.content_w
                inner_w = table_w - icon_col
                weight_sum = sum(weights) or 1.0
                col_ws = [int(inner_w * (w / weight_sum)) for w in weights]
                # fix rounding
                col_ws[-1] += inner_w - sum(col_ws)
                # header
                draw.rounded_rectangle(
                    (self.pad, y, self.width - self.pad, y + header_h),
                    radius=0,
                    fill=HEADER_BG,
                )
                draw.rectangle((self.pad, y, self.width - self.pad, y + header_h), fill=HEADER_BG)
                cx = self.pad + icon_col
                for i, hname in enumerate(headers):
                    draw.text((cx + 8, y + 10), hname, font=self.sub_f, fill=MUTED)
                    cx += col_ws[i]
                # rows
                ry = y + header_h
                if not rows:
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + row_h), fill=ROW_A)
                    draw.text((self.pad + icon_col + 8, ry + 12), "(none from live probes)", font=self.body_f, fill=MUTED)
                    ry += row_h
                for idx, (skind, scolor, cells) in enumerate(rows):
                    bg = ROW_A if idx % 2 == 0 else ROW_B
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + row_h), fill=bg)
                    _draw_status_icon(draw, self.pad + 12, ry + (row_h - 18) // 2, skind, scolor, size=18)
                    cx = self.pad + icon_col
                    for i, cell in enumerate(cells):
                        max_w = col_ws[i] - 16
                        shown = _fit_cell(draw, cell, self.mono_f, max_w)
                        # status-ish columns tint
                        fill = TEXT
                        low = str(cell).lower()
                        if low in ("online", "running", "available", "up", "health_ok", "ok"):
                            fill = OK
                        elif low in ("unknown", "degraded", "warn"):
                            fill = WARN
                        elif low in ("offline", "down", "stopped", "error", "unavailable"):
                            fill = BAD
                        draw.text((cx + 8, ry + (row_h - 18) // 2), shown, font=self.mono_f, fill=fill)
                        cx += col_ws[i]
                    # row separator
                    draw.line((self.pad, ry + row_h - 1, self.width - self.pad, ry + row_h - 1), fill=LINE, width=1)
                    ry += row_h
                # table border
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=1)
                continue
            if kind == "bullets":
                _, y, wrapped_all, _total = el
                yy = y
                for parts, color in wrapped_all:
                    for i, part in enumerate(parts):
                        prefix = "• " if i == 0 else "  "
                        if i == 0:
                            _draw_status_icon(
                                draw,
                                self.pad + 4,
                                yy + 2,
                                "warn" if color == WARN else ("bad" if color == BAD else "ok"),
                                color,
                                size=16,
                            )
                            draw.text((self.pad + 28, yy), f"{prefix}{part.lstrip('• ').lstrip()}", font=self.body_f, fill=color)
                        else:
                            draw.text((self.pad + 28, yy), f"  {part}", font=self.body_f, fill=color)
                        yy += 26
                    yy += 8
                continue
            if kind == "footer":
                text = el[1]
                draw.line((self.pad, height - 52, self.width - self.pad, height - 52), fill=LINE, width=1)
                draw.text((self.pad, height - 38), text, font=self.small_f, fill=MUTED)
        return img


def _section_status_from_rows(statuses: list[Any]) -> tuple[str, tuple[int, int, int]]:
    kinds = [_status_color(s) for s in statuses]
    if any(k == "bad" for k, _ in kinds):
        return "DOWN", BAD
    if any(k == "warn" for k, _ in kinds) or not statuses:
        return "WARN", WARN
    if statuses and all(k == "ok" for k, _ in kinds):
        return "OK", OK
    return "—", MUTED


def render_visibility_image(report: dict[str, Any], width: int = 1800) -> bytes:
    """Return high-res PNG bytes for a mobile-zoomable status card with tables."""
    # Mobile-friendly: tall card, wide logical canvas so pinch-zoom keeps sharp text.
    width = max(1600, int(width))
    c = _Canvas(width=width)

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

    c.title_block(
        title="ClusterMCP  ·  Visibility Report",
        meta=f"Generated {report.get('generated_at', '—')}   ·   data_policy={report.get('data_policy', 'live_probes_only')}   ·   high-res mobile card",
        overall_label=label,
        overall_color=color,
    )
    c.gap(8)

    # Cluster summary chips with icons
    cname = cluster.get("name") or "—"
    quorate = cluster.get("quorate")
    qtxt = "yes" if quorate is True else ("no" if quorate is False else "—")
    qcolor = OK if quorate is True else (BAD if quorate is False else WARN)
    node_s = f"{summary.get('nodes_online', '—')}/{summary.get('total_nodes', '—')}"
    chips: list[tuple[str, str, tuple[int, int, int] | None]] = [
        ("Cluster", str(cname), OK if cname != "—" else WARN),
        ("Quorate", qtxt, qcolor),
        ("Nodes", node_s, OK if str(summary.get("nodes_online")) == str(summary.get("total_nodes")) else WARN),
        ("VMs", str(summary.get("total_vms", "—")), None),
        ("CTs", str(summary.get("total_containers", "—")), OK if summary.get("total_containers") else WARN),
        ("Ceph", str(summary.get("ceph_health", ceph.get("health_status", "—"))), _status_color(summary.get("ceph_health", ceph.get("health_status")))[1]),
    ]
    if mcp:
        dirty = "dirty" if mcp.get("dirty") else "clean"
        chips.append(("MCP", f"{mcp.get('version', '—')}@{mcp.get('commit', '—')}", OK if dirty == "clean" else WARN))
        chips.append(("PVE", str(mcp.get("pve_host", "—")), None))
        chips.append(("Git", f"{mcp.get('branch', '—')} · {dirty}", OK if dirty == "clean" else WARN))
    c.section_header("Cluster summary", label, color, subtitle="Live probe snapshot — icons mark each fact")
    c.kv_chips(chips)
    c.gap(6)

    # Nodes table
    node_statuses = [n.get("status") for n in nodes]
    ns_label, ns_color = _section_status_from_rows(node_statuses)
    c.section_header("Nodes", ns_label, ns_color, subtitle=f"{len(nodes)} hosts from live inventory")
    node_rows: list[tuple[str, tuple[int, int, int], list[str]]] = []
    for n in nodes:
        sk, sc = _status_color(n.get("status"))
        node_rows.append(
            (
                sk,
                sc,
                [
                    str(n.get("node") or "—"),
                    str(n.get("status") or "—"),
                    str(n.get("ip") or "—"),
                    str(n.get("cpu_human") or "—"),
                    str(n.get("mem_human") or "—"),
                    str(n.get("containers_count", "—")),
                    str(n.get("vms_count", "—")),
                    str(n.get("uptime_human") or "—"),
                ],
            )
        )
    c.table(
        headers=["Node", "Status", "IP", "CPU", "Memory", "CTs", "VMs", "Uptime"],
        col_weights=[1.4, 0.9, 1.3, 0.8, 1.5, 0.6, 0.6, 1.0],
        rows=node_rows,
        row_h=48,
    )

    # Ceph section
    health = ceph.get("health_status") or (ceph.get("health") or {}).get("status") or "—"
    hk, hc = _status_color(health)
    # section badge
    if osd_summary.get("detail_available") is False and warnings:
        sec_l, sec_c = "WARN", WARN
    else:
        sec_l, sec_c = ("OK", OK) if hk == "ok" else (("DOWN", BAD) if hk == "bad" else ("WARN", WARN))
    pg = ceph.get("pg_states") or {}
    pg_str = ", ".join(f"{k}={v}" for k, v in sorted(pg.items(), key=lambda kv: -kv[1])[:6]) or "—"
    c.section_header(
        "Ceph",
        sec_l,
        sec_c,
        subtitle=f"PGs: {pg_str}   ·   OSD source: {osd_summary.get('source') or '—'}",
    )
    ceph_chips = [
        ("Health", str(health), hc),
        ("MONs", str(ceph.get("mon_count") if ceph.get("mon_count") is not None else "—"), OK if ceph.get("mon_count") else WARN),
        ("OSD total", str(osd_summary.get("total") if osd_summary.get("total") is not None else "—"), None),
        ("OSD up", str(osd_summary.get("up") if osd_summary.get("up") is not None else "—"), OK if osd_summary.get("up") else WARN),
        ("OSD in", str(osd_summary.get("in") if osd_summary.get("in") is not None else "—"), OK if osd_summary.get("in") else WARN),
        (
            "Detail",
            "yes" if osd_summary.get("detail_available") else "no",
            OK if osd_summary.get("detail_available") else WARN,
        ),
    ]
    c.kv_chips(ceph_chips)

    if osds:
        osd_rows = []
        for o in osds:
            sk, sc = _status_color(o.get("status"))
            usage = o.get("usage")
            usage_s = f"{usage:.1f}%" if isinstance(usage, int | float) else "—"
            in_s = "yes" if o.get("in") is True else ("no" if o.get("in") is False else "—")
            osd_rows.append(
                (
                    sk,
                    sc,
                    [
                        str(o.get("name") or "—"),
                        str(o.get("status") or "—"),
                        in_s,
                        usage_s,
                        str(o.get("node") or "—"),
                    ],
                )
            )
        c.table(
            headers=["OSD", "Status", "In", "Usage", "Host"],
            col_weights=[1.0, 1.0, 0.7, 0.9, 1.2],
            rows=osd_rows,
            row_h=46,
        )
    else:
        c.table(
            headers=["OSD detail"],
            col_weights=[1.0],
            rows=[
                (
                    "warn",
                    WARN,
                    ["Per-OSD utilization not available from live tree probe (not fabricated)"],
                )
            ],
            row_h=48,
        )

    # Containers
    ct_statuses = [ct.get("status") for ct in containers]
    ct_l, ct_c = _section_status_from_rows(ct_statuses)
    c.section_header("Containers", ct_l, ct_c, subtitle=f"{len(containers)} LXC from cluster/resources")
    ct_rows = []
    for ct in containers:
        sk, sc = _status_color(ct.get("status"))
        ct_rows.append(
            (
                sk,
                sc,
                [
                    str(ct.get("vmid") or "—"),
                    str(ct.get("name") or "—"),
                    str(ct.get("node") or "—"),
                    str(ct.get("status") or "—"),
                    str(ct.get("cpu_human") or "—"),
                    str(ct.get("mem_human") or "—"),
                    str(ct.get("disk_human") or "—"),
                    str(ct.get("uptime_human") or "—"),
                    str(ct.get("tags") or "—"),
                ],
            )
        )
    c.table(
        headers=["VMID", "Name", "Node", "Status", "CPU", "Memory", "Disk", "Uptime", "Tags"],
        col_weights=[0.7, 1.3, 1.2, 0.9, 0.7, 1.4, 1.4, 0.9, 1.3],
        rows=ct_rows,
        row_h=48,
    )

    # Storage
    st_statuses = [s.get("status") for s in storage]
    st_l, st_c = _section_status_from_rows(st_statuses if st_statuses else ["unknown"])
    c.section_header("Storage", st_l, st_c, subtitle=f"{len(storage)} storage objects · fill% only when probe provides used bytes")
    st_rows = []
    for s in storage:
        sk, sc = _status_color(s.get("status"))
        ratio = s.get("ratio")
        ratio_s = f"{ratio * 100:.1f}%" if isinstance(ratio, float) else "—"
        st_rows.append(
            (
                sk,
                sc,
                [
                    str(s.get("node") or "—"),
                    str(s.get("storage") or "—"),
                    str(s.get("type") or "—"),
                    str(s.get("status") or "—"),
                    str(s.get("used_human") or "—"),
                    str(s.get("total_human") or "—"),
                    ratio_s,
                ],
            )
        )
    c.table(
        headers=["Node", "Storage", "Type", "Status", "Used", "Total", "Fill"],
        col_weights=[1.2, 1.4, 1.0, 1.0, 1.0, 1.2, 0.7],
        rows=st_rows,
        row_h=46,
    )

    # Attention
    if warnings:
        c.section_header("Attention", "ATTN", WARN, subtitle=f"{len(warnings)} item(s) from live probes")
        c.bullet_block(WARN, [(str(w), WARN) for w in warnings])
    else:
        c.section_header("Attention", "OK", OK, subtitle="No warnings from live probes")
        c.bullet_block(OK, [("No warnings from live probes.", OK)])

    c.footer("Stronghold · live PVE/Ceph probes via ClusterMCP · no recalled metrics · pinch-zoom safe")

    img = c.render()
    buf = io.BytesIO()
    # high quality PNG; optimize keeps size reasonable without killing sharp text
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
