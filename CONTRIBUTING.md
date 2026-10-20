# Contributing

Thanks for wanting to help. This project is a **tested** aggregator: the value is not how many
links it contains, but how many of them actually carry traffic. Contributions that respect that
are very welcome.

## Ways to contribute

| Type | How |
|---|---|
| **Add a source** | Edit [`sources.txt`](sources.txt) and open a PR |
| **Report a dead config** | Open an issue with the tag from the end of the remark (`1d974`) |
| **Improve the pipeline** | PR against `scripts/update.py` |
| **Improve the docs** | PR against any `.md` file |
| **Report a security issue** | See [SECURITY.md](SECURITY.md) — please do not open a public issue |

## Adding a source

Requirements for a source to be accepted:

1. **Public** — no login, no API key, no paywall.
2. **Redistributable** — the operator does not forbid re-publishing the links.
3. **Machine-readable enough** — one of:
   - a plain list (`vmess://`, `vless://`, `trojan://`, `ss://` one per line),
   - a base64 subscription (the whole file encoded),
   - an HTML page that contains those links in the markup (Telegram web previews do).
4. **Actually maintained** — it must have produced at least one passing config recently.
5. **Not a duplicate** of a source already listed.

Format in `sources.txt`:

```
# comment describing the source
https://example.com/path/to/list.txt
```

Placeholders `{Y}` `{M}` `{D}` `{YMD}` are replaced with the current UTC date, which keeps
dated URLs working without edits.

Before opening the PR, prove the source yields links:

```bash
python -c "import sys; sys.path.insert(0,'scripts'); import update as u; \
print(len(u.extract_links(u.http_get('YOUR_URL'))))"
```

A number greater than `0` with sensible schemes is enough. A full run is not required.

## Reporting a dead config

Include the **tag** (the last field of the remark, e.g. `1d974`) and, if you can, the protocol
and country. Configs die all the time and the list is rebuilt every 30 minutes, so a single
failure is not a bug — report it only if the same tag keeps appearing for several runs.

## Pull requests

- Keep `scripts/update.py` **standard-library only** — no new dependencies. The workflow must
  stay able to run on a bare `python:3.12` image.
- Python 3.9+ syntax.
- Write files with `encoding="utf-8"`; remarks contain emoji.
- Never PR anything inside `output/` — CI regenerates and owns that directory.
- One logical change per PR, with a short description of what it changes and why.
- If you touch the output layout, update [OUTPUTS.md](OUTPUTS.md) and the relevant section of
  [README.md](README.md) in the same PR.

## Local checks before pushing

```bash
python -c "import ast; ast.parse(open('scripts/update.py', encoding='utf-8').read())"
XRAY_BIN=/path/to/xray MAX_TEST_MINUTES=1 MAX_OUTPUT=20 python scripts/update.py
head -n 8 output/top100.txt     # first config line must start with a scheme://
```

The last line is the important one: every published line must be a real link, not a remark.

## Style

Match the surrounding code: small functions, explicit names, comments only where the reason is
not obvious, no clever one-liners in the hot path. Logs go to `stderr` via `log()`.

## Code of conduct

By participating you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

<sub>Back to [README.md](README.md) · Questions: [@xray_ehi_hub](https://t.me/xray_ehi_hub)</sub>
