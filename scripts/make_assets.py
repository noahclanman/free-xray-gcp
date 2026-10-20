"""Generate the README assets (hero banner, pipeline diagram, QR codes).

Run once after changing links; the images are committed so the README never
depends on an external image service:

    pip install "qrcode[pil]"
    python scripts/make_assets.py
"""
from pathlib import Path

import qrcode
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

HERO = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="330" viewBox="0 0 1200 330" role="img" aria-label="Free Xray Configs — real-delay verified, updated every 30 minutes">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#08101d"/>
      <stop offset="0.55" stop-color="#0b1a2b"/>
      <stop offset="1" stop-color="#062430"/>
    </linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#19f5b4" stop-opacity="0.55"/>
      <stop offset="0.5" stop-color="#1d3a52" stop-opacity="0.9"/>
      <stop offset="1" stop-color="#2bb3ff" stop-opacity="0.55"/>
    </linearGradient>
    <linearGradient id="text" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#b9f4ff"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.12" cy="0.18" r="0.75">
      <stop offset="0" stop-color="#19f5b4" stop-opacity="0.20"/>
      <stop offset="1" stop-color="#19f5b4" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="1200" height="330" rx="20" fill="url(#bg)"/>
  <rect width="1200" height="330" rx="20" fill="url(#glow)"/>
  <rect x="1" y="1" width="1198" height="328" rx="19" fill="none" stroke="url(#edge)" stroke-width="2"/>

  <circle cx="120" cy="104" r="40" fill="none" stroke="#19f5b4" stroke-opacity="0.55" stroke-width="2"/>
  <ellipse cx="120" cy="104" rx="40" ry="16" fill="none" stroke="#19f5b4" stroke-opacity="0.35"/>
  <ellipse cx="120" cy="104" rx="17" ry="40" fill="none" stroke="#19f5b4" stroke-opacity="0.35"/>
  <line x1="80" y1="104" x2="160" y2="104" stroke="#19f5b4" stroke-opacity="0.25"/>

  <text x="190" y="72" font-family="Segoe UI, Arial, sans-serif" font-size="14" font-weight="700" letter-spacing="3.4" fill="#19f5b4">LIVE — REBUILT EVERY 30 MINUTES</text>
  <text x="186" y="140" font-family="Segoe UI, Arial, sans-serif" font-size="54" font-weight="800" fill="url(#text)">Free Xray Configs</text>
  <text x="190" y="180" font-family="Segoe UI, Arial, sans-serif" font-size="18" fill="#9db8cc">Not a scraped dump. Every config proxied a real HTTP request before it shipped.</text>

  <g font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="700">
    <rect x="190" y="208" width="82" height="32" rx="16" fill="#0f2b3a" stroke="#1f5a6b"/>
    <text x="231" y="229" fill="#7ee7ff" text-anchor="middle">VLESS</text>
    <rect x="284" y="208" width="86" height="32" rx="16" fill="#0f2b3a" stroke="#1f5a6b"/>
    <text x="327" y="229" fill="#7ee7ff" text-anchor="middle">VMess</text>
    <rect x="382" y="208" width="92" height="32" rx="16" fill="#0f2b3a" stroke="#1f5a6b"/>
    <text x="428" y="229" fill="#7ee7ff" text-anchor="middle">Trojan</text>
    <rect x="486" y="208" width="136" height="32" rx="16" fill="#0f2b3a" stroke="#1f5a6b"/>
    <text x="554" y="229" fill="#7ee7ff" text-anchor="middle">Shadowsocks</text>
  </g>

  <g font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#c3d6e4">
    <text x="190" y="280" fill="#6e879b">Asia first · GCP first · real measured latency · no sign-up</text>
  </g>

  <rect x="742" y="58" width="408" height="214" rx="14" fill="#081521" fill-opacity="0.86" stroke="#1d3a52"/>
  <text x="770" y="92" font-family="Segoe UI, Arial, sans-serif" font-size="12" font-weight="700" letter-spacing="2.2" fill="#7fe7c4">WHAT EVERY LINK HAS SURVIVED</text>

  <g font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#d7e6f0">
    <circle cx="782" cy="122" r="7" fill="#19f5b4" fill-opacity="0.18" stroke="#19f5b4"/>
    <path d="M778.5 122 l2.5 2.6 l4.6 -5.2" fill="none" stroke="#19f5b4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="804" y="127">Parsed, repaired, deduplicated</text>

    <circle cx="782" cy="157" r="7" fill="#19f5b4" fill-opacity="0.18" stroke="#19f5b4"/>
    <path d="M778.5 157 l2.5 2.6 l4.6 -5.2" fill="none" stroke="#19f5b4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="804" y="162">TCP handshake actually completed</text>

    <circle cx="782" cy="192" r="7" fill="#19f5b4" fill-opacity="0.18" stroke="#19f5b4"/>
    <path d="M778.5 192 l2.5 2.6 l4.6 -5.2" fill="none" stroke="#19f5b4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="804" y="197">Fetched a real URL through Xray</text>

    <circle cx="782" cy="227" r="7" fill="#19f5b4" fill-opacity="0.18" stroke="#19f5b4"/>
    <path d="M778.5 227 l2.5 2.6 l4.6 -5.2" fill="none" stroke="#19f5b4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="804" y="232">Sorted by a measured delay, not a ping</text>
  </g>

  <text x="1128" y="300" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#5d7788" text-anchor="end">github.com/noahclanman/free-xray-gcp</text>
