# V2Ray Deploy-Site Config Collector

A tool that collects free V2Ray / Xray configs hosted on free deployment platforms  
(Railway, Vercel, Netlify, Cloudflare Pages, Workers, and more).

This project has two parts:

1. **GUI version** – for manual use  
2. **Automated version** – collects and publishes configs every 24 hours

---

## Auto-Updated Subscription Link
https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/main/configs.txt

- Updates every day at 10:00 UTC
- Only keeps configs whose domain belongs to free hosting platforms

---

## Project Files

| File | Description |
|------|-------------|
| `collector_ui.py` | Graphical interface (Tkinter) |
| `scripts/collect.py` | Automated collector script |
| `sources.txt` | List of subscription sources |
| `configs.txt` | Final subscription output |
| `.github/workflows/build.yml` | Daily automated workflow |

---

## Requirements

- Python **3.10+**
- Tkinter (included with official Python installer on Windows)
- Internet connection

```bash
pip install -r requirements.txt
