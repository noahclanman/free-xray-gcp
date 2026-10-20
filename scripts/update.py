#!/usr/bin/env python3
"""
GCP-first, really-working proxy aggregator.

fetch sources -> keep proxy links -> resolve host -> TCP prefilter
-> start xray per config and fetch a real 204 URL through it
-> sort GCP first / Asia first -> write a category tree into output/

Layout (mirrors the 0xRadikal/Free-v2ray-Configs conventions):

    output/all/configs.txt            all verified configs
    output/gcp/configs.txt            every working GCP-hosted config
    output/fast/configs.txt           low-latency subset
    output/top100.txt                 fastest 100 overall
    output/protocols/*.txt            vmess / vless / trojan / shadowsocks
    output/transports/*.txt           tls / reality / ws_tls / grpc_tls / ...
    output/Countries/*.txt            one file per country (+ index.json)
    output/regions/*.txt              Asia / Europe / ...
    output/index.json                 machine-readable catalogue
    output/health.json                last run health

Every list also ships a *_base64.txt subscription twin (except Countries and
regions, which are browse-only).
"""
import base64
import gzip
import html
import ipaddress
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from array import array
from bisect import bisect_right
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
BUILD = ROOT / ".output_build"

# ---- settings (override with env vars in the workflow if you like) ----------
PROTOCOLS = tuple(p.strip().lower() for p in os.getenv(
    "PROTOCOLS", "vmess,vless,trojan,ss").split(",") if p.strip())
GCP_RANGES_URL = os.getenv("GCP_RANGES", "https://www.gstatic.com/ipranges/cloud.json")
GEOIP_URL = os.getenv(
    "GEOIP_URL", "https://download.db-ip.com/free/dbip-country-lite-%Y-%m.csv.gz")
XRAY_BIN = os.getenv("XRAY_BIN", "xray")
REPO = os.getenv("REPO", "")            # "owner/repo", used in headers + index.json
BRAND = os.getenv("BRAND", "")          # optional label, e.g. "@noahclanman"
SUPPORT_URL = os.getenv("SUPPORT_URL", "")  # optional, shown in the list headers
MAX_OUTPUT = int(os.getenv("MAX_OUTPUT", "1000"))
TOP_N = int(os.getenv("TOP_N", "100"))
FAST_MS = float(os.getenv("FAST_MS", "400"))
RESOLVE_WORKERS = int(os.getenv("RESOLVE_WORKERS", "200"))
TEST_WORKERS = int(os.getenv("TEST_WORKERS", "16"))  # parallel xray instances
MAX_TEST_MINUTES = float(os.getenv("MAX_TEST_MINUTES", "20"))
TCP_TIMEOUT = float(os.getenv("TCP_TIMEOUT", "1.5"))  # cheap prefilter only
TCP_PREFILTER = os.getenv("TCP_PREFILTER", "1") != "0"
GCP_ONLY = os.getenv("GCP_ONLY", "0") == "1"          # 1 = strict GCP, no fill
TEST_TIMEOUT = float(os.getenv("TEST_TIMEOUT", "7"))
TEST_URLS = [u.strip() for u in os.getenv(
    "TEST_URLS",
    "https://www.gstatic.com/generate_204,https://cp.cloudflare.com/generate_204",
).split(",") if u.strip()]
UA = {"User-Agent": "gcp-v2ray-aggregator/3.0"}

SCHEMES = "|".join(map(re.escape, PROTOCOLS))
LINK_RE = re.compile(r"^(%s)://" % SCHEMES, re.I)
SCAN_RE = re.compile(r"(?:%s)://[^\s\"'<>`\\]+" % SCHEMES, re.I)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- countries --
# ISO-3166 alpha-2 -> English name. Anything missing falls back to the code.
COUNTRY_NAMES = {
    "AE": "United Arab Emirates", "AF": "Afghanistan", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BD": "Bangladesh", "BE": "Belgium", "BG": "Bulgaria", "BH": "Bahrain",
    "BJ": "Benin", "BO": "Bolivia", "BR": "Brazil", "BY": "Belarus",
    "CA": "Canada", "CH": "Switzerland", "CI": "Côte d'Ivoire", "CL": "Chile",
    "CM": "Cameroon", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "DO": "Dominican Republic", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "ES": "Spain",
    "ET": "Ethiopia", "FI": "Finland", "FR": "France", "GB": "United Kingdom",
    "GE": "Georgia", "GH": "Ghana", "GR": "Greece", "GT": "Guatemala",
    "HK": "Hong Kong", "HN": "Honduras", "HR": "Croatia", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India",
    "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan", "KH": "Cambodia", "KR": "South Korea", "KW": "Kuwait",
    "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon", "LK": "Sri Lanka",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya",
    "MA": "Morocco", "MD": "Moldova", "ME": "Montenegro", "MK": "North Macedonia",
    "MM": "Myanmar", "MN": "Mongolia", "MO": "Macau", "MT": "Malta",
    "MU": "Mauritius", "MV": "Maldives", "MX": "Mexico", "MY": "Malaysia",
    "NG": "Nigeria", "NL": "The Netherlands", "NO": "Norway", "NP": "Nepal",
    "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PH": "Philippines", "PK": "Pakistan", "PL": "Poland", "PR": "Puerto Rico",
    "PS": "Palestine", "PT": "Portugal", "PY": "Paraguay", "QA": "Qatar",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia",
    "SD": "Sudan", "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia",
    "SK": "Slovakia", "SN": "Senegal", "SO": "Somalia", "SY": "Syria",
    "TH": "Thailand", "TJ": "Tajikistan", "TM": "Turkmenistan",
    "TN": "Tunisia", "TR": "Turkey", "TW": "Taiwan", "TZ": "Tanzania",
    "UA": "Ukraine", "UG": "Uganda", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VE": "Venezuela", "VN": "Vietnam", "ZA": "South Africa",
    "ZM": "Zambia", "ZW": "Zimbabwe", "SC": "Seychelles", "ZZ": "Unknown",
}

