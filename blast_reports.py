"""
DeSales Baseball - Blast Motion Hitting Reports
================================================

Creates two kinds of PDF reports from Blast Motion exports:
  * Individual reports - one per player, from an "All swings by player" CSV
  * Team report        - from an "Average performance" CSV

How to run
----------
    pip install pandas matplotlib
    python blast_reports.py              # opens the point-and-click window
    python blast_reports.py file.csv     # no window: detects which export it is
                                         # and writes reports next to the CSV

Edit the SETTINGS section below to change team name, colors, or which
metrics appear in the report.
"""

import os
import sys
from datetime import datetime

import pandas as pd
import matplotlib

matplotlib.use("Agg")  # draw to files, not the screen
import matplotlib.lines
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
TEAM_NAME = "DeSales Baseball"
REPORT_TITLE = "Blast Motion Hitting Report"
TEAM_REPORT_TITLE = "Blast Motion Team Report"

# Players left out by default (not on the roster). They start unchecked in the
# window and are skipped when the script runs without the window.
EXCLUDE_PLAYERS = ["Carson Torresani"]

# Logo shown in the header. Put the PNG in the same folder as this script
# (or give a full path). If the file isn't found, the header just skips it.
LOGO_FILE = "desales_logo.png"
LOGO_HEIGHT = 0.062   # logo size as a share of page height (banner is 0.085)

NAVY = "#002856"   
RED = "#C10230"    
INK = "#1F2933"
MUTED = "#6B7785"
GRID = "#E3E7EC"
PANEL = "#F4F6F9"

# Metric groups shown in the summary table: (column in CSV, label, unit, decimals)
METRIC_GROUPS = [
    ("Speed & Power", [
        ("Bat Speed (MPH)", "Bat Speed", "mph", 1),
        ("Peak Hand Speed (MPH)", "Peak Hand Speed", "mph", 1),
        ("Rotational Acceleration (G's)", "Rotational Accel.", "g", 1),
        ("Power (kW)", "Power", "kW", 2),
    ]),
    ("Swing Path", [
        ("Attack Angle (°'s)", "Attack Angle", "°", 1),
        ("Vert. Bat Angle (°'s)", "Vertical Bat Angle", "°", 1),
        ("On Plane Efficiency (%)", "On-Plane Efficiency", "%", 0),
    ]),
    ("Timing", [
        ("Time to Contact (s)", "Time to Contact", "s", 3),
        ("Commit Time (s)", "Commit Time", "s", 3),
    ]),
    ("Body & Connection", [
        ("Early Connection (°'s)", "Early Connection", "°", 1),
        ("Connection at Impact (°'s)", "Connection at Impact", "°", 1),
        ("Hinge Angle at Impact (°'s)", "Hinge Angle at Impact", "°", 1),
        ("Body Tilt Angle (°'s)", "Body Tilt Angle", "°", 1),
    ]),
]

# Headline tiles at the top of page 1: (column, label, unit, decimals)
KPI_TILES = [
    ("Bat Speed (MPH)", "Bat Speed", "mph", 1),
    ("Attack Angle (°'s)", "Attack Angle", "°", 1),
    ("Vert. Bat Angle (°'s)", "Vert. Bat Angle", "°", 1),
    ("Early Connection (°'s)", "Early Connection", "°", 1),
    ("Connection at Impact (°'s)", "Conn. at Impact", "°", 1),
    ("Rotational Acceleration (G's)", "Rot. Accel.", "g", 1),
    ("On Plane Efficiency (%)", "On-Plane Eff.", "%", 0),
    ("Time to Contact (s)", "Time to Contact", "s", 3),
]

# Team target ranges. Use "low" and/or "high" - leave one out for a
# minimum-only or maximum-only target. "ideal" is optional (dashed line).
# Add a metric here and it automatically gets a target band, a Target column
# in the summary table, and an "in target" percentage.
TARGETS = {
    "Bat Speed (MPH)":            {"low": 67},   # minimum only
    "Attack Angle (°'s)":         {"low": 5, "high": 20},
    "Vert. Bat Angle (°'s)":      {"low": -45, "high": -30},
    "Early Connection (°'s)":     {"low": 80, "high": 100, "ideal": 90},
    "Connection at Impact (°'s)": {"low": 80, "high": 105, "ideal": 90},
}

IN_RANGE = "#1E7B4A"     # avg inside target
OUT_RANGE = "#C2410C"    # avg outside target
BAND = "#2E9E62"         # target band shading on charts

# Glossary (page 3): column -> plain-language explanation.
# Targets are pulled from TARGETS above, or from GLOSSARY_GUIDE when a metric
# has no team target.
GLOSSARY = {
    "Bat Speed (MPH)":
        "How fast the sweet spot of the bat (6 inches from the tip) is moving "
        "at impact. The main driver of exit velocity. For Major League Baseball, "
        "the average Bat Speed is 72 mph, and for NCAA Division-I players, "
        "the average is 67 mph.",
    "Peak Hand Speed (MPH)":
        "The fastest the hands move during the swing, measured on the handle "
        "6 inches from the knob. It peaks just before impact as the wrists "
        "unhinge.",
    "Rotational Acceleration (G's)":
        "How quickly the bat accelerates into the swing plane. High values mean "
        "speed is built by rotating the body in sequence rather than pulling "
        "with the hands.",
    "Power (kW)":
        "Average power produced during the swing, calculated from the bat's "
        "mass, bat speed at impact, and how quickly the bat accelerated. A "
        "NCAA/MiLB range is 3.20 – 5.20 kW",
    "On Plane Efficiency (%)":
        "Share of the swing where the bat stays on the plane set by the "
        "vertical bat angle at contact. Higher means a more efficient path "
        "that stays in the hitting zone longer.",
    "Attack Angle (°'s)":
        "The angle of the bat's path at impact. Positive means swinging up, "
        "negative means swinging down, 0° is level. A slight upward path "
        "matches the downward plane of the pitch.",
    "Vert. Bat Angle (°'s)":
        "The tilt of the bat at impact relative to the ground. Negative means "
        "the barrel is below the hands. Higher pitches flatten this angle; "
        "lower pitches make it steeper.",
    "Time to Contact (s)":
        "Time from the start of the downswing to impact. Lower means the hitter "
        "can wait longer and still get to the ball.",
    "Commit Time (s)":
        "Time from the start of the downswing to the point where the hitter is "
        "committed to swinging, around when the wrists start to unhinge. Lower "
        "means more time to recognize the pitch.",
    "Early Connection (°'s)":
        "Angle between the body's tilt and the bat at the start of the "
        "downswing. Around 90° means the bat is set perpendicular to the body, "
        "which helps get on plane early and adjust to pitch location. "
        "Low Early Connection (<80°): The bat is laid off too flat relative to "
        "the spine at the start of rotation. High Early Connection (>105°): "
        "The barrel is positioned too high or upright relative to the spine "
        "when rotation begins. (<80°): Weak opposite-field contact, trouble "
        "with low pitches, choppy swing path, reduced On-Plane Efficiency (<70%). "
        "(>105°): Pull-side rollovers, weak ground balls, casting, and power " 
        "loss on outside pitches.",
    "Connection at Impact (°'s)":
        "The same body-to-bat relationship, measured at impact. Staying near "
        "90° across pitch locations shows the hitter is adjusting with the "
        "body, not just the hands.",
    "Hinge Angle at Impact (°'s)":
        "How much the wrists are hinged (bat relative to the hands and "
        "forearms) at impact.",
    "Body Tilt Angle (°'s)":
        "How far the upper body is tilted at impact. Body tilt is what "
        "connection is measured against, and it changes with pitch height.",
}

