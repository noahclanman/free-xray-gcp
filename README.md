# GCP V2Ray

Auto-updating, **really working** subscription of **VMess / VLESS / Trojan / Shadowsocks**
configs. Configs hosted on **Google Cloud (GCP)** are tested first and listed at the top;
the rest is filled with the fastest configs that passed the same live test. Every config is
verified by actually proxying an HTTP request through it, not by a TCP ping. Refreshed every
~30 minutes by GitHub Actions.

## Subscription links

Replace `YOUR_USER/YOUR_REPO` with your own:

```
# all GCP configs (plain)
https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/output/gcp_v2ray.txt

# all GCP configs (base64 - classic subscription format)
https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/output/gcp_v2ray_base64.txt

# per protocol
https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/output/gcp_vmess.txt
https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/output/gcp_vless.txt

# stats (count, regions, last update)
https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/output/stats.json
```

Each config is named after its host, e.g. `GCP asia-southeast1 | 412ms | a1b2c` for a
GCP-hosted server, or `OTHER | 690ms | c3d4e` for a verified non-GCP fill config.
The `ms` value is the **real end-to-end delay** measured through the proxy (DNS + TCP +
TLS + HTTP request to a `generate_204` endpoint), not a TCP ping. GCP configs come first,
each block sorted fastest first.

## How it works

1. Downloads every source in `sources.txt` (plain or base64).
2. Keeps only `vmess://`, `vless://`, `trojan://` and `ss://` links and removes duplicates.
3. Resolves each server hostname to an IP and marks which ones are inside Google's official
   Cloud ranges (<https://www.gstatic.com/ipranges/cloud.json>).
4. Cheap TCP prefilter, then the real test: for every candidate, Xray is started with that
   config and the script fetches a real `204` URL through it. Configs that fail to load,
   time out, or return an error are thrown away.
5. Publishes up to 500 working configs into `output/`: all live GCP configs first, then the
   fastest other verified configs, each with its measured delay.

There are only a few dozen GCP-hosted configs in the whole free pool on a good day, so the
non-GCP fill is what keeps the subscription usable. Set `GCP_ONLY=1` (see below) if you want
the strict version instead.

If a run finds no working configs or no source is reachable, it exits without touching `output/`,
so your last good list stays online.

## Setup (5 minutes)

1. Create a new GitHub repo and upload all these files (keep the folder structure).
2. Repo **Settings -> Actions -> General -> Workflow permissions -> Read and write permissions**.
3. Go to the **Actions** tab, open **Update GCP V2Ray configs**, click **Run workflow**.
4. After it finishes, `output/` appears. Use the raw links above.

## Customize

| Want | Change |
|---|---|
| More sources | add lines to `sources.txt` |
| Only some protocols | `PROTOCOLS: "vmess,vless"` in `.github/workflows/update.yml` |
| Keep more / fewer | `MAX_OUTPUT` |
| Strict GCP only, no fill | `GCP_ONLY: "1"` in `.github/workflows/update.yml` |
| Test more servers at once | `TEST_WORKERS` (16 on CI, more uses more RAM) |
| Shorter / longer run | `MAX_TEST_MINUTES` (default 20) |
| Stricter test | `TEST_TIMEOUT` down to 5, or add your own URL to `TEST_URLS` |
| Specific GCP regions only | filter on `region` in `scripts/update.py` (e.g. `region.startswith("asia-")`) |
| Run locally | `python scripts/update.py` (Python 3.9+, needs `xray` in PATH or `XRAY_BIN` set) |

## Notes

- A config in `output/` answered a real HTTP request through Xray at the time of the run,
  so it should connect. "Should" and not "will": free servers are overloaded, rate-limited
  and often die within hours, and your own network may be filtered differently than the
  GitHub runner that tested them. Re-run the workflow (or wait 30 min) to refresh.
- The delay shown is measured from a GitHub datacenter, so your own ping will differ.
  Use it to rank configs, not as an absolute number.
- Free public configs are shared by many people and may be monitored by whoever runs the server.
  Do not use them for anything sensitive.
- Use responsibly and follow the laws where you live.
