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

# Export geometry
# Discord downscales by longest edge. A 3200×23000 strip becomes ~500px wide.
# Keep width large and height bounded (2-col lists + compact rows).
BASE_WIDTH = 1600
DEFAULT_WIDTH = 4096
PHONE_COL_CSS = 390
# Fit-width target on ~390px Discord column. Do not cap body so low that text
# is unreadable after Discord shows the attachment full-bleed.
TARGET_BODY_CSS_PX = 16


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
    """Wide export + independent type density for Discord fit-width readability."""

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        target_body_css: float = TARGET_BODY_CSS_PX,
        phone_col_css: float = PHONE_COL_CSS,
    ):
        self.width = int(width)
        # body_px chosen for TARGET_BODY_CSS_PX at phone fit-width:
        # body_css ≈ body_px * PHONE_COL / width
        raw_body = int(round(float(target_body_css) * self.width / float(phone_col_css)))
        # Soft ceiling: large enough to read, not so large single-card height
        # blows Discord long-edge (which shrinks the whole attachment).
        self.body_px = max(56, min(raw_body, 140))
        self.scale = self.body_px / 58.0
        self.pad = max(32, int(self.body_px * 0.25))
        self.content_w = self.width - self.pad * 2
        self.y = self.pad
        self.elements: list[tuple] = []
        self.title_f = _font(max(self.body_px + 14, 72), bold=True)
        self.head_f = _font(max(self.body_px - 4, 56), bold=True)
        self.sub_f = _font(max(int(self.body_px * 0.65), 36), bold=True)
        self.body_f = _font(self.body_px)
        self.mono_f = _font(max(int(self.body_px * 0.88), 48))
        self.small_f = _font(max(int(self.body_px * 0.68), 36))
        self.chip_f = _font(max(int(self.body_px * 0.75), 40))
        self.attn_f = _font(max(int(self.body_px * 0.5), 30))
        self.icon = max(28, int(self.body_px * 0.45))
        self.row_h = max(72, int(self.body_px * 1.55))
        self.header_h = max(58, int(self.body_px * 1.25))
        self.section_h = max(72, int(self.body_px * 1.5))
        self.scratch = Image.new("RGB", (self.width, max(120, self.body_px * 2)), BG)
        self.d0 = ImageDraw.Draw(self.scratch)

    def u(self, n: float | int) -> int:
        """Scale a base design unit by type density (not merely canvas width)."""
        return max(1, int(round(float(n) * self.scale)))

    def gap(self, n: int = 56) -> None:
        g = max(self.u(n), int(self.body_px * 0.35))
        self.elements.append(("gap", g))
        self.y += g

    def title_block(self, title: str, meta: str, overall_label: str, overall_color: tuple[int, int, int]) -> None:
        self.elements.append(("title", self.y, title, meta, overall_label, overall_color))
        self.y += int(self.body_px * 4.4) + 28

    def section_header(self, name: str, status_label: str, status_color: tuple[int, int, int], subtitle: str = "") -> None:
        h = self.section_h + (int(self.body_px * 0.7) if subtitle else 0)
        self.elements.append(("section", self.y, name, status_label, status_color, subtitle, h))
        self.y += h + int(self.body_px * 0.45)

    def kv_chips(self, items: list[tuple[str, str, tuple[int, int, int] | None]]) -> None:
        x = 0
        rows = 1
        row_h = 0
        max_w = self.content_w
        for label, value, vcolor in items:
            text = f"{label}  {value}"
            tw, th = _text_size(self.d0, text, self.chip_f)
            chip_w = tw + (int(self.body_px * 0.7) if vcolor else int(self.body_px * 0.45))
            chip_h = th + int(self.body_px * 0.45)
            row_h = max(row_h, chip_h)
            if x + chip_w > max_w and x > 0:
                rows += 1
                x = 0
            x += chip_w + int(self.body_px * 0.22)
        total_h = rows * (row_h + int(self.body_px * 0.25)) + 6
        self.elements.append(("chips", self.y, items, total_h))
        self.y += total_h + int(self.body_px * 0.4)

    def table(
        self,
        headers: list[str],
        col_weights: list[float],
        rows: list[tuple[str, tuple[int, int, int], list[str]]],
        row_h: int | None = None,
    ) -> None:
        rh = self.row_h if row_h is None else max(self.row_h, int(self.body_px * 1.45))
        hh = self.header_h
        h = hh + max(1, len(rows)) * rh + 12
        self.elements.append(("table", self.y, headers, col_weights, rows, rh, hh, h))
        self.y += h + int(self.body_px * 0.4)

    def multiline_rows(
        self,
        rows: list[tuple[str, tuple[int, int, int], str, str]],
        row_h: int = 100,
        single_line: bool = False,
    ) -> None:
        mult = 1.45 if single_line else 1.85
        rh = max(int(self.body_px * mult), int(self.row_h * (1.05 if single_line else 1.15)))
        h = max(1, len(rows)) * rh + 12
        self.elements.append(("mrows", self.y, rows, rh, h, single_line))
        self.y += h + int(self.body_px * 0.4)

    def multiline_rows_2col(
        self,
        rows: list[tuple[str, tuple[int, int, int], str, str]],
        row_h: int = 100,
        cols: int = 2,
        single_line: bool = True,
    ) -> None:
        cols = max(2, min(3, int(cols)))
        mult = 1.45 if single_line else 1.85
        rh = max(int(self.body_px * mult), int(self.row_h * (1.05 if single_line else 1.15)))
        if not rows:
            self.multiline_rows(rows, row_h=row_h, single_line=single_line)
            return
        chunk = (len(rows) + cols - 1) // cols
        columns: list[list] = []
        for i in range(cols):
            part = rows[i * chunk : (i + 1) * chunk]
            columns.append(part)
        max_len = max(len(c) for c in columns)
        for c in columns:
            while len(c) < max_len:
                c.append(("muted", MUTED, "", ""))
        h = max_len * rh + 12
        self.elements.append(("mrowsN", self.y, columns, rh, h, cols, single_line))
        self.y += h + int(self.body_px * 0.4)

    def attention_block(self, lines: list[tuple[str, tuple[int, int, int]]]) -> None:
        """Smaller Attention type; one next-step line each."""
        font = self.attn_f
        line_h = max(int(self.body_px * 0.95), 40)
        total = int(self.body_px * 0.3)
        wrapped_all: list[tuple[list[str], tuple[int, int, int]]] = []
        max_w = self.content_w - int(self.body_px * 1.2)
        for text, color in lines:
            parts = _wrap(self.d0, text, font, max_w)
            wrapped_all.append((parts, color))
            total += len(parts) * line_h + int(self.body_px * 0.35)
        self.elements.append(("attn", self.y, wrapped_all, total, line_h))
        self.y += total + int(self.body_px * 0.4)

    def bullet_block(self, lines: list[tuple[str, tuple[int, int, int]]]) -> None:
        # legacy path — prefer attention_block for Attention section
        self.attention_block(lines)

    def footer(self, text: str) -> None:
        self.elements.append(("footer", text))
        self.y += self.u(96)

    def render(self) -> Image.Image:
        u = self.u
        height = max(self.y + self.pad, u(1200))
        img = Image.new("RGB", (self.width, height), BG)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (u(24), u(24), self.width - u(24), height - u(24)),
            radius=u(28),
            fill=CARD,
            outline=CARD_BORDER,
            width=max(2, u(3)),
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
                    y + u(14),
                    "ok" if olabel == "OK" else ("bad" if olabel == "DOWN" else "warn"),
                    ocolor,
                    size=u(52),
                )
                draw.text((self.pad + u(72), y), title, font=self.title_f, fill=TEXT)
                draw.text((self.pad + u(72), y + u(96)), meta, font=self.small_f, fill=MUTED)
                pill = f"OVERALL  {olabel}"
                pw, ph = _text_size(draw, pill, self.sub_f)
                px = self.pad + u(72)
                py = y + u(156)
                draw.rounded_rectangle((px, py, px + pw + u(48), py + ph + u(28)), radius=u(18), fill=ocolor)
                draw.text((px + u(24), py + u(12)), pill, font=self.sub_f, fill=ICON_RING)
                continue
            if kind == "section":
                _, y, name, slabel, scolor, subtitle, h = el
                draw.rounded_rectangle(
                    (self.pad, y, self.width - self.pad, y + h - u(8)),
                    radius=u(18),
                    fill=HEADER_BG,
                    outline=LINE,
                    width=max(2, u(2)),
                )
                if slabel.upper() in ("OK", "HEALTHY", "ONLINE"):
                    kind_icon = "ok"
                elif slabel.upper() in ("DOWN", "CRITICAL"):
                    kind_icon = "bad"
                else:
                    kind_icon = "warn"
                _draw_status_icon(draw, self.pad + u(24), y + u(28), kind_icon, scolor, size=u(44))
                draw.text((self.pad + u(84), y + u(24)), name, font=self.head_f, fill=ACCENT)
                tag = slabel.upper()
                tw, th = _text_size(draw, tag, self.sub_f)
                tx = self.width - self.pad - tw - u(48)
                draw.rounded_rectangle((tx, y + u(24), tx + tw + u(28), y + u(24) + th + u(20)), radius=u(14), fill=scolor)
                draw.text((tx + u(14), y + u(32)), tag, font=self.sub_f, fill=ICON_RING)
                if subtitle:
                    draw.text((self.pad + u(84), y + u(92)), subtitle, font=self.small_f, fill=MUTED)
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
                    chip_w = tw + (u(56) if vcolor else u(40))
                    chip_h = th + u(32)
                    if x + chip_w > max_x and x > self.pad:
                        x = self.pad
                        row_y += max(row_h, chip_h) + u(16)
                        row_h = 0
                    row_h = max(row_h, chip_h)
                    draw.rounded_rectangle(
                        (x, row_y, x + chip_w, row_y + chip_h),
                        radius=u(16),
                        fill=(32, 38, 56),
                        outline=LINE,
                        width=max(2, u(2)),
                    )
                    if vcolor:
                        _draw_status_icon(
                            draw,
                            x + u(16),
                            row_y + (chip_h - self.icon) // 2,
                            _status_color(value)[0],
                            vcolor,
                            size=self.icon,
                        )
                        draw.text((x + u(64), row_y + u(14)), text, font=self.chip_f, fill=TEXT)
                    else:
                        draw.text((x + u(18), row_y + u(14)), text, font=self.chip_f, fill=TEXT)
                    x += chip_w + u(16)
                continue
            if kind == "table":
                _, y, headers, weights, rows, rh, hh, _h = el
                icon_col = u(80)
                inner_w = self.content_w - icon_col
                weight_sum = sum(weights) or 1.0
                col_ws = [int(inner_w * (w / weight_sum)) for w in weights]
                col_ws[-1] += inner_w - sum(col_ws)
                draw.rectangle((self.pad, y, self.width - self.pad, y + hh), fill=HEADER_BG)
                cx = self.pad + icon_col
                for i, hname in enumerate(headers):
                    draw.text((cx + u(12), y + (hh - u(44)) // 2), hname, font=self.sub_f, fill=MUTED)
                    cx += col_ws[i]
                ry = y + hh
                if not rows:
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + rh), fill=ROW_A)
                    draw.text(
                        (self.pad + icon_col + u(12), ry + (rh - u(50)) // 2),
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
                        self.pad + u(20),
                        ry + (rh - self.icon) // 2,
                        skind,
                        scolor,
                        size=self.icon,
                    )
                    cx = self.pad + icon_col
                    for i, cell in enumerate(cells):
                        max_w = col_ws[i] - u(24)
                        shown = _fit_cell(draw, cell, self.mono_f, max_w)
                        draw.text(
                            (cx + u(12), ry + (rh - u(48)) // 2),
                            shown,
                            font=self.mono_f,
                            fill=_cell_fill(str(cell)),
                        )
                        cx += col_ws[i]
                    draw.line((self.pad, ry + rh - 1, self.width - self.pad, ry + rh - 1), fill=LINE, width=max(2, u(2)))
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=max(2, u(2)))
                continue
            if kind == "mrows":
                # el may be (mrows,y,rows,rh,h) or (+ single_line)
                single_line = bool(el[5]) if len(el) > 5 else False
                _, y, rows, rh, _h = el[:5]
                ry = y
                for idx, (skind, scolor, primary, secondary) in enumerate(rows):
                    bg = ROW_A if idx % 2 == 0 else ROW_B
                    draw.rectangle((self.pad, ry, self.width - self.pad, ry + rh), fill=bg)
                    _draw_status_icon(
                        draw,
                        self.pad + u(20),
                        ry + (rh - self.icon) // 2,
                        skind,
                        scolor,
                        size=self.icon,
                    )
                    max_w = self.content_w - u(110)
                    text = primary if single_line or not secondary else primary
                    p = _fit_cell(draw, text, self.mono_f, max_w)
                    if single_line or not secondary:
                        draw.text((self.pad + u(80), ry + (rh - int(self.body_px * 0.9)) // 2), p, font=self.mono_f, fill=TEXT)
                    else:
                        s = _fit_cell(draw, secondary, self.small_f, max_w)
                        draw.text((self.pad + u(80), ry + u(18)), p, font=self.mono_f, fill=TEXT)
                        draw.text((self.pad + u(80), ry + u(18) + max(36, int(self.body_px * 0.75))), s, font=self.small_f, fill=MUTED)
                    draw.line((self.pad, ry + rh - 1, self.width - self.pad, ry + rh - 1), fill=LINE, width=max(2, u(2)))
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=max(2, u(2)))
                continue
            if kind == "mrows2":
                # backward-compat 2-col tuple shape
                _, y, left, right, rh, _h = el
                columns = [left, right]
                cols = 2
                single_line = False
                gap = u(16)
                col_w = (self.content_w - gap * (cols - 1)) // cols
                ry = y
                n = len(left)
                for idx_row in range(n):
                    bg = ROW_A if idx_row % 2 == 0 else ROW_B
                    for ci, col in enumerate(columns):
                        skind, scolor, primary, secondary = col[idx_row]
                        x0 = self.pad + ci * (col_w + gap)
                        x1 = x0 + col_w
                        draw.rectangle((x0, ry, x1, ry + rh), fill=bg)
                        if primary:
                            _draw_status_icon(
                                draw,
                                x0 + u(10),
                                ry + (rh - self.icon) // 2,
                                skind,
                                scolor,
                                size=self.icon,
                            )
                            max_w = col_w - u(70)
                            p = _fit_cell(draw, primary, self.mono_f, max_w)
                            draw.text((x0 + u(44), ry + (rh - int(self.body_px * 0.9)) // 2), p, font=self.mono_f, fill=TEXT)
                        draw.line((x0, ry + rh - 1, x1, ry + rh - 1), fill=LINE, width=max(2, u(2)))
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=max(2, u(2)))
                continue
            if kind == "mrowsN":
                single_line = bool(el[6]) if len(el) > 6 else True
                _, y, columns, rh, _h, cols = el[:6]
                gap = u(14)
                col_w = (self.content_w - gap * (cols - 1)) // cols
                ry = y
                n = len(columns[0])
                for idx_row in range(n):
                    bg = ROW_A if idx_row % 2 == 0 else ROW_B
                    for ci, col in enumerate(columns):
                        skind, scolor, primary, secondary = col[idx_row]
                        x0 = self.pad + ci * (col_w + gap)
                        x1 = x0 + col_w
                        draw.rectangle((x0, ry, x1, ry + rh), fill=bg)
                        if primary:
                            _draw_status_icon(
                                draw,
                                x0 + u(8),
                                ry + (rh - self.icon) // 2,
                                skind,
                                scolor,
                                size=self.icon,
                            )
                            max_w = col_w - u(64)
                            line = primary if single_line or not secondary else primary
                            p = _fit_cell(draw, line, self.mono_f, max_w)
                            if single_line or not secondary:
                                draw.text(
                                    (x0 + u(40), ry + (rh - int(self.body_px * 0.85)) // 2),
                                    p,
                                    font=self.mono_f,
                                    fill=TEXT,
                                )
                            else:
                                s = _fit_cell(draw, secondary, self.small_f, max_w)
                                draw.text((x0 + u(40), ry + u(14)), p, font=self.mono_f, fill=TEXT)
                                draw.text(
                                    (x0 + u(40), ry + u(14) + max(32, int(self.body_px * 0.75))),
                                    s,
                                    font=self.small_f,
                                    fill=MUTED,
                                )
                        draw.line((x0, ry + rh - 1, x1, ry + rh - 1), fill=LINE, width=max(2, u(2)))
                    ry += rh
                draw.rectangle((self.pad, y, self.width - self.pad, ry), outline=LINE, width=max(2, u(2)))
                continue
            if kind in ("bullets", "attn"):
                _, y, wrapped_all, _total, line_h = el
                font = self.attn_f if kind == "attn" else self.body_f
                icon_sz = max(18, int(self.body_px * 0.35)) if kind == "attn" else u(34)
                yy = y
                for parts, color in wrapped_all:
                    for i, part in enumerate(parts):
                        if i == 0:
                            _draw_status_icon(
                                draw,
                                self.pad + u(8),
                                yy + max(2, int(line_h * 0.1)),
                                "warn" if color == WARN else ("bad" if color == BAD else "ok"),
                                color,
                                size=icon_sz,
                            )
                            body = part.lstrip("• ").lstrip()
                            draw.text((self.pad + u(48), yy), f"→ {body}", font=font, fill=color)
                        else:
                            draw.text((self.pad + u(48), yy), f"  {part}", font=font, fill=color)
                        yy += line_h
                    yy += max(8, int(self.body_px * 0.2))
                continue
            if kind == "footer":
                text = el[1]
                draw.line((self.pad, height - u(84), self.width - self.pad, height - u(84)), fill=LINE, width=max(2, u(2)))
                draw.text((self.pad, height - u(64)), text, font=self.small_f, fill=MUTED)
        return img


def _attention_next_steps(warnings: list[str]) -> list[str]:
    """Map raw warnings to a single concrete next step each (no diagnosis essays)."""
    steps: list[str] = []
    seen: set[str] = set()

    def add(step: str) -> None:
        s = step.strip()
        if s and s not in seen:
            seen.add(s)
            steps.append(s)

    for w in warnings:
        wl = str(w).lower()
        if "cephfs-immich" in wl or ("storage status unknown" in wl and "immich" in wl):
            add(
                "Next: on pvenodetwo + pvenodethree, fix or remove storage "
                "`cephfs-immich` (PVE → Datacenter → Storage) until status is available"
            )
        elif "stripped untrusted" in wl or ("osd" in wl and "fixture" in wl):
            add(
                "Next: deploy ClusterMCP build with live OSD tree "
                "(no fallback fixture) so /ceph/osds returns real detail"
            )
        elif "per-osd utilization" in wl or "osd tree" in wl or "osd inventory" in wl:
            add(
                "Next: verify Ceph OSD tree API from MCP LXC "
                "(`/nodes/<node>/ceph/osd`) and redeploy fixed CephClient"
            )
        elif "offline nodes" in wl:
            add(f"Next: bring offline node(s) online — {w.split(':',1)[-1].strip()}")
        elif "ceph health" in wl:
            add(f"Next: inspect Ceph health detail on a mon (`ceph -s`) — {w}")
        elif "degraded" in wl or ("incomplete" in wl and "pg" in wl):
            add("Next: run `ceph pg dump_stuck` / check recovering PGs until active+clean")
        elif "probe error" in wl:
            add(f"Next: restore failing probe path — {w}")
        else:
            add(f"Next: {w}")

    return steps or ["Next: no open attention items"]


def _section_status_from_rows(statuses: list[Any]) -> tuple[str, tuple[int, int, int]]:
    kinds = [_status_color(s) for s in statuses]
    if any(k == "bad" for k, _ in kinds):
        return "DOWN", BAD
    if any(k == "warn" for k, _ in kinds) or not statuses:
        return "WARN", WARN
    if statuses and all(k == "ok" for k, _ in kinds):
        return "OK", OK
    return "—", MUTED


def _fill_overview(
    c: _Canvas,
    report: dict[str, Any],
    page_label: str,
    *,
    include_footer: bool = True,
    include_ceph: bool = True,
    include_attention: bool = False,
) -> None:
    overall = str((report.get("summary") or {}).get("overall") or report.get("overall") or "unknown")
    label, color = _traffic(overall)
    cluster = report.get("cluster") or {}
    summary = report.get("summary") or {}
    ceph = report.get("ceph") or {}
    mcp = report.get("mcp") or {}
    nodes = list(report.get("node_inventory") or [])
    width = c.width

    c.title_block(
        title="ClusterMCP  ·  Visibility",
        meta=(
            f"{report.get('generated_at', '—')}  ·  live_probes_only  ·  "
            f"{width}px  ·  body {c.body_px}px  ·  {page_label}"
        ),
        overall_label=label,
        overall_color=color,
    )
    c.gap(32)

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
    c.gap(28)

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

    if include_ceph:
        _append_ceph(c, report)

    if include_attention:
        _append_attention(c, report)

    if include_footer:
        c.footer(f"Stronghold · live probes · {width}px · body {c.body_px}px · {page_label}")


def _append_ceph(c: _Canvas, report: dict[str, Any]) -> None:
    ceph = report.get("ceph") or {}
    osd_summary = ceph.get("osd_summary") or {}
    osds = list(ceph.get("osds") or [])
    health = ceph.get("health_status") or (ceph.get("health") or {}).get("status") or "—"
    hk, hc = _status_color(health)
    sec_l, sec_c = ("WARN", WARN) if osd_summary.get("detail_available") is False else (
        ("OK", OK) if hk == "ok" else (("DOWN", BAD) if hk == "bad" else ("WARN", WARN))
    )
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
            single_line=False,
        )
    c.gap(24)


def _append_attention(c: _Canvas, report: dict[str, Any]) -> None:
    warnings = list(report.get("warnings") or [])
    if warnings:
        steps = _attention_next_steps(warnings)
        c.section_header("Attention", "ATTN", WARN, subtitle="one next step each")
        c.attention_block([(s, WARN) for s in steps])
    else:
        c.section_header("Attention", "OK", OK, subtitle="No open next steps")
        c.attention_block([("Next: none — cluster probes clean", OK)])


def _append_containers(c: _Canvas, report: dict[str, Any]) -> None:
    containers = list(report.get("containers") or [])
    ct_statuses = [ct.get("status") for ct in containers]
    ct_l, ct_c = _section_status_from_rows(ct_statuses)
    c.section_header("Containers", ct_l, ct_c, subtitle=f"{len(containers)} LXC")
    ct_mrows: list[tuple[str, tuple[int, int, int], str, str]] = []
    for ct in containers:
        sk, sc = _status_color(ct.get("status"))
        tags = f" · {ct.get('tags')}" if ct.get("tags") else ""
        primary = (
            f"{ct.get('vmid')} {ct.get('name')} · {ct.get('node')} · {ct.get('status')} · "
            f"CPU {ct.get('cpu_human') or '—'} · RAM {ct.get('mem_human') or '—'} · "
            f"disk {ct.get('disk_human') or '—'} · up {ct.get('uptime_human') or '—'}{tags}"
        )
        ct_mrows.append((sk, sc, primary, ""))
    c.multiline_rows_2col(ct_mrows, cols=2, single_line=True)
    c.gap(24)


def _append_storage(c: _Canvas, report: dict[str, Any]) -> None:
    storage = list(report.get("storage") or [])
    st_statuses = [s.get("status") for s in storage]
    st_l, st_c = _section_status_from_rows(st_statuses if st_statuses else ["unknown"])
    c.section_header("Storage", st_l, st_c, subtitle=f"{len(storage)} objects")
    st_mrows: list[tuple[str, tuple[int, int, int], str, str]] = []
    for s in storage:
        sk, sc = _status_color(s.get("status"))
        ratio = s.get("ratio")
        ratio_s = f"{ratio * 100:.1f}%" if isinstance(ratio, float) else "—"
        primary = (
            f"{s.get('node')}/{s.get('storage')} · {s.get('status')} · {s.get('type') or '—'} · "
            f"{s.get('used_human') or '—'}/{s.get('total_human') or '—'} · fill {ratio_s}"
        )
        st_mrows.append((sk, sc, primary, ""))
    c.multiline_rows_2col(st_mrows, cols=2, single_line=True)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def render_visibility_pages(
    report: dict[str, Any],
    width: int = DEFAULT_WIDTH,
    target_body_css: float = TARGET_BODY_CSS_PX,
) -> list[tuple[str, bytes]]:
    """Two-page Discord-friendly report (Wil default).

    Page 1: Summary + Nodes + Attention
    Page 2: Ceph + Containers + Storage
    """
    width = max(BASE_WIDTH, int(width))
    pages: list[tuple[str, bytes]] = []

    c1 = _Canvas(width=width, target_body_css=target_body_css)
    _fill_overview(
        c1,
        report,
        "1/2 · summary · nodes · attention",
        include_footer=True,
        include_ceph=False,
        include_attention=True,
    )
    pages.append(("01-summary-nodes-attention", _png_bytes(c1.render())))

    overall = str((report.get("summary") or {}).get("overall") or report.get("overall") or "unknown")
    label, color = _traffic(overall)
    c2 = _Canvas(width=width, target_body_css=target_body_css)
    c2.title_block(
        title="ClusterMCP  ·  Ceph · CTs · Storage",
        meta=(
            f"{report.get('generated_at', '—')}  ·  live_probes_only  ·  "
            f"{width}px  ·  body {c2.body_px}px  ·  2/2"
        ),
        overall_label=label,
        overall_color=color,
    )
    c2.gap(28)
    _append_ceph(c2, report)
    _append_containers(c2, report)
    _append_storage(c2, report)
    c2.footer(f"Stronghold · live probes · {width}px · body {c2.body_px}px · 2/2")
    pages.append(("02-ceph-containers-storage", _png_bytes(c2.render())))

    return pages


def render_visibility_image(
    report: dict[str, Any],
    width: int = DEFAULT_WIDTH,
    target_body_css: float = TARGET_BODY_CSS_PX,
) -> bytes:
    """Single full report PNG (optional; prefer two-page default)."""
    width = max(BASE_WIDTH, int(width))
    c = _Canvas(width=width, target_body_css=target_body_css)
    _fill_overview(
        c,
        report,
        "full report",
        include_footer=False,
        include_ceph=True,
        include_attention=False,
    )
    _append_containers(c, report)
    _append_storage(c, report)
    _append_attention(c, report)
    c.footer(f"Stronghold · live probes · {width}px · body {c.body_px}px · single image")
    return _png_bytes(c.render())
