#!/usr/bin/env python3
"""Tkinter UI: collect v2ray configs from many subscriptions, filter by deploy-site
domains (railway / vercel / netlify / ...), and live e2e check whether each node works.

- many subscription URLs at once (plain / base64 / per-line base64 subs)
- matches server address AND sni / ws-host params (IP nodes with railway SNI)
- live result rows, progress bar with % for scan and for alive-check
- e2e HTTP check with dead-page detection (Railway "The train has not arrived at
  the station.", Vercel/Netlify "Not Found", deployment-not-found ...)
- optional proxy (default http://127.0.0.1:10808) for the check + "Test proxy"
- filter box, clickable status counters, column sort, double-click = copy config

Run:  python collector_ui.py
"""

import concurrent.futures
import base64
import json
import os
import queue
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, unquote, urlsplit
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

# --- inlined from collect_railway.py so this file runs on its own ---

DEFAULT_SUBSCRIPTIONS = [
    "https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/refs/heads/main/configs.txt",
]

SCHEMES = (
    "vless://", "vmess://", "trojan://", "ss://", "ssr://",
    "tuic://", "hysteria2://", "hy2://", "hysteria://", "wireguard://",
)

B64_RE = re.compile(r"^[A-Za-z0-9+/=_-]+$")

LINK_LINE_RE = re.compile(
    r"(?im)^\s*(vless|vmess|trojan|ss|ssr|tuic|hysteria2?|hy2|wireguard)://")