ASIA = {
    "AE", "AF", "AM", "AZ", "BD", "BH", "BN", "BT", "CN", "CY", "GE", "HK",
    "ID", "IL", "IN", "IQ", "IR", "JO", "JP", "KG", "KH", "KP", "KR", "KW",
    "KZ", "LA", "LB", "LK", "MM", "MN", "MO", "MV", "MY", "NP", "OM", "PH",
    "PK", "PS", "QA", "SA", "SG", "SY", "TH", "TJ", "TL", "TM", "TR", "TW",
    "UZ", "VN", "YE",
}
EUROPE = {
    "AD", "AL", "AT", "BA", "BE", "BG", "BY", "CH", "CZ", "DE", "DK", "EE",
    "ES", "FI", "FO", "FR", "GB", "GG", "GI", "GR", "HR", "HU", "IE", "IM",
    "IS", "IT", "JE", "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT",
    "NL", "NO", "PL", "PT", "RO", "RS", "RU", "SE", "SI", "SK", "SM", "UA",
    "VA", "XK",
}
NORTH_AMERICA = {
    "AG", "AI", "AW", "BB", "BL", "BM", "BQ", "BS", "BZ", "CA", "CR", "CU",
    "CW", "DM", "DO", "GD", "GL", "GP", "GT", "HN", "HT", "JM", "KN", "KY",
    "LC", "MF", "MQ", "MS", "MX", "NI", "PA", "PM", "PR", "SV", "SX", "TC",
    "TT", "US", "VC", "VG", "VI",
}
SOUTH_AMERICA = {
    "AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PE", "PY", "SR",
    "UY", "VE",
}
AFRICA = {
    "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ",
    "DZ", "EG", "EH", "ER", "ET", "GA", "GH", "GM", "GN", "GQ", "GW", "KE",
    "KM", "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU", "MW", "MZ", "NA",
    "NE", "NG", "RE", "RW", "SC", "SD", "SH", "SL", "SN", "SO", "SS", "ST",
    "SZ", "TD", "TG", "TN", "TZ", "UG", "YT", "ZA", "ZM", "ZW",
}
OCEANIA = {
    "AS", "AU", "CC", "CK", "CX", "FJ", "FM", "GU", "KI", "MH", "MP", "NC",
    "NF", "NR", "NU", "NZ", "PF", "PG", "PN", "PW", "SB", "TK", "TO", "TV",
    "UM", "VU", "WF", "WS",
}


def country_name(cc):
    return COUNTRY_NAMES.get(cc, cc)


def continent(cc):
    if cc in ASIA:
        return "Asia"
    if cc in EUROPE:
        return "Europe"
    if cc in NORTH_AMERICA:
        return "North America"
    if cc in SOUTH_AMERICA:
        return "South America"
    if cc in AFRICA:
        return "Africa"
    if cc in OCEANIA:
        return "Oceania"
    return "Other"


def flag(cc):
    if len(cc) != 2 or not cc.isalpha() or cc == "ZZ":
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc.upper())


class GeoIP:
    """Compact reader for the DB-IP Country Lite CSV (IPv4 ranges)."""

    def __init__(self, starts, ends, codes):
        self.starts, self.ends, self.codes = starts, ends, codes

    def country(self, ip):
        try:
            addr = int(ipaddress.IPv4Address(ip))
        except (ValueError, ipaddress.AddressValueError):
            return "ZZ"
        i = bisect_right(self.starts, addr) - 1
        if i >= 0 and addr <= self.ends[i]:
            return self.codes[i * 2:i * 2 + 2].decode("ascii", "ignore") or "ZZ"
        return "ZZ"


