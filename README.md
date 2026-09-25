# V2Ray Deploy-Site Config Collector

Collect v2ray configs (vless / vmess / trojan / ss / ssr / tuic / hysteria2 /
wireguard) from many subscriptions, keep only the ones hosted on a deploy site
(railway, vercel, netlify, pages.dev, ...), then e2e check whether each node is
still alive.

No dependencies — Python standard library only.

## Files

| File              | What it is                                   |
|-------------------|----------------------------------------------|
| `collector_ui.py` | Tkinter GUI (scan, live list, e2e check)     |
| `collect_railway.py` | CLI version of the same collector          |
| `requirements.txt`| empty (stdlib only)                          |

## Requirements

- Python **3.10+** (tested on 3.13)
- Tkinter — included with the python.org installer on Windows
- internet access to the subscription URLs

```
pip install -r requirements.txt   # nothing to install, kept for tooling
```

## Run

```
python collector_ui.py            # GUI
python collect_railway.py         # CLI (default: ebrasha + barry-far lists)
```

### CLI examples

```
python collect_railway.py SUB_URL [SUB_URL ...] -d railway.app -d vercel.app -o out.txt
python collect_railway.py C:\subs\mylist.txt -d up.railway.app -v
python collect_railway.py SUB_URL --server-only        # ignore sni/ws-host match
python collect_railway.py SUB_URL --timeout 10 --insecure
```

## GUI

### 1) Scan

- **Subscriptions** box: one URL per line (local `.txt` files work too).
- **`add sub:`** entry + `Add` — append more subs one after another (Enter works).
- **`Import subs...`** — pick a `.txt`; its URLs are appended, and if the file
  itself contains configs / base64 it is added as a source too.
- **Deploy-site patterns** box: comma separated (`railway.app, vercel.app, ...`).
  `*` wildcards and `/regex/` are supported.
- `also match sni / ws-host` (default on) — catches IP-based nodes whose
  `up.railway.app` only appears in the SNI / ws `host` parameter.
- Rows appear **live** while scanning, with a `%` progress bar.

### 2) Check alive (e2e)

Runs `TCP connect` to the server, then an HTTP request to the **matched domain**
(optionally through a proxy) and classifies:

| Status     | Meaning                                                        |
|------------|----------------------------------------------------------------|
| `LIVE`     | HTTP 2xx and no known error page                               |
| `DEAD`     | HTTP 4xx/5xx or a dead page: Railway "The train has not arrived at the station.", Vercel `DEPLOYMENT_NOT_FOUND`, Netlify "Page Not Found", ... |
| `PORT OPEN`| server port accepts TCP but speaks no HTTP                     |
| `DOWN`     | connection refused / timed out / TLS failure                   |

- `proxy` + `Test` — use `http://127.0.0.1:10808` (or any proxy) for the check.
- `threads` / `timeout` — concurrency and per-host timeout (seconds).
- Progress bar shows `checking 12/40 hosts — LIVE 3 DEAD 9 ...` with `%`.

### Results panel

- **Domain list (left)** — every matched domain with its config count.
  - `only show`  → selecting a domain shows only that domain
  - `don't show` → selecting a domain hides it
  - `off`        → ignore the selection
- **filter** box — free text over host / domain / type / status / note / source.
- Counters on top (`LIVE`, `DEAD`, `DOWN`, `PORT-OPEN`, `NEW`) are clickable
  filters; `ALL` clears the filter.
- Column headers sort (▲/▼); double-click copies the config link.

### Copy commands

| Action                     | Result                                      |
|----------------------------|---------------------------------------------|
| `Copy all  [Ctrl+C]`       | copies all shown configs (honours `only LIVE`) |
| `Ctrl+C`                   | copies selected rows (or all shown)         |
| `Alt + click` on a row     | copies **only the domain** of that row      |
| `Copy domains` button      | copies only domains (list selection, else all shown) |
| double-click               | copies that one config                      |

### Keyboard

`F5` scan · `F6` check alive · `Esc` stop · `Ctrl+C` copy

### Save

`Save...` writes one config per line (`.txt`), by default only `LIVE` ones —
untick `only LIVE` to save everything.

## Supported subscription formats

- plain text, one link per line
- whole-file base64 (e.g. `All_Configs_base64_Sub.txt`)
- nested (double) base64
- per-line base64 configs, with or without `#profile-title` headers
- local `.txt` files

## Notes

- Matching is case-insensitive substring/regex against the server address,
  the `sni=` / `peer=` parameter and the ws `host=` parameter.
- The e2e check talks to the **deployment domain**, not the raw IP, so Railway /
  Vercel / Netlify "domain not provisioned" pages are detected as `DEAD`.
- Use responsibly and only on subscriptions you are allowed to access.
