# Free Xray Configs — GCP first

A self-updating subscription of **VMess / VLESS / Trojan / Shadowsocks** configs.
Every config in this repo **actually proxied a real HTTP request** through Xray before it was
published — there are no TCP-ping-only entries. Configs hosted on **Google Cloud (GCP)** are
tested first and published in their own folder; the main list is **Asia-first**, then sorted by
measured latency.

Updated every 30 minutes by GitHub Actions. No server, no account, no dependencies.

## Subscribe

Pick one link and paste it into v2rayNG / v2rayN / Hiddify / NekoBox / Streisand.

| Collection | What it is | Subscription link |
|---|---|---|
| **All** | every verified config, Asia first | [`all/configs_base64.txt`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/all/configs_base64.txt) |
| **GCP** | only configs hosted on Google Cloud | [`gcp/configs_base64.txt`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/gcp/configs_base64.txt) |
| **Low ping** | fastest configs under 400 ms | [`fast/configs_base64.txt`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/fast/configs_base64.txt) |
| **Top 100** | the 100 fastest overall | [`top100.txt`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/top100.txt) |

Per protocol (`protocols/`) and per transport (`transports/`) lists — including
`reality`, `tls`, `ws_tls`, `grpc_tls`, `xhttp_tls`, `httpupgrade_tls`, `non_tls` — plus
`Countries/<Country>.txt` and `regions/Asia.txt` are listed in **[OUTPUTS.md](OUTPUTS.md)**.

Plain-text variants exist next to every subscription file (`configs.txt` vs
`configs_base64.txt`), and jsDelivr mirrors are available:
`https://cdn.jsdelivr.net/gh/noahclanman/free-xray-gcp@main/output/...`

## Naming

```
JP 🇯🇵 | 288ms | 1d974            verified config in Japan
GCP SG 🇸🇬 | 402ms | 3ae49        same, but the server IP is inside Google Cloud
```

`288ms` is the **real end-to-end delay** measured through the proxy — DNS + TCP + TLS + the
HTTP request — not a TCP handshake. The short hash identifies the server across updates, so
your client keeps its selection when the list refreshes.

## How a run works

```
sources.txt
    │  GitHub lists, base64 subscriptions, Telegram channels (HTML scraped)
    ▼
extract vmess:// vless:// trojan:// ss://   →  dedupe by server+credentials
    ▼
resolve hostnames  →  GeoIP (DB-IP Country Lite) + Google Cloud prefix match
    ▼
cheap TCP prefilter (1.5 s)
    ▼
REAL TEST: start Xray with the config, fetch a generate_204 URL through it
    │  pass → keep the measured delay     fail → discard
    ▼
sort: Asia first, then GCP, then latency
    ▼
output/  (categories, countries, transports, index.json, health.json)
```

All GCP candidates are tested before anything else, so a working GCP config is never
dropped because the time budget ran out. If a run finds nothing at all, `output/` is left
untouched and the previous list stays online.

## Repository layout

```
sources.txt                 where configs come from (add your own)
scripts/update.py           the whole pipeline, standard library only
.github/workflows/update.yml  cron: every 30 minutes
output/
├── all/configs.txt         every verified config (Asia first)
├── gcp/configs.txt         GCP-hosted only (created when at least one is alive)
├── fast/configs.txt        low-latency subset
├── top100.txt              fastest 100
├── protocols/              vmess, vless, trojan, shadowsocks
├── transports/             tls, reality, ws_tls, grpc_tls, xhttp_tls, ...
├── Countries/              one file per country + index.json
├── regions/                Asia, Europe, North America, ...
├── index.json              machine-readable catalogue with counts and links
└── health.json             last run: sources, counts, duration
```

## Run it yourself

```bash
python scripts/update.py          # needs Python 3.9+ and xray on PATH (or XRAY_BIN)
```

| Variable | Default | Meaning |
|---|---|---|
| `XRAY_BIN` | `xray` | path to the Xray binary used for the real test |
| `MAX_OUTPUT` | `1000` | cap on published configs |
| `MAX_TEST_MINUTES` | `20` | time budget for the real test phase (CI uses 15) |
| `TEST_WORKERS` | `16` | parallel Xray instances |
| `TEST_TIMEOUT` | `7` | seconds allowed for one proxied request |
| `TEST_URLS` | gstatic + cloudflare `generate_204` | fallback test targets |
| `FAST_MS` | `400` | threshold for the `fast/` list |
| `MAX_MS` | `4000` | drop non-GCP configs slower than this (GCP ones are kept) |
| `TCP_PREFILTER` | `1` | set `0` to test every config with Xray |
| `GCP_ONLY` | `0` | set `1` to publish GCP configs only |
| `PROTOCOLS` | `vmess,vless,trojan,ss` | protocols to keep |
| `REPO` / `BRAND` | – | used in list headers and `index.json` |

To fork this: create a repo, push the files, enable **Settings → Actions → General →
Workflow permissions → Read and write**, then run the workflow once.

## Honest limits

- **The GCP pool is tiny.** Of ~17,000 unique configs, normally only ~10 resolve to a Google
  Cloud IP, and free ones are often dead. When none pass the real test, `gcp/` is not
  published and the folder disappears from the list. `index.json` still reports
  `categories.gcp.count = 0`.
- **A passing config can still die.** Servers are shared, rate-limited and disappear within
  hours. The list is regenerated every 30 minutes; the app you use keeps the last copy.
- **Latency is measured from a GitHub datacenter**, not from your network. Use it to rank
  configs, not as an absolute number.
- **Free configs are not private.** Assume the operator can see your traffic metadata.
  Do not use them for banking, logins or anything sensitive.

## Legal

This repository only aggregates publicly posted configuration links and tests reachability.
It does not host, operate or endorse any server. Use it in accordance with the laws that
apply to you.
