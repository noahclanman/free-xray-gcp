"""Generate the README assets (hero banner, pipeline diagram, social card, QR codes).

Everything is rendered at 4x and downscaled to 2x, so the PNGs stay sharp on
retina displays and on GitHub's image proxy (which never serves a blurry SVG
font fallback).

    pip install "qrcode[pil]"
    python scripts/make_assets.py
"""
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from qrcode.constants import ERROR_CORRECT_M

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
REPO = "noahclanman/free-xray-gcp"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/output"
TELEGRAM = "https://t.me/xray_ehi_hub"
DONATE = "https://donate.opencfg.xyz/"
TRC20 = "TFwFqETTpgMr799EpDFSRYJZ3ZW2FH2Pve"
EVM = "0x13cec186826d5cae07960a1e5947dc06cba12672"
TON = "UQA01GcpQ2wzqIBCJgY5thTFEBWq8g2R-3zlH8okGpIsfXnP"

QR_CODES = {
    "qr_top100": f"{RAW}/top100.txt",
    "qr_all": f"{RAW}/all/configs_base64.txt",
    "qr_fast": f"{RAW}/fast/configs_base64.txt",
    "qr_telegram": TELEGRAM,
    "qr_donate": DONATE,
    "qr_trc20": TRC20,
    "qr_evm": EVM,
    "qr_ton": TON,
}

# palette
BG_A = (7, 12, 21)
BG_B = (8, 19, 27)
WHITE = (255, 255, 255)
MUTED = (158, 182, 201)
DIM = (108, 134, 153)
ACCENT = (25, 240, 178)
BLUE = (52, 176, 255)
PANEL = (8, 21, 33)
PANEL_EDGE = (30, 60, 84)

S = 4  # supersampling factor (4x render -> 2x output)


