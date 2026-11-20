# V2Ray / Xray Config Collector

> [Persian version](README.md)

A simple desktop app for collecting V2Ray and Xray configs, finding configs hosted on free platforms, and checking whether they are alive.

## Features

- Supports plain text, Base64, local files, and multiple subscriptions
- Supports `vless`, `vmess`, `trojan`, `ss`, `ssr`, `tuic`, `hysteria2`, and `wireguard`
- Filters configs by free hosting domain
- Uses TCP and HTTP checks to show `LIVE`, `DEAD`, `DOWN`, and `PORT OPEN`
- Filter, sort, copy, and save results
- Includes dark and light themes

## Subscription link

```text
https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/refs/heads/main/configs.txt
```

This file updates automatically every day at 10:00 UTC. The `e2econfig.txt` file keeps the configs that passed the health check.

## Requirements

- Python 3.10+
- Tkinter, included with the official Python installer for Windows
- Internet access

No third-party packages are required.

## Run

```powershell
python collector_ui.py
```

To run the automatic collector manually:

```powershell
python scripts/collect.py
```

## Quick guide

1. Press `F5` to scan subscription sources.
2. Press `F6` to check whether the found configs are alive.
3. Use filters and the site selector to find the results you need.
4. Double-click or press `Ctrl+C` to copy a result, then use `Save...` to export it.

| Status | Meaning |
|---|---|
| `LIVE` | The HTTP request succeeded |
| `DEAD` | The site or service returned an error |
| `DOWN` | The connection failed or timed out |
| `PORT OPEN` | The port is open, but no HTTP response was received |

## Shortcuts

`F5` scan · `F6` check alive · `F7` check selected site · `Esc` stop · `Ctrl+C` copy

## Important files

- `collector_ui.py`: graphical application
- `scripts/collect.py`: automatic collector
- `sources.txt`: subscription sources
- `configs.txt`: automatic output

Only use sources that you are allowed to access.