# Guidance shown in the glossary for metrics with no team target.
GLOSSARY_GUIDE = {
    "Peak Hand Speed (MPH)": "No team target. Read alongside bat speed.",
    "Rotational Acceleration (G's)": "No team target. Higher is better.",
    "Power (kW)": "No team target. Higher is better.",
    "On Plane Efficiency (%)": "No team target. Higher is better.",
    "Time to Contact (s)": "No team target. Lower is better.",
    "Commit Time (s)": "No team target. Lower is better.",
    "Hinge Angle at Impact (°'s)": "No team target. Track for consistency.",
    "Body Tilt Angle (°'s)": "No team target. Varies with pitch height.",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
BAT_SPEED = "Bat Speed (MPH)"
ATTACK = "Attack Angle (°'s)"
VBA = "Vert. Bat Angle (°'s)"
OPE = "On Plane Efficiency (%)"
EARLY = "Early Connection (°'s)"
CONN = "Connection at Impact (°'s)"
TTC = "Time to Contact (s)"


def load_swings(csv_path):
    """Read a Blast 'All swings by player' export and tidy it up."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip().strip('"') for c in df.columns]

    required = {"first_name", "last_name", "Swing Timestamp", BAT_SPEED}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "This doesn't look like an 'All swings by player' export.\n"
            f"Missing columns: {', '.join(sorted(missing))}"
        )

    if "actiontype" in df.columns:
        df = df[df["actiontype"].fillna("swing").str.lower() == "swing"]

    df["Swing Timestamp"] = pd.to_datetime(df["Swing Timestamp"], errors="coerce")
    df["Player"] = (df["first_name"].fillna("").str.strip() + " "
                    + df["last_name"].fillna("").str.strip()).str.strip()

    # Blast exports On-Plane Efficiency as a fraction (0.56) -> show as 56
    if OPE in df.columns and df[OPE].dropna().max() <= 1.5:
        df[OPE] = df[OPE] * 100

    return df.sort_values("Swing Timestamp").reset_index(drop=True)


def list_players(df):
    return sorted(df["Player"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def fmt(value, decimals):
    if pd.isna(value):
        return "–"
    return f"{value:,.{decimals}f}"


def target_for(col):
    t = TARGETS.get(col)
    if not t:
        return None
    lo, hi = t.get("low"), t.get("high")
    if lo is not None and hi is not None:
        lo, hi = sorted((lo, hi))
    return {"low": lo, "high": hi, "ideal": t.get("ideal")}


def in_target(value, t):
    return ((t["low"] is None or value >= t["low"])
            and (t["high"] is None or value <= t["high"]))


def target_text(col, unit, dec=0):
    t = target_for(col)
    if not t:
        return ""
    u = unit if unit in ("%", "°") else f" {unit}"
    if t["high"] is None:
        txt = f"{fmt(t['low'], dec)}{u} or more"
    elif t["low"] is None:
        txt = f"{fmt(t['high'], dec)}{u} or less"
    else:
        txt = f"{fmt(t['low'], dec)} to {fmt(t['high'], dec)}{u}"
    if t["ideal"] is not None:
        txt += f" (ideal {fmt(t['ideal'], dec)}{u})"
    return txt


def pct_in_target(s, col):
    t = target_for(col)
    if not t or s.empty:
        return None
    return s.apply(lambda v: in_target(v, t)).mean() * 100


def status_color(value, col):
    t = target_for(col)
    if not t or pd.isna(value):
        return INK
    return IN_RANGE if in_target(value, t) else OUT_RANGE


def add_band(ax, col, axis):
    """Shade a metric's target range on the x or y axis of a chart."""
    t = target_for(col)
    if not t:
        return False
    span = ax.axvspan if axis == "x" else ax.axhspan
    line = ax.axvline if axis == "x" else ax.axhline
    get = ax.get_xlim if axis == "x" else ax.get_ylim
    setl = ax.set_xlim if axis == "x" else ax.set_ylim
    lim_lo, lim_hi = get()
    pad = (lim_hi - lim_lo) * 0.04
    # widen the axis so the edges of the target range are visible
    if t["low"] is not None:
        lim_lo = min(lim_lo, t["low"] - pad)
    if t["high"] is not None:
        lim_hi = max(lim_hi, t["high"] + pad)
    lo = t["low"] if t["low"] is not None else lim_lo - 1000
    hi = t["high"] if t["high"] is not None else lim_hi + 1000
    span(lo, hi, color=BAND, alpha=0.10, lw=0, zorder=0)
    for edge in (t["low"], t["high"]):
        if edge is not None:
            line(edge, color=BAND, lw=0.8, alpha=0.6, zorder=1)
    setl(lim_lo, lim_hi)
    if t["ideal"] is not None:
        line(t["ideal"], color=BAND, lw=1.2, ls="--", zorder=1)
    return True


def style_axis(ax, title):
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold", color=NAVY, pad=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#B8C0CA")
    ax.tick_params(colors=MUTED, labelsize=7.5, length=0)
    ax.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_size(8)
    ax.yaxis.label.set_size(8)


_LOGO_CACHE = {}


def prepare_logo(path):
    """Load the logo and make it header-ready, whatever version is supplied:
    removes a white/solid background, drops stray marks (like a TM) that
    aren't attached to the main logo, and adds a thin white outline so it
    stands out on the navy banner."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    im = Image.open(path).convert("RGBA")
    # Work at a sensible size (big logos slow things down, tiny ones look soft)
    scale = 600 / max(im.size)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                   Image.LANCZOS)
    w, h = im.size
    arr = np.array(im).copy()

    # 1. Remove a solid background (sampled from the corners) if there is one
    corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
    if all(c[3] > 200 for c in corners):
        bg = np.mean([c[:3] for c in corners], axis=0)
        rgb = Image.fromarray(arr[:, :, :3].copy()).copy()  # editable copy
        marker = (255, 0, 255) if tuple(bg.astype(int)) != (255, 0, 255) else (0, 255, 0)
        for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
            if tuple(rgb.getpixel(pt)) != marker:
                ImageDraw.floodfill(rgb, pt, marker, thresh=40)
        hit = np.all(np.array(rgb) == marker, axis=2)
        arr[hit, 3] = 0

    # 2. Keep only the main shape (drops a separate TM / (R) mark)
    mask = Image.fromarray(np.where(arr[:, :, 3] > 40, 255, 0).astype("uint8")).copy()
    cx, cy = w // 2, h // 2
    if mask.getpixel((cx, cy)) == 255:
        ImageDraw.floodfill(mask, (cx, cy), 128)
        arr[np.array(mask) != 128, 3] = 0

    im = Image.fromarray(arr)
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)

    # 3. White outline - skipped if the logo's edge is already white
    a = np.array(im)
    solid = a[:, :, 3] > 128
    inner = np.zeros_like(solid)
    inner[1:-1, 1:-1] = (solid[1:-1, 1:-1] & solid[:-2, 1:-1] & solid[2:, 1:-1]
                         & solid[1:-1, :-2] & solid[1:-1, 2:])
    edge = solid & ~inner
    edge_rgb = a[:, :, :3][edge]
    already_outlined = edge.any() and (edge_rgb.min(axis=1) > 215).mean() > 0.6
    if already_outlined:
        return finish_logo(im)
    pad = 14
    canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, (pad, pad), im)
    alpha = canvas.split()[3].point(lambda v: 255 if v > 40 else 0)
    ring = alpha.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(0.8))
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    white.putalpha(ring)
    out = Image.alpha_composite(white, canvas)
    return finish_logo(out)


def finish_logo(im):
    """Shrink to the exact print size with a high-quality filter, so the PDF
    doesn't have to resize it (older matplotlib versions do that badly)."""
    import numpy as np
    from PIL import Image
    target_h = int(LOGO_HEIGHT * 11 * 450)          # ~450 dpi when printed
    if im.height > target_h:
        target_w = max(1, round(im.width * target_h / im.height))
        im = im.resize((target_w, target_h), Image.LANCZOS)
    return np.asarray(im).astype(float) / 255.0


