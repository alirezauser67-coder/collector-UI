#!/usr/bin/env python3
"""
Collect free configs whose host / sni / address belong to free hosting platforms.
Updated every 24 hours via GitHub Actions.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import unquote, quote

# ====================== CONFIG ======================

ALLOWED_DOMAINS = [
    "railway.app",
    "vercel.app",
    "netlify.app",
    "pages.dev",
    "workers.dev",
    "onrender.com",
    "fly.dev",
    "glitch.me",
    "herokuapp.com",
    "appspot.com",
    "azurewebsites.net",
    "web.app",
    "firebaseapp.com",
    "deno.dev",
    "r2.dev",
    "supabase.co",
    "cyclic.app",
    "gigalixir.app",
    "koyeb.app",
    "coolify.io",
    "dokploy.com",
]

SOURCES_FILE = "sources.txt"
OUTPUT_FILE = "configs.txt"
OUTPUT_BASE64 = "configs_base64.txt"
PROFILE_TITLE = "notALITREZAconfigs"
PROFILE_URL = "https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/main/configs.txt"  # ← تغییر بده

FETCH_TIMEOUT = 40
FETCH_RETRIES = 3

# ====================================================


def load_sources() -> list[str]:
    if not os.path.exists(SOURCES_FILE):
        print(f"ERROR: {SOURCES_FILE} not found")
        sys.exit(1)
    urls = []
    with open(SOURCES_FILE, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def is_allowed(value: str) -> bool:
    """Check if host/sni/address ends with one of the allowed domains."""
    if not value:
        return False
    value = value.lower().strip()
    for domain in ALLOWED_DOMAINS:
        if value == domain or value.endswith("." + domain):
            return True
    return False


def decode_if_base64(text: str) -> str:
    if "://" in text:
        return text
    compact = "".join(text.split())
    if not compact:
        return text
    try:
        decoded = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=False)
        candidate = decoded.decode("utf-8", "replace")
        return candidate if "://" in candidate else text
    except Exception:
        return text


def fetch(url: str) -> str:
    last_err = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Free-Hosting-Configs/1.0"},
            )
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = e
            print(f"  attempt {attempt}/{FETCH_RETRIES} failed: {e}")
            if attempt < FETCH_RETRIES:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def extract_fields(line: str) -> dict | None:
    """
    Extract host, sni, address from a share link (vless / trojan / vmess).
    Returns dict with keys: host, sni, address, raw
    """
    line = line.strip()
    if not line or line.startswith("#") or "://" not in line:
        return None

    scheme = line.split("://", 1)[0].lower()
    if scheme not in ("vless", "trojan", "vmess"):
        return None

    try:
        if scheme == "vmess":
            # vmess is base64 JSON
            payload = line.split("://", 1)[1].split("#", 1)[0]
            payload += "=" * (-len(payload) % 4)
            data = base64.urlsafe_b64decode(payload.encode()).decode("utf-8", "replace")
            import json
            obj = json.loads(data)
            return {
                "host": str(obj.get("host", "")),
                "sni": str(obj.get("sni", "")),
                "address": str(obj.get("add", "")),
                "raw": line,
            }
        else:
            # vless / trojan
            rest = line.split("://", 1)[1]
            if "#" in rest:
                rest = rest.split("#", 1)[0]

            query = ""
            if "?" in rest:
                rest, query = rest.split("?", 1)

            if "@" in rest:
                _, hostport = rest.rsplit("@", 1)
            else:
                hostport = rest

            # address
            if hostport.startswith("["):
                address = hostport[1:].split("]", 1)[0]
            else:
                address = hostport.rsplit(":", 1)[0]

            # query params
            params = {}
            for part in query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[unquote(k).lower()] = unquote(v)

            return {
                "host": params.get("host", ""),
                "sni": params.get("sni", ""),
                "address": address,
                "raw": line,
            }
    except Exception:
        return None


def main():
    print("=== Free-Hosting-Configs Collector ===")
    sources = load_sources()
    print(f"Loaded {len(sources)} sources")

    all_lines = []
    for i, url in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] Fetching {url}")
        try:
            body = decode_if_base64(fetch(url))
            lines = body.splitlines()
            usable = sum(1 for l in lines if "://" in l)
            print(f"      → {len(lines)} lines, {usable} potential configs")
            all_lines.extend(lines)
        except Exception as e:
            print(f"      ! Failed: {e}")

    print(f"\nTotal lines collected: {len(all_lines)}")

    # Filter
    seen = set()
    kept = []
    for line in all_lines:
        fields = extract_fields(line)
        if not fields:
            continue

        host = fields["host"]
        sni = fields["sni"]
        address = fields["address"]

        if is_allowed(host) or is_allowed(sni) or is_allowed(address):
            # Deduplicate by raw line (simple but effective)
            key = fields["raw"].split("#")[0].strip()  # ignore remark
            if key not in seen:
                seen.add(key)
                kept.append(fields["raw"])

    print(f"Kept after filtering (host/sni/address match): {len(kept)}")

    # Write output
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        f"#profile-title: {PROFILE_TITLE}",
        f"#profile-update-interval: 1",
        f"#profile-web-page-url: {PROFILE_URL}",
        f"# Generated: {stamp}",
        f"# Total configs: {len(kept)}",
        f"# Filter: host / sni / address must belong to free hosting platforms",
        "",
    ]

    content = "\n".join(header + kept) + "\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    # Base64 version
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    with open(OUTPUT_BASE64, "w", encoding="utf-8") as f:
        f.write(b64)

    print(f"\n✓ Written {OUTPUT_FILE} and {OUTPUT_BASE64}")
    print(f"✓ {len(kept)} configs ready")


if __name__ == "__main__":
    main()
