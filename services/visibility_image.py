"""Render a single Stronghold visibility report image from live report data.

Discord-mobile first: large type, airy layout, per-row status icons.
Body type is sized so fit-to-width on a ~390px Discord column stays readable;
pinch-zoom still has sharp native pixels (no post-scale blur).
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
TEXT = (236, 240, 250)
MUTED = (160, 174, 196)
OK = (52, 211, 153)
WARN = (251, 191, 36)
BAD = (251, 113, 133)
ACCENT = (56, 189, 248)
LINE = (48, 58, 78)
ICON_RING = (12, 14, 22)

# Discord chat ~390px. Target ≥14px on-screen body at fit-width
# ⇒ body_font >= 14 * WIDTH / 390. WIDTH=1600 ⇒ ~57px body.
DEFAULT_WIDTH = 1600


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


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: Any) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0]), int(box[3] - box[1])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
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
    size: int = 28,
) -> None:
    r = size // 2
    cx, cy = x + r, y + r
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color, outline=ICON_RING, width=max(2, size // 12))
    w = max(3, size // 6)
    if kind == "ok":
        draw.line(
            [(cx - r // 2, cy), (cx - r // 7, cy + r // 2), (cx + r // 2 + 1, cy - r // 2)],
            fill=ICON_RING,
            width=w,
        )
    elif kind == "bad":
        o = max(4, r // 2)
        draw.line([(cx - o, cy - o), (cx + o, cy + o)], fill=ICON_RING, width=w)
        draw.line([(cx + o, cy - o), (cx - o, cy + o)], fill=ICON_RING, width=w)
    elif kind == "warn":
        draw.line([(cx, cy - r // 2), (cx, cy + r // 5)], fill=ICON_RING, width=w)
        br = max(3, size // 10)
        draw.ellipse((cx - br, cy + r // 3, cx + br, cy + r // 3 + br * 2), fill=ICON_RING)
    else:
        draw.line([(cx - r // 2, cy), (cx + r // 2, cy)], fill=ICON_RING, width=w)


def _fit_cell(draw: ImageDraw.ImageDraw, text: str, font: Any, max_w: int) -> str:
    text = str(text if text is not None else "—")
    if max_w <= 12:
        return text
    tw, _ = _text_size(draw, text, font)
    if tw <= max_w:
        return text
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


def _cell_fill(cell: str) -> tuple[int, int, int]:
    low = str(cell).lower()
    if low in ("online", "running", "available", "up", "health_ok", "ok", "yes", "clean"):
        return OK
    if low in ("unknown", "degraded", "warn", "dirty", "no"):
        return WARN
    if low in ("offline", "down", "stopped", "error", "unavailable"):
        return BAD
    return TEXT


class _Canvas:
    def __init__(self, width: int = DEFAULT_WIDTH):
        self.width = width
        self.pad = 64
        self.content_w = width - self.pad * 2
        self.y = self.pad
        self.elements: list[tuple] = []
        # Sized for ≥14 CSS-px body after Discord fit-width on ~390px chat:
        # body_px >= 14 * width / 390  (at 1600 ⇒ ~57)
        self.title_f = _font(78, bold=True)
        self.head_f = _font(56, bold=True)
        self.sub_f = _font(40, bold=True)
        self.body_f = _font(58)
        self.mono_f = _font(52)
        self.small_f = _font(42)
        self.chip_f = _font(46)
        self.icon = 40
        self.row_h = 120
        self.header_h = 96
        self.section_h = 120
        self.scratch = Image.new("RGB", (width, 160), BG)
        self.d0 = ImageDraw.Draw(self.scratch)

    def gap(self, n: int = 36) -> None:
        self.elements.append(("gap", n))
        self.y += n

    def title_block(self, title: str, meta: str, overall_label: str, overall_color: tuple[int, int, int]) -> None:
        self.elements.append(("title", self.y, title, meta, overall_label, overall_color))
        self.y += 78 + 20 + 48 + 28 + 72 + 44

    def section_header(self, name: str, status_label: str, status_color: tuple[int, int, int], subtitle: str = "") -> None:
        h = self.section_h + (48 if subtitle else 0)
        self.elements.append(("section", self.y, name, status_label, status_color, subtitle, h))
        self.y += h + 24

    def kv_chips(self, items: list[tuple[str, str, tuple[int, int, int] | None]]) -> None:
        x = 0
        rows = 1
        row_h = 0
        max_w = self.content_w
        for label, value, vcolor in items:
            text = f"{label}  {value}"
            tw, th = _text_size(self.d0, text, self.chip_f)
            chip_w = tw + (56 if vcolor else 40)
            chip_h = th + 32
            row_h = max(row_h, chip_h)
            if x + chip_w > max_w and x > 0:
                rows += 1
                x = 0
            x += chip_w + 16
        total_h = rows * (row_h + 16) + 8
        self.elements.append(("chips", self.y, items, total_h))
        self.y += total_h + 20

    def table(
        self,
        headers: list[str],
        col_weights: list[float],
        rows: list[tuple[str, tuple[int, int, int], list[str]]],
        row_h: int | None = None,
    ) -> None:
        rh = row_h or self.row_h
        hh = self.header_h
        h = hh + max(1, len(rows)) * rh + 10
        self.elements.append(("table", self.y, headers, col_weights, rows, rh, hh, h))
        self.y += h + 28

    def multiline_rows(
        self,
        rows: list[tuple[str, tuple[int, int, int], str, str]],
        row_h: int = 150,
    ) -> None:
        h = max(1, len(rows)) * row_h + 8
        self.elements.append(("mrows", self.y, rows, row_h, h))
        self.y += h + 36

    def bullet_block(self, lines: list[tuple[str, tuple[int, int, int]]]) -> None:
        total = 16
        wrapped_all: list[tuple[list[str], tuple[int, int, int]]] = []
        max_w = self.content_w - 90
        for text, color in lines:
            parts = _wrap(self.d0, text, self.body_f, max_w)
            wrapped_all.append((parts, color))
            total += len(parts) * 60 + 20
        self.elements.append(("bullets", self.y, wrapped_all, total))
        self.y += total + 20

    def footer(self, text: str) -> None:
        self.elements.append(("footer", text))
        self.y += 96

    def render(self) -> Image.Image:
        height = max(self.y + self.pad, 1200)
        img = Image.new("RGB", (self.width, height), BG)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (24, 24, self.width - 24, height - 24),
            radius=28,
            fill=CARD,
            outline=CARD_BORDER,
            width=3,
        )

        for el in self.elements:
            kind = el[0]
            if kind == "gap":
                continue
            if kind == "title":
                _, y, title, meta, olabel, ocolor = el
                _draw_status_icon(
                    draw,
                    self.pad,
                    y + 14,
                    "ok" if olabel == "OK" else ("bad" if olabel == "DOWN" else "warn"),
                    ocolor,
                    size=52,
                )
                draw.text((self.pad + 72, y), title, font=self.title_f, fill=TEXT)
                draw.text((self.pad + 72, y + 96), meta, font=self.small_f, fill=MUTED)
                pill = f"OVERALL  {olabel}"
                pw, ph = _text_size(draw, pill, self.sub_f)
                px = self.pad + 72
                py = y + 156
                draw.rounded_rectangle((px, py, px + pw + 48, py + ph + 28), radius=18, fill=ocolor)
                draw.text((px + 24, py + 12), pill, font=self.sub_f, fill=ICON_RING)
                continue
            if kind == "section":
                _, y, name, slabel, scolor, subtitle, h = el
                draw.rounded_rectangle(
                    (self.pad, y, self.width - self.pad, y + h - 8),
                    radius=18,
                    fill=HEADER_BG,
                    outline=LINE,
                    width=2,
                )
                if slabel.upper() in ("OK", "HEALTHY", "ONLINE"):
                    kind_icon = "ok"
                elif slabel.upper() in ("DOWN", "CRITICAL"):
                    kind_icon = "bad"
                else:
                    kind_icon = "warn"
                _draw_status_icon(draw, self.pad + 24, y + 28, kind_icon, scolor, size=44)
                draw.text((self.pad + 84, y + 24), name, font=self.head_f, fill=ACCENT)
                tag = slabel.upper()
                tw, th = _text_size(draw, tag, self.sub_f)
                tx = self.width - self.pad - tw - 48
                draw.rounded_rectangle((tx, y + 24, tx + tw + 28, y + 24 + th + 20), radius=14, fill=scolor)
                draw.text((tx + 14, y + 32), tag, font=self.sub_f, fill=ICON_RING)
                if subtitle:
                    draw.text((self.pad + 84, y + 92), subtitle, font=self.small_f, fill=MUTED)
                continue
            if kind == "chips":
                _, y, items, _total_h = el
                x = self.pad
                row_y = y
                max_x = self.width - self.pad
                row_h = 0
                for label, value, vcolor in items:
                    text = f"{label}  {value}"
                    tw, th = _text_size(draw, text, self.chip_f)
                    chip_w = tw + (56 if vcolor else 40)
                    chip_h = th + 32
                    if x + chip_w > max_x and x > self.pad:
                        x = self.pad
                        row_y += max(row_h, chip_h) + 16
                        row_h = 0
                    row_h = max(row_h, chip_h)
                    draw.rounded_rectangle(
                        (x, row_y, x + chip_w, row_y + chip_h),
                        radius=16,
                        fill=(32, 38, 56),
                        outline=LINE,
                        width=2,
                    )
                    if vcolor:
                        _draw_status_icon(
                            draw,
                            x + 16,
                            row_y + (chip_h - self.icon) // 2,
                            _status_color(value)[0],
                            vcolor,
                            size=self.icon,
                        )
                        draw.text((x + 64, row_y + 14), text, font=self.chip_f, fill=TEXT)
                    else:
                        draw.text((x + 18, row_y + 14), text, font=self.chip_f, fill=TEXT)
                    x += chip_w + 16
                continue
            if kind == "table":
                _, y, headers, weights, rows, rh, hh, _h = el
                icon_col = 80
                inner_w = self.content_w - icon_col
                weight_sum = sum(weights) or 1.0
                col_ws = [int(inner_w * (w / weight_sum)) for w in weights]
                col_ws[-1] += inner_w - sum(col_ws)
                draw.rectangle((self.pad, y, self.width - self.pad, y + hh), fill=HEADER_BG)
                cx = self.pad + icon_col
                for i, hname in enumerate(headers):
                    draw.text((cx + 12, y + (hh - 44) // 2), hname, font=self.sub_f, fill=MUTED)
                    cx += col_ws[i]
                ry = y + hh
                if not rows:
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + rh), fill=ROW_A)
                    draw.text(
                        (self.pad + icon_col + 12, ry + (rh - 50) // 2),
                        "(none from live probes)",
                        font=self.body_f,
                        fill=MUTED,
                    )
                    ry += rh
                for idx, (skind, scolor, cells) in enumerate(rows):
                    bg = ROW_A if idx % 2 == 0 else ROW_B
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + rh), fill=bg)
                    _draw_status_icon(
                        draw,
                        self.pad + 20,
                        ry + (rh - self.icon) // 2,
                        skind,
                        scolor,
                        size=self.icon,
                    )
                    cx = self.pad + icon_col
                    for i, cell in enumerate(cells):
                        max_w = col_ws[i] - 24
                        shown = _fit_cell(draw, cell, self.mono_f, max_w)
                        draw.text(
                            (cx + 12, ry + (rh - 48) // 2),
                            shown,
                            font=self.mono_f,
                            fill=_cell_fill(str(cell)),
                        )
                        cx += col_ws[i]
                    draw.line((self.pad, ry + rh - 1, self.width - self.pad, ry + rh - 1), fill=LINE, width=2)
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=2)
                continue
            if kind == "mrows":
                _, y, rows, rh, _h = el
                ry = y
                for idx, (skind, scolor, primary, secondary) in enumerate(rows):
                    bg = ROW_A if idx % 2 == 0 else ROW_B
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + rh), fill=bg)
                    _draw_status_icon(
                        draw,
                        self.pad + 20,
                        ry + (rh - self.icon) // 2,
                        skind,
                        scolor,
                        size=self.icon,
                    )
                    max_w = self.content_w - 110
                    p = _fit_cell(draw, primary, self.mono_f, max_w)
                    s = _fit_cell(draw, secondary, self.small_f, max_w)
                    draw.text((self.pad + 80, ry + 22), p, font=self.mono_f, fill=TEXT)
                    draw.text((self.pad + 80, ry + 22 + 58), s, font=self.small_f, fill=MUTED)
                    draw.line((self.pad, ry + rh - 1, self.width - self.pad, ry + rh - 1), fill=LINE, width=2)
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=2)
                continue
            if kind == "bullets":
                _, y, wrapped_all, _total = el
                yy = y
                for parts, color in wrapped_all:
                    for i, part in enumerate(parts):
                        if i == 0:
                            _draw_status_icon(
                                draw,
                                self.pad + 8,
                                yy + 6,
                                "warn" if color == WARN else ("bad" if color == BAD else "ok"),
                                color,
                                size=34,
                            )
                            body = part.lstrip("• ").lstrip()
                            draw.text((self.pad + 56, yy), f"• {body}", font=self.body_f, fill=color)
                        else:
                            draw.text((self.pad + 56, yy), f"  {part}", font=self.body_f, fill=color)
                        yy += 60
                    yy += 20
                continue
            if kind == "footer":
                text = el[1]
                draw.line((self.pad, height - 84, self.width - self.pad, height - 84), fill=LINE, width=2)
                draw.text((self.pad, height - 64), text, font=self.small_f, fill=MUTED)
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


def render_visibility_image(report: dict[str, Any], width: int = DEFAULT_WIDTH) -> bytes:
    """Return Discord-mobile-readable PNG (large type, airy tables)."""
    width = max(1400, int(width))
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
        title="ClusterMCP  ·  Visibility",
        meta=f"{report.get('generated_at', '—')}  ·  live_probes_only  ·  mobile large-type",
        overall_label=label,
        overall_color=color,
    )
    c.gap(20)

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
        (
            "Ceph",
            str(summary.get("ceph_health", ceph.get("health_status", "—"))),
            _status_color(summary.get("ceph_health", ceph.get("health_status")))[1],
        ),
    ]
    if mcp:
        dirty = "dirty" if mcp.get("dirty") else "clean"
        chips.append(("MCP", f"{mcp.get('version', '—')}@{mcp.get('commit', '—')}", OK if dirty == "clean" else WARN))
        chips.append(("Git", f"{mcp.get('branch', '—')} · {dirty}", OK if dirty == "clean" else WARN))
    c.section_header("Summary", label, color, subtitle="Live probe chips")
    c.kv_chips(chips)
    c.gap(12)

    node_statuses = [n.get("status") for n in nodes]
    ns_label, ns_color = _section_status_from_rows(node_statuses)
    c.section_header("Nodes", ns_label, ns_color, subtitle=f"{len(nodes)} hosts")
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
                    str(n.get("cpu_human") or "—"),
                    str(n.get("mem_human") or "—"),
                    f"CT {n.get('containers_count', '—')}",
                    str(n.get("uptime_human") or "—"),
                ],
            )
        )
    c.table(
        headers=["Node", "Status", "CPU", "Memory", "CTs", "Uptime"],
        col_weights=[1.5, 1.0, 0.9, 1.6, 0.8, 1.1],
        rows=node_rows,
    )

    health = ceph.get("health_status") or (ceph.get("health") or {}).get("status") or "—"
    hk, hc = _status_color(health)
    if osd_summary.get("detail_available") is False:
        sec_l, sec_c = "WARN", WARN
    else:
        sec_l, sec_c = ("OK", OK) if hk == "ok" else (("DOWN", BAD) if hk == "bad" else ("WARN", WARN))
    pg = ceph.get("pg_states") or {}
    pg_str = ", ".join(f"{k}={v}" for k, v in sorted(pg.items(), key=lambda kv: -kv[1])[:4]) or "—"
    c.section_header("Ceph", sec_l, sec_c, subtitle=f"PGs {pg_str}")
    c.kv_chips(
        [
            ("Health", str(health), hc),
            ("MONs", str(ceph.get("mon_count") if ceph.get("mon_count") is not None else "—"), OK if ceph.get("mon_count") else WARN),
            ("OSD up", str(osd_summary.get("up") if osd_summary.get("up") is not None else "—"), OK if osd_summary.get("up") else WARN),
            ("OSD in", str(osd_summary.get("in") if osd_summary.get("in") is not None else "—"), OK if osd_summary.get("in") else WARN),
            ("Total", str(osd_summary.get("total") if osd_summary.get("total") is not None else "—"), None),
            ("Detail", "yes" if osd_summary.get("detail_available") else "no", OK if osd_summary.get("detail_available") else WARN),
        ]
    )
    if osds:
        osd_rows = []
        for o in osds:
            sk, sc = _status_color(o.get("status"))
            usage = o.get("usage")
            usage_s = f"{usage:.1f}%" if isinstance(usage, int | float) else "—"
            in_s = "yes" if o.get("in") is True else ("no" if o.get("in") is False else "—")
            osd_rows.append(
                (sk, sc, [str(o.get("name") or "—"), str(o.get("status") or "—"), in_s, usage_s, str(o.get("node") or "—")])
            )
        c.table(
            headers=["OSD", "Status", "In", "Usage", "Host"],
            col_weights=[1.0, 1.0, 0.7, 0.9, 1.2],
            rows=osd_rows,
        )
    else:
        c.multiline_rows(
            [
                (
                    "warn",
                    WARN,
                    "OSD tree detail unavailable",
                    f"source={osd_summary.get('source') or '—'} · not fabricated",
                )
            ],
            row_h=140,
        )

    ct_statuses = [ct.get("status") for ct in containers]
    ct_l, ct_c = _section_status_from_rows(ct_statuses)
    c.section_header("Containers", ct_l, ct_c, subtitle=f"{len(containers)} LXC")
    ct_mrows: list[tuple[str, tuple[int, int, int], str, str]] = []
    for ct in containers:
        sk, sc = _status_color(ct.get("status"))
        tags = f" · {ct.get('tags')}" if ct.get("tags") else ""
        primary = f"{ct.get('vmid')}  {ct.get('name')}  ·  {ct.get('node')}  ·  {ct.get('status')}"
        secondary = (
            f"CPU {ct.get('cpu_human') or '—'}   RAM {ct.get('mem_human') or '—'}   "
            f"disk {ct.get('disk_human') or '—'}   up {ct.get('uptime_human') or '—'}{tags}"
        )
        ct_mrows.append((sk, sc, primary, secondary))
    c.multiline_rows(ct_mrows, row_h=150)

    st_statuses = [s.get("status") for s in storage]
    st_l, st_c = _section_status_from_rows(st_statuses if st_statuses else ["unknown"])
    c.section_header("Storage", st_l, st_c, subtitle=f"{len(storage)} objects")
    st_mrows: list[tuple[str, tuple[int, int, int], str, str]] = []
    for s in storage:
        sk, sc = _status_color(s.get("status"))
        ratio = s.get("ratio")
        ratio_s = f"{ratio * 100:.1f}%" if isinstance(ratio, float) else "—"
        primary = f"{s.get('node')}/{s.get('storage')}  ·  {s.get('status')}"
        secondary = (
            f"{s.get('type') or '—'}   used {s.get('used_human') or '—'} / {s.get('total_human') or '—'}   fill {ratio_s}"
        )
        st_mrows.append((sk, sc, primary, secondary))
    c.multiline_rows(st_mrows, row_h=140)

    if warnings:
        c.section_header("Attention", "ATTN", WARN, subtitle=f"{len(warnings)} item(s)")
        c.bullet_block([(str(w), WARN) for w in warnings])
    else:
        c.section_header("Attention", "OK", OK, subtitle="No warnings")
        c.bullet_block([("No warnings from live probes.", OK)])

    c.footer("Stronghold · live probes only · large-type Discord mobile card")

    img = c.render()
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()