def load_logo():
    if "img" not in _LOGO_CACHE:
        path = LOGO_FILE
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        img = None
        if os.path.exists(path):
            try:
                img = prepare_logo(path)
            except Exception:  # noqa: BLE001 - fall back to the raw image
                try:
                    img = plt.imread(path)
                except Exception:  # noqa: BLE001 - a bad logo shouldn't stop reports
                    img = None
        _LOGO_CACHE["img"] = img
    return _LOGO_CACHE["img"]


def draw_header(fig, title, sub_line, page_label, kicker=None):
    """Navy banner with logo. Measured in inches so it looks the same on
    portrait and landscape pages."""
    W, H = fig.get_size_inches()
    band, stripe = 0.935 / H, 0.066 / H
    fig.patches.append(Rectangle((0, 1 - band), 1, band, transform=fig.transFigure,
                                 color=NAVY, zorder=0))
    fig.patches.append(Rectangle((0, 1 - band - stripe), 1, stripe,
                                 transform=fig.transFigure, color=RED, zorder=0))
    left, right = 0.34 / W, 1 - 0.425 / W
    text_x = 0.425 / W
    logo = load_logo()
    if logo is not None:
        h_in = LOGO_HEIGHT * 11
        w_in = h_in * logo.shape[1] / logo.shape[0]
        ax_logo = fig.add_axes([left, 1 - band / 2 - h_in / H / 2, w_in / W, h_in / H])
        # "none" = embed the prepared image as-is; the PDF viewer scales it
        ax_logo.imshow(logo, interpolation="none")
        ax_logo.axis("off")
        ax_logo.set_zorder(10)  # draw above the header banner
        text_x = left + (w_in + 0.153) / W
    top_line = 1 - 0.352 / H
    kicker = kicker or REPORT_TITLE
    fig.text(text_x, top_line, f"{TEAM_NAME.upper()}  ·  {kicker.upper()}",
             color="#C9D3E3", fontsize=8, fontweight="bold")
    fig.text(text_x, 1 - 0.77 / H, title, color="white", fontsize=21,
             fontweight="bold")
    fig.text(right, top_line, page_label, color="#C9D3E3", fontsize=8, ha="right",
             fontweight="bold")
    fig.text(right, 1 - 0.726 / H, sub_line, color="white", fontsize=9, ha="right")


def draw_footer(fig):
    fig.text(0.05, 0.02, f"Generated {datetime.now():%b %d, %Y} from Blast Motion data",
             color=MUTED, fontsize=7)


def draw_kpi_tiles(fig, d, top, height, in_target_label="in target"):
    cols = 4
    rows = (len(KPI_TILES) + cols - 1) // cols
    left, right, gap = 0.05, 0.95, 0.014
    w = (right - left - gap * (cols - 1)) / cols
    h = (height - gap * (rows - 1)) / rows
    for i, (col, label, unit, dec) in enumerate(KPI_TILES):
        if col not in d.columns:
            continue
        r, c = divmod(i, cols)
        x = left + c * (w + gap)
        y = top - (r + 1) * h - r * gap
        fig.patches.append(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.008",
            transform=fig.transFigure, facecolor=PANEL, edgecolor="none"))
        fig.patches.append(Rectangle((x, y + 0.008), 0.004, h - 0.016,
                                     transform=fig.transFigure,
                                     color=status_color(d[col].mean(), col)
                                     if target_for(col) else NAVY))
        s = d[col].dropna()
        fig.text(x + 0.016, y + h - 0.020, label.upper(), fontsize=7,
                 color=MUTED, fontweight="bold")
        unit_txt = unit if unit in ("%", "°") else f" {unit}"
        fig.text(x + 0.016, y + 0.030, f"{fmt(s.mean(), dec)}{unit_txt}",
                 fontsize=16, color=status_color(s.mean(), col), fontweight="bold")
        pct = pct_in_target(s, col)
        if pct is not None:
            fig.text(x + w - 0.010, y + 0.034, f"{pct:.0f}%\n{in_target_label}",
                     fontsize=6.5, color=MUTED, ha="right", va="bottom",
                     linespacing=1.1)
            sub_txt = f"target {target_text(col, unit)}"
        else:
            sub_txt = f"range {fmt(s.min(), dec)} to {fmt(s.max(), dec)}"
        fig.text(x + 0.016, y + 0.012, sub_txt, fontsize=6.3, color=MUTED)


