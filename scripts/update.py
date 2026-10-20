#!/usr/bin/env python3
"""
GCP-only V2Ray aggregator with REAL proxy testing.

fetch sources -> keep proxy links -> resolve host -> keep only Google Cloud IPs
-> cheap TCP prefilter -> start xray per config, fetch a real 204 URL through
   the proxy, measure the round trip -> sort by real delay -> write output/

Google publishes its Cloud IP ranges at:
https://www.gstatic.com/ipranges/cloud.json
"""
import base64
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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlunparse, quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

# ---- settings (override with env vars in the workflow if you like) ----------
PROTOCOLS = tuple(p.strip().lower() for p in os.getenv(
    "PROTOCOLS", "vmess,vless,trojan,ss").split(",") if p.strip())
GCP_RANGES_URL = os.getenv("GCP_RANGES", "https://www.gstatic.com/ipranges/cloud.json")
XRAY_BIN = os.getenv("XRAY_BIN", "xray")
MAX_OUTPUT = int(os.getenv("MAX_OUTPUT", "500"))     # keep the N fastest
RESOLVE_WORKERS = int(os.getenv("RESOLVE_WORKERS", "200"))
TEST_WORKERS = int(os.getenv("TEST_WORKERS", "12"))  # parallel xray instances
MAX_TEST_MINUTES = float(os.getenv("MAX_TEST_MINUTES", "20"))
TCP_TIMEOUT = float(os.getenv("TCP_TIMEOUT", "1.5"))  # cheap prefilter only
TCP_PREFILTER = os.getenv("TCP_PREFILTER", "1") != "0"
GCP_ONLY = os.getenv("GCP_ONLY", "0") == "1"        # 1 = strict GCP, no fill configs
TEST_TIMEOUT = float(os.getenv("TEST_TIMEOUT", "7"))
TEST_URLS = [u.strip() for u in os.getenv(
    "TEST_URLS",
    "https://www.gstatic.com/generate_204,https://cp.cloudflare.com/generate_204",
).split(",") if u.strip()]
UA = {"User-Agent": "gcp-v2ray-aggregator/2.0"}

LINK_RE = re.compile(r"^(%s)://" % "|".join(map(re.escape, PROTOCOLS)), re.I)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- fetching ---
def http_get(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return Path(url).read_text(encoding="utf-8", errors="ignore")  # local file
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
    text = text.lstrip("\ufeff").strip()
    # A base64 subscription can only contain the base64 alphabet, so a real link
    # anywhere in the file means it is already plain text. Do not rely on the
    # first few characters: many sources start with "#profile-*" comment lines.
    if "://" not in text:
        try:
            decoded = b64decode(text)
        except Exception:  # noqa: BLE001
            return []
        if "://" in decoded:
            text = decoded
    return [l.strip() for l in text.splitlines() if LINK_RE.match(l.strip())]


def load_sources():
    lines = (ROOT / "sources.txt").read_text(encoding="utf-8").splitlines()
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
    net = (net or "tcp").lower()
    net = {"gun": "grpc", "h2": "http", "splithttp": "xhttp"}.get(net, net)
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
    sec = "tls" if tls in ("tls", "reality") else "none"
    net = str(j.get("net") or "tcp")
    host = _first(j, "host")
    path = _first(j, "path")
    st = build_stream(
        net=net, security=sec, host=host, path=path,
        sni=_first(j, "sni") or host or add, fp=_first(j, "fp"),
        alpn=_first(j, "alpn"), pbk=_first(j, "pbk"), sid=_first(j, "sid"),
        header_type=_first(j, "type"),
        service_name=_first(j, "serviceName") or (path if net == "grpc" else None),
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
        service_name=q.get("serviceName") or (q.get("path") if net == "grpc" else None),
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
        service_name=q.get("serviceName") or (q.get("path") if net == "grpc" else None),
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
                    results.append((ms, item[0], item[3]))
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


# -------------------------------------------------------------------- main ---
def main():
    version, err = xray_version()
    if version is None:
        log(f"xray not usable ({XRAY_BIN}): {err}")
        sys.exit(1)
    log(f"xray: {version}")

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
    parsed = {l: link_endpoint(l) for l in links}
    hosts = {h for h, _ in parsed.values() if h}
    log(f"resolving {len(hosts)} hosts ...")
    with ThreadPoolExecutor(RESOLVE_WORKERS) as ex:
        ips = dict(zip(hosts, ex.map(resolve_host, hosts)))

    # classify: GCP-hosted configs are always tested first, everything else fills the list
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

    # GCP block first (fastest GCP config at the top), then the verified fill
    alive = sorted(results, key=lambda x: (0 if x[2] else 1, x[0]))[:MAX_OUTPUT]
    log(f"publishing {len(alive)} "
        f"({sum(1 for a in alive if a[2])} GCP + {sum(1 for a in alive if not a[2])} other)")

    if not alive:
        log("Nothing alive this run - keeping previous output.")
        sys.exit(1)

    final = []
    for ms, l, region in alive:
        tag = sha1(identity(l).encode()).hexdigest()[:5]
        label = f"GCP {region}" if region else "OTHER"
        try:
            final.append((rename(l, f"{label} | {int(ms)}ms | {tag}"), l, region))
        except Exception:  # noqa: BLE001
            final.append((l, l, region))

    OUT.mkdir(exist_ok=True)
    lines = [f for f, _, _ in final]
    (OUT / "gcp_v2ray.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "gcp_v2ray_base64.txt").write_text(
        base64.b64encode("\n".join(lines).encode()).decode(), encoding="utf-8")
    for proto in PROTOCOLS:
        part = [f for f, o, _ in final if o.lower().startswith(proto + "://")]
        p = OUT / f"gcp_{proto}.txt"
        if part:
            p.write_text("\n".join(part) + "\n", encoding="utf-8")
        elif p.exists():
            p.unlink()  # never publish an empty subscription
    for stale in OUT.glob("gcp_*.txt"):
        name = stale.stem[4:]
        if name not in PROTOCOLS and name != "v2ray" and name != "v2ray_base64":
            stale.unlink()

    by_region = {}
    for _, _, r in final:
        by_region[r or "other"] = by_region.get(r or "other", 0) + 1
    (OUT / "stats.json").write_text(json.dumps({
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "collected": len(raw), "unique": len(links),
        "on_gcp": gcp_count, "tcp_reachable": len(candidates), "tested": tested,
        "working": len(results), "published": len(final),
        "gcp_published": sum(1 for _, _, r in final if r),
        "test": "real proxy fetch " + " / ".join(TEST_URLS),
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
    }, indent=2) + "\n", encoding="utf-8")
    log("done")


if __name__ == "__main__":
    main()