</svg>
"""

PIPELINE = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="230" viewBox="0 0 1200 230" role="img" aria-label="Pipeline: collect, repair, dial, prove, publish">
  <defs>
    <linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2bb3ff" stop-opacity="0.5"/>
      <stop offset="1" stop-color="#19f5b4" stop-opacity="0.5"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="230" rx="16" fill="#0a1522" stroke="#1d3a52"/>

  <g font-family="Segoe UI, Arial, sans-serif">
    <g>
      <rect x="34" y="60" width="196" height="96" rx="12" fill="#0e2233" stroke="#245a73"/>
      <text x="52" y="86" font-size="12" font-weight="700" fill="#5fd0ff" letter-spacing="2">L0 · COLLECT</text>
      <text x="52" y="112" font-size="14" fill="#dceaf4">GitHub lists,</text>
      <text x="52" y="132" font-size="14" fill="#dceaf4">Telegram, base64</text>
    </g>
    <g>
      <rect x="268" y="60" width="196" height="96" rx="12" fill="#0e2233" stroke="#245a73"/>
      <text x="286" y="86" font-size="12" font-weight="700" fill="#5fd0ff" letter-spacing="2">L1 · REPAIR</text>
      <text x="286" y="112" font-size="14" fill="#dceaf4">Parse, normalise,</text>
      <text x="286" y="132" font-size="14" fill="#dceaf4">dedupe by identity</text>
    </g>
    <g>
      <rect x="502" y="60" width="196" height="96" rx="12" fill="#0e2233" stroke="#245a73"/>
      <text x="520" y="86" font-size="12" font-weight="700" fill="#5fd0ff" letter-spacing="2">L2 · DIAL</text>
      <text x="520" y="112" font-size="14" fill="#dceaf4">Resolve, GeoIP,</text>
      <text x="520" y="132" font-size="14" fill="#dceaf4">cheap TCP prefilter</text>
    </g>
    <g>
      <rect x="736" y="60" width="196" height="96" rx="12" fill="#0e2233" stroke="#2c7a63"/>
      <text x="754" y="86" font-size="12" font-weight="700" fill="#19f5b4" letter-spacing="2">L3 · PROVE</text>
      <text x="754" y="112" font-size="14" fill="#dceaf4">Start Xray, fetch</text>
      <text x="754" y="132" font-size="14" fill="#dceaf4">generate_204 → ms</text>
    </g>
    <g>
      <rect x="970" y="60" width="196" height="96" rx="12" fill="#122a24" stroke="#19f5b4"/>
      <text x="988" y="86" font-size="12" font-weight="700" fill="#19f5b4" letter-spacing="2">PUBLISH</text>
      <text x="988" y="112" font-size="14" fill="#dceaf4">Asia → GCP → ms,</text>
      <text x="988" y="132" font-size="14" fill="#dceaf4">countries + TLS</text>
    </g>

    <g stroke="#2bb3ff" stroke-width="2" fill="none" stroke-linecap="round">
      <line x1="232" y1="108" x2="258" y2="108"/><path d="M252 102 l8 6 l-8 6"/>
      <line x1="466" y1="108" x2="492" y2="108"/><path d="M486 102 l8 6 l-8 6"/>
      <line x1="700" y1="108" x2="726" y2="108"/><path d="M720 102 l8 6 l-8 6"/>
      <line x1="934" y1="108" x2="960" y2="108"/><path d="M954 102 l8 6 l-8 6"/>
    </g>

    <rect x="34" y="182" width="1132" height="10" rx="5" fill="url(#bar)"/>
    <text x="34" y="214" font-size="12" fill="#6e879b">Everything the upstreams published</text>
    <text x="1166" y="214" font-size="12" fill="#19f5b4" text-anchor="end">What actually survives</text>
  </g>
</svg>
"""


def write_svg(name: str, content: str) -> None:
    (ASSETS / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"  {name}")


def write_qr(name: str, data: str) -> None:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0b1220", back_color="white")
    img.save(ASSETS / f"{name}.png")
    print(f"  {name}.png")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    print("svg:")
    write_svg("hero.svg", HERO)
    write_svg("pipeline.svg", PIPELINE)
    print("qr:")
    for name, data in QR_CODES.items():
        write_qr(name, data)


if __name__ == "__main__":
    main()