def draw_metric_table(ax, d, title="Session Summary",
                      note="Green = session average inside the team target, "
                           "orange = outside.  In Target = share of swings "
                           "inside the range.",
                      headers=None):
    ax.axis("off")
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold",
                 color=NAVY, pad=8)
    headers = headers or ["Metric", "Avg", "Max", "Min", "Std Dev", "Spread",
                          "Target", "In Target"]
    xs = [0.0, 0.345, 0.43, 0.515, 0.60, 0.70, 0.765, 1.0]
    aligns = ["left", "right", "right", "right", "right", "right", "left", "right"]

    lines = []
    for group, metrics in METRIC_GROUPS:
        present = [m for m in metrics if m[0] in d.columns]
        if not present:
            continue
        lines.append(("group", group))
        for m in present:
            lines.append(("metric", m))

    row_h = 1.0 / (len(lines) + 1)
    y = 1.0 - row_h / 2
    for x, h, a in zip(xs, headers, aligns):
        ax.text(x, y, h.upper(), fontsize=6.8, color=MUTED, fontweight="bold",
                ha=a, va="center", transform=ax.transAxes)
    ax.plot([0, 1], [1.0 - row_h, 1.0 - row_h], color="#B8C0CA", lw=0.8,
            transform=ax.transAxes)

    stripe = False
    for kind, item in lines:
        y -= row_h
        if kind == "group":
            ax.text(0.0, y, item, fontsize=7.5, color=RED, fontweight="bold",
                    va="center", transform=ax.transAxes)
            stripe = False
            continue
        col, label, unit, dec = item
        s = d[col].dropna()
        if stripe:
            ax.add_patch(Rectangle((-0.01, y - row_h / 2), 1.02, row_h,
                                   transform=ax.transAxes, color=PANEL, zorder=0))
        stripe = not stripe
        mean, sd = s.mean(), s.std()
        # Consistency: how tightly swings cluster (CV for speed-type metrics,
        # +/- spread for angles that can sit near zero)
        if unit in ("°", "%"):
            cons = f"± {fmt(sd, dec)}"
        else:
            cv = (sd / abs(mean) * 100) if mean else float("nan")
            cons = f"{fmt(cv, 1)}% CV"
        pct = pct_in_target(s, col)
        tgt = target_text(col, unit).split(" (ideal")[0] if pct is not None else "–"
        vals = [f"{label} ({unit})", fmt(mean, dec), fmt(s.max(), dec),
                fmt(s.min(), dec), fmt(sd, dec), cons, tgt,
                f"{pct:.0f}%" if pct is not None else "–"]
        for i, (x, v, a) in enumerate(zip(xs, vals, aligns)):
            color = status_color(mean, col) if i in (1, 7) else (
                MUTED if v == "–" else INK)
            ax.text(x, y, v, fontsize=7.6, color=color, ha=a, va="center",
                    fontweight="bold" if i == 1 or (i == 7 and pct is not None)
                    else "normal",
                    transform=ax.transAxes)
    ax.text(0.0, -0.035, note,
            fontsize=6.6, color=MUTED, transform=ax.transAxes, va="top")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def draw_bat_speed_trend(ax, d):
    s = d[BAT_SPEED].reset_index(drop=True)
    x = range(1, len(s) + 1)
    ax.bar(x, s, color="#9FB3CF", width=0.75, label="Swing")
    window = max(3, min(5, len(s) // 4)) if len(s) >= 6 else 1
    if window > 1:
        roll = s.rolling(window, min_periods=1).mean()
        ax.plot(x, roll, color=RED, lw=2, label=f"{window}-swing rolling avg")
    ax.axhline(s.mean(), color=NAVY, lw=1, ls="--", label=f"Avg {s.mean():.1f}")
    t = target_for(BAT_SPEED)
    lo = max(0, s.min() - 5)
    hi_lim = s.max() + 3
    if t:
        if t["low"] is not None:
            lo = min(lo, t["low"] - 1)
        if t["high"] is not None:
            hi_lim = max(hi_lim, t["high"] + 1)
        band_lo = t["low"] if t["low"] is not None else lo
        band_hi = t["high"] if t["high"] is not None else hi_lim
        ax.axhspan(band_lo, band_hi, color=BAND, alpha=0.12, lw=0, zorder=0,
                   label=f"Target {target_text(BAT_SPEED, 'mph')}")
    ax.set_ylim(lo, hi_lim)
    ax.set_xlim(0.3, len(s) + 0.7)
    ax.set_xlabel("Swing # (in order taken)")
    ax.set_ylabel("Bat speed (mph)")
    style_axis(ax, "Bat Speed by Swing")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7, frameon=False, loc="lower right", ncol=4,
              bbox_to_anchor=(1.0, 1.0), borderaxespad=0.2)

    # Simple first-half vs second-half fatigue note
    if len(s) >= 10:
        half = len(s) // 2
        diff = s.iloc[half:].mean() - s.iloc[:half].mean()
        trend = "faster" if diff > 0 else "slower"
        ax.text(0.0, -0.30,
                f"Second half of the session averaged {abs(diff):.1f} mph {trend} "
                f"than the first half.",
                transform=ax.transAxes, fontsize=7.5, color=MUTED)


def scatter(ax, d, xcol, ycol, title, xlabel, ylabel):
    sub = d[[xcol, ycol]].dropna()
    ax.scatter(sub[xcol], sub[ycol], s=26, color=NAVY, alpha=0.75,
               edgecolor="white", linewidth=0.6, zorder=3)
    ax.margins(0.06)
    banded = add_band(ax, xcol, "x") | add_band(ax, ycol, "y")
    ax.scatter([sub[xcol].mean()], [sub[ycol].mean()], s=110, color=RED,
               marker="X", edgecolor="white", linewidth=0.8, zorder=4,
               label="Average")
    if banded:
        ax.fill_between([], [], color=BAND, alpha=0.25, label="Target range")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    style_axis(ax, title)
    ax.legend(fontsize=7, frameon=False, loc="best", framealpha=0.9)


def histogram(ax, d, col, title, xlabel, decimals=1):
    s = d[col].dropna()
    ax.hist(s, bins=min(12, max(5, len(s) // 4)), color="#9FB3CF",
            edgecolor="white", linewidth=0.8)
    ax.axvline(s.mean(), color=RED, lw=2, label=f"Avg {s.mean():.{decimals}f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Swings")
    style_axis(ax, title)
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7, frameon=False, loc="upper right")


def draw_top_swings(ax, d, n=5):
    ax.axis("off")
    ax.set_title(f"Top {n} Swings by Bat Speed", loc="left", fontsize=10,
                 fontweight="bold", color=NAVY, pad=8)
    cols = [("Swing Timestamp", "Time", None), (BAT_SPEED, "Bat Spd", 1),
            ("Peak Hand Speed (MPH)", "Hand Spd", 1),
            ("Rotational Acceleration (G's)", "Rot Acc", 1),
            (ATTACK, "Attack ∠", 1), (OPE, "On-Plane %", 0),
            (TTC, "TTC (s)", 3), (CONN, "Conn. Impact", 1)]
    cols = [c for c in cols if c[0] in d.columns]
    top = d.sort_values(BAT_SPEED, ascending=False).head(n)
    # first column (time) is wide; the rest share the remaining width
    xs = [0.0] + [0.24 + i * (0.76 / (len(cols) - 2)) for i in range(len(cols) - 1)]
    row_h = 1.0 / (n + 1.5)
    y = 1 - row_h / 2
    for i, (x, (_, h, _)) in enumerate(zip(xs, cols)):
        ax.text(x, y, h.upper(), fontsize=6.8, color=MUTED, fontweight="bold",
                ha="left" if i == 0 else "right", va="center",
                transform=ax.transAxes)
    ax.plot([0, 1], [1 - row_h, 1 - row_h], color="#B8C0CA", lw=0.8,
            transform=ax.transAxes)
    for r, (_, row) in enumerate(top.iterrows()):
        y -= row_h
        if r % 2 == 0:
            ax.add_patch(Rectangle((-0.01, y - row_h / 2), 1.02, row_h,
                                   transform=ax.transAxes, color=PANEL, zorder=0))
        for i, (x, (col, _, dec)) in enumerate(zip(xs, cols)):
            v = row[col]
            txt = (f"{v.month}/{v.day}  {v.strftime('%I:%M:%S %p').lstrip('0')}" if dec is None and pd.notna(v)
                   else fmt(v, dec))
            ax.text(x, y, txt, fontsize=7.8, color=INK, va="center",
                    ha="left" if i == 0 else "right",
                    fontweight="bold" if col == BAT_SPEED else "normal",
                    transform=ax.transAxes)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def draw_glossary(fig):
    import textwrap
    fig.text(0.05, 0.872, "Metric Glossary", fontsize=13, fontweight="bold",
             color=NAVY)
    fig.text(0.05, 0.853, "What each Blast Motion number measures, and what we "
             "want to see.", fontsize=8, color=MUTED)

    x_name, x_def, x_tgt = 0.05, 0.255, 0.735
    y = 0.825
    line_h = 0.0118
    fig.text(x_name, y, "METRIC", fontsize=6.8, color=MUTED, fontweight="bold")
    fig.text(x_def, y, "WHAT IT MEASURES", fontsize=6.8, color=MUTED,
             fontweight="bold")
    fig.text(x_tgt, y, "TEAM TARGET", fontsize=6.8, color=MUTED, fontweight="bold")
    y -= 0.008
    fig.add_artist(matplotlib.lines.Line2D([0.05, 0.95], [y, y], color="#B8C0CA",
                                           lw=0.8, transform=fig.transFigure))
    y -= 0.008

    for group, metrics in METRIC_GROUPS:
        y -= 0.016
        fig.text(x_name, y, group, fontsize=8, color=RED, fontweight="bold")
        y -= 0.006
        for col, label, unit, dec in metrics:
            definition = GLOSSARY.get(col, "")
            def_lines = textwrap.wrap(definition, 70) or [""]
            t = target_for(col)
            if t:
                tgt = target_text(col, unit)
                tgt_lines = textwrap.wrap(tgt, 28)
                tcolor, tweight = IN_RANGE, "bold"
            else:
                tgt_lines = textwrap.wrap(GLOSSARY_GUIDE.get(col, "–"), 32)
                tcolor, tweight = MUTED, "normal"
            n = max(len(def_lines), len(tgt_lines), 2)
            row_top = y - 0.003
            row_h = n * line_h + 0.008
            fig.patches.append(Rectangle((0.04, row_top - row_h), 0.92, row_h,
                                         transform=fig.transFigure,
                                         color=PANEL, zorder=0))
            ty = row_top - 0.004 - line_h * 0.75
            fig.text(x_name + 0.006, ty, f"{label}", fontsize=8.2, color=INK,
                     fontweight="bold")
            fig.text(x_name + 0.006, ty - line_h, f"({unit})", fontsize=7,
                     color=MUTED)
            for k, ln in enumerate(def_lines):
                fig.text(x_def, ty - k * line_h, ln, fontsize=7.6, color=INK)
            for k, ln in enumerate(tgt_lines):
                fig.text(x_tgt, ty - k * line_h, ln, fontsize=7.6, color=tcolor,
                         fontweight=tweight)
            y = row_top - row_h


def session_line(d):
    dates = d["Swing Timestamp"].dropna().dt.date.unique()
    if len(dates) == 0:
        when = "Date unknown"
    elif len(dates) == 1:
        t = pd.Timestamp(dates[0])
        when = f"{t:%b} {t.day}, {t.year}"
    else:
        a, b = pd.Timestamp(min(dates)), pd.Timestamp(max(dates))
        when = (f"{a:%b} {a.day} – {b:%b} {b.day}, {b.year} "
                f"({len(dates)} sessions)")
    env = ""
    if "Environment Tag" in d.columns:
        tags = d["Environment Tag"].dropna().str.title().unique()
        env = "  ·  " + " / ".join(tags) if len(tags) else ""
    return f"{when}  ·  {len(d)} swings{env}"


def build_player_report(d, out_path):
    player = d["Player"].iloc[0]
    sub = session_line(d)
    plt.rcParams["font.family"] = "DejaVu Sans"

    with PdfPages(out_path) as pdf:
        # ---- Page 1: summary ------------------------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        draw_header(fig, player, sub, "PAGE 1 OF 3")
        draw_kpi_tiles(fig, d, top=0.885, height=0.175)
        ax_tbl = fig.add_axes([0.05, 0.345, 0.90, 0.335])
        draw_metric_table(ax_tbl, d)
        ax_trend = fig.add_axes([0.10, 0.095, 0.85, 0.185])
        draw_bat_speed_trend(ax_trend, d)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Page 2: swing characteristics ----------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        draw_header(fig, player, sub, "PAGE 2 OF 3")
        gs = fig.add_gridspec(2, 2, left=0.09, right=0.95, top=0.855, bottom=0.36,
                              hspace=0.42, wspace=0.28)
        scatter(fig.add_subplot(gs[0, 0]), d, BAT_SPEED, ATTACK,
                "Attack Angle vs. Bat Speed", "Bat speed (mph)", "Attack angle (°)")
        scatter(fig.add_subplot(gs[0, 1]), d, VBA, ATTACK,
                "Attack Angle vs. Vertical Bat Angle", "Vertical bat angle (°)",
                "Attack angle (°)")
        scatter(fig.add_subplot(gs[1, 0]), d, EARLY, CONN,
                "Connection: Early vs. Impact", "Early connection (°)",
                "Connection at impact (°)")
        histogram(fig.add_subplot(gs[1, 1]), d, OPE,
                  "On-Plane Efficiency Distribution", "On-plane efficiency (%)", 0)
        ax_top = fig.add_axes([0.05, 0.07, 0.90, 0.20])
        draw_top_swings(ax_top, d)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Page 3: glossary -----------------------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        draw_header(fig, player, sub, "PAGE 3 OF 3")
        draw_glossary(fig)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

    return out_path


def safe_name(text):
    return "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in text).strip()


def generate_reports(csv_path, out_dir, players=None, log=print):
    df = load_swings(csv_path)
    players = players or list_players(df)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for p in players:
        d = df[df["Player"] == p]
        if d.empty:
            log(f"Skipped {p}: no swings found")
            continue
        date_tag = d["Swing Timestamp"].max()
        date_tag = date_tag.strftime("%Y-%m-%d") if pd.notna(date_tag) else "undated"
        out = os.path.join(out_dir, f"{safe_name(p)} - Hitting Report {date_tag}.pdf")
        build_player_report(d, out)
        log(f"Saved {os.path.basename(out)}  ({len(d)} swings)")
        written.append(out)
    return written


# ---------------------------------------------------------------------------
# Team report (from the "Average performance" export)
# ---------------------------------------------------------------------------
SWINGS = "Swing Count"
ROT = "Rotational Acceleration (G's)"

# Short column labels for the roster table: (column, header, decimals)
ROSTER_COLUMNS = [
    ("Speed & Power", [
        ("Bat Speed (MPH)", "Bat\nSpeed", 1),
        ("Peak Hand Speed (MPH)", "Hand\nSpeed", 1),
        ("Rotational Acceleration (G's)", "Rot.\nAccel.", 1),
        ("Power (kW)", "Power\n(kW)", 2),
    ]),
    ("Swing Path", [
        ("Attack Angle (°'s)", "Attack\nAngle", 1),
        ("Vert. Bat Angle (°'s)", "Vert. Bat\nAngle", 1),
        ("On Plane Efficiency (%)", "On-Plane\nEff. %", 0),
    ]),
    ("Timing", [
        ("Time to Contact (s)", "Time to\nContact", 3),
        ("Commit Time (s)", "Commit\nTime", 3),
    ]),
    ("Body & Connection", [
        ("Early Connection (°'s)", "Early\nConn.", 1),
        ("Connection at Impact (°'s)", "Conn. at\nImpact", 1),
        ("Hinge Angle at Impact (°'s)", "Hinge\nAngle", 1),
        ("Body Tilt Angle (°'s)", "Body\nTilt", 1),
    ]),
]


def load_team_averages(csv_path):
    """Read a Blast 'Average performance' export (one row per player)."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip().strip('"') for c in df.columns]
    required = {"first_name", "last_name", BAT_SPEED}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "This doesn't look like an 'Average performance' export.\n"
            f"Missing columns: {', '.join(sorted(missing))}"
        )
    if "Swing Timestamp" in df.columns:
        raise ValueError("This looks like an 'All swings by player' file. Use it "
                         "on the Individual Reports tab instead.")
    df["Player"] = (df["first_name"].fillna("").str.strip() + " "
                    + df["last_name"].fillna("").str.strip()).str.strip()
    df["Last"] = df["last_name"].fillna("").str.strip()
    if OPE in df.columns and df[OPE].dropna().max() <= 1.5:
        df[OPE] = df[OPE] * 100
    if SWINGS not in df.columns:
        df[SWINGS] = float("nan")
    return df.reset_index(drop=True)


def is_excluded(name):
    return name.strip().lower() in {p.strip().lower() for p in EXCLUDE_PLAYERS}


def short_names(df):
    """Last name, plus first initial when two players share a last name."""
    dup = df["Last"].duplicated(keep=False)
    return [f"{r.first_name.strip()[0]}. {r.Last}" if dup[i] else r.Last
            for i, r in df.iterrows()]


def draw_hitter_bars(ax, df):
    d = df.sort_values(BAT_SPEED, ascending=False).reset_index(drop=True)
    t = target_for(BAT_SPEED)
    colors = [IN_RANGE if (t and in_target(v, t)) else "#9FB3CF"
              for v in d[BAT_SPEED]]
    x = range(len(d))
    ax.bar(x, d[BAT_SPEED], color=colors, width=0.72, zorder=2)
    team = d[BAT_SPEED].mean()
    ax.axhline(team, color=NAVY, lw=1, ls="--", zorder=3,
               label=f"Team avg {team:.1f}")
    lo = max(0, d[BAT_SPEED].min() - 6)
    hi = d[BAT_SPEED].max() + 2
    if t and t["low"] is not None:
        ax.axhline(t["low"], color=BAND, lw=1.4, zorder=3,
                   label=f"Target {target_text(BAT_SPEED, 'mph')}")
        lo = min(lo, t["low"] - 4)
    for i, v in enumerate(d[BAT_SPEED]):
        ax.text(i, v - 0.4, f"{v:.1f}", ha="center", va="top", fontsize=5.8,
                color="white", fontweight="bold", zorder=4)
    ax.set_ylim(lo, hi + 1.5)
    ax.set_xlim(-0.6, len(d) - 0.4)
    ax.set_xticks(list(x))
    ax.set_xticklabels(short_names(d), rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Avg bat speed (mph)")
    style_axis(ax, "Average Bat Speed by Hitter")
    ax.tick_params(axis="x", colors=INK)
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7, frameon=False, loc="lower right", ncol=2,
              bbox_to_anchor=(1.0, 1.0), borderaxespad=0.2)


def draw_roster_table(fig, df, top, bottom, left=0.04, right=0.965):
    groups = [(g, [c for c in cols if c[0] in df.columns])
              for g, cols in ROSTER_COLUMNS]
    groups = [(g, cols) for g, cols in groups if cols]
    metric_cols = [c for _, cols in groups for c in cols]
    d = df.sort_values(BAT_SPEED, ascending=False).reset_index(drop=True)

    ax = fig.add_axes([left, bottom, right - left, top - bottom])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    name_w, swings_w = 0.15, 0.055
    col_w = (1 - name_w - swings_w) / len(metric_cols)
    xs = [name_w + swings_w + (i + 0.5) * col_w for i in range(len(metric_cols))]

    n_rows = len(d) + 1                    # players + team average
    head_h = 0.10
    row_h = (1 - head_h) / (n_rows + 0.4)

    # group bands + column headers
    i = 0
    for g, cols in groups:
        x0 = name_w + swings_w + i * col_w
        x1 = x0 + len(cols) * col_w
        ax.add_patch(Rectangle((x0 + 0.002, 1 - 0.035), x1 - x0 - 0.004, 0.033,
                               color=NAVY, zorder=1))
        ax.text((x0 + x1) / 2, 1 - 0.0185, g.upper(), ha="center", va="center",
                fontsize=6.5, color="white", fontweight="bold", zorder=2)
        i += len(cols)
    hy = 1 - 0.035 - (head_h - 0.035) / 2
    ax.text(0.005, hy, "HITTER", fontsize=6.3, color=MUTED, fontweight="bold",
            va="center")
    ax.text(name_w + swings_w / 2, hy, "Swings", fontsize=6.3, color=MUTED,
            fontweight="bold", va="center", ha="center")
    for x, (col, label, _) in zip(xs, metric_cols):
        ax.text(x, hy, label, fontsize=6.3, color=MUTED, fontweight="bold",
                ha="center", va="center", linespacing=1.05)
        t = target_for(col)
        if t:
            ax.text(x, 1 - head_h + 0.004,
                    target_text(col, "").split(" (ideal")[0].replace(" or more", "+")
                    .replace(" or less", "-").replace(" to ", "–"),
                    fontsize=5.4, color=IN_RANGE, ha="center", va="bottom")
    ax.plot([0, 1], [1 - head_h, 1 - head_h], color="#B8C0CA", lw=0.8)

    def draw_row(y, name, swings, values, bold=False, shade=False):
        if shade:
            ax.add_patch(Rectangle((0, y - row_h / 2), 1, row_h, color=PANEL,
                                   zorder=0))
        ax.text(0.005, y, name, fontsize=7.2, color=INK, va="center",
                fontweight="bold" if bold else "normal")
        ax.text(name_w + swings_w / 2, y, swings, fontsize=7, color=MUTED,
                va="center", ha="center")
        for x, (col, _, dec), v in zip(xs, metric_cols, values):
            t = target_for(col)
            color = status_color(v, col) if t else INK
            weight = "bold" if (t or bold) else "normal"
            if t and pd.notna(v):
                tint = IN_RANGE if in_target(v, t) else OUT_RANGE
                ax.add_patch(Rectangle((x - col_w / 2 + 0.003, y - row_h / 2 + 0.003),
                                       col_w - 0.006, row_h - 0.006, color=tint,
                                       alpha=0.10, lw=0, zorder=0.5))
            ax.text(x, y, fmt(v, dec), fontsize=7, color=color, va="center",
                    ha="center", fontweight=weight)

    y = 1 - head_h - row_h / 2
    for r, row in d.iterrows():
        sw = row[SWINGS]
        draw_row(y, row["Player"], "–" if pd.isna(sw) else f"{int(sw):,}",
                 [row[c[0]] for c in metric_cols], shade=(r % 2 == 1))
        y -= row_h
    # team average row
    y -= row_h * 0.15
    ax.plot([0, 1], [y + row_h / 2 + row_h * 0.075] * 2, color=NAVY, lw=1)
    total = d[SWINGS].sum()
    draw_row(y, "Team Average", f"{int(total):,}" if total == total else "–",
             [d[c[0]].mean() for c in metric_cols], bold=True)


def label_points(ax, xs, ys, names, fontsize=5.8):
    """Name each dot, nudging labels apart so they don't overlap."""
    import numpy as np
    fig = ax.figure
    pts = ax.transData.transform(np.column_stack([xs, ys]))     # pixels
    px_per_pt = fig.dpi / 72
    char_w = fontsize * 0.58 * px_per_pt
    h = fontsize * 1.15 * px_per_pt
    widths = np.array([len(n) * char_w for n in names])
    # start each label just up-right of its dot
    pos = pts + np.array([3, 2]) * px_per_pt
    for _ in range(300):
        moved = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx = min(pos[i, 0] + widths[i], pos[j, 0] + widths[j]) - max(pos[i, 0], pos[j, 0])
                dy = min(pos[i, 1] + h, pos[j, 1] + h) - max(pos[i, 1], pos[j, 1])
                if dx > 0 and dy > 0:
                    shift = (dy / 2 + 0.5)
                    if pos[i, 1] >= pos[j, 1]:
                        pos[i, 1] += shift
                        pos[j, 1] -= shift
                    else:
                        pos[i, 1] -= shift
                        pos[j, 1] += shift
                    moved = True
        if not moved:
            break
    for (x, y), (px, py), p0, n in zip(zip(xs, ys), pos, pts, names):
        off = (px - p0[0]) / px_per_pt, (py - p0[1]) / px_per_pt
        far = abs(off[1] - 2) > fontsize * 0.9
        ax.annotate(n, (x, y), xytext=off, textcoords="offset points",
                    fontsize=fontsize, color=INK, va="bottom", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none",
                              alpha=0.65),
                    arrowprops=dict(arrowstyle="-", color="#9AA5B1", lw=0.5,
                                    shrinkA=0, shrinkB=2) if far else None)


def team_scatter(ax, df, xcol, ycol, title, xlabel, ylabel):
    sub = df[[xcol, ycol, "Last", "first_name"]].dropna(subset=[xcol, ycol])
    ax.scatter(sub[xcol], sub[ycol], s=30, color=NAVY, alpha=0.8,
               edgecolor="white", linewidth=0.6, zorder=3)
    ax.margins(0.10)
    banded = add_band(ax, xcol, "x") | add_band(ax, ycol, "y")
    ax.scatter([sub[xcol].mean()], [sub[ycol].mean()], s=110, color=RED,
               marker="X", edgecolor="white", linewidth=0.8, zorder=4,
               label="Team average")
    if banded:
        ax.fill_between([], [], color=BAND, alpha=0.25, label="Target range")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    style_axis(ax, title)
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    label_points(ax, sub[xcol], sub[ycol], short_names(sub.reset_index(drop=True)))
    ax.legend(fontsize=7, frameon=True, framealpha=0.9, edgecolor="none",
              loc="best")


def draw_ope_ranked(ax, df):
    """Each hitter's on-plane efficiency, ranked, shown against the team average."""
    d = df[["Player", "first_name", "Last", OPE]].dropna(subset=[OPE])
    d = d.sort_values(OPE, ascending=True).reset_index(drop=True)
    team = d[OPE].mean()
    ys = range(len(d))
    above = d[OPE] >= team
    colors = [NAVY if a else "#9FB3CF" for a in above]
    ax.hlines(ys, team, d[OPE], colors=colors, lw=2.2, zorder=2)
    ax.scatter(d[OPE], ys, s=34, color=colors, edgecolor="white", linewidth=0.7,
               zorder=3)
    ax.axvline(team, color=RED, lw=1.2, ls="--", zorder=1,
               label=f"Team avg {team:.0f}%")
    for y, v, a in zip(ys, d[OPE], above):
        ax.text(v + (1.2 if a else -1.2), y, f"{v:.0f}", va="center",
                ha="left" if a else "right", fontsize=6, color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(short_names(d), fontsize=6.3)
    lo, hi = d[OPE].min(), d[OPE].max()
    ax.set_xlim(lo - 7, hi + 6)
    ax.set_ylim(-0.7, len(d) - 0.3)
    ax.set_xlabel("On-plane efficiency (%)")
    style_axis(ax, "On-Plane Efficiency by Hitter")
    ax.tick_params(axis="y", colors=INK)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=7, frameon=True, framealpha=0.9, edgecolor="none",
              loc="lower right")


def draw_targets_met(ax, df):
    """How many of the team targets each hitter's average meets."""
    cols = [c for c in TARGETS if c in df.columns]
    met = df[cols].apply(lambda r: sum(in_target(r[c], target_for(c))
                                       for c in cols if pd.notna(r[c])), axis=1)
    d = df.assign(_met=met).sort_values(["_met", BAT_SPEED],
                                        ascending=[True, True]).reset_index(drop=True)
    names = short_names(d)
    ax.barh(range(len(d)), d["_met"], color=[
        IN_RANGE if m == len(cols) else ("#9FB3CF" if m >= len(cols) / 2 else OUT_RANGE)
        for m in d["_met"]], height=0.7, zorder=2)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(names, fontsize=6.8)
    ax.set_xlim(0, len(cols))
    ax.set_xticks(range(len(cols) + 1))
    ax.set_xlabel(f"Targets met (of {len(cols)})")
    style_axis(ax, "Targets Met by Hitter")
    ax.tick_params(axis="y", colors=INK)
    ax.grid(axis="y", visible=False)
    for i, m in enumerate(d["_met"]):
        ax.text(m + 0.06, i, str(m), va="center", fontsize=6.5, color=INK)


def build_team_report(df, out_path, label=""):
    plt.rcParams["font.family"] = "DejaVu Sans"
    n = len(df)
    total = df[SWINGS].sum()
    sub = (f"{label}  ·  " if label else "") + f"{n} hitters"
    if total == total:
        sub += f"  ·  {int(total):,} swings"
    title = "Team Report"
    kicker = TEAM_REPORT_TITLE
    pages = 4

    def header(fig, i):
        draw_header(fig, title, sub, f"PAGE {i} OF {pages}", kicker=kicker)

    with PdfPages(out_path) as pdf:
        # ---- Page 1: team overview -----------------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        header(fig, 1)
        draw_kpi_tiles(fig, df, top=0.885, height=0.175,
                       in_target_label="of hitters\nin target")
        ax_tbl = fig.add_axes([0.05, 0.345, 0.90, 0.335])
        draw_metric_table(
            ax_tbl, df, title="Team Summary",
            headers=["Metric", "Team Avg", "Best", "Lowest", "Std Dev", "Spread",
                     "Target", "Hitters In"],
            note="Team Avg = average of each hitter's average (every hitter counts "
                 "equally).  Hitters In = share of hitters whose average is in "
                 "the target.")
        ax_bars = fig.add_axes([0.10, 0.105, 0.85, 0.165])
        draw_hitter_bars(ax_bars, df)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Page 2: full roster (landscape) -------------------------------
        fig = plt.figure(figsize=(11, 8.5))
        header(fig, 2)
        fig.text(0.04, 0.845, "Hitter-by-Hitter Averages", fontsize=12,
                 fontweight="bold", color=NAVY)
        fig.text(0.04, 0.825, "Sorted by bat speed.  Shaded cells: green = "
                 "hitter's average is inside the team target, orange = outside.",
                 fontsize=7.5, color=MUTED)
        draw_roster_table(fig, df, top=0.805, bottom=0.06)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Page 3: comparisons -------------------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        header(fig, 3)
        gs = fig.add_gridspec(2, 2, left=0.09, right=0.96, top=0.855, bottom=0.40,
                              hspace=0.32, wspace=0.30)
        team_scatter(fig.add_subplot(gs[0, 0]), df, BAT_SPEED, ATTACK,
                     "Attack Angle vs. Bat Speed", "Bat speed (mph)",
                     "Attack angle (°)")
        team_scatter(fig.add_subplot(gs[0, 1]), df, VBA, ATTACK,
                     "Attack Angle vs. Vertical Bat Angle",
                     "Vertical bat angle (°)", "Attack angle (°)")
        team_scatter(fig.add_subplot(gs[1, 0]), df, EARLY, CONN,
                     "Connection: Early vs. Impact", "Early connection (°)",
                     "Connection at impact (°)")
        draw_ope_ranked(fig.add_subplot(gs[1, 1]), df)
        ax_met = fig.add_axes([0.17, 0.065, 0.79, 0.27])
        draw_targets_met(ax_met, df)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---- Page 4: glossary ----------------------------------------------
        fig = plt.figure(figsize=(8.5, 11))
        header(fig, 4)
        draw_glossary(fig)
        draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)
    return out_path


