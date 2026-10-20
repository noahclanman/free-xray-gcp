# GCP V2Ray

Auto-updating list of **VMess / VLESS** configs whose server IP is inside **Google Cloud (GCP)**
address space. Refreshed every ~30 minutes by GitHub Actions.

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

Each config is named `GCP <region> | <ms> | <id>`, e.g. `GCP asia-southeast1 | 42ms | a1b2c`.
Sorted fastest first.

## How it works

1. Downloads every source in `sources.txt` (plain or base64).
2. Keeps only `vmess://` and `vless://` links and removes duplicates.
3. Resolves each server hostname to an IP.
4. Keeps it only if that IP is inside Google's official ranges
   (<https://www.gstatic.com/ipranges/cloud.json>), so configs behind Cloudflare or other hosts are dropped.
5. Opens a TCP connection to each (2 rounds, both must pass) and measures latency.
6. Publishes the fastest 500 into `output/`.

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
| Also trojan / shadowsocks | `PROTOCOLS: "vmess,vless,trojan,ss"` in `.github/workflows/update.yml` |
| Keep more / fewer | `MAX_OUTPUT` |
| Specific GCP regions only | filter on `region` in `scripts/update.py` (e.g. `region.startswith("asia-")`) |
| Run locally | `python scripts/update.py` (Python 3.9+, no dependencies) |

## Notes

- "TCP open" means the server is reachable, not guaranteed to proxy traffic. A free config can
  still be dead or rate-limited. For stricter testing, run each config through xray/sing-box and
  request a test URL.
- Free public configs are shared by many people and may be monitored by whoever runs the server.
  Do not use them for anything sensitive.
- Use responsibly and follow the laws where you live.
