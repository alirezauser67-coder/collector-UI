# V2Ray Deploy-Site Config Collector

A tool that collects free V2Ray / Xray configs (vless, vmess, trojan, ss, ssr,
tuic, hysteria2, wireguard) hosted on free deployment platforms — Railway,
Vercel, Netlify, Cloudflare Pages / Workers, Render, Fly, GitHub Pages, ... —
then end-to-end checks which of them are still alive.

> 🇫🇷 Farsi version: [README.md](README.md)

No dependencies — Python standard library only.

---

## Auto-updated subscription

https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/refs/heads/main/configs.txt

- refreshed every day at 10:00 UTC (≈ 13:30 Tehran)
- only configs whose domain belongs to a free hosting platform are kept

---

## Project files

| File | Description |
|------|-------------|
| `collector_ui.py` | Graphical interface (Tkinter) — scan, live list, e2e check |
| `collect_railway.py` | Command-line version of the same collector |
| `scripts/collect.py` | Automated collector (publishes `configs.txt`) |
| `sources.txt` | List of subscription sources |
| `configs.txt` | Final auto-generated subscription |
| `.github/workflows/` | Daily automated workflow |
| `requirements.txt` | empty (standard library only) |
| `README.md` / `readmeEN.md` | documentation (Farsi / English) |

---

## Requirements

- Python **3.10+** (tested on 3.13)
- Tkinter — ships with the python.org Windows installer
- internet access to the subscription URLs

```bash
pip install -r requirements.txt   # nothing to install, kept for tooling
```

## Run

```bash
python collector_ui.py     # GUI
python collect_railway.py  # CLI — default source: configs.txt above
```

### CLI examples

```bash
python collect_railway.py SUB_URL [SUB_URL ...] -d railway.app -d vercel.app -o out.txt
python collect_railway.py C:\subs\mylist.txt -d up.railway.app -v
python collect_railway.py SUB_URL --server-only    # ignore sni / ws-host match
python collect_railway.py SUB_URL --timeout 10 --insecure
```

---

## GUI

### 1) Scan

- **Subscriptions** box — one source per line; local `.txt` files work too.
  Default (only): `https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/refs/heads/main/configs.txt`
- **`add sub:`** + `Add` — append more subs one after another (Enter works)
- **`Import subs...`** — pick a `.txt`: its URLs are appended, and if the file
  itself contains configs / base64 it is added as a source too
- **Deploy-site patterns** — comma separated (`railway.app, vercel.app, ...`);
  `*` wildcards and `/regex/` are supported
- `also match sni / ws-host` (on by default) — catches IP-based nodes whose
  `up.railway.app` only appears in the `sni=` / ws `host=` parameter
- rows appear **live** while scanning, with a `%` progress bar

### 2) Check alive (e2e)

TCP connect to the server + HTTP request to the **matched domain**
(optionally through a proxy):

| Status | Meaning |
|--------|---------|
| `LIVE` | HTTP 2xx and no known error page |
| `DEAD` | HTTP 4xx/5xx or a dead page: Railway *"The train has not arrived at the station."*, Vercel `DEPLOYMENT_NOT_FOUND`, Netlify *"Page Not Found"* ... |
| `PORT OPEN` | port accepts TCP but speaks no HTTP |
| `DOWN` | connection refused / timeout / TLS failure |

- `proxy` + `Test` — check through `http://127.0.0.1:10808` (or any proxy)
- `threads` / `timeout` — concurrency and per-host timeout
- progress bar: `checking 12/40 hosts — LIVE 3 DEAD 9 ...` with `%`

### Results panel

- **Site selector (left)** — matched configs grouped by site, e.g.
  `railway.app (120)`, `vercel.app (35)`.
  - `only show` → selecting `railway.app` shows **only** railway.app configs
  - `don't show` → hides that site
  - `off` → ignore the selection
  - **`Live scan site [F7]`** button → alive-checks only the selected site(s);
    rows of every other site are left untouched
- **`LIVE always on top`** (default on) — healthy configs stay at the top of
  the list after every sort / check
- **`show only LIVE`** tick — hide everything that is not `LIVE`
- **`hide duplicates`** tick — one row per node (`type + host + port + domain`);
  when a node appears twice, the `LIVE` copy is the one that stays
- **filter** box — free text over host / domain / type / status / note / source
- counters on top (`LIVE`, `DEAD`, `DOWN`, `PORT-OPEN`, `NEW`) are clickable
  filters; `ALL` clears the filter
- column headers sort (▲/▼)

### Copy commands

| Action | Result |
|--------|--------|
| `Copy all [Ctrl+C]` | with rows selected → copies the **selection**; otherwise every shown config (honours `only LIVE`) |
| `Ctrl+C` | copies selected rows (or all shown if none) |
| double-click | copies the selected row(s) |
| `Alt + click` on a row | copies **only the domain** of that row |
| `Copy domains` button | copies only domains (site from the selector, else full domains of shown rows) |

### Keyboard

`F5` scan · `F6` check alive · `F7` check alive of the selected site · `Esc` stop · `Ctrl+C` copy

### Save

`Save...` writes one config per line (`.txt`) — by default only `LIVE` ones;
untick `only LIVE` to save everything.

---

## Supported subscription formats

- plain text, one link per line
- whole-file base64 (e.g. `All_Configs_base64_Sub.txt`)
- nested (double) base64 and base64 wrapped at ~76 columns
- per-line base64 configs, with or without `#profile-title` headers
- local `.txt` files

## Notes

- Matching is case-insensitive substring/regex against the server address,
  the `sni=` / `peer=` parameter and the ws `host=` parameter.
- The e2e check talks to the **deployment domain**, not the raw IP, so
  Railway / Vercel / Netlify "domain not provisioned" pages are `DEAD`.
- Use responsibly and only on subscriptions you are allowed to access.