def b64d(data: str) -> bytes | None:
    data = data.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    if not data:
        return None
    data += "=" * (-len(data) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(data)
        except Exception:
            continue
    return None


def http_get(url: str, timeout: float, insecure: bool) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36"),
        "Accept": "*/*",
    })
    ctx = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def fetch_source(url: str, timeout: float = 30.0, insecure: bool = False) -> str:
    """Read a subscription from an http(s) URL or from a local .txt file."""
    if url.lower().startswith(("http://", "https://")):
        return http_get(url, timeout, insecure).decode("utf-8", "ignore")
    path = url.strip().strip("\"'")
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def looks_like_b64_line_list(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    ok = sum(1 for l in lines
             if len(l) > 24 and not l.startswith("#") and B64_RE.match(l))
    return ok >= max(2, int(0.7 * len(lines)))


def _b64_like(text: str) -> bool:
    return len(text) > 16 and bool(B64_RE.match(text))


def normalize_subscription(text: str) -> str:
    """Handle plain links, base64 blob, wrapped/nested base64, per-line base64."""
    text = text.strip().lstrip("﻿")
    for _ in range(4):
        if LINK_LINE_RE.search(text):
            return text
        if looks_like_b64_line_list(text):
            # either per-line base64 configs, or a blob wrapped at ~76 columns:
            # decode both ways and keep whichever yields more config links
            per_line = split_links(text)
            joined = b64d("".join(text.split()))
            inner = joined.decode("utf-8", "ignore") if joined else ""
            if inner:
                joined_links = split_links(inner)
                if len(joined_links) > len(per_line):
                    text = inner
                    continue
            return text
        decoded = b64d(text)
        if not decoded:
            return text
        inner = decoded.decode("utf-8", "ignore").strip()
        if not inner or inner == text:
            return text
        if not (LINK_LINE_RE.search(inner) or _b64_like(inner)
                or inner.count("://") >= 2):
            return text                      # decoding was wrong: keep original
        text = inner
    return text


def split_links(text: str, _depth: int = 0) -> list[str]:
    links: list[str] = []
    for chunk in re.split(r"[\r\n\s]+", text):
        chunk = chunk.strip().strip("'\";,")
        if not chunk:
            continue
        if chunk.lower().startswith(SCHEMES):
            links.append(chunk)
            continue
        if _depth >= 3 or not (len(chunk) > 24 and B64_RE.match(chunk)):
            continue
        decoded = b64d(chunk)
        if not decoded:
            continue
        inner = decoded.decode("utf-8", "ignore").strip()
        if not inner:
            continue
        if inner.lower().startswith(SCHEMES):
            links.append(inner)
        elif "://" in inner or looks_like_b64_line_list(inner):
            links.extend(split_links(inner, _depth + 1))
    return links


def link_fields(link: str) -> dict:
    """Return host/sni/host-header of a config link (best effort)."""
    scheme = link.split("://", 1)[0].lower()
    fields = {"host": "", "sni": "", "header_host": "", "port": ""}

    if scheme == "vmess":
        payload = link.split("://", 1)[1].split("#", 1)[0]
        raw = b64d(payload)
        if not raw:
            return fields
        try:
            obj = json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            return fields
        fields["host"] = str(obj.get("add") or "")
        fields["port"] = str(obj.get("port") or "")
        fields["sni"] = str(obj.get("sni") or obj.get("host") or "")
        return fields

    if scheme == "ssr":
        payload = link.split("://", 1)[1].split("#", 1)[0]
        raw = b64d(payload)
        if raw:
            body = raw.decode("utf-8", "ignore")
            if ":" in body:
                fields["host"] = (body.rsplit(":", 1)[0]
                                  .rsplit("/", 1)[-1].split(":")[0])
        return fields

    try:
        parts = urlsplit(link)
        fields["host"] = parts.hostname or ""
        fields["port"] = str(parts.port or "")
        qs = parse_qs(parts.query)
        get = lambda k: (qs.get(k) or [""])[0]
        fields["sni"] = get("sni") or get("peer") or get("servername")
        fields["header_host"] = get("host")
        if not fields["header_host"] and parts.query:
            fields["header_host"] = parse_qs(
                unquote(parts.query)).get("host", [""])[0]
    except Exception:
        pass
    return fields


# ------------------------------------------------------- end inlined section

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

DEFAULT_PATTERNS = (
    "railway.app, vercel.app, netlify.app, pages.dev, workers.dev, onrender.com, "
    "fly.dev, glitch.me, herokuapp.com, appspot.com, azurewebsites.net, web.app, "
    "firebaseapp.com, deno.dev, r2.dev, supabase.co, cyclic.app, gigalixir.app, "
    "koyeb.app, coolify.io, dokploy.com"
)

DEAD_MARKERS = [
    "the train has not arrived at the station",
    "hasn't left the station",
    "domain has provisioned",
    "deployment_not_found",
    "this deployment has been removed",
    "your page could not be found",
    "404 | not found",
    "not found - request id",
    "page not found",
    "service not found",
    "no such app",
    "application error",
    "there is nothing here",
    "does not exist",
    "doesn't exist",
    "no web site is configured",
]

STATUSES = ("NEW", "CHECKING", "LIVE", "DEAD", "DOWN", "PORT OPEN")


# ---------------------------------------------------------------- core logic
def parse_patterns(text: str) -> list[re.Pattern]:
    out = []
    for part in text.split(","):
        part = part.strip().lower()
        if not part or part.startswith("#"):
            continue
        if part.startswith("/") and part.endswith("/") and len(part) > 2:
            rx = part[1:-1]
        elif "*" in part:
            rx = re.escape(part).replace(r"\*", ".*")
        else:
            rx = re.escape(part)
        out.append(re.compile(rx))
    return out


def match_deploy(value: str, patterns: list[re.Pattern]) -> bool:
    value = (value or "").lower()
    return bool(value) and any(p.search(value) for p in patterns)


def site_of(domain: str) -> str:
    """x.up.railway.app -> railway.app  (group selector value)."""
    domain = (domain or "").strip().lower()
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def find_match(fields: dict, patterns: list[re.Pattern],
               match_any: bool) -> str:
    """Return the deploy domain found in server / sni / ws-host (or "")."""
    for key in ("host",) + (("sni", "header_host") if match_any else ()):
        value = (fields.get(key) or "").strip()
        if match_deploy(value, patterns):
            return value.split(",")[0].strip()
    return ""


def tcp_open(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def http_probe(host: str, port: int, timeout: float,
               use_proxy: bool, proxy_url: str) -> tuple[int | None, str, str]:
    handlers: list = []
    if use_proxy and proxy_url:
        handlers.append(urllib.request.ProxyHandler(
            {"http": proxy_url, "https": proxy_url}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    handlers.append(urllib.request.HTTPSHandler(
        context=ssl._create_unverified_context()))
    opener = urllib.request.build_opener(*handlers)

    schemes = ["https", "http"] if port in (80, 8080, 8000, 8888) else ["https"]
    last_err = ""
    for scheme in schemes:
        req = urllib.request.Request(f"{scheme}://{host}:{port}/",
                                     headers={"User-Agent": UA})
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read(20000).decode("utf-8", "ignore"), ""
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(20000)
            except Exception:
                pass
            return exc.code, body.decode("utf-8", "ignore"), ""
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
    return None, "", last_err


def evaluate(status: int | None, body: str, tcp_ok: bool, err: str) -> tuple[str, str]:
    low = body.lower()
    for marker in DEAD_MARKERS:
        if marker in low:
            return "DEAD", f"dead page: {marker[:45]}"
    if status is not None:
        if status >= 400:
            return "DEAD", f"HTTP {status}"
        return "LIVE", f"HTTP {status}"
    if tcp_ok:
        return "PORT OPEN", "port open, no HTTP"
    return "DOWN", err or "connection failed"


def proxy_works(proxy_url: str, timeout: float) -> tuple[bool, str]:
    handler = urllib.request.ProxyHandler(
        {"http": proxy_url, "https": proxy_url})
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request("http://www.gstatic.com/generate_204",
                                 headers={"User-Agent": UA})
    try:
        started = time.time()
        with opener.open(req, timeout=timeout) as resp:
            return (resp.status == 204 or resp.status == 200,
                    f"HTTP {resp.status} in {time.time() - started:.2f}s")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- UI
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("V2Ray Deploy-Site Collector + E2E Checker")
        root.geometry("1320x840")
        root.minsize(960, 620)

        self.q: queue.Queue = queue.Queue()
        self.stop_evt = threading.Event()
        self.busy = False
        self.rows: list[dict] = []
        self.seen: set[str] = set()
        self.sort_col = "domain"
        self.sort_desc = False

        self.filter_var = tk.StringVar()
        self.total_var = tk.StringVar(value="TOTAL 0")
        self.live_var = tk.StringVar(value="LIVE 0")
        self.dead_var = tk.StringVar(value="DEAD 0")
        self.down_var = tk.StringVar(value="DOWN 0")
        self.port_var = tk.StringVar(value="PORT-OPEN 0")
        self.new_var = tk.StringVar(value="NEW 0")
        self.scanned_var = tk.StringVar(value="scanned 0")
        self.pct_var = tk.StringVar(value="0%")
        self.status_var = tk.StringVar(value="ready")

        self._styles(root)
        self._build(root)
        self.root.after(50, self._poll)

    # ---------------- styles / layout ----------------
    @staticmethod
    def _styles(root):
        try:
            ttk.Style(root).theme_use("clam")
        except Exception:
            pass
        s = ttk.Style(root)
        s.configure("TButton", padding=(10, 4))
        s.configure("Primary.TButton", padding=(12, 5), font=("Segoe UI", 9, "bold"))
        s.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        s.configure("Sub.TLabel", font=("Segoe UI", 9))
        s.configure("Badge.TLabel", font=("Consolas", 10, "bold"), padding=(9, 3))
        s.configure("LiveBadge.TLabel", foreground="#0a7d2f")
        s.configure("DeadBadge.TLabel", foreground="#c1121f")
        s.configure("DownBadge.TLabel", foreground="#b26a00")
        s.configure("PortBadge.TLabel", foreground="#444444")
        s.configure("NewBadge.TLabel", foreground="#0057b8")
        s.configure("Treeview", rowheight=21, font=("Consolas", 9))
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        s.configure("status.TLabel", font=("Segoe UI", 9))

    def _build(self, root):
        # ---------- header ----------
        head = ttk.Frame(root, padding=(10, 8, 10, 4))
        head.pack(fill="x")
        ttk.Label(head, text="V2Ray Deploy-Site Config Collector",
                  style="Header.TLabel").pack(side="left")
        badges = ttk.Frame(head)
        badges.pack(side="right")
        specs = (
            ("total", self.total_var, "", None),
            ("live", self.live_var, "LIVE", "LiveBadge.TLabel"),
            ("dead", self.dead_var, "DEAD", "DeadBadge.TLabel"),
            ("down", self.down_var, "DOWN", "DownBadge.TLabel"),
            ("port", self.port_var, "PORT OPEN", "PortBadge.TLabel"),
            ("new", self.new_var, "", "NewBadge.TLabel"),
            ("all", tk.StringVar(value="ALL"), "", None),
        )
        for key, var, quick, style in specs:
            b = ttk.Label(badges, textvariable=var, style=style or "Badge.TLabel",
                          relief="ridge", cursor="hand2")
            b.pack(side="left", padx=2)
            if quick:
                b.bind("<Button-1>", lambda e, c=quick: self._quick_filter(c))
            elif key == "all":
                b.bind("<Button-1>", lambda e: self.filter_var.set(""))
                b.bind("<Enter>", lambda e: b.configure(relief="sunken"))
                b.bind("<Leave>", lambda e: b.configure(relief="ridge"))
            self.badges = getattr(self, "badges", {})
            self.badges[key] = b

        # ---------- toolbar ----------
        bar = ttk.Frame(root, padding=(10, 4))
        bar.pack(fill="x")
        self.b_scan = ttk.Button(bar, text="1) Scan subscriptions  [F5]",
                                 command=self.start_scan, style="Primary.TButton")
        self.b_scan.pack(side="left")
        self.b_check = ttk.Button(bar, text="2) Check alive  [F6]",
                                  command=self.start_check, style="Primary.TButton")
        self.b_check.pack(side="left", padx=4)
        self.b_stop = ttk.Button(bar, text="Stop", command=self.stop,
                                 state="disabled")
        self.b_stop.pack(side="left", padx=4)
        self.b_clear = ttk.Button(bar, text="Clear", command=self.clear)
        self.b_clear.pack(side="left", padx=4)
        ttk.Button(bar, text="Copy all  [Ctrl+C]",
                   command=self.copy_all).pack(side="left", padx=4)
        ttk.Button(bar, text="Save...", command=self.save).pack(side="left", padx=4)
        self.only_alive = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="only LIVE",
                        variable=self.only_alive).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="Import subs...", command=self.import_subs).pack(
            side="left", padx=(0, 8))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.match_any = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="also match sni / ws-host",
                        variable=self.match_any).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.use_proxy = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="proxy", variable=self.use_proxy).pack(side="left")
        self.proxy_url = tk.StringVar(value="http://127.0.0.1:10808")
        ttk.Entry(bar, textvariable=self.proxy_url, width=19).pack(side="left")
        ttk.Button(bar, text="Test", width=5,
                   command=self.test_proxy).pack(side="left", padx=2)
        ttk.Label(bar, text="threads").pack(side="left", padx=(8, 2))
        self.threads = tk.IntVar(value=20)
        ttk.Spinbox(bar, from_=1, to=100, textvariable=self.threads,
                    width=4).pack(side="left")
        ttk.Label(bar, text="timeout").pack(side="left", padx=(8, 2))
        self.timeout = tk.DoubleVar(value=6.0)
        ttk.Spinbox(bar, from_=1, to=30, textvariable=self.timeout,
                    width=4).pack(side="left")

        # ---------- main panes ----------
        paned = ttk.Panedwindow(root, orient="vertical")
        paned.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        setup = ttk.Frame(paned)
        paned.add(setup, weight=2)
        left = ttk.LabelFrame(setup, text=" Subscriptions — one URL per line ",
                              padding=4)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.subs = tk.Text(left, height=6, wrap="none", font=("Consolas", 9))
        ssb = ttk.Scrollbar(left, orient="vertical", command=self.subs.yview)
        self.subs.configure(yscrollcommand=ssb.set)
        ssb.pack(side="right", fill="y")
        self.subs.pack(fill="both", expand=True)
        self.subs.insert("1.0", "\n".join(DEFAULT_SUBSCRIPTIONS))
        addf = ttk.Frame(left)
        addf.pack(fill="x", pady=(4, 0))
        ttk.Label(addf, text="add sub:").pack(side="left")
        self.new_sub = tk.StringVar()
        ent = ttk.Entry(addf, textvariable=self.new_sub)
        ent.pack(side="left", fill="x", expand=True, padx=4)
        ent.bind("<Return>", lambda e: self.add_subs())
        ttk.Button(addf, text="Add", command=self.add_subs).pack(side="left")

        right = ttk.LabelFrame(setup, text=" Deploy-site patterns (comma) ",
                               padding=4)
        right.pack(side="left", fill="both", expand=True)
        self.pats = tk.Text(right, height=6, wrap="word", font=("Consolas", 9))
        self.pats.pack(fill="both", expand=True)
        self.pats.insert("1.0", DEFAULT_PATTERNS)

        res = ttk.LabelFrame(paned, text=" Results (live) ", padding=4)
        paned.add(res, weight=4)
        rf = ttk.Frame(res)
        rf.pack(fill="x")
        ttk.Label(rf, text="filter:").pack(side="left")
        self.filter_var.trace_add("write", lambda *_: self._render())
        ttk.Entry(rf, textvariable=self.filter_var, width=28).pack(
            side="left", padx=4)
        self.live_top = tk.BooleanVar(value=True)
        ttk.Checkbutton(rf, text="LIVE always on top",
                        variable=self.live_top,
                        command=self._render).pack(side="left", padx=(8, 0))
        self.show_live = tk.BooleanVar(value=False)
        ttk.Checkbutton(rf, text="show only LIVE",
                        variable=self.show_live,
                        command=self._render).pack(side="left", padx=(8, 0))
        self.hide_dup = tk.BooleanVar(value=False)
        ttk.Checkbutton(rf, text="hide duplicates",
                        variable=self.hide_dup,
                        command=self._render).pack(side="left", padx=(8, 0))
        self.matched_var = tk.StringVar(value="")
        ttk.Label(rf, textvariable=self.matched_var, style="Sub.TLabel").pack(
            side="left", padx=8)
        ttk.Label(rf, text="double-click = copy link   |   Alt+click row = copy "
                           "domain   |   Ctrl+C = copy   |   click a column "
                           "header to sort",
                  style="Sub.TLabel").pack(side="right")

        hf = ttk.Panedwindow(res, orient="horizontal")
        hf.pack(fill="both", expand=True, pady=(4, 0))

        # ---- domain list: select a domain -> show only it (or exclude it) ----
        dpanel = ttk.LabelFrame(
            hf, text=" Sites — pick railway.app / vercel.app ... to show only "
                     "that site ", padding=4)
        hf.add(dpanel, weight=0)
        dlistf = ttk.Frame(dpanel)
        dlistf.pack(fill="both", expand=True)
        self.domain_list = tk.Listbox(dlistf, exportselection=False,
                                      font=("Consolas", 9), width=34,
                                      selectmode="extended", height=10,
                                      activestyle="dotbox")
        dsb = ttk.Scrollbar(dlistf, orient="vertical",
                            command=self.domain_list.yview)
        self.domain_list.configure(yscrollcommand=dsb.set)
        dsb.pack(side="right", fill="y")
        self.domain_list.pack(fill="both", expand=True)
        self.domain_list.bind("<<ListboxSelect>>", self._on_domain_select)

        modef = ttk.Frame(dpanel)
        modef.pack(fill="x", pady=(5, 0))
        self.domain_mode = tk.StringVar(value="only")
        ttk.Label(modef, text="mode:").pack(side="left")
        for val, label in (("only", "only show"), ("exclude", "don't show"),
                           ("off", "off")):
            ttk.Radiobutton(modef, text=label, value=val,
                            variable=self.domain_mode,
                            command=self._render).pack(side="left", padx=(4, 0))
        btns = ttk.Frame(dpanel)
        btns.pack(fill="x", pady=(5, 0))
        ttk.Button(btns, text="Copy domains", command=self.copy_domains).pack(
            fill="x")
        self.domains_var = tk.StringVar(value="0 sites")
        ttk.Label(dpanel, textvariable=self.domains_var,
                  style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        # ---- results table ----
        tf = ttk.Frame(hf)
        hf.add(tf, weight=1)
        cols = ("type", "host", "port", "domain", "status", "note", "source")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 selectmode="extended")
        widths = {"type": 65, "host": 210, "port": 50, "domain": 250,
                  "status": 95, "note": 230, "source": 150}
        for c in cols:
            self.tree.heading(c, text=c.upper(),
                              command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        for tag, color in (("LIVE", "#0a7d2f"), ("DEAD", "#c1121f"),
                           ("DOWN", "#b26a00"), ("PORT OPEN", "#555555"),
                           ("CHECKING", "#0057b8"), ("NEW", "#444444")):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure("alt", background="#f4f6fa")
        self.tree.bind("<Double-1>", self._copy_row)
        self.tree.bind("<Button-1>", self._on_tree_click)

        self._domain_items: list[str] = []

        logf = ttk.LabelFrame(paned, text=" Log ", padding=4)
        paned.add(logf, weight=1)
        self.log = tk.Text(logf, height=7, state="disabled", bg="#141414",
                           fg="#d7d7d7", font=("Consolas", 9))
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        # ---------- status / progress ----------
        foot = ttk.Frame(root, padding=(10, 5))
        foot.pack(fill="x")
        self.pbar = ttk.Progressbar(foot, length=280, maximum=100)
        self.pbar.pack(side="left")
        ttk.Label(foot, textvariable=self.pct_var, width=5,
                  style="Badge.TLabel").pack(side="left", padx=(6, 10))
        ttk.Label(foot, textvariable=self.scanned_var,
                  style="Badge.TLabel", relief="ridge").pack(side="left",
                                                             padx=(0, 8))
        ttk.Label(foot, textvariable=self.status_var,
                  style="status.TLabel").pack(side="left", fill="x", expand=True)

        root.bind("<F5>", lambda e: self.start_scan())
        root.bind("<F6>", lambda e: self.start_check())
        root.bind("<Escape>", lambda e: self.stop())
        root.bind("<Control-c>", self._on_ctrl_c)
        root.bind("<Control-C>", self._on_ctrl_c)

    # ---------------- helpers ----------------
    def log_line(self, text: str):
        self.q.put(("log", text))

    def _quick_filter(self, status: str):
        self.filter_var.set("" if self.filter_var.get() == status else status)

    def _match_text(self, r: dict) -> str:
        return (r["host"] + r["domain"] + r["type"] + r["status"] +
                r["note"] + r["source"]).lower()

    def _selected_domains(self) -> set[str]:
        return {self._domain_items[i]
                for i in self.domain_list.curselection()
                if i < len(self._domain_items)}

    def _domain_ctx(self) -> tuple[set[str], str]:
        mode = self.domain_mode.get()
        return (self._selected_domains(), mode if mode != "off" else "")

    def _passes(self, r: dict, sel: set[str], mode: str,
                show_live: bool | None = None) -> bool:
        if (self.show_live.get() if show_live is None else show_live) \
                and r.get("status") != "LIVE":
            return False
        needle = self.filter_var.get().strip().lower()
        if needle and needle not in self._match_text(r):
            return False
        if sel and mode:
            site = site_of(r.get("domain", ""))
            if mode == "only" and site not in sel:
                return False
            if mode == "exclude" and site in sel:
                return False
        return True

    @staticmethod
    def _dup_key(r: dict) -> str:
        host = (r.get("host") or "").lower()
        port = r.get("port") or ""
        domain = (r.get("domain") or "").lower()
        if host or domain:
            return f"{r.get('type', '')}|{host}|{port}|{domain}"
        return r.get("link", "")

    def _dedupe(self, idxs: list[int]) -> list[int]:
        """One row per node; a LIVE row wins over a DEAD/NEW duplicate."""
        best: dict[str, int] = {}
        for i in idxs:
            key = self._dup_key(self.rows[i])
            current = best.get(key)
            if current is None:
                best[key] = i
            elif (self.rows[i]["status"] == "LIVE"
                  and self.rows[current]["status"] != "LIVE"):
                best[key] = i
        return sorted(best.values())

    def _visible(self) -> list[int]:
        sel, mode = self._domain_ctx()
        show_live = bool(self.show_live.get())
        idxs = [i for i, r in enumerate(self.rows)
                if self._passes(r, sel, mode, show_live)]
        if self.hide_dup.get():
            idxs = self._dedupe(idxs)
        key = self.sort_col
        idxs.sort(key=lambda i: (str(self.rows[i].get(key, "")).lower(), i),
                  reverse=self.sort_desc)
        if self.live_top.get():
            idxs.sort(key=lambda i: 0 if self.rows[i]["status"] == "LIVE" else 1)
        return idxs

    def _sync_domains(self):
        counts: dict[str, int] = {}
        for r in self.rows:
            d = site_of(r.get("domain") or r.get("host") or "?")
            counts[d] = counts.get(d, 0) + 1
        if counts == getattr(self, "_domain_counts", None):
            return
        self._domain_counts = counts
        selected = self._selected_domains()
        items = sorted(counts, key=lambda d: (-counts[d], d))
        self._domain_items = items
        self.domain_list.delete(0, "end")
        for d in items:
            self.domain_list.insert("end", f"{d}   ({counts[d]})")
        for i, d in enumerate(items):
            if d in selected:
                self.domain_list.selection_set(i)
        self.domains_var.set(f"{len(items)} sites")

    def _on_domain_select(self, _event=None):
        self._render()

    def copy_domains(self):
        """Copy only the domains (selected in the list, else shown rows)."""
        sel = self._selected_domains()
        if sel:
            picked, what = sorted(sel), "copy domains (selected)"
        else:
            picked = sorted({self.rows[i].get("domain")
                             for i in self._visible()
                             if self.rows[i].get("domain")})
            what = "copy domains (shown)"
        self._to_clipboard(picked, what, noun="domains")

    def _on_tree_click(self, event):
        """Alt + click a row -> copy only that domain."""
        if not (event.state & 0x20000):
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        domain = self.rows[int(iid)].get("domain") or ""
        self._to_clipboard([domain] if domain else [],
                           "Alt+click -> domain", noun="domain")
        return None

    @staticmethod
    def _append_line(widget: tk.Text, line: str):
        """Append a full line (Tk 'end' index sits on the last line)."""
        body = widget.get("1.0", "end -1c")
        if body and not body.endswith("\n"):
            widget.insert("end", "\n")
        widget.insert("end", line + "\n")

    def add_subs(self):
        """Append subscription URLs one after another (Enter or Add)."""
        raw = self.new_sub.get().strip()
        if not raw:
            return
        existing = {u.strip() for u in self.subs.get("1.0", "end").splitlines()}
        added = 0
        for part in re.split(r"[\s,;]+", raw):
            part = part.strip().strip("'\"")
            if not part:
                continue
            if (part.startswith("http") or os.path.isfile(part)) \
                    and part not in existing:
                self._append_line(self.subs, part)
                existing.add(part)
                added += 1
        self.new_sub.set("")
        total = sum(1 for u in existing
                    if u.startswith("http") or os.path.isfile(u))
        self.log_line(f"[+] added {added} source(s) — {total} total in list"
                      if added else "[-] no new URL / file found")
        self.subs.see("end")

    @staticmethod
    def _values(r: dict) -> tuple:
        return (r["type"], r["host"], r["port"], r["domain"], r["status"],
                r["note"], r["source"])

    def _render(self):
        keep = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        visible: set[str] = set()
        for n, i in enumerate(self._visible()):
            r = self.rows[i]
            tags = (r["status"],) + (("alt",) if n % 2 else ())
            iid = str(i)
            self.tree.insert("", "end", iid=iid, values=self._values(r),
                             tags=tags)
            visible.add(iid)
        restored = [iid for iid in keep if iid in visible]
        if restored:
            self.tree.selection_set(restored)
        self.matched_var.set(f"{len(visible)} shown")

    def _sort_by(self, col: str):
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, False
        arrow = " ▼" if self.sort_desc else " ▲"
        for c in self.tree["columns"]:
            text = c.upper()
            self.tree.heading(c, text=text + (arrow if c == col else ""))
        self._render()

    def _copy_row(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        links = [self.rows[int(i)]["link"] for i in sel]
        self._to_clipboard(links, f"double-click ({len(links)} selected)"
                           if len(links) > 1 else "double-click")

    def _to_clipboard(self, links: list[str], what: str, noun: str = "configs"):
        if not links:
            self.status_var.set("nothing to copy")
            self.log_line(f"[-] {what}: nothing to copy")
            return
        text = "\n".join(links)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"copied {len(links)} {noun} to clipboard")
        self.log_line(f"[+] {what}: copied {len(links)} {noun} to clipboard "
                      f"({len(text)} chars)")

    def copy_all(self):
        """Copy selected rows, or every visible row if none are selected."""
        if self.tree.selection():
            return self.copy_selected()
        idxs = self._visible()
        only_alive = bool(self.only_alive.get())
        links = [self.rows[i]["link"] for i in idxs
                 if not only_alive or self.rows[i]["status"] == "LIVE"]
        if only_alive and not links and idxs:
            links = [self.rows[i]["link"] for i in idxs]
            self.log_line("[i] no LIVE rows yet — copied all shown rows")
            only_alive = False
        self._to_clipboard(links, "copy all" + (" (LIVE)" if only_alive else ""))

    def _on_ctrl_c(self, _event=None):
        if isinstance(self.root.focus_get(), (tk.Text, tk.Entry, tk.Spinbox)):
            return None  # keep normal copy inside text boxes
        self.copy_selected()
        return "break"

    def copy_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.copy_all()
            return
        self._to_clipboard([self.rows[int(i)]["link"] for i in sel],
                           f"copy selected ({len(sel)})")

    def _update_stats(self):
        counts = {s: 0 for s in STATUSES}
        for r in self.rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        self.total_var.set(f"TOTAL {len(self.rows)}")
        self.live_var.set(f"LIVE {counts['LIVE']}")
        self.dead_var.set(f"DEAD {counts['DEAD']}")
        self.down_var.set(f"DOWN {counts['DOWN']}")
        self.port_var.set(f"PORT-OPEN {counts['PORT OPEN']}")
        self.new_var.set(f"NEW {counts['NEW'] + counts['CHECKING']}")

    def _poll(self):
        dirty = False
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", msg[1] + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "row":
                    idx = len(self.rows)
                    self.rows.append(msg[1])
                    r = self.rows[idx]
                    if self._passes(r, *self._domain_ctx()):
                        if str(idx) not in self.tree.get_children():
                            self.tree.insert("", "end", iid=str(idx),
                                             values=self._values(r),
                                             tags=(r["status"],))
                    dirty = True
                elif kind == "status_row":
                    i, status, note = msg[1], msg[2], msg[3]
                    self.rows[i]["status"] = status
                    self.rows[i]["note"] = note
                    if str(i) in self.tree.get_children():
                        self.tree.item(str(i), values=self._values(self.rows[i]),
                                       tags=(status,))
                    dirty = True
                elif kind == "progress":
                    self.pbar["value"] = msg[1]
                    self.pct_var.set(f"{msg[1]:.0f}%")
                    self.status_var.set(msg[2])
                elif kind == "scanned":
                    self.scanned_var.set(f"scanned {msg[1]}")
                elif kind == "done":
                    self._set_busy(False)
                    self.pbar["value"] = 0 if msg[2] else 100
                    self.pct_var.set("0%" if msg[2] else "100%")
                    self.status_var.set(msg[1])
                    self._render()   # LIVE rows jump to the top
        except queue.Empty:
            pass
        if dirty:
            self._update_stats()
            self._sync_domains()
            self.matched_var.set(f"{len(self.tree.get_children())} shown")
        self.root.after(50, self._poll)

    def _set_busy(self, busy: bool):
        self.busy = busy
        st = "disabled" if busy else "normal"
        self.b_scan.configure(state=st)
        self.b_check.configure(state=st)
        self.b_clear.configure(state=st)
        self.b_stop.configure(state="normal" if busy else "disabled")

    def stop(self):
        if self.busy:
            self.stop_evt.set()
            self.log_line("[!] stop requested — finishing current tasks...")

    def clear(self):
        self.rows.clear()
        self.seen.clear()
        self._domain_counts = None
        self._sync_domains()
        self._render()
        self._update_stats()
        self.pbar["value"] = 0
        self.pct_var.set("0%")
        self.scanned_var.set("scanned 0")
        self.status_var.set("cleared")
        self.log_line("[*] results cleared")

    # ---------------- extra actions ----------------
    def import_subs(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        existing = {u.strip() for u in self.subs.get("1.0", "end").splitlines()}
        added = 0
        for line in text.splitlines():
            line = line.strip()
            if (line.startswith("http") or os.path.isfile(line)) \
                    and line not in existing:
                self._append_line(self.subs, line)
                existing.add(line)
                added += 1
        has_cfg = bool(re.search(
            r"(?im)(vless|vmess|trojan|ss|ssr|tuic|hysteria2?)://", text))
        if (added == 0 or has_cfg) and path not in existing:
            self._append_line(self.subs, path)
            added += 1
            self.log_line(f"[+] added file as subscription source: {path}")
        self.subs.see("end")
        self.log_line(f"[+] imported {added} source(s) from {path}")

    def test_proxy(self):
        if self.busy:
            return
        proxy = self.proxy_url.get().strip()
        self.log_line(f"[*] testing proxy {proxy} ...")
        threading.Thread(target=self._test_proxy_worker, args=(proxy,),
                         daemon=True).start()

    def _test_proxy_worker(self, proxy: str):
        ok, info = proxy_works(proxy, float(self.timeout.get()))
        self.log_line(("[+] proxy OK: " if ok else "[-] proxy FAILED: ") + info)
        self.q.put(("progress", 100 if ok else 0,
                    f"proxy {'works' if ok else 'failed'}: {info}"))

    # ---------------- 1) scan ----------------
    def start_scan(self):
        if self.busy:
            return
        urls = [u.strip() for u in self.subs.get("1.0", "end").splitlines()]
        urls = [u for u in urls if u and not u.startswith("#")]
        pattern_text = self.pats.get("1.0", "end")
        timeout = float(self.timeout.get())
        match_any = bool(self.match_any.get())
        if not urls:
            messagebox.showwarning("No subscriptions", "Add at least one sub URL.")
            return
        if not parse_patterns(pattern_text):
            messagebox.showwarning("No patterns", "Add at least one deploy pattern.")
            return
        self.stop_evt.clear()
        self._set_busy(True)
        self.pbar["value"] = 0
        threading.Thread(target=self._scan_worker,
                         args=(urls, pattern_text, timeout, match_any),
                         daemon=True).start()

    def _scan_worker(self, urls, pattern_text, timeout, match_any):
        patterns = parse_patterns(pattern_text)
        n_subs = len(urls)
        found = 0
        scanned = 0
        for si, url in enumerate(urls):
            if self.stop_evt.is_set():
                break
            self.q.put(("progress", 100.0 * si / n_subs,
                        f"downloading sub {si + 1}/{n_subs} ..."))
            try:
                raw = fetch_source(url, timeout, False)
            except Exception as exc:
                self.log_line(f"[!] fetch failed {url}: {exc}")
                continue
            links = split_links(normalize_subscription(raw))
            src = url.rstrip("/").split("/")[-1][:40]
            hits = 0
            for li, link in enumerate(links):
                if self.stop_evt.is_set():
                    break
                scanned += 1
                if li % 400 == 0:
                    pct = 100.0 * (si + li / max(len(links), 1)) / n_subs
                    self.q.put(("progress", pct,
                                f"sub {si + 1}/{n_subs}: {li}/{len(links)} "
                                f"parsed — {found} matched"))
                    self.q.put(("scanned", scanned))
                if link in self.seen:
                    continue
                self.seen.add(link)
                fields = link_fields(link)
                domain = find_match(fields, patterns, match_any)
                if not domain:
                    continue
                self.q.put(("row", {
                    "link": link,
                    "type": link.split("://", 1)[0].upper(),
                    "host": fields["host"],
                    "port": fields["port"] or "443",
                    "domain": domain,
                    "status": "NEW",
                    "note": "" if domain == fields["host"]
                            else f"matched via {'sni' if domain == fields.get('sni') else 'ws-host'}",
                    "source": src,
                }))
                hits += 1
                found += 1
            self.log_line(f"[*] {url} -> {len(links)} configs, +{hits} matched")
            self.q.put(("scanned", scanned))
            self.q.put(("progress", 100.0 * (si + 1) / n_subs,
                        f"sub {si + 1}/{n_subs} done — {found} matched"))
        stopped = self.stop_evt.is_set()
        self.q.put(("done", f"scan {'stopped' if stopped else 'finished'} — "
                            f"{found} new of {scanned} scanned (total "
                            f"{len(self.rows)})", stopped))

    # ---------------- 2) check alive ----------------
    def start_check(self):
        if self.busy:
            return
        if not self.rows:
            messagebox.showinfo("Nothing to check",
                                "Scan some subscriptions first.")
            return
        settings = {
            "timeout": float(self.timeout.get()),
            "use_proxy": bool(self.use_proxy.get()),
            "proxy": self.proxy_url.get().strip(),
            "workers": max(1, int(self.threads.get())),
        }
        groups: dict[tuple, list[int]] = {}
        for i, row in enumerate(self.rows):
            try:
                port = int(row["port"] or 443)
            except ValueError:
                port = 443
            key = (row["host"], port, row.get("domain") or row["host"])
            groups.setdefault(key, []).append(i)
        self.stop_evt.clear()
        self._set_busy(True)
        self.pbar["value"] = 0
        for idxs in groups.values():
            for i in idxs:
                self.q.put(("status_row", i, "CHECKING", ""))
        threading.Thread(target=self._check_worker, args=(groups, settings),
                         daemon=True).start()

    def _check_worker(self, groups: dict, cfg: dict):
        total = len(groups)
        done = 0
        counts = {"LIVE": 0, "DEAD": 0, "DOWN": 0, "PORT OPEN": 0}
        proxy_note = " via proxy" if cfg["use_proxy"] else ""

        def task(key):
            if self.stop_evt.is_set():
                return None
            server, port, domain = key
            tcp_ok, tcp_err = tcp_open(server, port, cfg["timeout"])
            target = domain if domain else server
            status, body, err = http_probe(target, port, cfg["timeout"],
                                           cfg["use_proxy"], cfg["proxy"])
            state, note = evaluate(status, body, tcp_ok, tcp_err or err)
            if domain and domain != server and state in ("LIVE", "DEAD"):
                note += f" (via {domain})"
            return key, state, note + (proxy_note if state == "LIVE" else "")

        with concurrent.futures.ThreadPoolExecutor(
                max_workers=cfg["workers"]) as pool:
            for res in pool.map(task, list(groups)):
                done += 1
                if res is not None:
                    key, state, note = res
                    counts[state] += 1
                    for i in groups[key]:
                        self.q.put(("status_row", i, state, note))
                self.q.put(("progress", 100.0 * done / total,
                            f"checking {done}/{total} hosts — "
                            f"LIVE {counts['LIVE']}  DEAD {counts['DEAD']}  "
                            f"DOWN {counts['DOWN']}  "
                            f"PORT-OPEN {counts['PORT OPEN']}"))

        stopped = self.stop_evt.is_set()
        self.q.put(("done",
                    f"check {'stopped' if stopped else 'done'} | "
                    f"LIVE {counts['LIVE']}  DEAD {counts['DEAD']}  "
                    f"DOWN {counts['DOWN']}  PORT-OPEN {counts['PORT OPEN']}"
                    f"{proxy_note}", stopped))

    # ---------------- save ----------------
    def save(self):
        if not self.rows:
            messagebox.showinfo("Nothing to save", "Scan first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"deploy_configs_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        only_alive = bool(self.only_alive.get())
        picked = [r for r in self.rows if not only_alive or r["status"] == "LIVE"]
        if not picked:
            messagebox.showinfo("Nothing", "No rows match the save option.")
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(r["link"] for r in picked) + "\n")
        self.status_var.set(f"saved {len(picked)} configs -> {path}")
        self.log_line(f"[+] saved {len(picked)} configs to {path}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