def generate_team_report(csv_path, out_dir, players=None, label="", log=print):
    df = load_team_averages(csv_path)
    if players is None:
        players = [p for p in df["Player"] if not is_excluded(p)]
    left_out = [p for p in df["Player"] if p not in players]
    df = df[df["Player"].isin(players)].reset_index(drop=True)
    if df.empty:
        raise ValueError("No players selected for the team report.")
    os.makedirs(out_dir, exist_ok=True)
    tag = safe_name(label) if label else datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(out_dir, f"Team Hitting Report {tag}.pdf")
    build_team_report(df, out, label)
    if left_out:
        log(f"Left out: {', '.join(left_out)}")
    log(f"Saved {os.path.basename(out)}  ({len(df)} hitters)")
    return out


# ---------------------------------------------------------------------------
# Point-and-click window
# ---------------------------------------------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(f"{TEAM_NAME} – Blast Motion Reports")
    root.geometry("600x600")
    root.minsize(520, 520)

    tk.Label(root, text="Blast Motion Reports", font=("Helvetica", 16, "bold"),
             fg=NAVY).pack(anchor="w", padx=14, pady=(14, 6))
    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def make_tab(kind):
        """kind = 'individual' or 'team'"""
        frame = tk.Frame(tabs)
        tabs.add(frame, text="  Individual Reports  " if kind == "individual"
                 else "  Team Report  ")
        state = {"df": None, "csv": None}
        csv_var = tk.StringVar(value="No file chosen")
        out_var = tk.StringVar(value="")
        label_var = tk.StringVar(value="")
        file_desc = ("an 'All swings by player' CSV" if kind == "individual"
                     else "an 'Average performance' CSV")

        tk.Label(frame, text=f"1. Choose {file_desc}   2. Pick players   "
                 "3. Create", fg=MUTED).pack(anchor="w", padx=12, pady=(10, 0))
        f1 = tk.Frame(frame)
        f1.pack(fill="x", padx=12, pady=6)
        tk.Label(f1, textvariable=csv_var, anchor="w", relief="groove",
                 padx=6).pack(side="left", fill="x", expand=True)

        # Scrollable list of checkboxes, one per player
        box = tk.Frame(frame, relief="groove", bd=1)
        canvas = tk.Canvas(box, height=200, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def on_wheel(event):
            if event.num == 4:
                step = -1
            elif event.num == 5:
                step = 1
            else:
                d = event.delta
                step = -1 if d > 0 else 1
                if abs(d) >= 120:          # Windows sends multiples of 120
                    step = -int(d / 120)
            canvas.yview_scroll(step, "units")

        def bind_wheel(_):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_wheel(_):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        box.bind("<Enter>", bind_wheel)
        box.bind("<Leave>", unbind_wheel)
        state["checks"] = []               # (player name, BooleanVar)

        def set_all(value):
            for _, var in state["checks"]:
                var.set(value)
        logbox = tk.Text(frame, height=5, state="disabled", bg=PANEL, relief="flat")

        def log(msg):
            logbox.configure(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.configure(state="disabled")
            root.update_idletasks()

        def choose_csv():
            path = filedialog.askopenfilename(
                title=f"Choose {file_desc}", filetypes=[("CSV files", "*.csv")])
            if not path:
                return
            try:
                df = (load_swings(path) if kind == "individual"
                      else load_team_averages(path))
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Couldn't read file", str(e))
                return
            state["df"], state["csv"] = df, path
            csv_var.set(os.path.basename(path))
            if not out_var.get():
                out_var.set(os.path.join(os.path.dirname(path), "Hitting Reports"))
            for child in inner.winfo_children():
                child.destroy()
            state["checks"] = []
            if kind == "individual":
                names = list_players(df)
                counts = df["Player"].value_counts()
            else:
                names = df["Player"].tolist()
                counts = df.set_index("Player")[SWINGS]
            for p in names:
                n = counts.get(p)
                n_txt = "" if n is None or pd.isna(n) else f"   ({int(n):,} swings)"
                var = tk.BooleanVar(value=not is_excluded(p))
                tk.Checkbutton(inner, text=f"{p}{n_txt}", variable=var,
                               anchor="w").pack(fill="x", anchor="w", padx=4)
                state["checks"].append((p, var))
            canvas.yview_moveto(0)
            skipped = [p for p in names if is_excluded(p)]
            log(f"Loaded {len(names)} player(s)."
                + (f" Unchecked: {', '.join(skipped)}" if skipped else ""))

        tk.Button(f1, text="Choose CSV…", command=choose_csv).pack(
            side="left", padx=(8, 0))
        tip = ("Check the players to make reports for:" if kind == "individual"
               else "Check the players to include in the team averages:")
        tk.Label(frame, text=tip, anchor="w").pack(fill="x", padx=12)
        box.pack(fill="both", expand=True, padx=12)
        fsel = tk.Frame(frame)
        fsel.pack(fill="x", padx=12)
        tk.Button(fsel, text="Check all",
                  command=lambda: set_all(True)).pack(side="left", pady=(4, 0))
        tk.Button(fsel, text="Uncheck all",
                  command=lambda: set_all(False)).pack(side="left", padx=6,
                                                       pady=(4, 0))

        if kind == "team":
            fl = tk.Frame(frame)
            fl.pack(fill="x", padx=12, pady=(6, 0))
            tk.Label(fl, text="Report label (optional, e.g. Fall 2026):").pack(
                side="left")
            tk.Entry(fl, textvariable=label_var).pack(side="left", fill="x",
                                                      expand=True, padx=6)

        f2 = tk.Frame(frame)
        f2.pack(fill="x", padx=12, pady=6)
        tk.Label(f2, text="Save to:").pack(side="left")
        tk.Entry(f2, textvariable=out_var).pack(side="left", fill="x", expand=True,
                                                padx=6)

        def choose_out():
            p = filedialog.askdirectory(title="Choose output folder")
            if p:
                out_var.set(p)

        tk.Button(f2, text="Browse…", command=choose_out).pack(side="left")

        def create():
            if state["df"] is None:
                messagebox.showinfo("No file", f"Choose {file_desc} first.")
                return
            names = [p for p, var in state["checks"] if var.get()]
            if not names:
                messagebox.showinfo("No players", "Select at least one player.")
                return
            out = out_var.get().strip() or os.path.dirname(state["csv"])
            try:
                if kind == "individual":
                    files = generate_reports(state["csv"], out, names, log=log)
                else:
                    files = [generate_team_report(state["csv"], out, names,
                                                  label=label_var.get().strip(),
                                                  log=log)]
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Something went wrong", str(e))
                return
            if files and messagebox.askyesno(
                    "Done", f"Created {len(files)} report(s).\nOpen the folder?"):
                open_folder(out)

        ttk.Button(frame, text="Create Reports" if kind == "individual"
                   else "Create Team Report", command=create).pack(pady=(2, 6))
        logbox.pack(fill="x", padx=12, pady=(0, 10))

    make_tab("individual")
    make_tab("team")
    root.mainloop()


def open_folder(path):
    import subprocess
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv = sys.argv[1]
        out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
            os.path.dirname(os.path.abspath(csv)), "Hitting Reports")
        cols = pd.read_csv(csv, nrows=0, encoding="utf-8-sig").columns
        if any("Swing Timestamp" in c for c in cols):
            df_all = load_swings(csv)
            generate_reports(csv, out, [p for p in list_players(df_all)
                                        if not is_excluded(p)])
        else:
            generate_team_report(csv, out)
    else:
        run_gui()