def load_geoip():
    """Download the DB-IP Country Lite CSV, walking back a few months if needed."""
    now = datetime.now(timezone.utc)
    last = None
    for back in range(3):
        url = (now - timedelta(days=31 * back)).strftime(GEOIP_URL)
        try:
            raw = http_get_bytes(url, timeout=180)
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        if url.endswith(".gz"):
            raw = gzip.decompress(raw)
        starts, ends, codes = array("I"), array("I"), bytearray()
        for line in raw.decode("utf-8", "ignore").splitlines():
            parts = line.split(",")
            if len(parts) != 3 or ":" in parts[0]:
                continue  # IPv6 ranges are skipped; configs almost always use IPv4
            try:
                a = int(ipaddress.IPv4Address(parts[0]))
                b = int(ipaddress.IPv4Address(parts[1]))
            except ValueError:
                continue
            starts.append(a)
            ends.append(b)
            codes += parts[2].strip().encode()[:2].ljust(2, b"Z")
        if not starts:
            last = RuntimeError("empty geoip database")
            continue
        log(f"geoip: {len(starts)} IPv4 ranges ({url.rsplit('/', 1)[-1]})")
        return GeoIP(starts, ends, codes)
    raise RuntimeError(f"geoip download failed: {last}")


# ---------------------------------------------------------------- fetching ---
def http_get_bytes(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_get(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return Path(url).read_text(encoding="utf-8", errors="ignore")
    last = None
    for _ in range(3):
        try:
            return http_get_bytes(url, timeout=30).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise RuntimeError(f"{url}: {last}")


def b64decode(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode(errors="ignore")


def clean_link(link):
    return link.strip().rstrip(").,;:'\"<>]}")


def scan_links(text):
    """Find proxy links anywhere in the payload (plain lists, HTML, Telegram)."""
    text = html.unescape(text)
    return [clean_link(m.group(0)) for m in SCAN_RE.finditer(text)]


def extract_links(text: str):
    text = text.lstrip("\ufeff")
    found = scan_links(text)
    if found:
        return found
    # No plain link found: maybe the whole payload is a base64 subscription.
    try:
        decoded = b64decode(text)
    except Exception:  # noqa: BLE001
        return []
    return scan_links(decoded)


def expand_source(src: str) -> str:
    now = datetime.now(timezone.utc)
    return (src.replace("{Y}", now.strftime("%Y"))
               .replace("{M}", now.strftime("%m"))
               .replace("{D}", now.strftime("%d"))
               .replace("{YMD}", now.strftime("%Y%m%d")))


def load_sources():
    lines = (ROOT / "sources.txt").read_text(encoding="utf-8").splitlines()
    return [expand_source(l.strip()) for l in lines
            if l.strip() and not l.strip().startswith("#")]


# ---------------------------------------------------------------- GCP ranges --
def load_gcp_ranges():
    data = json.loads(http_get(GCP_RANGES_URL))
    nets = []  # (network, region)
    for p in data["prefixes"]:
        cidr = p.get("ipv4Prefix") or p.get("ipv6Prefix")
        if cidr:
            nets.append((ipaddress.ip_network(cidr), p.get("scope", "global")))
    v4 = sorted((n for n in nets if n[0].version == 4), key=lambda x: int(x[0].network_address))
    v6 = [n for n in nets if n[0].version == 6]
    log(f"GCP ranges loaded: {len(v4)} IPv4 + {len(v6)} IPv6 prefixes")
    return v4, v6


def gcp_region(ip_str, v4, v6):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    pool = v4 if ip.version == 4 else v6
    best = None
    for net, region in pool:  # linear scan is fine for ~1-2k prefixes
        if ip in net and (best is None or net.prefixlen > best[0].prefixlen):
            best = (net, region)
    return best[1] if best else None


def resolve_host(host):
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)[0][4][0]
    except OSError:
        return None


# ----------------------------------------------------------------- parsing ---
def _first(d, key, default=None):
    v = d.get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None or str(v).strip() == "":
        return default
    return v


def norm_net(net):
    net = (net or "tcp").lower()
    return {"gun": "grpc", "h2": "http", "splithttp": "xhttp", "raw": "tcp"}.get(net, net)


def ss_parts(link):
    """Return (method, password, host, port) for a SIP002 or legacy ss:// link."""
    body = link[5:].split("#", 1)[0].split("?", 1)[0]
    if "@" in body:
        userinfo, hostpart = body.rsplit("@", 1)
        userinfo = unquote(userinfo)
        if ":" not in userinfo:
            userinfo = b64decode(userinfo)
    else:  # legacy: everything is base64
        userinfo, hostpart = b64decode(body).rsplit("@", 1)
    method, password = userinfo.split(":", 1)
    # Some exporters append a remark to the port without a "#", so take the
    # leading digits instead of trusting the whole tail to be numeric.
    m = re.match(r"^(\[[0-9a-fA-F:]+\]|[^:]+):(\d+)", hostpart)
    if not m:
        raise ValueError("no host/port")
    return method, password, m.group(1).strip("[]"), int(m.group(2))


def link_endpoint(link):
    """Return (host, port) or (None, None)."""
    low = link.lower()
    try:
        if low.startswith("vmess://"):
            j = json.loads(b64decode(link[8:]))
            return str(j["add"]).strip(), int(j["port"])
        if low.startswith("ss://"):
            _, _, host, port = ss_parts(link)
            return host, port
        u = urlparse(link)
        return u.hostname, u.port
    except Exception:  # noqa: BLE001
        return None, None


def build_stream(net="tcp", security="none", host=None, path=None, sni=None,
                 fp=None, alpn=None, pbk=None, sid=None, header_type=None,
                 service_name=None):
    """Translate URL/JSON transport fields into an xray streamSettings block."""
    net = norm_net(net)
    sec = (security or "none").lower()
    st = {"network": net, "security": sec if sec in ("tls", "reality") else "none"}
    name = sni or host
    if sec == "tls":
        tls = {}
        if name:
            tls["serverName"] = name
        if fp:
            tls["fingerprint"] = fp
        if alpn:
            tls["alpn"] = [a.strip() for a in alpn.split(",") if a.strip()]
        st["tlsSettings"] = tls
    elif sec == "reality":
        reality = {"serverName": name or "", "fingerprint": fp or "chrome", "spiderX": "/"}
        if pbk:
            reality["publicKey"] = pbk
        if sid is not None:
            reality["shortId"] = sid
        st["realitySettings"] = reality

    if net == "ws":
        ws = {"path": path or "/"}
        if host:
            ws["headers"] = {"Host": host}
        st["wsSettings"] = ws
    elif net == "grpc":
        st["grpcSettings"] = {"serviceName": service_name or path or ""}
    elif net == "http":
        hs = {"path": path or "/"}
        if host:
            hs["host"] = [h.strip() for h in host.split(",") if h.strip()]
        st["httpSettings"] = hs
    elif net == "xhttp":
        st["xhttpSettings"] = {"path": path or "/", "host": host or ""}
    elif net == "httpupgrade":
        st["httpupgradeSettings"] = {"path": path or "/", "host": host or ""}
    elif net == "tcp" and header_type and header_type.lower() != "none":
        header = {"type": header_type}
        if header_type.lower() == "http":
            header["request"] = {"path": [path or "/"], "headers": {"Host": [host] if host else []}}
        st["tcpSettings"] = {"header": header}
    return st


def vmess_outbound(j):
    add = str(j.get("add", "")).strip()
    port = int(j.get("port") or 0)
    if not add or not port:
        return None
    tls = str(j.get("tls", "")).lower()
    sec = "reality" if tls == "reality" else ("tls" if tls in ("tls", "xtls") else "none")
    net = str(j.get("net") or "tcp")
    host = _first(j, "host")
    path = _first(j, "path")
    st = build_stream(
        net=net, security=sec, host=host, path=path,
        sni=_first(j, "sni") or host or add, fp=_first(j, "fp"),
        alpn=_first(j, "alpn"), pbk=_first(j, "pbk"), sid=_first(j, "sid"),
        header_type=_first(j, "type"),
        service_name=_first(j, "serviceName") or (path if norm_net(net) == "grpc" else None),
    )
    user = {
        "id": j.get("id"),
        "alterId": int(j.get("aid") or 0),
        "security": _first(j, "scy", "auto"),
    }
    return {
        "protocol": "vmess",
        "settings": {"vnext": [{"address": add, "port": port, "users": [user]}]},
        "streamSettings": st,
    }


def vless_outbound(link):
    u = urlparse(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if not u.hostname or not u.port:
        return None
    user = {"id": unquote(u.username or ""), "encryption": q.get("encryption") or "none"}
    if q.get("flow"):
        user["flow"] = q["flow"]
    net = q.get("type") or "tcp"
    st = build_stream(
        net=net, security=q.get("security") or "none",
        host=q.get("host"), path=q.get("path"),
        sni=q.get("sni") or q.get("host"), fp=q.get("fp"),
        alpn=q.get("alpn"), pbk=q.get("pbk"), sid=q.get("sid"),
        header_type=q.get("headerType"),
        service_name=q.get("serviceName") or (q.get("path") if norm_net(net) == "grpc" else None),
    )
    return {
        "protocol": "vless",
        "settings": {"vnext": [{"address": u.hostname, "port": u.port, "users": [user]}]},
        "streamSettings": st,
    }


def trojan_outbound(link):
    u = urlparse(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if not u.hostname:
        return None
    net = q.get("type") or "tcp"
    st = build_stream(
        net=net, security=q.get("security") or "tls",
        host=q.get("host"), path=q.get("path"),
        sni=q.get("sni") or q.get("host"), fp=q.get("fp"),
        alpn=q.get("alpn"), pbk=q.get("pbk"), sid=q.get("sid"),
        header_type=q.get("headerType"),
        service_name=q.get("serviceName") or (q.get("path") if norm_net(net) == "grpc" else None),
    )
    return {
        "protocol": "trojan",
        "settings": {"servers": [{
            "address": u.hostname, "port": u.port or 443,
            "password": unquote(u.username or ""),
        }]},
        "streamSettings": st,
    }


def ss_outbound(link):
    method, password, host, port = ss_parts(link)
    return {
        "protocol": "shadowsocks",
        "settings": {"servers": [{
            "address": host, "port": int(port),
            "method": method, "password": password,
        }]},
    }


def outbound(link):
    low = link.lower()
    try:
        if low.startswith("vmess://"):
            return vmess_outbound(json.loads(b64decode(link[8:])))
        if low.startswith("vless://"):
            return vless_outbound(link)
        if low.startswith("trojan://"):
            return trojan_outbound(link)
        if low.startswith("ss://"):
            return ss_outbound(link)
    except Exception:  # noqa: BLE001
        return None
    return None


def props(link):
    """Return (protocol, transport, security) without starting xray."""
    low = link.lower()
    try:
        if low.startswith("vmess://"):
            j = json.loads(b64decode(link[8:]))
            tls = str(j.get("tls") or "").lower()
            sec = "reality" if tls == "reality" else ("tls" if tls in ("tls", "xtls") else "none")
            return "vmess", norm_net(str(j.get("net") or "tcp")), sec
        if low.startswith("vless://"):
            q = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}
            sec = (q.get("security") or "none").lower()
            return "vless", norm_net(q.get("type") or "tcp"), sec if sec in ("tls", "reality") else "none"
        if low.startswith("trojan://"):
            q = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}
            sec = (q.get("security") or "tls").lower()
            return "trojan", norm_net(q.get("type") or "tcp"), sec if sec in ("tls", "reality") else "none"
        if low.startswith("ss://"):
            return "shadowsocks", "tcp", "none"
    except Exception:  # noqa: BLE001
        pass
    return low.split("://")[0], "tcp", "none"


def rename(link, new_name):
    """Set the display name (remark) of a link."""
    if link.lower().startswith("vmess://"):
        j = json.loads(b64decode(link[8:]))
        j["ps"] = new_name
        raw = json.dumps(j, separators=(",", ":"), ensure_ascii=False)
        return "vmess://" + base64.b64encode(raw.encode()).decode()
    u = urlparse(link)
    return urlunparse(u._replace(fragment=quote(new_name, safe="")))


def identity(link):
    """Dedup key: same server + credentials = same config, whatever the remark."""
    if link.lower().startswith("vmess://"):
        j = json.loads(b64decode(link[8:]))
        j.pop("ps", None)
        return "vmess:" + json.dumps(j, sort_keys=True)
    u = urlparse(link)
    return urlunparse(u._replace(fragment=""))


# ------------------------------------------------------------ real testing ---
def tcp_ok(ip, port):
    try:
        socket.create_connection((ip, port), timeout=TCP_TIMEOUT).close()
        return True
    except OSError:
        return False


_port_lock = threading.Lock()
_next_port = [21000]


def alloc_port():
    with _port_lock:
        p = _next_port[0]
        _next_port[0] = 21000 if p >= 40000 else p + 1
        return p


def wait_port(port, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def proxy_fetch(port, url, timeout):
    """GET url through the local xray HTTP proxy, return ms for 200/204 else None."""
    proxy = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    req = urllib.request.Request(url, headers=UA)
    t0 = time.perf_counter()
    with opener.open(req, timeout=timeout) as r:
        r.read(64)
        code = r.status
    if code not in (200, 204):
        return None
    return (time.perf_counter() - t0) * 1000


def real_test(link, timeout=TEST_TIMEOUT):
    """Start xray with this config and fetch a real URL through it.

    Returns the end-to-end delay in ms (DNS + TCP + TLS + HTTP through the
    proxy) or None when the config does not carry traffic.
    """
    ob = outbound(link)
    if not ob:
        return None
    port = alloc_port()
    cfg = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "listen": "127.0.0.1", "port": port, "protocol": "http",
            "settings": {"timeout": 0},
        }],
        "outbounds": [ob],
    }
    tmp = tempfile.mkdtemp(prefix="xray-")
    proc = None
    try:
        cfg_path = Path(tmp) / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.Popen(
            [XRAY_BIN, "-c", str(cfg_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # bail out early if xray rejected the config instead of waiting the full timeout
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if proc.poll() is not None:
                return None
            if wait_port(port, 0.5):
                break
        else:
            return None
        for url in TEST_URLS:
            try:
                ms = proxy_fetch(port, url, timeout)
            except Exception:  # noqa: BLE001
                ms = None
            if ms is not None:
                return ms
        return None
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(tmp, ignore_errors=True)


def run_tests(items, target, deadline):
    """Start xray tests until `target` configs pass or the time budget is spent."""
    results = []
    tested = 0
    pending = {}
    it = iter(items)
    with ThreadPoolExecutor(TEST_WORKERS) as ex:
        def feed():
            while len(pending) < TEST_WORKERS * 2:
                try:
                    item = next(it)
                except StopIteration:
                    return
                pending[ex.submit(real_test, item[0])] = item

        feed()
        last_log = time.monotonic()
        while pending:
            if len(results) >= target or time.monotonic() >= deadline:
                break
            done, _ = wait(list(pending), timeout=1, return_when=FIRST_COMPLETED)
            for f in done:
                item = pending.pop(f)
                tested += 1
                try:
                    ms = f.result()
                except Exception:  # noqa: BLE001
                    ms = None
                if ms is not None:
                    results.append((ms, item))
            feed()
            if time.monotonic() - last_log > 15:
                log(f"  ... tested {tested}, working {len(results)}")
                last_log = time.monotonic()
        for f in pending:
            f.cancel()
    return results, tested


def xray_version():
    try:
        r = subprocess.run([XRAY_BIN, "version"], capture_output=True,
                           text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return (out[0] if out else "?"), None


# ------------------------------------------------------------------ outputs ---
def txt_header(title, count):
    lines = [
        f"#profile-title: {title}",
        "#profile-update-interval: 1",
        "#subscription-userinfo: upload=0; download=0; total=0; expire=0",
    ]
    if REPO:
        lines.append(f"#profile-web-page-url: https://github.com/{REPO}")
    if SUPPORT_URL:
        lines.append(f"#support-url: {SUPPORT_URL}")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    prefix = f"{BRAND} — " if BRAND else ""
    lines.append(f"# {prefix}{title} — {count} configs — {stamp}")
    return "\n".join(lines)


def remark(rec):
    cc = rec["cc"]
    f = flag(cc)
    tag = rec["tag"]
    who = f"{cc} {f}".strip() if f else cc
    prefix = "GCP " if rec["region"] else ""
    return f"{prefix}{who} | {int(rec['ms'])}ms | {tag}"


def write_list(path, recs, title, base64_twin=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [remark(r) for r in recs]
    text = txt_header(title, len(body)) + "\n" + "\n".join(body) + "\n"
    path.write_text(text, encoding="utf-8")
    if base64_twin:
        twin = path.with_name(path.stem + "_base64.txt")
        twin.write_text(base64.b64encode("\n".join(body).encode()).decode(),
                        encoding="utf-8")


def prio_key(rec):
    """Asia first, then GCP, then latency."""
    return (0 if rec["continent"] == "Asia" else 1,
            0 if rec["region"] else 1,
            rec["ms"])


def build_catalog(recs_by_cat, countries, index_path):
    categories, protocols, transports, regions = {}, {}, {}, {}

    for name, recs, txt, b64 in recs_by_cat:
        categories[name] = {
            "count": len(recs),
            "files": {"configs_txt": txt, "configs_base64": b64},
        }

    all_recs = recs_by_cat[0][1]
    for rec in all_recs:
        protocols[rec["proto"]] = protocols.get(rec["proto"], 0) + 1
        net, sec = rec["transport"], rec["security"]
        transports[net] = transports.get(net, 0) + 1
        if sec != "none":
            transports[f"{net}_{sec}"] = transports.get(f"{net}_{sec}", 0) + 1
        regions[rec["continent"]] = regions.get(rec["continent"], 0) + 1

    index = {
        "repo": REPO,
        "brand": BRAND,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "update_interval_minutes": 30,
        "eligibility": "every config opened a real HTTP request through xray",
        "raw_base": f"https://raw.githubusercontent.com/{REPO}/main/output",
        "mirror_base": f"https://cdn.jsdelivr.net/gh/{REPO}@main/output",
        "categories": dict(sorted(categories.items())),
        "protocols": dict(sorted(protocols.items(), key=lambda kv: -kv[1])),
        "transports": dict(sorted(transports.items(), key=lambda kv: -kv[1])),
        "regions": dict(sorted(regions.items(), key=lambda kv: -kv[1])),
        "countries": countries,
        "total_unique": len(all_recs),
    }
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return index


# -------------------------------------------------------------------- main ---
def main():
    started = time.monotonic()
    version, err = xray_version()
    if version is None:
        log(f"xray not usable ({XRAY_BIN}): {err}")
        sys.exit(1)
    log(f"xray: {version}")

    try:
        geo = load_geoip()
    except Exception as e:  # noqa: BLE001
        geo = None
        log(f"geoip unavailable ({e}) - countries will be unknown")

    v4, v6 = load_gcp_ranges()

    raw = []
    sources_ok, sources_failed = [], []
    for src in load_sources():
        try:
            links = extract_links(http_get(src))
            log(f"  {len(links):>6} links  {src}")
            raw += links
            sources_ok.append(src)
        except Exception as e:  # noqa: BLE001
            log(f"  FAILED  {e}")
            sources_failed.append({"source": src, "error": str(e)[:200]})
    if not sources_ok:
        log("No source could be fetched - keeping previous output.")
        sys.exit(1)

    unique = {}
    for l in raw:
        try:
            unique.setdefault(identity(l), l)
        except Exception:  # noqa: BLE001
            pass
    links = list(unique.values())
    log(f"collected {len(raw)}, unique {len(links)}")

    # resolve every distinct host once, in parallel
    parsed = {l: link_endpoint(l) for l in links}
    hosts = {h for h, _ in parsed.values() if h}
    log(f"resolving {len(hosts)} hosts ...")
    with ThreadPoolExecutor(RESOLVE_WORKERS) as ex:
        ips = dict(zip(hosts, ex.map(resolve_host, hosts)))

    entries = []
    for l in links:
        h, p = parsed[l]
        ip = ips.get(h) if h else None
        if not ip or not p:
            continue
        entries.append((l, ip, p, gcp_region(ip, v4, v6)))
    gcp_count = sum(1 for e in entries if e[3])
    log(f"on Google Cloud IPs: {gcp_count} | other hosts: {len(entries) - gcp_count}")
    if GCP_ONLY:
        entries = [e for e in entries if e[3]]
        log(f"GCP_ONLY=1 -> testing only {len(entries)} GCP configs")

    candidates = entries
    if TCP_PREFILTER and entries:
        with ThreadPoolExecutor(RESOLVE_WORKERS) as ex:
            reachable = list(ex.map(lambda x: tcp_ok(x[1], x[2]), entries))
        candidates = [e for e, ok in zip(entries, reachable) if ok]
        log(f"tcp reachable: {len(candidates)}/{len(entries)}")

    # GCP first; the rest are rotated every run so repeat runs sample other configs
    seed = int(datetime.now(timezone.utc).strftime("%Y%m%d%H"))
    gcp_candidates = [e for e in candidates if e[3]]
    other_candidates = [e for e in candidates if not e[3]]
    random.Random(seed).shuffle(other_candidates)
    ordered = gcp_candidates + other_candidates

    deadline = time.monotonic() + MAX_TEST_MINUTES * 60
    log(f"proxy-testing {len(ordered)} configs ({TEST_WORKERS} at a time, "
        f"{MAX_TEST_MINUTES:.0f} min budget) ...")
    results, tested = run_tests(ordered, MAX_OUTPUT, deadline)
    log(f"tested {tested}, working {len(results)}")

    # GCP configs are rare, so give the ones that failed one more, slower attempt
    passed = {item[0] for _, item in results}
    retry = [e for e in gcp_candidates if e[0] not in passed]
    if retry:
        log(f"retrying {len(retry)} GCP configs with a longer timeout ...")
        with ThreadPoolExecutor(min(TEST_WORKERS, len(retry))) as ex:
            retried = list(ex.map(lambda e: (e, real_test(e[0], TEST_TIMEOUT * 1.5)), retry))
        for entry, ms in retried:
            tested += 1
            if ms is not None:
                results.append((ms, entry))
        log(f"after retry: {sum(1 for _, i in results if i[3])} working GCP configs")

    if not results:
        log("Nothing alive this run - keeping previous output.")
        sys.exit(1)

    # enrich the survivors
    recs = []
    for ms, (link, ip, port, region) in results:
        proto, net, sec = props(link)
        cc = geo.country(ip) if geo else "ZZ"
        recs.append({
            "link": link, "ms": ms, "region": region, "ip": ip,
            "cc": cc, "continent": continent(cc),
            "proto": proto, "transport": net, "security": sec,
            "tag": sha1(identity(link).encode()).hexdigest()[:5],
        })
    recs.sort(key=prio_key)
    recs = recs[:MAX_OUTPUT]
    for r in recs:
        r["name"] = remark(r)
        r["out"] = rename(r["link"], r["name"])

    log(f"publishing {len(recs)} "
        f"({sum(1 for r in recs if r['region'])} GCP, "
        f"{sum(1 for r in recs if r['continent'] == 'Asia')} Asia)")

    # ---- build the tree in a scratch dir, then swap it in atomically
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)

    def rel(p):
        return str(p.relative_to(BUILD)).replace(os.sep, "/")

    def emit(subdir, name, subset, title, b64=True):
        path = BUILD / subdir / f"{name}.txt" if subdir else BUILD / f"{name}.txt"
        write_list(path, subset, title, base64_twin=b64)
        twin = (BUILD / subdir / f"{name}_base64.txt") if subdir else (BUILD / f"{name}_base64.txt")
        return rel(path), rel(twin)

    catalogue = []

    all_txt, all_b64 = emit("all", "configs", recs, "ALL verified configs")
    catalogue.append(("all", recs, all_txt, all_b64))

    gcp_recs = [r for r in recs if r["region"]]
    if gcp_recs:
        t, b = emit("gcp", "configs", gcp_recs, "GCP verified configs")
        catalogue.append(("gcp", gcp_recs, t, b))
    else:
        catalogue.append(("gcp", [], None, None))

    fast_recs = [r for r in recs if r["ms"] <= FAST_MS]
    if len(fast_recs) < 25:
        fast_recs = recs[:25]
    fast_recs = sorted(fast_recs, key=lambda r: r["ms"])
    if fast_recs:
        t, b = emit("fast", "configs", fast_recs,
                    f"LOW PING (<= {int(FAST_MS)} ms)")
        catalogue.append(("fast", fast_recs, t, b))

    # protocols
    for proto in sorted({r["proto"] for r in recs}):
        subset = [r for r in recs if r["proto"] == proto]
        t, b = emit("protocols", proto, subset, proto.upper())
        catalogue.append((f"protocols/{proto}", subset, t, b))

    # transports / security profiles
    groups = {}
    for r in recs:
        net, sec = r["transport"], r["security"]
        if sec in ("tls", "reality"):
            groups.setdefault(f"{net}_{sec}", []).append(r)
        if sec == "tls":
            groups.setdefault("tls", []).append(r)
        elif sec == "reality":
            groups.setdefault("reality", []).append(r)
        else:
            groups.setdefault("non_tls", []).append(r)
    for key in sorted(groups):
        subset = sorted(groups[key], key=lambda r: r["ms"])
        t, b = emit("transports", key, subset, key.upper().replace("_", " "))
        catalogue.append((f"transports/{key}", subset, t, b))

    # countries + regions
    by_country = {}
    for r in recs:
        by_country.setdefault(r["cc"], []).append(r)
    countries = []
    for cc in sorted(by_country, key=lambda c: (-len(by_country[c]), c)):
        name = country_name(cc)
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or cc
        subset = sorted(by_country[cc], key=lambda r: r["ms"])
        path = BUILD / "Countries" / f"{safe}.txt"
        write_list(path, subset, f"{name} ({cc})", base64_twin=False)
        countries.append({
            "code": cc, "name": name, "flag": flag(cc),
            "region": continent(cc), "count": len(subset),
            "file": rel(path),
        })
    (BUILD / "Countries" / "index.json").write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "all",
            "criterion": "passed a real proxied request through xray",
            "location_method": "GeoIP (DB-IP Country Lite)",
            "countries": countries,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_region = {}
    for r in recs:
        by_region.setdefault(r["continent"], []).append(r)
    for name in sorted(by_region, key=lambda n: (n != "Asia", -len(by_region[n]))):
        subset = sorted(by_region[name], key=lambda r: r["ms"])
        emit("regions", name.replace(" ", "_"), subset, name.upper(), b64=False)

    # top100
    top = sorted(recs, key=lambda r: r["ms"])[:TOP_N]
    write_list(BUILD / "top100.txt", top, f"TOP {len(top)} fastest", base64_twin=False)
    catalogue.append(("top100", top, "top100.txt", None))

    # health.json
    health = {
        "status": "ok",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(time.monotonic() - started, 1),
        "xray": version,
        "geoip": "db-ip country lite" if geo else "unavailable",
        "sources": {"active": len(sources_ok), "failed": sources_failed},
        "counts": {
            "links_collected": len(raw), "unique": len(links),
            "on_gcp": gcp_count, "tcp_reachable": len(candidates),
            "tested": tested, "working": len(results), "published": len(recs),
        },
    }
    (BUILD / "health.json").write_text(
        json.dumps(health, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    index = build_catalog(catalogue, countries, BUILD / "index.json")
    log("categories: " + ", ".join(
        f"{k}={v['count']}" for k, v in index["categories"].items()))

    # swap the freshly built tree in; keeps the old list if anything above failed
    shutil.rmtree(OUT, ignore_errors=True)
    BUILD.rename(OUT)
    log(f"done in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
