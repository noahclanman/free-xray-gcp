#!/usr/bin/env python3
"""
GCP-only V2Ray aggregator.

fetch sources -> keep vmess/vless -> resolve host -> keep only Google Cloud IPs
-> TCP-test (measure latency) -> rename by GCP region -> write output/

Google publishes its Cloud IP ranges at:
https://www.gstatic.com/ipranges/cloud.json
"""
import base64
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse, quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

# ---- settings (override with env vars in the workflow if you like) ----------
PROTOCOLS = tuple(os.getenv("PROTOCOLS", "vmess,vless").split(","))  # add trojan,ss if wanted
GCP_RANGES_URL = os.getenv("GCP_RANGES", "https://www.gstatic.com/ipranges/cloud.json")
TCP_TIMEOUT = float(os.getenv("TCP_TIMEOUT", "4"))
TCP_ROUNDS = int(os.getenv("TCP_ROUNDS", "2"))       # must pass every round
WORKERS = int(os.getenv("WORKERS", "100"))
MAX_OUTPUT = int(os.getenv("MAX_OUTPUT", "500"))     # keep the N fastest
UA = {"User-Agent": "gcp-v2ray-aggregator/1.0"}

LINK_RE = re.compile(r"^(%s)://" % "|".join(map(re.escape, PROTOCOLS)), re.I)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- fetching ---
def http_get(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return Path(url).read_text(errors="ignore")  # local file (handy for tests)
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode(errors="ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise RuntimeError(f"{url}: {last}")


def b64decode(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode(errors="ignore")


def extract_links(text: str):
    text = text.strip()
    if "://" not in text[:40]:  # whole file is a base64 subscription
        try:
            text = b64decode(text)
        except Exception:  # noqa: BLE001
            return []
    return [l.strip() for l in text.splitlines() if LINK_RE.match(l.strip())]


def load_sources():
    lines = (ROOT / "sources.txt").read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


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


# ----------------------------------------------------------------- parsing ---
def host_port(link: str):
    try:
        if link.lower().startswith("vmess://"):
            j = json.loads(b64decode(link[8:]))
            return str(j["add"]).strip(), int(j["port"])
        u = urlparse(link)
        return u.hostname, u.port
    except Exception:  # noqa: BLE001
        return None, None


def resolve(host):
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)[0][4][0]
    except OSError:
        return None


def tcp_latency(ip, port):
    """Median connect time in ms, or None if any round fails."""
    times = []
    for _ in range(TCP_ROUNDS):
        t = time.perf_counter()
        try:
            socket.create_connection((ip, port), timeout=TCP_TIMEOUT).close()
        except OSError:
            return None
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return times[len(times) // 2]


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


# -------------------------------------------------------------------- main ---
def main():
    v4, v6 = load_gcp_ranges()

    raw = []
    ok_sources = 0
    for src in load_sources():
        try:
            links = extract_links(http_get(src))
            log(f"  {len(links):>6} links  {src}")
            raw += links
            ok_sources += 1
        except Exception as e:  # noqa: BLE001
            log(f"  FAILED  {e}")
    if ok_sources == 0:
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
    parsed = {l: host_port(l) for l in links}
    hosts = {h for h, p in parsed.values() if h}
    with ThreadPoolExecutor(WORKERS) as ex:
        ips = dict(zip(hosts, ex.map(resolve, hosts)))

    # keep only Google Cloud IPs
    gcp = []
    for l in links:
        h, p = parsed[l]
        ip = ips.get(h) if h else None
        if not ip or not p:
            continue
        region = gcp_region(ip, v4, v6)
        if region:
            gcp.append((l, ip, p, region))
    log(f"on Google Cloud IPs: {len(gcp)}")

    # liveness + latency
    with ThreadPoolExecutor(WORKERS) as ex:
        lat = list(ex.map(lambda x: tcp_latency(x[1], x[2]), gcp))
    alive = sorted(
        ((ms, l, region) for (l, ip, p, region), ms in zip(gcp, lat) if ms is not None),
        key=lambda x: x[0],
    )[:MAX_OUTPUT]
    log(f"alive: {len(alive)}")

    if not alive:
        log("Nothing alive this run - keeping previous output.")
        sys.exit(1)

    final = []
    for ms, l, region in alive:
        tag = sha1(identity(l).encode()).hexdigest()[:5]
        try:
            final.append((rename(l, f"GCP {region} | {int(ms)}ms | {tag}"), l, region))
        except Exception:  # noqa: BLE001
            final.append((l, l, region))

    OUT.mkdir(exist_ok=True)
    lines = [f for f, _, _ in final]
    (OUT / "gcp_v2ray.txt").write_text("\n".join(lines) + "\n")
    (OUT / "gcp_v2ray_base64.txt").write_text(base64.b64encode("\n".join(lines).encode()).decode())
    for proto in PROTOCOLS:
        part = [f for f, o, _ in final if o.lower().startswith(proto + "://")]
        p = OUT / f"gcp_{proto}.txt"
        if part:
            p.write_text("\n".join(part) + "\n")
        elif p.exists():
            p.unlink()  # never publish an empty subscription

    by_region = {}
    for _, _, r in final:
        by_region[r] = by_region.get(r, 0) + 1
    (OUT / "stats.json").write_text(json.dumps({
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "collected": len(raw), "unique": len(links),
        "on_gcp": len(gcp), "alive_published": len(final),
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
    }, indent=2) + "\n")
    log("done")


if __name__ == "__main__":
    main()