def font(size: float, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """Segoe UI when available, with graceful fallbacks for other systems."""
    candidates = {
        "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
        "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
        "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    }[weight]
    roots = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]
    for name in candidates:
        for root in roots:
            candidate = root / name
            if candidate.exists():
                return ImageFont.truetype(str(candidate), int(size))
    try:
        return ImageFont.truetype(candidates[0], int(size))
    except OSError:
        return ImageFont.load_default(size=int(size))


def gradient(w: int, h: int, a, b) -> Image.Image:
    small = Image.new("RGB", (128, 128))
    px = small.load()
    for y in range(128):
        for x in range(128):
            t = (x + y) / 254
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return small.resize((w, h), Image.BICUBIC)


def add_glow(base: Image.Image, center, radius: float, opacity: float = 0.22) -> Image.Image:
    w, h = base.size
    low = (max(1, w // 8), max(1, h // 8))
    mask = Image.new("L", low, 0)
    cx, cy = center[0] / 8, center[1] / 8
    r = radius / 8
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r * 1.6, cy + r * 1.2], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(r / 2.2)).resize((w, h), Image.BICUBIC)
    layer = Image.new("RGBA", (w, h), ACCENT + (0,))
    layer.putalpha(mask.point(lambda v: int(v * opacity)))
    return Image.alpha_composite(base.convert("RGBA"), layer)


def tracked(draw, xy, text, f, fill, tracking):
    """Draw text with letter-spacing (PIL has none built in)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=f) + tracking


def chip(draw, x, y, label, f, S: int) -> float:
    pad = 17 * S
    height = 30 * S
    width = draw.textlength(label, font=f) + pad * 2
    box = [x, y, x + width, y + height]
    draw.rounded_rectangle(box, radius=height / 2, fill=(13, 40, 54), outline=(33, 92, 110),
                           width=max(1, int(1.2 * S)))
    draw.text((x + width / 2, y + height / 2 + 1), label, font=f, fill=(126, 231, 255), anchor="mm")
    return x + width


def check(draw, cx, cy, r, S: int):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 58, 48), outline=ACCENT,
                 width=max(1, int(1.5 * S)))
    draw.line(
        [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.10, cy + r * 0.36), (cx + r * 0.48, cy - r * 0.36)],
        fill=ACCENT, width=max(1, int(1.8 * S)), joint="curve")


def build_hero() -> Image.Image:
    W, H = 1200, 320
    w, h = W * S, H * S

    def P(v):
        return int(round(v * S))

    base = gradient(w, h, BG_A, BG_B)
    base = add_glow(base, (P(0), P(0)), P(330), 0.09)

    # subtle grid
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(P(40), w, P(48)):
        gd.line([(x, 0), (x, h)], fill=(255, 255, 255, 6), width=1)
    for y in range(P(40), h, P(48)):
        gd.line([(0, y), (w, y)], fill=(255, 255, 255, 6), width=1)
    base = Image.alpha_composite(base, grid)

    # right panel (translucent)
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([P(756), P(50), P(1150), P(268)], radius=P(16),
                         fill=PANEL + (228,), outline=PANEL_EDGE + (255,), width=max(1, P(1.2)))
    base = Image.alpha_composite(base, panel)
    d = ImageDraw.Draw(base)

    # globe
    cx, cy, r = P(126), P(112), P(42)
    stroke = max(2, P(1.8))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(25, 240, 178, 190), width=stroke)
    d.ellipse([cx - r, cy - int(r * 0.36), cx + r, cy + int(r * 0.36)],
              outline=(25, 240, 178, 110), width=max(1, P(1)))
    d.ellipse([cx - int(r * 0.36), cy - r, cx + int(r * 0.36), cy + r],
              outline=(25, 240, 178, 110), width=max(1, P(1)))
    d.line([(cx - r, cy), (cx + r, cy)], fill=(25, 240, 178, 80), width=max(1, P(1)))

    # eyebrow / title / subtitle
    f_eye = font(P(12.5), "bold")
    tracked(d, (P(200), P(72)), "LIVE  —  REBUILT EVERY 30 MINUTES", f_eye, ACCENT, P(3.1))

    f_title = font(P(55), "bold")
    d.text((P(196), P(158)), "Free Xray Configs", font=f_title, fill=WHITE, anchor="ls")

    f_sub = font(P(17), "regular")
    d.text((P(200), P(196)),
           "Every config proxied a real HTTP request before it shipped.",
           font=f_sub, fill=MUTED, anchor="ls")

    # protocol chips
    f_chip = font(P(13), "bold")
    x = P(200)
    for label in ("VLESS", "VMess", "Trojan", "Shadowsocks"):
        x = chip(d, x, P(214), label, f_chip, S) + P(11)

    f_foot = font(P(11.5), "regular")
    d.text((P(200), P(288)), "Asia first  ·  GCP first  ·  measured latency  ·  no sign-up",
           font=f_foot, fill=DIM, anchor="ls")
    d.text((P(1150), P(300)), f"github.com/{REPO}", font=font(P(10.5)), fill=(88, 112, 130),
           anchor="rs")

    # panel checklist
    f_pt = font(P(10), "bold")
    tracked(d, (P(786), P(86)), "WHAT EVERY LINK HAS SURVIVED", f_pt, (127, 231, 196), P(1.9))
    f_row = font(P(13), "regular")
    rows = [
        "Parsed, repaired, deduplicated",
        "TCP handshake actually completed",
        "Fetched a real URL through Xray",
        "Sorted by a measured delay, not a ping",
    ]
    for i, row in enumerate(rows):
        ry = P(124 + i * 36)
        check(d, P(796), ry - P(1), P(7.5), S)
        d.text((P(818), ry), row, font=f_row, fill=(216, 231, 241), anchor="lm")

    # rounded mask + downscale to 2x
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=P(18), fill=255)
    base.putalpha(mask)
    return base.resize((W * 2, H * 2), Image.LANCZOS)


def build_pipeline() -> Image.Image:
    W, H = 1200, 220
    w, h = W * S, H * S

    def P(v):
        return int(round(v * S))

    base = gradient(w, h, BG_A, BG_B)
    base = add_glow(base, (P(1120), P(20)), P(420), 0.10)
    d = ImageDraw.Draw(base)

    cards = [
        ("L0 · COLLECT", ["GitHub lists,", "Telegram, base64"], (52, 176, 255), (14, 34, 51), (36, 90, 115)),
        ("L1 · REPAIR", ["Parse, normalise,", "dedupe by identity"], (52, 176, 255), (14, 34, 51), (36, 90, 115)),
        ("L2 · DIAL", ["Resolve, GeoIP,", "cheap TCP prefilter"], (52, 176, 255), (14, 34, 51), (36, 90, 115)),
        ("L3 · PROVE", ["Start Xray, fetch", "generate_204 → ms"], (25, 240, 178), (13, 40, 40), (38, 110, 92)),
        ("PUBLISH", ["Asia → GCP → ms,", "countries + TLS"], (25, 240, 178), (16, 45, 37), ACCENT),
    ]

    x0, gap, cw, top, ch = 24, 24, 212, 34, 96
    f_head = font(P(10.5), "bold")
    f_body = font(P(13), "regular")

    for i, (title, lines, accent, fill, edge) in enumerate(cards):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([P(x), P(top), P(x + cw), P(top + ch)], radius=P(11),
                            fill=fill, outline=edge, width=max(1, P(1.3)))
        tracked(d, (P(x + 16), P(top + 26)), title, f_head, accent, P(1.6))
        for j, line in enumerate(lines):
            d.text((P(x + 16), P(top + 50 + j * 20)), line, font=f_body, fill=(219, 233, 243), anchor="ls")

    # arrows
    for i in range(len(cards) - 1):
        x = x0 + i * (cw + gap) + cw
        y = top + ch // 2
        d.line([(P(x + 5), P(y)), (P(x + gap - 7), P(y))], fill=BLUE, width=max(2, P(1.6)))
        d.polygon([(P(x + gap - 7), P(y - 4)), (P(x + gap - 1), P(y)), (P(x + gap - 7), P(y + 4))], fill=BLUE)

    # survival bar
    bar_y, bar_h = 158, 7
    for i in range(P(24), P(1176)):
        t = (i - P(24)) / (P(1176) - P(24))
        color = tuple(int(BLUE[k] + (ACCENT[k] - BLUE[k]) * t) for k in range(3)) + (210,)
        d.line([(i, P(bar_y)), (i, P(bar_y + bar_h))], fill=color)

    f_cap = font(P(11.5), "regular")
    d.text((P(24), P(196)), "Everything the upstreams published", font=f_cap, fill=DIM, anchor="ls")
    d.text((P(1176), P(196)), "What actually survives", font=font(P(11.5), "semibold"), fill=ACCENT, anchor="rs")

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=P(14), fill=255)
    base.putalpha(mask)
    return base.resize((W * 2, H * 2), Image.LANCZOS)


def build_social() -> Image.Image:
    W, H = 1280, 640
    w, h = W * S, H * S

    def P(v):
        return int(round(v * S))

    base = gradient(w, h, BG_A, BG_B)
    base = add_glow(base, (P(640), P(-40)), P(620), 0.09)
    d = ImageDraw.Draw(base)

    # globe mark
    cx, cy, r = P(640), P(96), P(34)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT + (200,), width=max(2, P(2)))
    d.ellipse([cx - r, cy - int(r * 0.36), cx + r, cy + int(r * 0.36)],
              outline=ACCENT + (110,), width=max(1, P(1)))
    d.ellipse([cx - int(r * 0.36), cy - r, cx + int(r * 0.36), cy + r],
              outline=ACCENT + (110,), width=max(1, P(1)))

    f_eye = font(P(14), "bold")
    text = "LIVE  —  REBUILT EVERY 30 MINUTES"
    width = sum(d.textlength(c, font=f_eye) + P(3.4) for c in text) - P(3.4)
    tracked(d, (P(640) - width / 2, P(170)), text, f_eye, ACCENT, P(3.4))

    f_title = font(P(76), "bold")
    d.text((P(640), P(300)), "Free Xray Configs", font=f_title, fill=WHITE, anchor="ms")

    f_sub = font(P(23), "regular")
    d.text((P(640), P(348)), "Real-delay verified  ·  GCP-first  ·  Asia-first",
           font=f_sub, fill=MUTED, anchor="ms")

    f_chip = font(P(15), "bold")
    labels = ("VLESS", "VMess", "Trojan", "Shadowsocks")
    widths = [d.textlength(l, font=f_chip) + P(34) for l in labels]
    total = sum(widths) + P(12) * (len(labels) - 1)
    x = P(640) - total / 2
    for label, cw in zip(labels, widths):
        height = P(34)
        d.rounded_rectangle([x, P(392), x + cw, P(392) + height], radius=height / 2,
                            fill=(13, 40, 54), outline=(33, 92, 110), width=max(1, P(1.3)))
        d.text((x + cw / 2, P(392) + height / 2 + 1), label, font=f_chip,
               fill=(126, 231, 255), anchor="mm")
        x += cw + P(12)

    f_url = font(P(21), "semibold")
    d.text((P(640), P(500)), "t.me/xray_ehi_hub", font=f_url, fill=ACCENT, anchor="ms")
    d.text((P(640), P(536)), f"github.com/{REPO}", font=font(P(15)), fill=DIM, anchor="ms")

    return base.resize((W, H), Image.LANCZOS)


def write_qr(name: str, data: str) -> None:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=14, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1220", back_color="white")
    img.save(ASSETS / f"{name}.png")
    print(f"  {name}.png")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    for name, builder in (("hero", build_hero), ("pipeline", build_pipeline), ("social-preview", build_social)):
        img = builder()
        img.save(ASSETS / f"{name}.png", optimize=True)
        print(f"  {name}.png  {img.size[0]}x{img.size[1]}")

    for name, data in QR_CODES.items():
        write_qr(name, data)

    for stale in ("hero.svg", "pipeline.svg"):
        p = ASSETS / stale
        if p.exists():
            p.unlink()
            print(f"  removed {stale}")


if __name__ == "__main__":
    main()
