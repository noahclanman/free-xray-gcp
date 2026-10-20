# Fork guide — run this on your own GitHub account

This guide is for anyone who wants their **own** copy of the aggregator: a fork that rebuilds
the lists every 30 minutes on GitHub's machines, with no server and no cost.

The whole thing is one Python script (standard library only) plus one workflow file, so the
only real work is flipping two settings that GitHub disables on forks by default.

---

## 1. Fork the repository

1. Open <https://github.com/noahclanman/free-xray-gcp>.
2. Click **Fork** (top right) → choose your account → **Create fork**.
3. Optionally rename it, e.g. `my-xray-configs`.

Your copy now lives at `https://github.com/<your-username>/<repo>`.

---

## 2. Enable Actions on the fork

GitHub disables workflows in forks until you confirm them.

1. Open the **Actions** tab of **your fork**.
2. Click the green **I understand my workflows, go ahead and enable them** button.

If you skip this, nothing will ever run and `output/` will stay exactly as you forked it.

---

## 3. Give the bot permission to commit (the step everyone misses)

The workflow commits the regenerated files back to your repository. The default token is
read-only, so without this step the run ends with **403 / "Permission denied"** at the commit
step.

1. **Settings** → **Actions** → **General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

That is the only repository setting that is strictly required.

---

## 4. Run it once, manually

1. **Actions** tab → **Update GCP V2Ray configs** (left sidebar).
2. **Run workflow** → branch `main` → **Run workflow**.
3. Open the run and watch the step **Build GCP-only list (real proxy test)**.

A full run takes about **15–20 minutes**: roughly two minutes to fetch and resolve, two to
three for the TCP prefilter, then 15 minutes of real Xray testing.

When it finishes you should see a new commit:

```
update: 2026-10-20 16:18 UTC
```

and a populated `output/` folder in your fork.

---

## 5. Your subscription URLs

Replace `<you>` and `<repo>` with your own values:

| What | URL |
|---|---|
| Everything (base64) | `https://raw.githubusercontent.com/<you>/<repo>/main/output/all/configs_base64.txt` |
| Top 100 | `https://raw.githubusercontent.com/<you>/<repo>/main/output/top100.txt` |
| Low ping | `https://raw.githubusercontent.com/<you>/<repo>/main/output/fast/configs_base64.txt` |
| GCP only | `https://raw.githubusercontent.com/<you>/<repo>/main/output/gcp/configs_base64.txt` |
| Status | `https://raw.githubusercontent.com/<you>/<repo>/main/output/index.json` |

These work exactly like the upstream ones. `raw.githubusercontent.com` caches for about five
minutes; if you need a long-cache mirror, jsDelivr works with the same path:

```
https://cdn.jsdelivr.net/gh/<you>/<repo>@main/output/all/configs_base64.txt
```

> jsDelivr caches for hours, so use it for sharing and `raw` for your own client.

---

## 6. Customize

### Sources

Edit [`sources.txt`](sources.txt) — one URL per line, `#` for comments. The line may be:

- a plain list of `vmess://` / `vless://` / `trojan://` / `ss://` links,
- a base64 subscription (the whole file is encoded),
- a raw GitHub URL,
- an HTML page (links are scraped out of it — this is how Telegram channels are read).

Placeholders `{Y}` `{M}` `{D}` `{YMD}` are replaced with the current UTC date, so dated URLs
keep working without edits.

### Settings

Either edit the `env:` block in [`.github/workflows/update.yml`](.github/workflows/update.yml)
or add repository variables under **Settings → Secrets and variables → Actions → Variables**.

| Variable | Default | Use it to |
|---|---|---|
| `MAX_OUTPUT` | `1000` | publish fewer/more configs |
| `MAX_TEST_MINUTES` | `15` in CI | trade list size for run time |
| `TEST_WORKERS` | `16` | more parallel Xray instances (CPU-bound) |
| `TEST_TIMEOUT` | `7` | allow slower servers to pass |
| `FAST_MS` | `400` | change the `low ping` cutoff |
| `MAX_MS` | `4000` | drop slow non-GCP configs |
| `GCP_ONLY` | `0` | publish only Google Cloud configs |
| `PROTOCOLS` | `vmess,vless,trojan,ss` | keep fewer protocols |
| `CHANNEL` | `@xray_ehi_hub` | print your own handle in every remark |
| `BRAND` | `@xray_ehi_hub` | header label in the list files |

### Schedule

The cron is in the workflow file:

```yaml
on:
  schedule:
    - cron: "*/30 * * * *"   # UTC, every 30 minutes
```

A run takes ~15–20 minutes, so do not set the interval below 20 minutes or runs will queue.
GitHub also delays scheduled runs during peak hours — 5–15 minutes of drift is normal.

---

## 7. Verify it worked

- `output/health.json` → `"status": "ok"` and `counts.published` greater than zero.
- `output/index.json` → totals per category, protocol and country.
- Open `output/top100.txt` — the first line must start with `vless://`, `vmess://`,
  `trojan://` or `ss://`, and end with a remark like
  `JP 🇯🇵 | @xray_ehi_hub | 1d974`.

If a run finds **zero** working configs, the script exits with an error and leaves the previous
`output/` untouched — you keep the last good list instead of an empty one.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Nothing runs on schedule | Actions not enabled on the fork | Step 2 |
| `403` / `Permission denied` on commit | Token is read-only | Step 3 |
| Workflow runs but `output/` never changes | No config passed the real test | Check the run log; try `TEST_TIMEOUT=10`, `MAX_MS=8000` |
| `gcp: 0` in `index.json` | No GCP-hosted config is alive right now | Expected; the folder returns when one passes |
| `xray not usable` | Download step failed | Re-run; check `Xray-linux-64.zip` availability |
| Scheduled runs stopped after ~60 days | GitHub disables schedules in inactive repos | Re-enable in the Actions tab or make any commit |
| Run takes > 40 min | Interval too short / budget too high | Lower `MAX_TEST_MINUTES` |
| `No source could be fetched` | All upstreams down or blocked | Check `sources.txt`, re-run |

---

## 9. Keeping the fork up to date

Use **Sync fork → Update branch** on GitHub whenever the upstream changes the script or adds
sources. If you have edited `sources.txt` yourself, resolve that one conflict by keeping your
file.

Scheduled workflows in forks are disabled after 60 days without repository activity — a
one-click **Sync fork** or any commit resets that timer.

---

## 10. Optional extras

- **Custom domain:** put Cloudflare in front of `raw.githubusercontent.com` for your own path,
  or use jsDelivr (`cdn.jsdelivr.net/gh/<you>/<repo>@main/output/...`).
- **Your own branding:** set `CHANNEL` and `BRAND`, and regenerate the README assets with
  `python scripts/make_assets.py` (needs `pip install "qrcode[pil]"`).
- **Pull requests to upstream:** see [CONTRIBUTING.md](CONTRIBUTING.md). Please do not PR
  generated files under `output/` — CI owns that directory.

---

<sub>Back to [README.md](README.md) · Questions: [@xray_ehi_hub](https://t.me/xray_ehi_hub)</sub>
