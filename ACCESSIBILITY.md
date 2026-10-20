# Accessibility

This project is a set of text files and a README. Still, "just text" can be hard to use, so
here is what we commit to and what we know is not perfect.

## Commitments

- **The data is never image-only.** Every subscription, every collection and every number is
  available as plain text or JSON. Screenshots and banners exist for orientation, not as the
  only source of information.
- **QR codes are always paired with the URL.** A QR code is a shortcut; the link is printed
  next to it and is copyable.
- **No-JavaScript.** Nothing here requires a script, an account or a login. `git clone` and
  `curl` are enough.
- **Semantic structure.** The README uses headings in order, real tables and real links, so
  screen readers and "jump to section" navigation work.
- **Alt text.** Every decorative or informative image has an `alt` attribute describing its
  purpose.
- **Colour is never the only signal.** Status is always stated in words ("verified", "failed",
  "0 configs"), not by colour alone.
- **Plain language.** Short sentences, defined terms, no jargon where a plain word exists.
- **Stable file names.** `output/all/configs.txt` keeps its meaning across runs, so bookmarks
  and scripts do not break silently.

## Known limitations

- **Badge images are third-party.** The live counters at the top of the README are rendered by
  shields.io. If they do not load, or a screen reader reads only the `alt` text, the same
  numbers are in
  [`output/index.json`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/index.json)
  (`total_unique`, `categories`, `regions`) and
  [`output/health.json`](https://raw.githubusercontent.com/noahclanman/free-xray-gcp/main/output/health.json).
- **Emoji in remarks.** Remarks use flag emoji (`JP 🇯🇵`). Screen readers may read them as
  "regional indicator symbol letters JP" or skip them. The ISO code always precedes the flag, so
  no information is lost.
- **The banner is an SVG.** Some older screen readers do not describe inline SVG well; the
  heading immediately below it carries the same message.
- **GitHub's theme, not ours.** Contrast is controlled by your GitHub theme. We avoid custom
  colours that only work on one theme.

## Feedback

If something here is hard to use with a screen reader, keyboard, magnification or a cognitive
load, tell us: [@xray_ehi_hub](https://t.me/xray_ehi_hub). Concrete reports ("the table in
section X is read out of order") are the most useful, and fixes ship in the next commit.

---

<sub>Back to [README.md](README.md)</sub>
