#!/usr/bin/env python3
"""
Kør: python3 mirapass-redaktion.py
Åbner automatisk http://localhost:7771 i browseren.
"""

import json, os, subprocess, webbrowser, threading, time, secrets, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

WP_BASE = "https://mirapass.dk/wp-json/wp/v2"


def _gemini_key() -> str:
    """Henter Gemini API-nøgle fra macOS Keychain (eller fil som fallback)."""
    r = subprocess.run(
        ["security", "find-generic-password", "-s", "mirapass-gemini", "-w"],
        capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    gemini_file = os.path.expanduser("~/.config/mirapass/gemini.key")
    with open(gemini_file) as f:
        return f.read().strip()


# ── Google Search Console OAuth2 ─────────────────────────────────────────────

GSC_CREDS_FILE  = os.path.expanduser("~/.config/mirapass/gsc_client.json")
GSC_KEYCHAIN    = "mirapass-gsc"
GSC_REDIRECT    = "http://localhost:7771/oauth2callback"
GSC_SCOPES      = "https://www.googleapis.com/auth/webmasters.readonly https://www.googleapis.com/auth/analytics.readonly"
_gsc_oauth_state = {}   # temp state: {state: client_info}

def _gsc_client_info():
    """Henter GSC client_id + client_secret fra Keychain, ellers fra fil."""
    r = subprocess.run(
        ["security", "find-generic-password", "-s", "mirapass-gsc-client", "-a", "client", "-w"],
        capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return json.loads(r.stdout.strip())
    # Fallback: læs fra fil og gem i Keychain til næste gang
    with open(GSC_CREDS_FILE) as f:
        raw = json.load(f)
    info = raw[list(raw.keys())[0]]
    client = {"client_id": info["client_id"], "client_secret": info["client_secret"],
              "auth_uri": info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
              "token_uri": info.get("token_uri", "https://oauth2.googleapis.com/token")}
    subprocess.run(
        ["security", "add-generic-password", "-s", "mirapass-gsc-client",
         "-a", "client", "-w", json.dumps(client), "-U"],
        capture_output=True)
    return client

def _gsc_token():
    """Henter gemt GSC token fra Keychain. Returnerer None hvis ikke autoriseret."""
    r = subprocess.run(
        ["security", "find-generic-password", "-s", GSC_KEYCHAIN, "-a", "oauth2", "-w"],
        capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return json.loads(r.stdout.strip())
    return None

def _gsc_save_token(token_data: dict):
    subprocess.run(
        ["security", "add-generic-password", "-s", GSC_KEYCHAIN,
         "-a", "oauth2", "-w", json.dumps(token_data), "-U"],
        capture_output=True)

def _gsc_refresh(token_data: dict) -> dict:
    """Fornyer access token via refresh token."""
    c = _gsc_client_info()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     c["client_id"],
        "client_secret": c["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type":    "refresh_token",
    }, timeout=15)
    new = r.json()
    token_data["access_token"] = new["access_token"]
    _gsc_save_token(token_data)
    return token_data

def gsc_auth_url() -> str:
    """Genererer Google OAuth URL og gemmer state."""
    c = _gsc_client_info()
    state = secrets.token_urlsafe(16)
    _gsc_oauth_state[state] = c
    params = urllib.parse.urlencode({
        "client_id":     c["client_id"],
        "redirect_uri":  GSC_REDIRECT,
        "response_type": "code",
        "scope":         GSC_SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

def gsc_handle_callback(code: str, state: str) -> bool:
    """Udveksler auth-kode for tokens og gemmer i Keychain."""
    c = _gsc_oauth_state.pop(state, None)
    if c is None:
        return False  # Ukendt/udløbet/forfalsket state — afvis
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     c["client_id"],
        "client_secret": c["client_secret"],
        "code":          code,
        "redirect_uri":  GSC_REDIRECT,
        "grant_type":    "authorization_code",
    }, timeout=15)
    data = r.json()
    if "refresh_token" not in data:
        return False
    _gsc_save_token({
        "access_token":  data["access_token"],
        "refresh_token": data["refresh_token"],
        "client_id":     c["client_id"],
        "client_secret": c["client_secret"],
    })
    return True

def gsc_fetch(site: str, start: str, end: str, dims: list) -> dict:
    """Kalder Search Console API og returnerer rows."""
    token = _gsc_token()
    if not token:
        return {"error": "ikke_autoriseret"}
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    body = {"startDate": start, "endDate": end,
            "dimensions": dims, "rowLimit": 500}
    r = requests.post(
        f"https://searchconsole.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
        headers=headers, json=body, timeout=30)
    if r.status_code == 401:
        token = _gsc_refresh(token)
        headers["Authorization"] = f"Bearer {token['access_token']}"
        r = requests.post(
            f"https://searchconsole.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
            headers=headers, json=body, timeout=30)
    return r.json()


GA_KEYCHAIN      = "mirapass-ga"
GA_PROP_KEYCHAIN = "mirapass-ga-property"

def _ga_token():
    """Henter GA4 access token — genbruger GSC token hvis det har analytics scope."""
    r = subprocess.run(["security","find-generic-password","-s",GA_KEYCHAIN,"-a","oauth2","-w"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return json.loads(r.stdout.strip())
    return _gsc_token()

def _ga_property_id():
    """Henter gemt GA4 property ID fra Keychain."""
    r = subprocess.run(["security","find-generic-password","-s",GA_PROP_KEYCHAIN,"-a","property","-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

def _ga_save_property(prop_id):
    subprocess.run(["security","add-generic-password","-s",GA_PROP_KEYCHAIN,"-a","property","-w",prop_id,"-U"], capture_output=True)

def ga_list_properties():
    """Lister alle GA4-properties via Admin API."""
    token = _ga_token()
    if not token: return []
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers, timeout=15)
    if r.status_code == 401:
        token = _gsc_refresh(token)
        headers["Authorization"] = f"Bearer {token['access_token']}"
        r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=headers, timeout=15)
    data = r.json()
    props = []
    for account in data.get("accountSummaries", []):
        for prop in account.get("propertySummaries", []):
            props.append({"id": prop["property"], "name": prop.get("displayName",""), "account": account.get("displayName","")})
    return props

def ga_fetch(property_id, start, end, dimensions, metrics, dimension_filter=None):
    """Kalder GA4 Data API og returnerer rows."""
    token = _ga_token()
    if not token: return {"error": "ikke_autoriseret"}
    headers = {"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"}
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics":    [{"name": m} for m in metrics],
        "limit": 50,
    }
    if dimension_filter:
        body["dimensionFilter"] = dimension_filter
    prop = property_id.replace("properties/","")
    r = requests.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport", headers=headers, json=body, timeout=30)
    if r.status_code == 401:
        token = _gsc_refresh(token)
        headers["Authorization"] = f"Bearer {token['access_token']}"
        r = requests.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport", headers=headers, json=body, timeout=30)
    return r.json()


def wp_auth() -> tuple:
    """Henter WP-credentials fra macOS Keychain (eller fil som fallback)."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "mirapass-wp", "-g"],
            capture_output=True, text=True)
        if r.returncode == 0:
            acct_line = next((l for l in r.stdout.splitlines() if '"acct"' in l), "")
            user = acct_line.split('"')[-2] if acct_line else ""
            pw_r = subprocess.run(
                ["security", "find-generic-password", "-s", "mirapass-wp", "-w"],
                capture_output=True, text=True)
            pw = pw_r.stdout.strip()
            if user and pw:
                return (user, pw)
    except Exception:
        pass
    # Fallback: plaintext fil
    creds_file = os.path.expanduser("~/.config/mirapass/wp.credentials")
    with open(creds_file) as f:
        user, pw = f.read().strip().split(":", 1)
    return (user, pw)

HTML = r"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mirapass – Redaktionsplan</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f1117;--surface:#161b22;--surface2:#1c2128;
  --border:#30363d;--text:#e6edf3;--muted:#7d8590;
  --green:#3fb950;--orange:#d29922;--blue:#58a6ff;
  --accent:#cc785c;
}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);min-height:100vh}

/* ── Header ─────────────────────────── */
header{background:var(--surface);border-bottom:1px solid var(--border);padding:0 2rem;height:56px;display:flex;align-items:center;gap:1.5rem;position:sticky;top:0;z-index:50}
.logo{font-weight:700;font-size:1rem;color:#fff;display:flex;align-items:center;gap:.5rem}
.logo-dot{width:10px;height:10px;background:var(--accent);border-radius:50%}
.header-right{margin-left:auto;display:flex;align-items:center;gap:.75rem}
#last-updated{font-size:.78rem;color:var(--muted)}
.btn{border-radius:6px;padding:.38rem .9rem;font-size:.82rem;cursor:pointer;transition:all .15s;font-weight:500;border:1px solid var(--border)}
.btn-ghost{background:var(--surface2);color:var(--text)}
.btn-ghost:hover{border-color:#58a6ff;color:#58a6ff}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-primary:hover{background:#b8694f;border-color:#b8694f}

/* ── Stats ───────────────────────────── */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;padding:1.5rem 2rem}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.1rem 1.4rem}
.stat-val{font-size:2rem;font-weight:700;color:#fff;line-height:1}
.stat-lbl{font-size:.78rem;color:var(--muted);margin-top:.35rem}
.stat.green .stat-val{color:var(--green)}
.stat.orange .stat-val{color:var(--orange)}
.stat.blue .stat-val{color:var(--blue)}

/* ── Tabs ────────────────────────────── */
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border);padding:0 2rem;margin-top:.25rem}
.tab{background:none;border:none;color:var(--muted);font-size:.88rem;padding:.6rem 1.1rem;cursor:pointer;border-bottom:2px solid transparent;transition:color .15s,border-color .15s;margin-bottom:-1px}
.tab.active{color:#fff;border-bottom-color:var(--accent)}
.tab:hover:not(.active){color:var(--text)}

/* ── Content panes ──────────────────── */
.pane{display:none;padding:1.5rem 2rem}
.pane.active{display:block}

/* ── Timeline ────────────────────────── */
.timeline-group{margin-bottom:2rem}
.tg-header{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);padding:.4rem 0;border-bottom:1px solid var(--border);margin-bottom:.75rem;font-weight:600}
.tg-header span{float:right;font-weight:400;text-transform:none;letter-spacing:0}
.tl-item{display:flex;align-items:center;gap:1rem;padding:.6rem .8rem;border-radius:8px;transition:background .12s;border:1px solid transparent}
.tl-item:hover{background:var(--surface);border-color:var(--border)}
.tl-time{font-size:.78rem;color:var(--muted);width:52px;flex-shrink:0;font-variant-numeric:tabular-nums}
.tl-badge{font-size:.68rem;font-weight:600;padding:.15rem .55rem;border-radius:12px;flex-shrink:0}
.badge-publish{background:rgba(63,185,80,.12);color:var(--green);border:1px solid rgba(63,185,80,.25)}
.badge-future{background:rgba(210,153,34,.12);color:var(--orange);border:1px solid rgba(210,153,34,.25)}
.tl-title{font-size:.9rem;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tl-title a{color:var(--text);text-decoration:none}
.tl-title a:hover{color:var(--blue)}
.tl-kw{font-size:.72rem;color:var(--muted);flex-shrink:0;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── Table ───────────────────────────── */
.toolbar{display:flex;gap:.75rem;margin-bottom:1rem;align-items:center}
#search{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:.45rem .85rem;color:var(--text);font-size:.88rem;width:260px;outline:none}
#search:focus{border-color:var(--blue)}
#filter-status{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:.45rem .7rem;color:var(--text);font-size:.88rem;outline:none;cursor:pointer}
.count-lbl{font-size:.8rem;color:var(--muted);margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:.85rem}
thead th{text-align:left;padding:.55rem .85rem;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;font-weight:600;border-bottom:1px solid var(--border);white-space:nowrap}
tbody tr{border-bottom:1px solid rgba(48,54,61,.5);transition:background .1s}
tbody tr:hover{background:var(--surface)}
td{padding:.6rem .85rem;vertical-align:middle}
td.td-title a{color:var(--text);text-decoration:none;font-weight:500}
td.td-title a:hover{color:var(--blue)}
td.td-date{font-size:.8rem;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
td.td-kw{font-size:.78rem;color:var(--muted)}
td.td-id{font-size:.75rem;color:#444;width:40px}
td.td-links{font-size:.75rem;color:var(--muted);text-align:center}

/* ── Modal overlay ───────────────────── */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);backdrop-filter:blur(4px);z-index:200;align-items:center;justify-content:center;padding:1rem}
.modal-overlay.open{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;width:100%;max-width:680px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden}
.modal-header{padding:1.2rem 1.5rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.75rem}
.modal-header h2{font-size:1rem;font-weight:600;color:#fff;flex:1}
.modal-close{background:none;border:none;color:var(--muted);font-size:1.3rem;cursor:pointer;line-height:1;padding:.2rem}
.modal-close:hover{color:#fff}
.modal-body{padding:1.5rem;overflow-y:auto;flex:1}
.modal-footer{padding:1rem 1.5rem;border-top:1px solid var(--border);display:flex;gap:.75rem;justify-content:flex-end}

/* ── Form inside modal ───────────────── */
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem}
.form-row.full{grid-template-columns:1fr}
.form-group label{display:block;font-size:.78rem;color:var(--muted);margin-bottom:.4rem;font-weight:500}
.form-group input,.form-group select,.form-group textarea{
  width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:7px;
  padding:.5rem .8rem;color:var(--text);font-size:.88rem;outline:none;font-family:inherit
}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--blue)}
.form-group textarea{resize:vertical;min-height:80px}

/* ── Chips ───────────────────────────── */
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.4rem}
.chip{background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:.25rem .75rem;font-size:.78rem;color:var(--muted);cursor:pointer;transition:all .15s;user-select:none}
.chip:hover{border-color:var(--accent);color:var(--text)}
.chip.active{background:rgba(204,120,92,.15);border-color:var(--accent);color:var(--accent)}

/* ── Generated prompt area ───────────── */
.prompt-box{background:var(--bg);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-top:1.5rem}
.prompt-box-header{padding:.6rem 1rem;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;font-size:.78rem;color:var(--muted)}
#generated-prompt{display:block;width:100%;background:transparent;border:none;color:#c9d1d9;font-family:"SF Mono","Fira Code",monospace;font-size:.78rem;line-height:1.6;padding:1rem;resize:none;height:240px;outline:none}

/* ── Schedule progress ───────────────── */
.progress-log{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem;max-height:200px;overflow-y:auto;font-family:monospace;font-size:.78rem;line-height:1.7;color:var(--muted);margin-top:1rem}
.log-ok{color:var(--green)}
.log-err{color:#f85149}
.log-info{color:var(--blue)}

/* ── Typography ──────────────────────── */
h2{font-size:1.05rem;font-weight:600}

/* ── Loading / empty ─────────────────── */
.loading{text-align:center;padding:4rem;color:var(--muted)}
.loading-spinner{width:28px;height:28px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 1rem}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── SEO Analyse ─────────────────────── */
.seo-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:.75rem;margin-bottom:1.5rem}
.seo-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1rem 1.2rem;text-align:center}
.seo-card-val{font-size:1.6rem;font-weight:700;line-height:1}
.seo-card-lbl{font-size:.72rem;color:var(--muted);margin-top:.3rem}
.seo-card.red .seo-card-val{color:#f85149}
.seo-card.orange .seo-card-val{color:var(--orange)}
.seo-card.green .seo-card-val{color:var(--green)}
.seo-score{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:50%;font-size:.75rem;font-weight:700;flex-shrink:0}
.score-good{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.3)}
.score-warn{background:rgba(210,153,34,.15);color:var(--orange);border:1px solid rgba(210,153,34,.3)}
.score-bad{background:rgba(248,81,73,.12);color:#f85149;border:1px solid rgba(248,81,73,.25)}
.seo-check{display:inline-flex;align-items:center;gap:.25rem;font-size:.72rem;padding:.18rem .55rem;border-radius:10px;font-weight:500;white-space:nowrap}
.chk-ok{background:rgba(63,185,80,.1);color:var(--green)}
.chk-warn{background:rgba(210,153,34,.1);color:var(--orange)}
.chk-miss{background:rgba(248,81,73,.08);color:#f85149}
.seo-sort-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:.72rem;padding:0 .3rem;vertical-align:middle}
.seo-sort-btn.asc::after{content:" ↑"}
.seo-sort-btn.desc::after{content:" ↓"}
.priority-badge{font-size:.68rem;font-weight:700;padding:.15rem .55rem;border-radius:10px}
.pri-high{background:rgba(248,81,73,.12);color:#f85149;border:1px solid rgba(248,81,73,.25)}
.pri-med{background:rgba(210,153,34,.12);color:var(--orange);border:1px solid rgba(210,153,34,.25)}
.pri-ok{background:rgba(63,185,80,.1);color:var(--green);border:1px solid rgba(63,185,80,.2)}
.seo-filter-bar{display:flex;gap:.6rem;margin-bottom:1rem;flex-wrap:wrap;align-items:center}
.seo-filter-bar select,.seo-filter-bar input{background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:.4rem .75rem;color:var(--text);font-size:.82rem;outline:none;cursor:pointer}
.seo-filter-bar input{width:220px}
.seo-filter-bar input:focus,.seo-filter-bar select:focus{border-color:var(--blue)}

@media(max-width:700px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .tl-kw{display:none}
  .col-kw,.col-id,.col-links{display:none}
  .form-row{grid-template-columns:1fr}
}

/* ── Dashboard / Overblik ────────────── */
.db-kpi-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:1rem;margin-bottom:1.25rem}
.db-kpi{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:.85rem 1.1rem;text-align:center}
.db-kpi .val{font-size:1.45rem;font-weight:700;line-height:1.15}
.db-kpi .lbl{font-size:.68rem;color:var(--muted);margin-top:.25rem}
.db-grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1.25rem;margin-bottom:1.25rem}
.db-widget{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.2rem 1.4rem}
.db-widget h3{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:.9rem;font-weight:600;display:flex;justify-content:space-between;align-items:center}
.db-row{display:flex;justify-content:space-between;align-items:center;padding:.28rem 0;font-size:.82rem}
.db-row+.db-row{border-top:1px solid var(--border)}
.db-row .lbl{color:var(--muted)}
.db-row .val{font-weight:600}
.db-bar{height:4px;background:var(--border);border-radius:2px;margin:.18rem 0 .5rem}
.db-bar-fill{height:4px;border-radius:2px;transition:width .5s ease}
.db-actions{display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem}
.db-act{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1rem 1.1rem;cursor:pointer;text-align:left;transition:border-color .18s,background .18s}
.db-act:hover{border-color:var(--accent);background:#1c2333}
.db-act .icon{font-size:1.3rem;margin-bottom:.4rem;display:block}
.db-act .albl{font-size:.8rem;font-weight:600;display:block}
.db-act .asub{font-size:.7rem;color:var(--muted);display:block;margin-top:.2rem}
.db-spin{display:inline-block;width:11px;height:11px;border:1.5px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite}
.db-badge{font-size:.64rem;font-weight:600;padding:.1rem .45rem;border-radius:4px}
.db-badge.ok{background:rgba(63,185,80,.12);color:var(--green)}
.db-badge.warn{background:rgba(210,153,34,.12);color:var(--orange)}
.db-badge.err{background:rgba(248,81,73,.08);color:#f85149}
.db-num-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-bottom:.8rem}
.db-num{text-align:center;padding:.5rem;background:var(--bg);border-radius:8px}
.db-num .v{font-size:1.3rem;font-weight:700;line-height:1.15}
.db-num .l{font-size:.67rem;color:var(--muted);margin-top:.15rem}
@media(max-width:900px){.db-grid3{grid-template-columns:1fr 1fr}.db-kpi-strip{grid-template-columns:repeat(3,1fr)}.db-actions{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.db-grid3{grid-template-columns:1fr}.db-kpi-strip{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>

<header>
  <div class="logo"><div class="logo-dot"></div>Mirapass Redaktion</div>
  <div class="header-right">
    <span id="last-updated">Henter data…</span>
    <button class="btn btn-ghost" onclick="loadPosts()">↻ Opdater</button>
    <button class="btn btn-primary" onclick="openModal()">+ Planlæg nye opslag</button>
  </div>
</header>

<!-- ═══════════════ MODAL ═══════════════ -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <h2>Planlæg nye opslag</h2>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body">

      <div class="form-row">
        <div class="form-group">
          <label>Antal opslag</label>
          <select id="m-antal">
            <option value="5">5 opslag</option>
            <option value="7" selected>7 opslag</option>
            <option value="10">10 opslag</option>
            <option value="14">14 opslag</option>
          </select>
        </div>
        <div class="form-group">
          <label>Interval mellem opslag</label>
          <select id="m-interval">
            <option value="2">Hver 2. time</option>
            <option value="4">Hver 4. time</option>
            <option value="8" selected>Hver 8. time</option>
            <option value="24">Én om dagen</option>
            <option value="48">Hver 2. dag</option>
          </select>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Startdato og -tidspunkt</label>
          <input type="datetime-local" id="m-start">
        </div>
        <div class="form-group">
          <label>Sprog / tone</label>
          <select id="m-tone">
            <option value="dansk, professionel og lettilgængelig">Professionel dansk</option>
            <option value="dansk, uformel og praktisk">Uformel og praktisk</option>
            <option value="dansk, teknisk og præcis">Teknisk og præcis</option>
          </select>
        </div>
      </div>

      <div class="form-group" style="margin-bottom:1rem">
        <label>Emneområder (vælg en eller flere)</label>
        <div class="chips" id="topic-chips">
          <span class="chip active" data-topic="sammenligning">Sammenligninger</span>
          <span class="chip active" data-topic="brancher">Brancher & faggrupper</span>
          <span class="chip active" data-topic="features">Features & guides</span>
          <span class="chip" data-topic="begynder">Begynderguides</span>
          <span class="chip" data-topic="produktivitet">Produktivitet</span>
          <span class="chip" data-topic="virksomhed">Virksomhed & SMV</span>
          <span class="chip" data-topic="teknik">API & teknik</span>
          <span class="chip" data-topic="kreativ">Kreativt indhold</span>
        </div>
      </div>

      <div class="form-row full">
        <div class="form-group">
          <label>Specifikke ønsker / noter (valgfrit)</label>
          <textarea id="m-notes" placeholder="F.eks. 'undgå emner vi allerede har dækket om X', 'fokus på dansk lovgivning', …"></textarea>
        </div>
      </div>

      <button class="btn btn-primary" style="width:100%;padding:.6rem" onclick="generatePrompt()">Generer Claude-prompt →</button>

      <div class="prompt-box" id="prompt-box" style="display:none">
        <div class="prompt-box-header">
          <span>Klar til at kopiere ind i Claude</span>
          <button class="btn btn-ghost" style="padding:.25rem .7rem;font-size:.75rem" onclick="copyPrompt()">Kopiér</button>
        </div>
        <textarea id="generated-prompt" readonly spellcheck="false"></textarea>
      </div>

    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Luk</button>
    </div>
  </div>
</div>

<!-- ═══════════════ PAGE ════════════════ -->
<div class="stats">
  <div class="stat"><div class="stat-val" id="s-total">–</div><div class="stat-lbl">Artikler i alt</div></div>
  <div class="stat green"><div class="stat-val" id="s-pub">–</div><div class="stat-lbl">Udgivet</div></div>
  <div class="stat orange"><div class="stat-val" id="s-sched">–</div><div class="stat-lbl">Planlagt</div></div>
  <div class="stat blue"><div class="stat-val" id="s-soon">–</div><div class="stat-lbl">Næste 7 dage</div></div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showDashboard(this)">Overblik</button>
  <button class="tab" onclick="showTab('timeline',this)">Tidslinje</button>
  <button class="tab" onclick="showTab('table',this)">Alle opslag</button>
  <button class="tab" onclick="showTab('seo',this)">SEO Analyse</button>
  <button class="tab" onclick="showSider(this)">Sider SEO</button>
  <button class="tab" onclick="showLinking(this)">Intern Linking</button>
  <button class="tab" onclick="showGSC(this)">Search Console</button>
  <button class="tab" onclick="showGA(this)">Google Analytics</button>
  <button class="tab" onclick="showOpportunities(this)">Muligheder</button>
</div>

<div id="pane-dashboard" class="pane active"></div>
<div id="pane-timeline" class="pane">
  <div class="loading"><div class="loading-spinner"></div>Indlæser…</div>
</div>
<div id="pane-seo" class="pane"></div>
<div id="pane-sider" class="pane"></div>
<div id="pane-linking" class="pane"></div>
<div id="pane-gsc" class="pane"></div>
<div id="pane-ga" class="pane"></div>
<div id="pane-opp" class="pane"></div>

<div id="pane-table" class="pane">
  <div class="toolbar">
    <input id="search" placeholder="Søg titel eller nøgleord…" oninput="filterTable()">
    <select id="filter-status" onchange="filterTable()">
      <option value="">Alle statusser</option>
      <option value="publish">Udgivet</option>
      <option value="future">Planlagt</option>
    </select>
    <span class="count-lbl" id="table-count"></span>
  </div>
  <table>
    <thead>
      <tr>
        <th class="col-id">#</th>
        <th>Titel</th>
        <th>Status</th>
        <th>Dato</th>
        <th class="col-kw">Fokus-nøgleord</th>
        <th class="col-links" title="Inbound links">↙</th>
      </tr>
    </thead>
    <tbody id="table-body"></tbody>
  </table>
</div>

<script>
let allPosts = [];

/* ── Modal ────────────────────────────── */
function openModal() {
  // Default start = next round hour
  const d = new Date(); d.setHours(d.getHours()+1, 0, 0, 0);
  document.getElementById('m-start').value = d.toISOString().slice(0,16);
  document.getElementById('modal').classList.add('open');
  document.getElementById('prompt-box').style.display = 'none';
}
function closeModal() { document.getElementById('modal').classList.remove('open'); }

document.querySelectorAll('.chip').forEach(c => {
  c.addEventListener('click', () => c.classList.toggle('active'));
});

function generatePrompt() {
  const antal   = +document.getElementById('m-antal').value;
  const interval= +document.getElementById('m-interval').value;
  const start   = document.getElementById('m-start').value;
  const tone    = document.getElementById('m-tone').value;
  const notes   = document.getElementById('m-notes').value.trim();
  const topics  = [...document.querySelectorAll('.chip.active')].map(c => c.dataset.topic);

  if (!start) { alert('Vælg en startdato.'); return; }

  // Calculate publish times
  const times = [];
  const base = new Date(start);
  for (let i = 0; i < antal; i++) {
    const t = new Date(base.getTime() + i * interval * 3600000);
    times.push(t.toISOString().slice(0,16).replace('T',' '));
  }

  // Existing slugs
  const slugs = allPosts.map(p => p.slug).join('\n  - ');

  const topicMap = {
    sammenligning: 'Sammenligninger (Claude vs andre AI-værktøjer)',
    brancher: 'Brancher og faggrupper (sundhed, jura, HR, økonomi, undervisning osv.)',
    features: 'Claude-features og guides (Artifacts, Extended Thinking, Projects, MCP, Computer Use)',
    begynder: 'Begynderguides og kom-i-gang',
    produktivitet: 'Produktivitet og arbejdsflow',
    virksomhed: 'Virksomhed, SMV og iværksætteri',
    teknik: 'API, Python og teknisk brug',
    kreativ: 'Kreativt indhold og skrivning',
  };
  const topicLines = topics.map(t => '  - ' + (topicMap[t] || t)).join('\n');

  const prompt = `Du er SEO- og GEO-ekspert for den danske WordPress-blog mirapass.dk, som handler om Claude AI.

Opret ${antal} nye blogindlæg og publicér dem planlagt på WordPress via REST API.

## Udgivelsestidspunkter
${times.map((t,i) => `  ${i+1}. ${t}`).join('\n')}

## Krav til hvert indlæg

**SEO:**
- Fokus-nøgleord naturligt i H1, første afsnit og 2-3 steder i brødtekst
- Yoast meta title (max 60 tegn) og meta description (max 155 tegn)
- Strukturerede overskrifter: H2 til sektioner, H3 til undersektioner
- Min. 1.200 ord

**GEO (Generative Engine Optimization):**
- Svar direkte på brugerens spørgsmål i første afsnit (featured snippet-format)
- FAQPage JSON-LD schema med 4-6 spørgsmål/svar
- Faktuelle sætninger der kan citeres af AI-søgemaskiner
- Nævn eksplicitte eksempler fra dansk kontekst

**Tone:** ${tone}

**Intern linkbuilding:**
- Tilføj én "Læs også"-boks (blå, venstre border) i hvert indlæg
- Link til 2-3 eksisterende relaterede artikler
- HTML-format: <div style="background:#f0f7ff;border-left:4px solid #0073aa;padding:16px 20px;margin:32px 0;border-radius:4px"><strong>Læs også:</strong><ul style="margin:8px 0 0 0"><li><a href="/slug/">Titel</a></li></ul></div>

## Emneområder
${topicLines}
${notes ? '\n## Specifikke ønsker\n' + notes : ''}

## Undgå disse eksisterende slugs (duplikater)
  - ${slugs}

## WordPress API
- Endpoint: https://mirapass.dk/wp-json/wp/v2/posts
- Auth: Basic [indlæses fra ~/.config/mirapass/wp.credentials]
- Brug status: "future" + date: "YYYY-MM-DDTHH:MM:SS" for planlagte opslag
- Meta-felter via: {"meta": {"_yoast_wpseo_title": "…", "_yoast_wpseo_metadesc": "…", "_yoast_wpseo_focuskw": "…"}}

Generér og opret alle ${antal} indlæg nu. Start med at lave indholdet til det første, publicér det, og fortsæt til næste.`;

  document.getElementById('generated-prompt').value = prompt;
  document.getElementById('prompt-box').style.display = 'block';
  document.getElementById('generated-prompt').scrollIntoView({behavior:'smooth',block:'nearest'});
}

function copyPrompt() {
  const ta = document.getElementById('generated-prompt');
  navigator.clipboard.writeText(ta.value).then(() => {
    const btn = event.target;
    btn.textContent = 'Kopieret ✓';
    setTimeout(() => btn.textContent = 'Kopiér', 2000);
  });
}

/* ── Data ─────────────────────────────── */
function showTab(id, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('pane-' + id).classList.add('active');
}

async function loadPosts() {
  document.getElementById('last-updated').textContent = 'Henter…';
  try {
    const res = await fetch('/api/posts');
    allPosts = await res.json();
    renderAll();
    const now = new Date();
    document.getElementById('last-updated').textContent =
      'Opdateret ' + now.toLocaleTimeString('da-DK', {hour:'2-digit',minute:'2-digit'});
  } catch(e) {
    document.getElementById('last-updated').textContent = 'Fejl: ' + e.message;
  }
}

function renderAll() {
  const now = new Date();
  const soon = new Date(now); soon.setDate(soon.getDate() + 7);
  const pub   = allPosts.filter(p => p.status === 'publish');
  const sched = allPosts.filter(p => p.status === 'future');
  const soonsched = sched.filter(p => new Date(p.date) <= soon);
  document.getElementById('s-total').textContent = allPosts.length;
  document.getElementById('s-pub').textContent   = pub.length;
  document.getElementById('s-sched').textContent = sched.length;
  document.getElementById('s-soon').textContent  = soonsched.length;
  renderTimeline(pub, sched);
  renderTable();
  renderSEO();
  dashExtData = null; // force external data refresh
  if (document.getElementById('pane-dashboard').classList.contains('active')) renderDashboardBase();
}

function fmtDate(d){ return new Date(d).toLocaleDateString('da-DK',{day:'numeric',month:'long',year:'numeric'}) }
function fmtTime(d){ return new Date(d).toLocaleTimeString('da-DK',{hour:'2-digit',minute:'2-digit'}) }
function dayKey(d){ const dt=new Date(d); return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0') }

function buildInbound() {
  const slugToId={}, inbound={};
  allPosts.forEach(p=>{ slugToId[p.slug]=p.id; inbound[p.id]=0; });
  allPosts.forEach(p=>{
    const hrefs=(p.content||'').match(/href="(?:https:\/\/mirapass\.dk)?\/([^/"]+)\//g)||[];
    hrefs.forEach(h=>{
      const slug=h.replace(/href="(?:https:\/\/mirapass\.dk)?\/|\/$/g,'');
      if(slugToId[slug]&&slugToId[slug]!==p.id) inbound[slugToId[slug]]++;
    });
  });
  return inbound;
}

function renderTimeline(pub, sched) {
  const pane = document.getElementById('pane-timeline');
  const futureSorted = [...sched].sort((a,b)=>new Date(a.date)-new Date(b.date));
  const now = new Date();
  const cutoff = new Date(now); cutoff.setDate(cutoff.getDate()-60);
  const recentPub = pub.filter(p=>new Date(p.date)>=cutoff).sort((a,b)=>new Date(b.date)-new Date(a.date));
  let html = '';

  if (futureSorted.length) {
    html += '<h3 style="font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:1.2rem;font-weight:600">Planlagte opslag ('+futureSorted.length+')</h3>';
    const byDay={};
    futureSorted.forEach(p=>{ const k=dayKey(p.date); if(!byDay[k])byDay[k]=[]; byDay[k].push(p); });
    Object.keys(byDay).sort().forEach(day=>{
      const items=byDay[day];
      const label=new Date(day).toLocaleDateString('da-DK',{weekday:'long',day:'numeric',month:'long'});
      html+='<div class="timeline-group"><div class="tg-header">'+label+'<span>'+items.length+' opslag</span></div>';
      items.forEach(p=>{
        const kw=(p.meta&&p.meta._yoast_wpseo_focuskw)||'';
        html+=`<div class="tl-item"><span class="tl-time">${fmtTime(p.date)}</span><span class="tl-badge badge-future">Planlagt</span><span class="tl-title"><a href="https://mirapass.dk/${p.slug}/" target="_blank">${p.title}</a></span><span class="tl-kw">${kw}</span></div>`;
      });
      html+='</div>';
    });
  }

  if (recentPub.length) {
    html+='<h3 style="font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:2rem 0 1.2rem;font-weight:600">Senest udgivet</h3>';
    const byMonth={};
    recentPub.forEach(p=>{ const k=new Date(p.date).getFullYear()+'-'+String(new Date(p.date).getMonth()+1).padStart(2,'0'); if(!byMonth[k])byMonth[k]=[]; byMonth[k].push(p); });
    Object.keys(byMonth).sort().reverse().forEach(m=>{
      const items=byMonth[m];
      const label=new Date(m+'-01').toLocaleDateString('da-DK',{month:'long',year:'numeric'});
      html+='<div class="timeline-group"><div class="tg-header" style="text-transform:capitalize">'+label+'<span>'+items.length+' opslag</span></div>';
      items.forEach(p=>{
        const kw=(p.meta&&p.meta._yoast_wpseo_focuskw)||'';
        html+=`<div class="tl-item"><span class="tl-time">${fmtDate(p.date).split(' ').slice(0,2).join(' ')}</span><span class="tl-badge badge-publish">Udgivet</span><span class="tl-title"><a href="https://mirapass.dk/${p.slug}/" target="_blank">${p.title}</a></span><span class="tl-kw">${kw}</span></div>`;
      });
      html+='</div>';
    });
  }
  pane.innerHTML = html || '<p style="color:var(--muted);padding:2rem">Ingen opslag fundet.</p>';
}

function filterTable() {
  const q  = (document.getElementById('search').value||'').toLowerCase();
  const st = document.getElementById('filter-status').value;
  const inbound = buildInbound();
  const rows = allPosts
    .filter(p=>{
      if(st&&p.status!==st) return false;
      if(q){ const kw=((p.meta&&p.meta._yoast_wpseo_focuskw)||'').toLowerCase(); if(!p.title.toLowerCase().includes(q)&&!kw.includes(q)&&!p.slug.includes(q)) return false; }
      return true;
    })
    .sort((a,b)=>new Date(b.date)-new Date(a.date));
  document.getElementById('table-count').textContent = rows.length + ' opslag';
  document.getElementById('table-body').innerHTML = rows.map(p=>{
    const kw=(p.meta&&p.meta._yoast_wpseo_focuskw)||'–';
    const badge=p.status==='publish'?'<span class="tl-badge badge-publish">Udgivet</span>':'<span class="tl-badge badge-future">Planlagt</span>';
    const dateStr=p.status==='future'?fmtDate(p.date)+' '+fmtTime(p.date):fmtDate(p.date);
    const cnt=inbound[p.id]||0, cntColor=cnt>=3?'var(--green)':cnt>0?'var(--orange)':'#555';
    return `<tr><td class="td-id col-id">${p.id}</td><td class="td-title"><a href="https://mirapass.dk/${p.slug}/" target="_blank">${p.title}</a></td><td>${badge}</td><td class="td-date">${dateStr}</td><td class="td-kw col-kw">${kw}</td><td class="td-links col-links" style="color:${cntColor};font-weight:600">${cnt}</td></tr>`;
  }).join('');
}

function renderTable(){ filterTable(); }

/* ── GSC page data cache ──────────────────────────────── */
let gscPageData = null;  // {slug: {clicks, impressions, position}}

/* ── SEO Analyse ─────────────────────────────────────── */
let seoSort = {col:'score', dir:'asc'};

function wordCount(html) {
  return (html || '').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim().split(' ').filter(w=>w.length>1).length;
}

function seoChecks(p, inboundCnt) {
  const m   = p.meta || {};
  const kw  = (m._yoast_wpseo_focuskw || '').trim();
  const mt  = (m._yoast_wpseo_title   || '').trim();
  const md  = (m._yoast_wpseo_metadesc|| '').trim();
  const img = !!p.featured_media;
  const exc = !!(p.excerpt || '').trim();
  const wc  = wordCount(p.content);
  const links = inboundCnt || 0;

  const checks = [
    { id:'kw',    label:'Fokus-nøgleord', ok: kw.length>0,                warn: false },
    { id:'mt',    label:'Meta title',     ok: mt.length>0 && mt.length<=60, warn: mt.length>0 && mt.length>60 },
    { id:'md',    label:'Meta beskrivelse', ok: md.length>=70 && md.length<=155, warn: md.length>0 && (md.length<70||md.length>155) },
    { id:'img',   label:'Featured image', ok: img,                         warn: false },
    { id:'exc',   label:'Excerpt',        ok: exc,                         warn: false },
    { id:'len',   label:'Ordantal',       ok: wc>=1200,                    warn: wc>=600 && wc<1200 },
    { id:'links', label:'Interne links',  ok: links>=3,                    warn: links>0 && links<3 },
  ];

  const score = checks.reduce((acc, c) => {
    if (c.ok) return acc + (c.id==='len'||c.id==='links' ? 2 : c.id==='kw' ? 2 : 1);
    if (c.warn) return acc + 0.5;
    return acc;
  }, 0);
  const maxScore = 9;

  return { checks, score, maxScore, kw, mt, md, img, exc, wc, links };
}

function scoreClass(score, max) {
  const pct = score / max;
  if (pct >= 0.85) return 'score-good';
  if (pct >= 0.55) return 'score-warn';
  return 'score-bad';
}

function priorityLabel(score, max) {
  const pct = score / max;
  if (pct >= 0.85) return '<span class="priority-badge pri-ok">OK</span>';
  if (pct >= 0.55) return '<span class="priority-badge pri-med">Forbedres</span>';
  return '<span class="priority-badge pri-high">Prioritet</span>';
}

function checkChip(c) {
  if (c.ok)   return `<span class="seo-check chk-ok">✓ ${c.label}</span>`;
  if (c.warn) return `<span class="seo-check chk-warn">⚠ ${c.label}</span>`;
  return           `<span class="seo-check chk-miss">✗ ${c.label}</span>`;
}

async function loadGscIntoSEO() {
  const btn = document.getElementById('gsc-into-seo-btn');
  if (btn) { btn.textContent = '↻ Henter…'; btn.disabled = true; }
  const end   = new Date(); end.setDate(end.getDate()-1);
  const start = new Date(); start.setDate(start.getDate()-28);
  const fmt = d => d.toISOString().slice(0,10);
  try {
    const data = await fetch(`/api/gsc/data?start=${fmt(start)}&end=${fmt(end)}&dims=page`).then(r=>r.json());
    if (data.error) {
      if (btn) { btn.textContent = '↻ Hent GSC'; btn.disabled = false; }
      alert('GSC ikke forbundet. Gå til Search Console-fanen og forbind først.');
      return;
    }
    const rows = data.rows || [];
    gscPageData = {};
    rows.forEach(r => {
      const url = r.keys[0];
      // extract slug: https://mirapass.dk/some-slug/ -> some-slug
      const m = url.match(/mirapass\.dk\/([^/]+)\/?$/);
      if (m) gscPageData[m[1]] = { clicks: r.clicks, impressions: r.impressions, position: r.position };
    });
  } catch(e) {
    if (btn) { btn.textContent = '↻ Hent GSC'; btn.disabled = false; }
    alert('Fejl ved hentning af GSC-data: ' + e.message);
    return;
  }
  renderSEO();
}

function renderSEO() {
  const pane = document.getElementById('pane-seo');
  const inbound = buildInbound();

  const rows = allPosts.map(p => {
    const { checks, score, maxScore, wc, links } = seoChecks(p, inbound[p.id]);
    return { p, checks, score, maxScore, wc, links };
  });

  // Summary cards
  const missing = key => rows.filter(r => !r.checks.find(c=>c.id===key).ok && !r.checks.find(c=>c.id===key).warn).length;
  const highPri = rows.filter(r => r.score/r.maxScore < 0.55).length;
  const medPri  = rows.filter(r => { const pct=r.score/r.maxScore; return pct>=0.55&&pct<0.85; }).length;
  const okCnt   = rows.filter(r => r.score/r.maxScore >= 0.85).length;

  // Filter + sort state
  const filterEl = document.getElementById('seo-filter-q');
  const priorityEl = document.getElementById('seo-priority');
  const q = filterEl ? filterEl.value.toLowerCase() : '';
  const priFilter = priorityEl ? priorityEl.value : '';

  let filtered = rows.filter(r => {
    const titleMatch = r.p.title.toLowerCase().includes(q) || r.p.slug.includes(q);
    if (!titleMatch) return false;
    const pct = r.score/r.maxScore;
    if (priFilter === 'high' && pct >= 0.55) return false;
    if (priFilter === 'med' && (pct < 0.55 || pct >= 0.85)) return false;
    if (priFilter === 'ok' && pct < 0.85) return false;
    return true;
  });

  filtered.sort((a,b) => {
    let va, vb;
    if (seoSort.col==='score') { va=a.score; vb=b.score; }
    else if (seoSort.col==='wc') { va=a.wc; vb=b.wc; }
    else if (seoSort.col==='links') { va=a.links; vb=b.links; }
    else { va=a.p.title; vb=b.p.title; }
    if (va<vb) return seoSort.dir==='asc'?-1:1;
    if (va>vb) return seoSort.dir==='asc'?1:-1;
    return 0;
  });

  function sortBtn(col, label) {
    const active = seoSort.col===col;
    return `<button class="seo-sort-btn${active?' '+seoSort.dir:''}" onclick="setSeoSort('${col}')">${label}</button>`;
  }

  const tableRows = filtered.map(({p, checks, score, maxScore, wc}) => {
    const sc = scoreClass(score, maxScore);
    const pct = Math.round(score/maxScore*100);
    const chips = checks.map(checkChip).join(' ');
    const badge = p.status === 'publish'
      ? '<span class="tl-badge badge-publish">Udgivet</span>'
      : '<span class="tl-badge badge-future">Planlagt</span>';
    // GSC columns
    let posCell = '<td style="text-align:right;color:var(--muted);font-size:.8rem">–</td>';
    let clickCell = '<td style="text-align:right;color:var(--muted);font-size:.8rem">–</td>';
    if (gscPageData && gscPageData[p.slug]) {
      const g = gscPageData[p.slug];
      const pos = g.position.toFixed(1);
      const posColor = g.position <= 5 ? 'var(--green)' : g.position <= 15 ? 'var(--orange)' : '#f85149';
      posCell = `<td style="text-align:right;font-size:.8rem;font-weight:600;color:${posColor}">${pos}</td>`;
      clickCell = `<td style="text-align:right;font-size:.8rem;color:var(--blue)">${g.clicks}</td>`;
    }
    return `<tr>
      <td style="text-align:center"><div class="seo-score ${sc}">${pct}%</div></td>
      <td>${priorityLabel(score, maxScore)}</td>
      <td style="font-size:.85rem"><a href="https://mirapass.dk/${p.slug}/" target="_blank" style="color:var(--text);text-decoration:none;font-weight:500" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${p.title} <span style="color:var(--muted);font-size:.75rem">↗</span></a></td>
      <td>${badge}</td>
      <td style="font-size:.78rem;color:var(--muted)">${wc.toLocaleString('da-DK')}</td>
      ${posCell}
      ${clickCell}
      <td style="white-space:nowrap;line-height:1.9">${chips}</td>
    </tr>`;
  }).join('');

  pane.innerHTML = `
    <div class="seo-grid">
      <div class="seo-card red"><div class="seo-card-val">${highPri}</div><div class="seo-card-lbl">Høj prioritet</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${medPri}</div><div class="seo-card-lbl">Kan forbedres</div></div>
      <div class="seo-card green"><div class="seo-card-val">${okCnt}</div><div class="seo-card-lbl">OK</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${missing('kw')}</div><div class="seo-card-lbl">Mangler nøgleord</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${missing('img')}</div><div class="seo-card-lbl">Mangler billede</div></div>
    </div>
    <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1rem;flex-wrap:wrap">
      <button onclick="runSeoGenerate()" style="background:#238636;color:#fff;border:none;border-radius:6px;padding:.5rem 1.1rem;cursor:pointer;font-size:.88rem">
        ✨ Generer og forbedr SEO-felter
      </button>
      <button id="gsc-into-seo-btn" onclick="loadGscIntoSEO()" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.5rem 1.1rem;cursor:pointer;font-size:.88rem">
        ↻ Hent GSC
      </button>
      <span style="font-size:.8rem;color:var(--muted)">Udfylder manglende + forbedrer for korte/lange meta title, meta beskrivelse og excerpt</span>
    </div>
    <div id="seo-gen-log" style="display:none;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1rem;font-family:monospace;font-size:.8rem;max-height:200px;overflow-y:auto;color:#e6edf3;white-space:pre-wrap"></div>
    <div class="seo-filter-bar">
      <input id="seo-filter-q" placeholder="Søg opslag…" value="${q}" oninput="renderSEO()">
      <select id="seo-priority" onchange="renderSEO()">
        <option value="" ${priFilter===''?'selected':''}>Alle prioriteter</option>
        <option value="high" ${priFilter==='high'?'selected':''}>Kun: Høj prioritet</option>
        <option value="med" ${priFilter==='med'?'selected':''}>Kun: Kan forbedres</option>
        <option value="ok" ${priFilter==='ok'?'selected':''}>Kun: OK</option>
      </select>
      <span style="font-size:.8rem;color:var(--muted);margin-left:auto">${filtered.length} opslag</span>
    </div>
    <table style="font-size:.83rem">
      <thead><tr>
        <th style="width:60px;text-align:center">${sortBtn('score','Score')}</th>
        <th style="width:100px">Prioritet</th>
        <th>${sortBtn('title','Titel')}</th>
        <th style="width:90px">Status</th>
        <th style="width:80px">${sortBtn('wc','Ord')}</th>
        <th style="width:60px;text-align:right">Pos.</th>
        <th style="width:55px;text-align:right">Klik</th>
        <th>Tjek</th>
      </tr></thead>
      <tbody>${tableRows}</tbody>
    </table>`;
}

function setSeoSort(col) {
  if (seoSort.col === col) seoSort.dir = seoSort.dir==='asc'?'desc':'asc';
  else { seoSort.col = col; seoSort.dir = col==='score'?'asc':'desc'; }
  renderSEO();
}

/* ── Intern Linking ───────────────────── */
let linkingData = null;

async function loadLinking() {
  const pane = document.getElementById('pane-linking');
  pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Analyserer links…</div>';
  try {
    const res = await fetch('/api/linking/audit');
    linkingData = await res.json();
    renderLinking();
  } catch(e) {
    pane.innerHTML = `<p style="color:#f85149;padding:2rem">Fejl: ${e.message}</p>`;
  }
}

function renderLinking() {
  const pane = document.getElementById('pane-linking');
  if (!linkingData) return;
  const { total, orphans, posts } = linkingData;
  const linked = total - orphans.length;
  const pct = Math.round(linked / total * 100);
  const barColor = pct === 100 ? '#3fb950' : pct >= 80 ? '#d29922' : '#f85149';

  const orphanRows = orphans.map(p => `
    <tr>
      <td><a href="${p.url}" target="_blank" style="color:var(--accent)">#${p.id}</a></td>
      <td><a href="${p.url}" target="_blank" style="color:var(--text);text-decoration:none;font-weight:500">${p.title}</a></td>
      <td style="color:var(--muted);font-size:.8rem">${p.slug}</td>
    </tr>`).join('');

  const allRows = posts
    .slice().sort((a,b) => (a.incoming + a.outgoing) - (b.incoming + b.outgoing))
    .map(p => {
      const total = p.incoming + p.outgoing;
      const totalColor = total === 0 ? '#f85149' : total < 3 ? '#d29922' : total < 6 ? '#58a6ff' : '#3fb950';
      const inColor = p.incoming === 0 ? '#f85149' : p.incoming < 3 ? '#d29922' : '#3fb950';
      const bar = Math.min(total, 10);
      const barPct = bar * 10;
      return `
    <tr>
      <td><a href="${p.url}" target="_blank" style="color:var(--accent)">#${p.id}</a></td>
      <td><a href="${p.url}" target="_blank" style="color:var(--text);text-decoration:none;font-weight:500">${p.title}</a></td>
      <td style="text-align:center;color:${inColor}">${p.incoming}</td>
      <td style="text-align:center;color:var(--muted)">${p.outgoing}</td>
      <td style="text-align:center">
        <span style="font-weight:600;color:${totalColor}">${total}</span>
        <div style="margin-top:3px;background:var(--border);border-radius:3px;height:4px;width:60px;display:inline-block;vertical-align:middle;margin-left:6px">
          <div style="width:${barPct}%;max-width:100%;background:${totalColor};height:4px;border-radius:3px"></div>
        </div>
      </td>
    </tr>`;}).join('');

  pane.innerHTML = `
    <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-bottom:1.5rem">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.25rem 1.75rem;min-width:180px">
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:.4rem">Med indgående links</div>
        <div style="font-size:1.9rem;font-weight:700;color:${barColor}">${linked}<span style="font-size:1rem;color:var(--muted);font-weight:400"> / ${total}</span></div>
        <div style="margin-top:.6rem;background:var(--border);border-radius:4px;height:6px">
          <div style="width:${pct}%;background:${barColor};height:6px;border-radius:4px;transition:width .4s"></div>
        </div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.25rem 1.75rem;min-width:160px">
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:.4rem">Forældreløse indlæg</div>
        <div style="font-size:1.9rem;font-weight:700;color:${orphans.length===0?'#3fb950':'#f85149'}">${orphans.length}</div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.25rem 1.75rem;min-width:180px">
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:.4rem">Maks. nye links pr. kørsel</div>
        <input id="build-limit" type="number" value="10" min="1" max="100"
          style="width:70px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:.3rem .5rem;font-size:1rem">
      </div>
      <div style="display:flex;flex-direction:column;gap:.6rem;justify-content:center">
        <button onclick="runLinkingBuild()" style="background:#238636;color:#fff;border:none;border-radius:6px;padding:.55rem 1.2rem;cursor:pointer;font-size:.88rem">
          🔗 Byg interne links
        </button>
        <button onclick="runLinkingFix()" ${orphans.length===0?'disabled':''} style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.55rem 1.2rem;cursor:pointer;font-size:.88rem;opacity:${orphans.length===0?'.4':'1'}">
          ⚡ Fix forældreløse (${orphans.length})
        </button>
        <button onclick="loadLinking()" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.45rem 1rem;cursor:pointer;font-size:.83rem">
          ↻ Opdater analyse
        </button>
      </div>
    </div>

    <div id="linking-log" style="display:none;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1.5rem;font-family:monospace;font-size:.8rem;max-height:220px;overflow-y:auto;color:#e6edf3;white-space:pre-wrap"></div>

    ${orphans.length > 0 ? `
    <h2 style="margin-bottom:.75rem">Forældreløse indlæg (${orphans.length})</h2>
    <table style="font-size:.85rem;margin-bottom:2rem">
      <thead><tr><th style="width:60px">ID</th><th>Titel</th><th>Slug</th></tr></thead>
      <tbody>${orphanRows}</tbody>
    </table>` : '<p style="color:#3fb950;margin-bottom:2rem">✅ Alle indlæg har mindst ét indgående link!</p>'}

    <h2 style="margin-bottom:.75rem">Alle indlæg — link-oversigt</h2>
    <table style="font-size:.83rem">
      <thead><tr>
        <th style="width:60px">ID</th>
        <th>Titel</th>
        <th style="text-align:center;width:60px">Ind ↓</th>
        <th style="text-align:center;width:60px">Ud ↑</th>
        <th style="text-align:center;width:140px">Total links</th>
      </tr></thead>
      <tbody>${allRows}</tbody>
    </table>`;
}

async function runLinkingFix() {
  const log = document.getElementById('linking-log');
  log.style.display = 'block';
  log.textContent = 'Starter fix…\n';

  try {
    const res = await fetch('/api/linking/fix', { method: 'POST' });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      log.textContent += decoder.decode(value);
      log.scrollTop = log.scrollHeight;
    }
    log.textContent += '\nFærdig — genindlæser analyse…\n';
    await loadLinking();
  } catch(e) {
    log.textContent += 'Fejl: ' + e.message;
  }
}

async function runLinkingBuild() {
  const log = document.getElementById('linking-log');
  const limit = parseInt(document.getElementById('build-limit').value) || 10;
  log.style.display = 'block';
  log.textContent = 'Bygger interne links…\n';
  try {
    const res = await fetch('/api/linking/build?limit=' + limit, { method: 'POST' });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      log.textContent += decoder.decode(value);
      log.scrollTop = log.scrollHeight;
    }
    log.textContent += '\nFærdig — genindlæser analyse…\n';
    await loadLinking();
  } catch(e) {
    log.textContent += 'Fejl: ' + e.message;
  }
}

/* ── SEO generator ────────────────────── */
async function runSeoGenerate() {
  const log = document.getElementById('seo-gen-log');
  log.style.display = 'block';
  log.textContent = 'Analyserer indlæg…\n';
  try {
    const res = await fetch('/api/seo/generate', { method: 'POST' });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      log.textContent += decoder.decode(value);
      log.scrollTop = log.scrollHeight;
    }
    log.textContent += '\nFærdig — genindlæser opslag…\n';
    await loadPosts();
    renderSEO();
  } catch(e) {
    log.textContent += 'Fejl: ' + e.message;
  }
}

function showLinking(btn) {
  showTab('linking', btn);
  if (!linkingData) loadLinking();
}

/* ── Search Console ───────────────────── */
let gscData = null;

async function showGSC(btn) {
  showTab('gsc', btn);
  const pane = document.getElementById('pane-gsc');
  if (gscData !== null) return;
  pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Tjekker forbindelse…</div>';
  const status = await fetch('/api/gsc/status').then(r=>r.json());
  if (!status.connected) {
    pane.innerHTML = `
      <div style="max-width:480px;margin:3rem auto;text-align:center">
        <div style="font-size:2.5rem;margin-bottom:1rem">🔍</div>
        <h2 style="margin-bottom:.75rem">Forbind Google Search Console</h2>
        <p style="color:var(--muted);margin-bottom:1.5rem">Log ind med den Google-konto der har adgang til mirapass.dk i Search Console.</p>
        <a href="/auth/gsc" style="background:var(--accent);color:#fff;border-radius:6px;padding:.65rem 1.4rem;text-decoration:none;font-size:.95rem">
          Forbind Google-konto
        </a>
      </div>`;
    return;
  }
  loadGSC();
}

async function loadGSC() {
  const pane = document.getElementById('pane-gsc');
  pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Henter Search Console data…</div>';
  const end   = new Date(); end.setDate(end.getDate()-1);
  const start = new Date(); start.setDate(start.getDate()-29);
  const fmt = d => d.toISOString().slice(0,10);
  try {
    const [byQuery, byPage] = await Promise.all([
      fetch(`/api/gsc/data?start=${fmt(start)}&end=${fmt(end)}&dims=query`).then(r=>r.json()),
      fetch(`/api/gsc/data?start=${fmt(start)}&end=${fmt(end)}&dims=page`).then(r=>r.json()),
    ]);
    if (byQuery.error === 'ikke_autoriseret') { gscData = null; showGSC(document.querySelector('.tab:last-child')); return; }
    gscData = { byQuery, byPage, start: fmt(start), end: fmt(end) };
    renderGSC();
  } catch(e) {
    pane.innerHTML = `<p style="color:#f85149;padding:2rem">Fejl: ${e.message}</p>`;
  }
}

function renderGSC() {
  const pane = document.getElementById('pane-gsc');
  if (!gscData) return;
  const rows   = gscData.byQuery.rows || [];
  const pRows  = gscData.byPage.rows  || [];

  const totClicks = rows.reduce((s,r)=>s+r.clicks,0);
  const totImpr   = rows.reduce((s,r)=>s+r.impressions,0);
  const avgCtr    = totImpr ? (totClicks/totImpr*100).toFixed(1) : 0;
  const avgPos    = rows.length ? (rows.reduce((s,r)=>s+r.position,0)/rows.length).toFixed(1) : 0;

  const topQueries = rows.slice().sort((a,b)=>b.clicks-a.clicks).slice(0,20).map(r=>`
    <tr>
      <td style="max-width:300px">${r.keys[0]}</td>
      <td style="text-align:right">${r.clicks}</td>
      <td style="text-align:right">${r.impressions}</td>
      <td style="text-align:right">${(r.ctr*100).toFixed(1)}%</td>
      <td style="text-align:right">${r.position.toFixed(1)}</td>
    </tr>`).join('');

  const topPages = pRows.slice().sort((a,b)=>b.clicks-a.clicks).slice(0,15).map(r=>{
    const slug = r.keys[0].replace('https://mirapass.dk','');
    return `
    <tr>
      <td><a href="${r.keys[0]}" target="_blank" style="color:var(--accent);font-size:.82rem">${slug}</a></td>
      <td style="text-align:right">${r.clicks}</td>
      <td style="text-align:right">${r.impressions}</td>
      <td style="text-align:right">${(r.ctr*100).toFixed(1)}%</td>
      <td style="text-align:right">${r.position.toFixed(1)}</td>
    </tr>`;}).join('');

  // Quick wins: position 4-20, impressions >= 10, sorted by impressions desc
  const quickWins = rows
    .filter(r => r.position >= 4 && r.position <= 20 && r.impressions >= 10)
    .slice().sort((a,b) => b.impressions - a.impressions)
    .slice(0, 25);

  function potentialLabel(pos) {
    if (pos <= 8)  return ['høj',    '#3fb950'];
    if (pos <= 15) return ['middel', 'var(--orange)'];
    return               ['lav',    '#f85149'];
  }

  const quickWinRows = quickWins.map(r => {
    const [potLabel, potColor] = potentialLabel(r.position);
    const barPct = Math.round(((20 - r.position) / 16) * 100);
    const qEnc = encodeURIComponent(r.keys[0]);
    return `<tr>
      <td style="max-width:260px;font-size:.82rem">${r.keys[0]}</td>
      <td style="text-align:right;font-size:.82rem">${r.impressions}</td>
      <td style="text-align:right;font-size:.82rem">${r.position.toFixed(1)}</td>
      <td style="width:130px">
        <div style="display:flex;align-items:center;gap:.5rem">
          <div style="flex:1;background:var(--border);border-radius:3px;height:6px">
            <div style="width:${barPct}%;background:${potColor};height:6px;border-radius:3px"></div>
          </div>
          <span style="font-size:.72rem;color:${potColor};font-weight:600;white-space:nowrap">${potLabel}</span>
        </div>
      </td>
      <td><button onclick="optimizeForKeyword(decodeURIComponent('${qEnc}'), ${r.position.toFixed(1)}, ${r.impressions})" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:.25rem .65rem;cursor:pointer;font-size:.78rem">Optimer →</button></td>
    </tr>`;
  }).join('');

  // CTR optimering: impressions >= 20 AND ctr < 0.03
  const lowCtrPages = pRows
    .filter(r => r.impressions >= 20 && r.ctr < 0.03)
    .slice().sort((a,b) => b.impressions - a.impressions)
    .slice(0, 20);

  const ctrRows = lowCtrPages.map(r => {
    const slug = r.keys[0].replace('https://mirapass.dk', '');
    const urlEnc = encodeURIComponent(r.keys[0]);
    // find top queries for this page by slug matching
    const pageSlug = r.keys[0].replace(/https:\/\/mirapass\.dk\/|\/$/g,'');
    const topKw = rows
      .filter(q => {
        // approximate: look for queries related to page slug words
        const slugWords = pageSlug.split('-').filter(w => w.length > 3);
        return slugWords.some(w => q.keys[0].toLowerCase().includes(w));
      })
      .sort((a,b) => b.impressions - a.impressions)
      .slice(0, 3)
      .map(q => q.keys[0])
      .join(', ');
    return `<tr>
      <td><a href="${r.keys[0]}" target="_blank" style="color:var(--accent);font-size:.82rem">${slug}</a></td>
      <td style="text-align:right;font-size:.82rem">${r.impressions}</td>
      <td style="text-align:right;font-size:.82rem;color:#f85149;font-weight:600">${(r.ctr*100).toFixed(1)}%</td>
      <td style="font-size:.75rem;color:var(--muted);max-width:200px">${topKw || '–'}</td>
      <td><button onclick="fixCtrForPage(decodeURIComponent('${urlEnc}'))" style="background:var(--accent);color:#fff;border:none;border-radius:5px;padding:.25rem .65rem;cursor:pointer;font-size:.78rem">Forbedr meta →</button></td>
    </tr>`;
  }).join('');

  pane.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;flex-wrap:wrap;gap:.5rem">
      <span style="font-size:.8rem;color:var(--muted)">${gscData.start} → ${gscData.end} (28 dage)</span>
      <div style="display:flex;gap:.5rem">
        <a href="/auth/gsc" style="background:var(--surface);color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:.35rem .8rem;font-size:.8rem;text-decoration:none" title="Re-autoriser for at opdatere tilladelser">🔑 Opdater tilladelser</a>
        <button onclick="gscData=null;loadGSC()" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.35rem .8rem;cursor:pointer;font-size:.8rem">↻ Opdater</button>
      </div>
    </div>
    <div style="display:flex;gap:1.25rem;flex-wrap:wrap;margin-bottom:1.75rem">
      ${[['Klik',totClicks,'#58a6ff'],['Visninger',totImpr,'var(--muted)'],['Gns. CTR',avgCtr+'%','#3fb950'],['Gns. position',avgPos,'#d29922']].map(([l,v,c])=>`
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem 1.4rem;min-width:130px">
        <div style="font-size:.75rem;color:var(--muted);margin-bottom:.3rem">${l}</div>
        <div style="font-size:1.7rem;font-weight:700;color:${c}">${typeof v==='number'?v.toLocaleString('da-DK'):v}</div>
      </div>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;flex-wrap:wrap;margin-bottom:2rem">
      <div>
        <h2 style="margin-bottom:.75rem">Top søgeord</h2>
        <table style="font-size:.82rem">
          <thead><tr><th>Søgning</th><th style="text-align:right">Klik</th><th style="text-align:right">Vis.</th><th style="text-align:right">CTR</th><th style="text-align:right">Pos.</th></tr></thead>
          <tbody>${topQueries}</tbody>
        </table>
      </div>
      <div>
        <h2 style="margin-bottom:.75rem">Top sider</h2>
        <table style="font-size:.82rem">
          <thead><tr><th>Side</th><th style="text-align:right">Klik</th><th style="text-align:right">Vis.</th><th style="text-align:right">CTR</th><th style="text-align:right">Pos.</th></tr></thead>
          <tbody>${topPages}</tbody>
        </table>
      </div>
    </div>

    <div style="margin-bottom:2rem">
      <h2 style="margin-bottom:.5rem">Quick wins <span style="font-size:.8rem;color:var(--muted);font-weight:400">(position 4–20, min. 10 visninger)</span></h2>
      <p style="font-size:.8rem;color:var(--muted);margin-bottom:.75rem">Søgeord der er tæt på top-3 — en lille forbedring kan give markant flere klik.</p>
      ${quickWins.length === 0
        ? '<p style="color:var(--muted);font-size:.85rem">Ingen quick wins fundet i perioden.</p>'
        : `<table style="font-size:.82rem">
          <thead><tr><th>Søgeord</th><th style="text-align:right">Vis.</th><th style="text-align:right">Pos.</th><th style="width:160px">Potentiale</th><th></th></tr></thead>
          <tbody>${quickWinRows}</tbody>
        </table>`}
    </div>

    <div style="margin-bottom:2rem">
      <h2 style="margin-bottom:.5rem">CTR Optimering <span style="font-size:.8rem;color:var(--muted);font-weight:400">(under 3% CTR, min. 20 visninger)</span></h2>
      <p style="font-size:.8rem;color:var(--muted);margin-bottom:.75rem">Sider der vises men ikke klikkes på — bedre meta title/beskrivelse kan øge CTR markant.</p>
      <div id="ctr-fix-log" style="display:none;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1rem;font-family:monospace;font-size:.8rem;max-height:180px;overflow-y:auto;color:#e6edf3;white-space:pre-wrap"></div>
      ${lowCtrPages.length === 0
        ? '<p style="color:var(--muted);font-size:.85rem">Ingen sider med lav CTR fundet.</p>'
        : `<table style="font-size:.82rem">
          <thead><tr><th>Side</th><th style="text-align:right">Vis.</th><th style="text-align:right">CTR</th><th>Top søgeord</th><th></th></tr></thead>
          <tbody>${ctrRows}</tbody>
        </table>`}
    </div>`;
}

function optimizeForKeyword(query, position, impressions) {
  // Find the best matching post
  const q = query.toLowerCase();
  let bestPost = null, bestScore = 0;
  allPosts.forEach(p => {
    let score = 0;
    const title = p.title.toLowerCase();
    const slug  = p.slug.toLowerCase().replace(/-/g,' ');
    const kw    = ((p.meta && p.meta._yoast_wpseo_focuskw) || '').toLowerCase();
    q.split(' ').forEach(word => {
      if (word.length < 3) return;
      if (title.includes(word)) score += 2;
      if (slug.includes(word))  score += 2;
      if (kw.includes(word))    score += 3;
    });
    if (score > bestScore) { bestScore = score; bestPost = p; }
  });

  const postInfo = bestPost && bestScore > 0
    ? `\nBedste match: "${bestPost.title}" (/${bestPost.slug}/)`
    : '\nIngen tæt matching side fundet — tjek manuelt.';

  const posRound = Math.round(position);
  const gap = Math.max(0, posRound - 3);

  alert(`Quick Win Forslag\n${'─'.repeat(40)}\nSøgeord: "${query}"\nNuværende position: ${position} (${impressions} visninger)\nGap til top-3: ~${gap} pladser\n${postInfo}\n\nHandlingsforslag:\n• Tilføj søgeordet til meta title (maks 60 tegn)\n• Brug søgeordet tidligt i meta beskrivelsen\n• Overvej at styrke H1/H2 med søgeordet\n• Interne links med søgeordet som ankertekst`);
}

async function fixCtrForPage(url) {
  const log = document.getElementById('ctr-fix-log');
  if (log) { log.style.display = 'block'; log.textContent = 'Sender til Gemini…\n'; }
  try {
    const res = await fetch('/api/gsc/fix-ctr', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (log) { log.textContent += decoder.decode(value); log.scrollTop = log.scrollHeight; }
    }
  } catch(e) {
    if (log) log.textContent += 'Fejl: ' + e.message;
  }
}

/* ── Google Analytics ─────────────────── */
let gaData = null;
let gaProperty = null;

async function showGA(btn) {
  showTab('ga', btn);
  if (gaData !== null) return;
  const pane = document.getElementById('pane-ga');
  pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Tjekker forbindelse…</div>';

  const status = await fetch('/api/ga/status').then(r=>r.json());
  if (!status.connected) {
    pane.innerHTML = `<div style="max-width:480px;margin:3rem auto;text-align:center">
      <div style="font-size:2.5rem;margin-bottom:1rem">📊</div>
      <h2 style="margin-bottom:.75rem">Forbind Google Analytics</h2>
      <p style="color:var(--muted);margin-bottom:1.5rem">Log ind med den Google-konto der har adgang til mirapass.dk i GA4.</p>
      <a href="/auth/gsc" style="background:var(--accent);color:#fff;border-radius:6px;padding:.65rem 1.4rem;text-decoration:none;font-size:.95rem">Forbind Google-konto</a>
    </div>`;
    return;
  }

  if (!status.property) {
    // No property selected yet — show property picker
    pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Henter properties…</div>';
    const props = await fetch('/api/ga/properties').then(r=>r.json());
    if (!props.length) {
      pane.innerHTML = '<p style="padding:2rem;color:var(--muted)">Ingen GA4 properties fundet. Tjek at Google Analytics API er aktiveret i Google Cloud Console.</p>';
      return;
    }
    const rows = props.map(p=>`<tr style="cursor:pointer" onclick="selectGAProperty('${p.id}','${p.name.replace(/'/g,"\\'")}')">
      <td><strong>${p.name}</strong></td>
      <td style="color:var(--muted);font-size:.82rem">${p.id}</td>
      <td style="color:var(--muted);font-size:.82rem">${p.account}</td>
    </tr>`).join('');
    pane.innerHTML = `<div style="max-width:600px;margin:2rem auto">
      <h2 style="margin-bottom:1rem">Vælg GA4 Property</h2>
      <table style="font-size:.88rem"><thead><tr><th>Property</th><th>ID</th><th>Konto</th></tr></thead><tbody>${rows}</tbody></table>
    </div>`;
    return;
  }

  gaProperty = status.property;
  loadGA();
}

async function selectGAProperty(id, name) {
  await fetch('/api/ga/set-property', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({property: id})});
  gaProperty = id;
  gaData = null;
  loadGA();
}

async function loadGA() {
  const pane = document.getElementById('pane-ga');
  pane.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Henter Analytics data…</div>';
  try {
    const [overview, pages, channels] = await Promise.all([
      fetch('/api/ga/data?type=overview').then(r=>r.json()),
      fetch('/api/ga/data?type=pages').then(r=>r.json()),
      fetch('/api/ga/data?type=channels').then(r=>r.json()),
    ]);
    gaData = { overview, pages, channels };
    renderGA();
  } catch(e) {
    pane.innerHTML = `<p style="color:#f85149;padding:2rem">Fejl: ${e.message}</p>`;
  }
}

function renderGA() {
  const pane = document.getElementById('pane-ga');
  if (!gaData) return;

  // Helper to get metric value from row
  const metricVal = (row, idx) => row.metricValues?.[idx]?.value || '0';
  const dimVal    = (row, idx) => row.dimensionValues?.[idx]?.value || '';

  // Overview: total organic sessions
  const ovRows = gaData.overview.rows || [];
  const totSessions = ovRows.reduce((s,r)=>s+parseInt(metricVal(r,0)),0);
  const totUsers    = ovRows.reduce((s,r)=>s+parseInt(metricVal(r,1)),0);
  const totNew      = ovRows.reduce((s,r)=>s+parseInt(metricVal(r,2)),0);

  // Pages table
  const pageRows = (gaData.pages.rows||[]).slice(0,20).map(r=>{
    const path     = dimVal(r,0);
    const sessions = parseInt(metricVal(r,0));
    const users    = parseInt(metricVal(r,1));
    const bounce   = (parseFloat(metricVal(r,2))*100).toFixed(0);
    const dur      = parseInt(metricVal(r,4));
    const durStr   = `${Math.floor(dur/60)}:${String(dur%60).padStart(2,'0')}`;
    return `<tr>
      <td><a href="https://mirapass.dk${path}" target="_blank" style="color:var(--accent);font-size:.8rem">${path}</a></td>
      <td style="text-align:right">${sessions}</td>
      <td style="text-align:right">${users}</td>
      <td style="text-align:right">${bounce}%</td>
      <td style="text-align:right">${durStr}</td>
    </tr>`;
  }).join('');

  // Channels table
  const chRows = (gaData.channels.rows||[]).map(r=>{
    const ch   = dimVal(r,0)||'(direct)';
    const sess = parseInt(metricVal(r,0));
    const usr  = parseInt(metricVal(r,1));
    const bnc  = (parseFloat(metricVal(r,2))*100).toFixed(0);
    const chColor = ch==='Organic Search'?'#3fb950':ch==='Direct'?'#58a6ff':ch.includes('Social')?'#d29922':'var(--muted)';
    return `<tr>
      <td><span style="color:${chColor};font-weight:500">${ch}</span></td>
      <td style="text-align:right">${sess.toLocaleString('da-DK')}</td>
      <td style="text-align:right">${usr.toLocaleString('da-DK')}</td>
      <td style="text-align:right">${bnc}%</td>
    </tr>`;
  }).join('');

  const newPct = totUsers ? Math.round(totNew/totUsers*100) : 0;

  pane.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;flex-wrap:wrap;gap:.5rem">
      <span style="font-size:.8rem;color:var(--muted)">Organisk søgetrafik — seneste 30 dage</span>
      <div style="display:flex;gap:.5rem">
        <a href="/auth/gsc" style="background:var(--surface);color:var(--muted);border:1px solid var(--border);border-radius:6px;padding:.35rem .8rem;font-size:.8rem;text-decoration:none" title="Re-autoriser for at tilføje Analytics-adgang">🔑 Opdater tilladelser</a>
        <button onclick="gaData=null;loadGA()" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.35rem .8rem;cursor:pointer;font-size:.8rem">↻ Opdater</button>
      </div>
    </div>
    <div style="display:flex;gap:1.25rem;flex-wrap:wrap;margin-bottom:1.75rem">
      ${[
        ['Org. sessioner', totSessions.toLocaleString('da-DK'), '#3fb950'],
        ['Brugere', totUsers.toLocaleString('da-DK'), '#58a6ff'],
        ['Nye brugere', totNew.toLocaleString('da-DK') + ' (' + newPct + '%)', '#d29922'],
      ].map(([l,v,c])=>`
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem 1.4rem;min-width:160px">
        <div style="font-size:.75rem;color:var(--muted);margin-bottom:.3rem">${l}</div>
        <div style="font-size:1.6rem;font-weight:700;color:${c}">${v}</div>
      </div>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem">
      <div>
        <h2 style="margin-bottom:.75rem">Top organiske sider</h2>
        <table style="font-size:.82rem">
          <thead><tr><th>Side</th><th style="text-align:right">Sess.</th><th style="text-align:right">Brugere</th><th style="text-align:right">Bounce</th><th style="text-align:right">Tid</th></tr></thead>
          <tbody>${pageRows || '<tr><td colspan="5" style="color:var(--muted);padding:1rem">Ingen data</td></tr>'}</tbody>
        </table>
      </div>
      <div>
        <h2 style="margin-bottom:.75rem">Trafik pr. kanal</h2>
        <table style="font-size:.82rem">
          <thead><tr><th>Kanal</th><th style="text-align:right">Sess.</th><th style="text-align:right">Brugere</th><th style="text-align:right">Bounce</th></tr></thead>
          <tbody>${chRows || '<tr><td colspan="4" style="color:var(--muted);padding:1rem">Ingen data</td></tr>'}</tbody>
        </table>
      </div>
    </div>`;
}

/* ── Auto-fix ─────────────────────────── */
async function autoFix(url, action, btn) {
  const log = document.getElementById('autofix-log');
  log.style.display = 'block';
  log.textContent = '';
  log.scrollIntoView({behavior:'smooth', block:'nearest'});
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  let success = false;
  try {
    const res = await fetch('/api/autofix', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url, action})
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      log.textContent += chunk;
      log.scrollTop = log.scrollHeight;
      if (chunk.includes('verificeret') || chunk.includes('Gemt')) success = true;
    }
    // Mark row as fixed — don't reset oppData (score is historical GSC/GA data)
    if (btn) {
      if (success) {
        btn.textContent = '✓ Gemt';
        btn.style.background = '#3fb95022';
        btn.style.color = '#3fb950';
        btn.style.borderColor = '#3fb950';
      } else {
        btn.textContent = 'Fejl';
        btn.style.color = '#f85149';
        btn.disabled = false;
      }
    }
  } catch(e) {
    log.textContent += 'Fejl: ' + e.message;
    if (btn) { btn.disabled = false; btn.textContent = 'Fix'; }
  }
}

/* ── Muligheds-matrix ─────────────────── */
let oppData = null;

async function showOpportunities(btn) {
  showTab('opp', btn);
  if (oppData) { renderOpportunities(); return; }
  document.getElementById('pane-opp').innerHTML = '<div class="loading"><div class="loading-spinner"></div>Kombinerer GSC + GA data…</div>';
  try {
    oppData = await fetch('/api/opportunities').then(r=>r.json());
    renderOpportunities();
  } catch(e) {
    document.getElementById('pane-opp').innerHTML = `<p style="color:#f85149;padding:2rem">Fejl: ${e.message}</p>`;
  }
}

function renderOpportunities() {
  const pane = document.getElementById('pane-opp');
  if (!oppData || !oppData.length) {
    pane.innerHTML = '<p style="padding:2rem;color:var(--muted)">Ingen data — tjek at GSC og GA er forbundet.</p>';
    return;
  }

  const actionLabel = {
    meta:        ['#d29922', 'Fix meta',       'Gode rankings men lav CTR → omskriv titel/beskrivelse'],
    content:     ['#f85149', 'Forbedr indhold','Lav ranking → indholdet skal styrkes'],
    engagement:  ['#58a6ff', 'Engagement',     'Klik men brugerne forlader hurtigt → forbedr indhold/struktur'],
    links:       ['#3fb950', 'Byg links',      'God performance → boost med interne links'],
  };

  const rows = oppData.map(d => {
    const [color, label, tip] = actionLabel[d.action] || ['var(--muted)','–',''];
    const scoreBar = `<div style="background:var(--border);border-radius:3px;height:6px;width:80px;display:inline-block;vertical-align:middle">
      <div style="width:${Math.min(d.opportunity,100)}%;background:${color};height:6px;border-radius:3px"></div></div>`;
    const durStr = d.duration != null ? `${Math.floor(d.duration/60)}:${String(d.duration%60|0).padStart(2,'0')}` : '–';
    const bounceStr = d.bounce != null ? d.bounce+'%' : '–';
    return `<tr>
      <td><a href="${d.url}" target="_blank" style="color:var(--text);font-size:.82rem;text-decoration:none" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${d.path}</a></td>
      <td style="text-align:center">${d.impressions}</td>
      <td style="text-align:center;color:${d.position<=10?'#3fb950':d.position<=15?'#d29922':'#f85149'}">${d.position}</td>
      <td style="text-align:center">${d.ctr}%</td>
      <td style="text-align:center">${d.sessions||'–'}</td>
      <td style="text-align:center">${bounceStr}</td>
      <td style="text-align:center">${durStr}</td>
      <td style="text-align:center">${scoreBar} <span style="font-size:.8rem;color:var(--muted)">${d.opportunity}</span></td>
      <td><span style="background:${color}22;color:${color};border-radius:4px;padding:.15rem .5rem;font-size:.78rem;white-space:nowrap" title="${tip}">${label}</span></td>
      <td><button onclick="autoFix('${d.url}','${d.action}',this)" style="background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:.25rem .6rem;cursor:pointer;font-size:.78rem;color:var(--text)">⚡ Fix</button></td>
    </tr>`;
  }).join('');

  // Summary counts by action
  const counts = {};
  oppData.forEach(d => counts[d.action] = (counts[d.action]||0)+1);

  pane.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;flex-wrap:wrap;gap:.5rem">
      <div style="display:flex;gap:.75rem;flex-wrap:wrap">
        ${Object.entries(actionLabel).map(([k,[c,l]])=>`
        <span style="background:${c}22;color:${c};border-radius:6px;padding:.3rem .75rem;font-size:.82rem">${l}: ${counts[k]||0}</span>`).join('')}
      </div>
      <button onclick="oppData=null;showOpportunities(document.querySelector('.tab.active'))" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.35rem .8rem;cursor:pointer;font-size:.8rem">Opdater</button>
    </div>
    <div id="autofix-log" style="display:none;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1rem;font-family:monospace;font-size:.8rem;max-height:200px;overflow-y:auto;color:#e6edf3;white-space:pre-wrap"></div>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.75rem">ℹ️ Scoren afspejler historisk GSC/GA-data (position, klik, CTR). Ændringer i WordPress gemmes med det samme, men scoren forbedres gradvist over 2–4 uger efterhånden som Google re-indekserer.</p>
    <table style="font-size:.83rem">
      <thead><tr>
        <th>Side</th>
        <th style="text-align:center;width:60px">Vis.</th>
        <th style="text-align:center;width:55px">Pos.</th>
        <th style="text-align:center;width:55px">CTR</th>
        <th style="text-align:center;width:55px">Sess.</th>
        <th style="text-align:center;width:65px">Bounce</th>
        <th style="text-align:center;width:55px">Tid</th>
        <th style="text-align:center;width:120px">Score</th>
        <th style="width:110px">Handling</th>
        <th style="width:60px"></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ── Dashboard / Overblik ──────────────────────────────── */
let dashExtData = null;

function getTabBtn(text) {
  return Array.from(document.querySelectorAll('.tab')).find(t => t.textContent.trim() === text);
}

async function showDashboard(btn) {
  showTab('dashboard', btn);
  if (allPosts.length) renderDashboardBase();
  if (dashExtData) {
    updateTrafficWidget(dashExtData.gsc, dashExtData.ga);
    updateOppWidget(dashExtData.opp);
  } else {
    loadDashboardExternal();
  }
}

function renderDashboardBase() {
  const pane = document.getElementById('pane-dashboard');
  if (!pane) return;
  if (!allPosts.length) { pane.innerHTML='<div class="loading"><div class="loading-spinner"></div>Indlæser data…</div>'; return; }

  const pub   = allPosts.filter(p => p.status === 'publish');
  const sched = allPosts.filter(p => p.status === 'future');
  const now   = new Date();
  const soon  = new Date(now); soon.setDate(soon.getDate()+7);
  const soonsched = sched.filter(p => new Date(p.date) <= soon);
  const n = pub.length || 1;

  // SEO completeness (published only)
  const hasTitle = pub.filter(p => ((p.meta&&p.meta._yoast_wpseo_title)||'').trim()).length;
  const hasDesc  = pub.filter(p => ((p.meta&&p.meta._yoast_wpseo_metadesc)||'').trim()).length;
  const hasKw    = pub.filter(p => ((p.meta&&p.meta._yoast_wpseo_focuskw)||'').trim()).length;
  const hasExc   = pub.filter(p => (p.excerpt||'').trim()).length;
  const seoScore = Math.round((hasTitle + hasDesc + hasKw) / (n * 3) * 100);
  const scoreColor = seoScore >= 80 ? 'var(--green)' : seoScore >= 60 ? 'var(--orange)' : '#f85149';

  // Internal links
  const inbound   = buildInbound();
  const orphans   = pub.filter(p => (inbound[p.id]||0) === 0).length;
  const totalLinks = Object.values(inbound).reduce((a,b)=>a+b, 0);
  const orphColor = orphans > 0 ? (orphans > 10 ? '#f85149' : 'var(--orange)') : 'var(--green)';

  function bar(count, total, color) {
    const pct = Math.round(count/(total||1)*100);
    return `<div class="db-bar"><div class="db-bar-fill" style="width:${pct}%;background:${color}"></div></div>`;
  }
  function pct(c,t){ return Math.round(c/(t||1)*100); }
  function barColor(p){ return p>=80?'var(--green)':p>=60?'var(--orange)':'#f85149'; }

  const seoRows = [
    ['Meta titel',    hasTitle, n],
    ['Meta beskr.',   hasDesc,  n],
    ['Focus keyword', hasKw,    n],
    ['Excerpt',       hasExc,   n],
  ].map(([lbl,c,t]) => {
    const p = pct(c,t), col = barColor(p);
    return `<div style="margin-bottom:.1rem">
      <div style="font-size:.74rem;color:var(--muted);display:flex;justify-content:space-between;margin-bottom:.12rem">
        <span>${lbl}</span><span style="color:${col}">${c}/${t} \xb7 ${p}%</span>
      </div>
      ${bar(c, t, col)}</div>`;
  }).join('');

  pane.innerHTML = `
    <div class="db-kpi-strip">
      <div class="db-kpi"><div class="val">${allPosts.length}</div><div class="lbl">Artikler i alt</div></div>
      <div class="db-kpi"><div class="val" style="color:var(--green)">${pub.length}</div><div class="lbl">Udgivet</div></div>
      <div class="db-kpi"><div class="val" style="color:var(--orange)">${sched.length}</div><div class="lbl">Planlagt</div></div>
      <div class="db-kpi"><div class="val" style="color:var(--blue)">${soonsched.length}</div><div class="lbl">N\xe6ste 7 dage</div></div>
      <div class="db-kpi"><div class="val" style="color:${scoreColor}">${seoScore}%</div><div class="lbl">SEO-sundhed</div></div>
    </div>

    <div class="db-grid3">
      <!-- Widget 1: Indhold & SEO -->
      <div class="db-widget">
        <h3>Indhold & SEO</h3>
        ${seoRows}
        <div style="border-top:1px solid var(--border);margin-top:.6rem;padding-top:.5rem">
          <div class="db-row"><span class="lbl">Interne links</span><span class="val">${totalLinks}</span></div>
          <div class="db-row"><span class="lbl" style="color:${orphColor}">For\xe6ldre\xf8se</span><span class="val" style="color:${orphColor}">${orphans} opslag</span></div>
        </div>
        <button onclick="showTab('seo',getTabBtn('SEO Analyse'))" style="margin-top:.8rem;width:100%;background:transparent;border:1px solid var(--border);border-radius:6px;padding:.35rem;font-size:.76rem;color:var(--muted);cursor:pointer" onmouseover="this.style.color='var(--accent)';this.style.borderColor='var(--accent)'" onmouseout="this.style.color='var(--muted)';this.style.borderColor='var(--border)'">\\xc5bn SEO Analyse →</button>
      </div>

      <!-- Widget 2: S\xf8getrafik (GSC + GA) — filled async -->
      <div class="db-widget" id="db-widget-traffic">
        <h3>S\xf8getrafik <span id="db-traffic-status" class="db-spin"></span></h3>
        <div style="text-align:center;padding:2rem 0;color:var(--muted);font-size:.8rem"><div class="loading-spinner" style="margin:0 auto .6rem"></div>Henter GSC + GA…</div>
      </div>

      <!-- Widget 3: Muligheder — filled async -->
      <div class="db-widget" id="db-widget-opp">
        <h3>Muligheder <span id="db-opp-status" class="db-spin"></span></h3>
        <div style="text-align:center;padding:2rem 0;color:var(--muted);font-size:.8rem"><div class="loading-spinner" style="margin:0 auto .6rem"></div>Beregner…</div>
      </div>
    </div>

    <!-- Quick actions -->
    <div class="db-widget" style="margin-bottom:0">
      <h3>Hurtige handlinger</h3>
      <div class="db-actions">
        <button class="db-act" onclick="showTab('seo',getTabBtn('SEO Analyse'))">
          <span class="icon">\U0001f50d</span><span class="albl">SEO Analyse</span><span class="asub">Gennemg\xe5 og optimer metadata</span>
        </button>
        <button class="db-act" onclick="showLinking(getTabBtn('Intern Linking'))">
          <span class="icon">\U0001f517</span><span class="albl">Intern Linking</span><span class="asub">Find og fix for\xe6ldre\xf8se indl\xe6g</span>
        </button>
        <button class="db-act" onclick="showOpportunities(getTabBtn('Muligheder'))">
          <span class="icon">⚡</span><span class="albl">Muligheder</span><span class="asub">Auto-fix SEO med GSC + GA data</span>
        </button>
        <button class="db-act" onclick="openModal()">
          <span class="icon">✍️</span><span class="albl">Planl\xe6g opslag</span><span class="asub">Generer Claude-prompt til ny indhold</span>
        </button>
      </div>
    </div>`;
}

async function loadDashboardExternal() {
  const fmt = d => d.toISOString().slice(0,10);
  const now   = new Date();
  const end   = fmt(new Date(now.getTime() - 86400000));
  const start = fmt(new Date(now.getTime() - 30*86400000));

  const [gscRes, gaRes, oppRes] = await Promise.allSettled([
    fetch(`/api/gsc/data?start=${start}&end=${end}&dims=page`).then(r=>r.json()),
    fetch('/api/ga/data?type=overview').then(r=>r.json()),
    fetch('/api/opportunities').then(r=>r.json()),
  ]);

  dashExtData = {
    gsc: gscRes.status === 'fulfilled' ? gscRes.value : null,
    ga:  gaRes.status  === 'fulfilled' ? gaRes.value  : null,
    opp: oppRes.status === 'fulfilled' ? oppRes.value : null,
  };

  updateTrafficWidget(dashExtData.gsc, dashExtData.ga);
  updateOppWidget(dashExtData.opp);
}

function updateTrafficWidget(gsc, ga) {
  const el = document.getElementById('db-widget-traffic');
  if (!el) return;

  let gscHtml = '', gaHtml = '', badge = '';

  if (gsc && !gsc.error) {
    const rows  = gsc.rows || [];
    const clicks = rows.reduce((s,r)=>s+(r.clicks||0), 0);
    const impr   = rows.reduce((s,r)=>s+(r.impressions||0), 0);
    const avgPos = rows.length ? (rows.reduce((s,r)=>s+(r.position||0),0)/rows.length).toFixed(1) : '–';
    const avgCtr = impr ? ((clicks/impr)*100).toFixed(1) : '–';
    const posCol = parseFloat(avgPos)<=5?'var(--green)':parseFloat(avgPos)<=12?'var(--orange)':'#f85149';
    const ctrCol = parseFloat(avgCtr)>=5?'var(--green)':parseFloat(avgCtr)>=2?'var(--orange)':'#f85149';
    badge = '<span class="db-badge ok">Forbundet</span>';
    gscHtml = `
      <div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:.5rem">Search Console — 30 dage</div>
      <div class="db-num-grid">
        <div class="db-num"><div class="v" style="color:var(--blue)">${clicks.toLocaleString('da-DK')}</div><div class="l">Klik</div></div>
        <div class="db-num"><div class="v">${impr.toLocaleString('da-DK')}</div><div class="l">Visninger</div></div>
        <div class="db-num"><div class="v" style="color:${posCol}">${avgPos}</div><div class="l">Gns. position</div></div>
        <div class="db-num"><div class="v" style="color:${ctrCol}">${avgCtr}%</div><div class="l">CTR</div></div>
      </div>`;
  } else if (gsc && gsc.error === 'ikke_autoriseret') {
    badge = '<span class="db-badge err">Ikke forbundet</span>';
    gscHtml = `<div style="font-size:.8rem;color:var(--muted);padding:.5rem 0 .75rem">Search Console ikke forbundet.<br><a href="/auth/gsc" style="color:var(--accent)">Forbind Google-konto →</a></div>`;
  } else {
    gscHtml = `<div style="font-size:.78rem;color:var(--muted);padding:.5rem 0">GSC-data utilg\xe6ngeligt</div>`;
  }

  if (ga && !ga.error) {
    const rows   = ga.rows || [];
    const totS   = rows.reduce((s,r)=>s+parseInt(r.metricValues?.[0]?.value||0), 0);
    const totU   = rows.reduce((s,r)=>s+parseInt(r.metricValues?.[1]?.value||0), 0);
    const totNew = rows.reduce((s,r)=>s+parseInt(r.metricValues?.[2]?.value||0), 0);
    const newPct = totU ? Math.round(totNew/totU*100) : 0;
    gaHtml = `
      <div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:.75rem 0 .4rem">Google Analytics — 30 dage</div>
      <div class="db-row"><span class="lbl">Organiske sessioner</span><span class="val" style="color:var(--green)">${totS.toLocaleString('da-DK')}</span></div>
      <div class="db-row"><span class="lbl">Brugere</span><span class="val">${totU.toLocaleString('da-DK')}</span></div>
      <div class="db-row"><span class="lbl">Nye brugere</span><span class="val">${totNew.toLocaleString('da-DK')} (${newPct}%)</span></div>`;
  } else if (ga && (ga.error === 'ikke_forbundet' || ga.error === 'ingen_property')) {
    gaHtml = `<div style="font-size:.78rem;color:var(--muted);padding:.5rem 0 0">Analytics ikke konfigureret.<br><a href="/auth/gsc" style="color:var(--accent)">Forbind →</a></div>`;
  }

  el.innerHTML = `<h3>S\xf8getrafik ${badge}</h3>${gscHtml}${gaHtml}
    <button onclick="showGSC(getTabBtn('Search Console'))" style="margin-top:.9rem;width:100%;background:transparent;border:1px solid var(--border);border-radius:6px;padding:.35rem;font-size:.76rem;color:var(--muted);cursor:pointer" onmouseover="this.style.color='var(--accent)';this.style.borderColor='var(--accent)'" onmouseout="this.style.color='var(--muted)';this.style.borderColor='var(--border)'">\xc5bn Search Console →</button>`;
}

function updateOppWidget(opps) {
  const el = document.getElementById('db-widget-opp');
  if (!el) return;

  if (!opps || opps.error || !Array.isArray(opps) || !opps.length) {
    const msg = (!opps || opps.error) ? 'Forbind GSC og GA for at se muligheder.' : 'Ingen muligheder fundet.';
    el.innerHTML = `<h3>Muligheder <span class="db-badge warn">Ingen data</span></h3><div style="font-size:.8rem;color:var(--muted);padding:.75rem 0">${msg}</div>`;
    return;
  }

  const actionMeta = {
    meta:       ['#d29922', 'Fix meta'],
    content:    ['#f85149', 'Forbedr indhold'],
    engagement: ['#58a6ff', 'Engagement'],
    links:      ['#3fb950', 'Byg links'],
  };
  const counts = {};
  opps.forEach(d => counts[d.action] = (counts[d.action]||0)+1);
  const maxN = Math.max(...Object.values(counts), 1);

  const bars = Object.entries(actionMeta).filter(([k])=>counts[k]).map(([k,[c,l]])=>{
    const n = counts[k]||0;
    const w = Math.round(n/maxN*100);
    return `<div style="display:flex;align-items:center;gap:.55rem;margin-bottom:.4rem;font-size:.79rem">
      <span style="width:88px;color:var(--muted);flex-shrink:0;font-size:.75rem">${l}</span>
      <div style="flex:1;background:var(--border);border-radius:2px;height:4px">
        <div style="width:${w}%;background:${c};border-radius:2px;height:4px"></div></div>
      <span style="color:${c};font-weight:700;width:16px;text-align:right;font-size:.8rem">${n}</span>
    </div>`;
  }).join('');

  const top3 = opps.slice(0,3).map(d => {
    const [color] = actionMeta[d.action] || ['var(--muted)'];
    const short = d.path.replace(/^\/|\/$/g,'').slice(0,26);
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:.3rem 0;border-top:1px solid var(--border);font-size:.77rem;gap:.4rem">
      <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);flex:1" title="${d.path}">/${short}/</span>
      <span style="color:${color};font-weight:700;flex-shrink:0">${d.opportunity}</span>
      <button onclick="showOpportunities(getTabBtn('Muligheder'))" style="background:${color}22;color:${color};border:1px solid ${color}44;border-radius:4px;padding:.12rem .45rem;cursor:pointer;font-size:.71rem;flex-shrink:0">Fix</button>
    </div>`;
  }).join('');

  const badge = `<span class="db-badge ok">${opps.length} sider</span>`;
  el.innerHTML = `
    <h3>Muligheder ${badge}</h3>
    ${bars}
    <div style="margin-top:.5rem">${top3}</div>
    <button onclick="showOpportunities(getTabBtn('Muligheder'))" style="margin-top:.8rem;width:100%;background:transparent;border:1px solid var(--border);border-radius:6px;padding:.35rem;font-size:.76rem;color:var(--muted);cursor:pointer" onmouseover="this.style.color='var(--accent)';this.style.borderColor='var(--accent)'" onmouseout="this.style.color='var(--muted)';this.style.borderColor='var(--border)'">Se alle muligheder →</button>`;
}

/* ── Sider SEO ─────────────────────────────────────── */
let allPages = [];
let siderSort = {col:'score', dir:'asc'};
let siderFilter = '';

async function showSider(btn) {
  showTab('sider', btn);
  if (allPages.length) { renderSider(); return; }
  document.getElementById('pane-sider').innerHTML = '<div class="loading"><div class="loading-spinner"></div>Henter WordPress-sider…</div>';
  try {
    allPages = await fetch('/api/pages').then(r=>r.json());
    renderSider();
  } catch(e) {
    document.getElementById('pane-sider').innerHTML = `<p style="color:#f85149;padding:2rem">Fejl: ${e.message}</p>`;
  }
}

function pageChecks(p) {
  const m   = p.meta || {};
  const kw  = (m._yoast_wpseo_focuskw  || '').trim();
  const mt  = (m._yoast_wpseo_title    || '').trim();
  const md  = (m._yoast_wpseo_metadesc || '').trim();
  const img = !!p.featured_media;
  const wc  = wordCount(p.content);

  const checks = [
    { id:'kw', label:'Focus kw',    ok: kw.length > 0,                          warn: false },
    { id:'mt', label:'Meta title',  ok: mt.length > 0 && mt.length <= 60,       warn: mt.length > 0 && mt.length > 60 },
    { id:'md', label:'Meta beskr.', ok: md.length >= 70 && md.length <= 155,    warn: md.length > 0 && (md.length < 70 || md.length > 155) },
    { id:'img',label:'Billede',     ok: img,                                     warn: false },
    { id:'len',label:'Indhold',     ok: wc >= 300,                               warn: wc >= 100 && wc < 300 },
  ];

  const score    = checks.reduce((a,c) => a + (c.ok ? (c.id==='kw'||c.id==='mt'||c.id==='md' ? 2 : 1) : c.warn ? 0.5 : 0), 0);
  const maxScore = 8;
  return { checks, score, maxScore, kw, mt, md, img, wc };
}

function renderSider() {
  const pane = document.getElementById('pane-sider');
  if (!allPages.length) { pane.innerHTML='<p style="padding:2rem;color:var(--muted)">Ingen sider fundet.</p>'; return; }

  const rows = allPages.map(p => ({ p, ...pageChecks(p) }));

  const highPri = rows.filter(r => r.score/r.maxScore < 0.5).length;
  const medPri  = rows.filter(r => { const x=r.score/r.maxScore; return x>=0.5 && x<0.85; }).length;
  const okCnt   = rows.filter(r => r.score/r.maxScore >= 0.85).length;
  const noMt    = rows.filter(r => !(r.mt)).length;
  const noMd    = rows.filter(r => !(r.md)).length;

  const q = siderFilter.toLowerCase();
  let filtered = rows.filter(r => !q || r.p.title.toLowerCase().includes(q) || r.p.slug.includes(q));
  filtered.sort((a,b) => {
    let va, vb;
    if (siderSort.col==='score') { va=a.score; vb=b.score; }
    else if (siderSort.col==='wc') { va=a.wc; vb=b.wc; }
    else { va=a.p.title; vb=b.p.title; }
    if (va<vb) return siderSort.dir==='asc'?-1:1;
    if (va>vb) return siderSort.dir==='asc'?1:-1;
    return 0;
  });

  function sBtn(col,lbl) {
    const act = siderSort.col===col;
    return `<button class="seo-sort-btn${act?' '+siderSort.dir:''}" onclick="setSiderSort('${col}')">${lbl}</button>`;
  }

  const tableRows = filtered.map(({p, checks, score, maxScore, wc}) => {
    const sc  = scoreClass(score, maxScore);
    const pct = Math.round(score/maxScore*100);
    const chips = checks.map(checkChip).join(' ');
    const badge = p.status==='publish'
      ? '<span class="tl-badge badge-publish">Udgivet</span>'
      : `<span class="tl-badge badge-future">${p.status}</span>`;
    const parent = p.parent ? `<span style="color:var(--muted);font-size:.72rem"> ↳ underside</span>` : '';
    const modDate = p.modified ? new Date(p.modified).toLocaleDateString('da-DK',{day:'numeric',month:'short',year:'numeric'}) : '';
    return `<tr>
      <td style="text-align:center"><div class="seo-score ${sc}">${pct}%</div></td>
      <td>${priorityLabel(score, maxScore)}</td>
      <td style="font-size:.85rem">
        <a href="${p.link}" target="_blank" style="color:var(--text);text-decoration:none;font-weight:500" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${p.title} <span style="color:var(--muted);font-size:.75rem">↗</span></a>${parent}
      </td>
      <td>${badge}</td>
      <td style="font-size:.78rem;color:var(--muted)">${wc}</td>
      <td style="font-size:.75rem;color:var(--muted)">${modDate}</td>
      <td style="white-space:nowrap;line-height:1.9">${chips}</td>
      <td><button onclick="fixPageSeo(${p.id},this)" style="background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:.25rem .65rem;cursor:pointer;font-size:.78rem;color:var(--text)">✨ Fix</button></td>
    </tr>`;
  }).join('');

  pane.innerHTML = `
    <div class="seo-grid">
      <div class="seo-card red"><div class="seo-card-val">${highPri}</div><div class="seo-card-lbl">Høj prioritet</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${medPri}</div><div class="seo-card-lbl">Kan forbedres</div></div>
      <div class="seo-card green"><div class="seo-card-val">${okCnt}</div><div class="seo-card-lbl">OK</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${noMt}</div><div class="seo-card-lbl">Ingen meta title</div></div>
      <div class="seo-card orange"><div class="seo-card-val">${noMd}</div><div class="seo-card-lbl">Ingen meta beskr.</div></div>
    </div>
    <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1rem;flex-wrap:wrap">
      <button onclick="fixAllPagesSeo()" style="background:#238636;color:#fff;border:none;border-radius:6px;padding:.5rem 1.1rem;cursor:pointer;font-size:.88rem">
        ✨ Generer SEO for alle sider
      </button>
      <button onclick="allPages=[];showSider(document.querySelector('.tab.active'))" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:.5rem 1rem;cursor:pointer;font-size:.85rem">↻ Opdater</button>
      <input placeholder="Søg sider…" value="${siderFilter}" oninput="siderFilter=this.value;renderSider()" style="background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:.4rem .75rem;color:var(--text);font-size:.82rem;outline:none">
      <span style="font-size:.8rem;color:var(--muted);margin-left:auto">${filtered.length} sider</span>
    </div>
    <div id="sider-fix-log" style="display:none;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1rem;font-family:monospace;font-size:.8rem;max-height:220px;overflow-y:auto;color:#e6edf3;white-space:pre-wrap"></div>
    <table style="font-size:.83rem">
      <thead><tr>
        <th style="width:60px;text-align:center">${sBtn('score','Score')}</th>
        <th style="width:100px">Prioritet</th>
        <th>${sBtn('title','Side')}</th>
        <th style="width:90px">Status</th>
        <th style="width:70px">${sBtn('wc','Ord')}</th>
        <th style="width:100px">Ændret</th>
        <th>Tjek</th>
        <th style="width:70px"></th>
      </tr></thead>
      <tbody>${tableRows}</tbody>
    </table>`;
}

function setSiderSort(col) {
  if (siderSort.col===col) siderSort.dir = siderSort.dir==='asc'?'desc':'asc';
  else { siderSort.col=col; siderSort.dir=col==='score'?'asc':'desc'; }
  renderSider();
}

async function fixPageSeo(pageId, btn) {
  const log = document.getElementById('sider-fix-log');
  log.style.display = 'block';
  log.scrollIntoView({behavior:'smooth',block:'nearest'});
  if (btn) { btn.disabled=true; btn.textContent='⏳'; }
  let success = false;
  try {
    const res = await fetch('/api/pages/seo-fix', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: pageId})
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      log.textContent += chunk;
      log.scrollTop = log.scrollHeight;
      if (chunk.includes('verificeret') || chunk.includes('Gemt')) success = true;
    }
    if (btn) {
      btn.textContent = success ? '✓ Gemt' : 'Fejl';
      btn.style.color = success ? '#3fb950' : '#f85149';
      btn.style.borderColor = success ? '#3fb950' : '#f85149';
    }
    // Reload page data to reflect changes
    if (success) {
      allPages = await fetch('/api/pages').then(r=>r.json());
      renderSider();
    }
  } catch(e) {
    log.textContent += 'Fejl: ' + e.message;
    if (btn) { btn.disabled=false; btn.textContent='✨ Fix'; }
  }
}

async function fixAllPagesSeo() {
  const log = document.getElementById('sider-fix-log');
  if (!log) return;
  log.style.display = 'block';
  log.textContent = '';
  log.scrollIntoView({behavior:'smooth',block:'nearest'});

  // Only fix pages missing meta title OR meta desc
  const toFix = allPages.filter(p => {
    const m = p.meta || {};
    const mt = (m._yoast_wpseo_title    || '').trim();
    const md = (m._yoast_wpseo_metadesc || '').trim();
    return !mt || !md;
  });

  if (!toFix.length) { log.textContent = 'Alle sider har allerede meta title og meta beskrivelse ✓'; return; }
  log.textContent = `Fixer ${toFix.length} sider...\\n\\n`;

  for (const page of toFix) {
    log.textContent += `─── ${page.title} (#${page.id}) ───\\n`;
    try {
      const res = await fetch('/api/pages/seo-fix', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id: page.id})
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const {done,value} = await reader.read();
        if (done) break;
        log.textContent += decoder.decode(value);
        log.scrollTop = log.scrollHeight;
      }
    } catch(e) {
      log.textContent += `Fejl: ${e.message}\\n`;
    }
    log.textContent += '\\n';
    await new Promise(r => setTimeout(r, 500)); // lille pause
  }

  log.textContent += '\\n✅ Alle sider er behandlet. Genindlæser...\\n';
  allPages = await fetch('/api/pages').then(r=>r.json());
  renderSider();
}

loadPosts();
</script>
</body>
</html>"""


# ── Intern linking helpers ────────────────────────────────────────────────────

_LINK_STOP = {
    "og","er","en","et","de","den","det","til","med","for","på","fra","af","om",
    "ved","som","der","hvad","kan","du","din","dit","i","at","ikke","hvornår",
    "hvilken","sådan","aldrig","bedre","mere","alle","hver",
    "the","and","for","with","how","your","from","into",
}

def _lk_raw(post):
    return post.get("content", {}).get("raw", "") or post.get("content", "")

def _lk_count_incoming(target, all_posts):
    slug = target.get("slug","")
    return sum(1 for p in all_posts if p["id"] != target["id"] and slug in _lk_raw(p))

def _lk_count_outgoing(post, all_posts):
    content = _lk_raw(post)
    return sum(1 for p in all_posts if p["id"] != post["id"] and p.get("slug","") in content)

def _lk_keywords(post):
    import re as _re
    title = post.get("title", {}).get("rendered", "") if isinstance(post.get("title"), dict) else post.get("title","")
    slug  = post.get("slug","").replace("-"," ")
    text  = f"{title} {slug}".lower()
    words = _re.findall(r"[a-zæøåA-ZÆØÅ]{3,}", text)
    seen, result = set(), []
    for w in words:
        if w.lower() not in _LINK_STOP and w.lower() not in seen:
            seen.add(w.lower())
            result.append(w)
    return result[:12]

def _lk_find_para(content, keywords, min_words=20):
    import re as _re
    paras = _re.findall(r'<p>(.*?)</p>', content, _re.DOTALL)
    best, best_score = None, 0
    for para in paras:
        if '<a ' in para:
            continue
        clean = _re.sub(r'<[^>]+>', '', para).strip()
        if len(clean.split()) < min_words:
            continue
        for kw in keywords:
            m = _re.search(r'\b' + _re.escape(kw) + r'\b', clean, _re.IGNORECASE)
            if m:
                score = len(clean.split()) - len(kw)
                if best is None or score < best_score:
                    best_score = score
                    best = (m.group(0), kw)
                break
    return best

def _lk_find_donor(target, all_posts, min_words=20):
    slug     = target.get("slug","")
    keywords = _lk_keywords(target)
    if not keywords:
        return None
    candidates = []
    for donor in all_posts:
        if donor["id"] == target["id"]:
            continue
        if slug in _lk_raw(donor):
            continue
        result = _lk_find_para(_lk_raw(donor), keywords, min_words)
        if result:
            find_text, _ = result
            incoming = _lk_count_incoming(donor, all_posts)
            candidates.append((incoming, donor, find_text))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    _, donor, find_text = candidates[0]
    return donor, find_text

def _lk_insert(content, find_text, url):
    import re as _re
    pattern = _re.compile(
        r'(<p>(?:(?!<a\s).)*?\b)(' + _re.escape(find_text) + r')(\b(?:(?!</p>).)*?</p>)',
        _re.DOTALL | _re.IGNORECASE,
    )
    new, n = pattern.subn(
        lambda m: m.group(1) + f'<a href="{url}">{m.group(2)}</a>' + m.group(3),
        content, count=1,
    )
    return new if n else content

def _lk_fetch_all():
    """Henter alle publicerede indlæg med fuldt rå indhold til linking-analyse."""
    posts, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=wp_auth(), params={
            "per_page": 100, "page": page, "context": "edit", "status": "publish",
        }, timeout=30)
        batch = r.json()
        if not batch or isinstance(batch, dict):
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts

def linking_audit():
    """Returnerer linking-status for alle indlæg."""
    all_posts = _lk_fetch_all()
    result = []
    for p in all_posts:
        inc = _lk_count_incoming(p, all_posts)
        out = _lk_count_outgoing(p, all_posts)
        result.append({
            "id":       p["id"],
            "title":    p.get("title",{}).get("rendered","") if isinstance(p.get("title"),dict) else p.get("title",""),
            "slug":     p.get("slug",""),
            "url":      p.get("link",""),
            "incoming": inc,
            "outgoing": out,
        })
    orphans = [r for r in result if r["incoming"] == 0]
    return {"total": len(result), "orphans": orphans, "posts": result}

def linking_fix_stream(wfile):
    """Streamer fix-log mens forældreløse indlæg linkes op. Skriver direkte til wfile."""
    def w(msg):
        try:
            wfile.write((msg + "\n").encode())
            wfile.flush()
        except Exception:
            pass

    all_posts = _lk_fetch_all()
    orphans   = [p for p in all_posts if _lk_count_incoming(p, all_posts) == 0]
    w(f"Hentede {len(all_posts)} indlæg — {len(orphans)} forældreløse\n")

    ok, skipped = 0, []
    for i, target in enumerate(orphans, 1):
        tid   = target["id"]
        title = (target.get("title",{}).get("rendered","") if isinstance(target.get("title"),dict) else target.get("title",""))[:55]
        turl  = target.get("link","")
        w(f"[{i}/{len(orphans)}] #{tid} {title}")

        result = _lk_find_donor(target, all_posts)
        if not result:
            w(f"  ⚠️  Ingen egnet donor\n")
            skipped.append(tid)
            continue

        donor, find_text = result
        did    = donor["id"]
        dtitle = (donor.get("title",{}).get("rendered","") if isinstance(donor.get("title"),dict) else donor.get("title",""))[:45]
        content     = _lk_raw(donor)
        new_content = _lk_insert(content, find_text, turl)

        if new_content == content:
            w(f"  ⚠️  Kunne ikke indsætte link i #{did}\n")
            skipped.append(tid)
            continue

        r = requests.post(f"{WP_BASE}/posts/{did}", auth=wp_auth(),
                          json={"content": new_content}, timeout=30)
        if r.status_code == 200:
            if isinstance(donor.get("content"), dict):
                donor["content"]["raw"] = new_content
            else:
                donor["content"] = new_content
            w(f"  ✅ Link fra #{did} '{dtitle}'\n")
            ok += 1
        else:
            w(f"  ❌ Gem fejlede for #{did} (HTTP {r.status_code})\n")
            skipped.append(tid)

        import time as _t; _t.sleep(0.5)

    w(f"\n{'='*50}")
    w(f"Færdig: {ok}/{len(orphans)} links tilføjet")
    if skipped:
        w(f"Sprunget over: {skipped}")


def seo_generate_stream(wfile):
    """
    Finder indlæg med manglende meta title, meta beskrivelse eller excerpt
    og genererer dem via Gemini. Streamer log til wfile.
    """
    import re as _re
    import json as _json

    def w(msg):
        try:
            wfile.write((msg + "\n").encode())
            wfile.flush()
        except Exception:
            pass

    # Hent alle indlæg med fuld context
    resp = requests.get(f"{WP_BASE}/posts", auth=wp_auth(),
                        params={"per_page": 100, "context": "edit",
                                "status": "publish"}, timeout=30)
    posts = resp.json()

    # Find indlæg der mangler felter ELLER kan forbedres
    needs = []
    for p in posts:
        m   = p.get("meta", {}) or {}
        mt  = (m.get("_yoast_wpseo_title",    "") or "").strip()
        md  = (m.get("_yoast_wpseo_metadesc", "") or "").strip()
        exc = (p.get("excerpt", {}).get("raw", "") or "").strip()
        issues = {}
        # Mangler helt
        if not mt:  issues["meta_title"] = ("mangler", "")
        if not md:  issues["meta_desc"]  = ("mangler", "")
        if not exc: issues["excerpt"]    = ("mangler", "")
        # Kan forbedres (findes men er udenfor optimal længde)
        if mt  and len(mt) > 60:              issues["meta_title"] = ("for lang",   mt)
        if md  and len(md) < 70:              issues["meta_desc"]  = ("for kort",   md)
        if md  and len(md) > 155:             issues["meta_desc"]  = ("for lang",   md)
        if issues:
            needs.append((p, issues))

    missing_cnt  = sum(1 for _, iss in needs if any(s=="mangler"  for s,_ in iss.values()))
    improve_cnt  = sum(1 for _, iss in needs if any(s!="mangler"  for s,_ in iss.values()))
    w(f"Fandt {len(needs)} indlæg der skal opdateres "
      f"({missing_cnt} mangler felt, {improve_cnt} kan forbedres)\n")
    if not needs:
        w("✅ Alle indlæg har korrekte meta title, meta beskrivelse og excerpt!")
        return

    gemini_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    api_key = _gemini_key()

    ok = 0
    for i, (p, issues) in enumerate(needs, 1):
        pid   = p["id"]
        title = p.get("title", {}).get("rendered", "") or p.get("title", "")
        slug  = p.get("slug", "")
        raw   = (p.get("content", {}).get("raw", "") or "")
        plain = _re.sub(r'<[^>]+>', ' ', raw)
        plain = _re.sub(r'\s+', ' ', plain).strip()[:1200]

        issues_str = ", ".join(f'{k} ({v})' for k, (v, _) in issues.items())
        w(f"[{i}/{len(needs)}] #{pid} {title[:55]}")
        w(f"  → {issues_str}")

        # Byg beskrivelse af eksisterende (dårlige) værdier til Gemini
        existing_notes = []
        for field, (status, val) in issues.items():
            if val:
                existing_notes.append(f'  Nuværende {field} ({status}): "{val}"')
        existing_block = "\n".join(existing_notes) if existing_notes else "  (ingen eksisterende værdier)"

        # Byg felter der skal genereres
        fields_needed = list(issues.keys())
        json_fields = {}
        if "meta_title" in fields_needed:
            json_fields["meta_title"] = "SEO-titel max 60 tegn, slut med | Mirapass"
        if "meta_desc" in fields_needed:
            json_fields["meta_desc"] = "Meta-beskrivelse 120-155 tegn, naturlig og klikvenlig"
        if "excerpt" in fields_needed:
            json_fields["excerpt"] = "Kort resumé 1-2 sætninger til kortlistevisning"
        json_template = _json.dumps(json_fields, ensure_ascii=False, indent=2)

        prompt = f"""Du er SEO-redaktør for mirapass.dk (dansk blog om Claude AI).

Indlæg:
Titel: {title}
Slug: {slug}
Indhold (uddrag): {plain}

Eksisterende felter der skal forbedres:
{existing_block}

Generer KUN disse felter på DANSK og returner valid JSON:
{json_template}

Regler:
- meta_title: max 60 tegn inkl. ' | Mirapass'
- meta_desc: præcis 120-155 tegn — tæl tegnene!
- excerpt: 150-250 tegn, ingen HTML
- Sprog: dansk, professionelt men tilgængeligt
- Returner KUN JSON, ingen forklaring"""

        try:
            r = requests.post(
                f"{gemini_url}?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.4}},
                timeout=30,
            )
            raw_resp = r.json()
            text = raw_resp["candidates"][0]["content"]["parts"][0]["text"]
            text = _re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=_re.MULTILINE)
            text = _re.sub(r'\s*```$', '', text.strip(), flags=_re.MULTILINE)
            generated = _json.loads(text.strip())
        except Exception as e:
            w(f"  ⚠️  Gemini fejl: {e}\n")
            continue

        meta_patch = {}
        if "meta_title" in issues:
            meta_patch["_yoast_wpseo_title"] = generated.get("meta_title", "")
        if "meta_desc" in issues:
            meta_patch["_yoast_wpseo_metadesc"] = generated.get("meta_desc", "")

        payload = {}
        if meta_patch:
            payload["meta"] = meta_patch
        if "excerpt" in issues:
            payload["excerpt"] = generated.get("excerpt", "")

        save = requests.post(f"{WP_BASE}/posts/{pid}", auth=wp_auth(),
                             json=payload, timeout=30)
        if save.status_code == 200:
            for field in fields_needed:
                val = generated.get(field, "")
                w(f'  {field}: "{val[:75]}"  ({len(val)} tegn)')
            w(f"  ✅ Gemt\n")
            ok += 1
        else:
            w(f"  ❌ Gem fejlede (HTTP {save.status_code})\n")

        import time as _t; _t.sleep(0.8)

    w(f"{'='*50}")
    w(f"Færdig: {ok}/{len(needs)} indlæg opdateret")


def linking_build_stream(wfile, limit=10):
    """
    Kører én runde generel link-building på alle indlæg.
    For hvert target-indlæg: find bedste donor der ikke allerede linker til det.
    Stopper efter `limit` nye links er tilføjet.
    """
    def w(msg):
        try:
            wfile.write((msg + "\n").encode())
            wfile.flush()
        except Exception:
            pass

    all_posts = _lk_fetch_all()
    w(f"Hentede {len(all_posts)} indlæg — søger link-muligheder (maks {limit})\n")

    # Sorter targets: færrest indgående links først (de har mest brug for links)
    targets = sorted(all_posts, key=lambda p: _lk_count_incoming(p, all_posts))

    added = 0
    for target in targets:
        if added >= limit:
            break
        tid   = target["id"]
        slug  = target.get("slug", "")
        turl  = target.get("link", "")
        title = (target.get("title", {}).get("rendered", "") if isinstance(target.get("title"), dict) else target.get("title", ""))[:55]

        result = _lk_find_donor(target, all_posts)
        if not result:
            continue

        donor, find_text = result
        did    = donor["id"]
        dtitle = (donor.get("title", {}).get("rendered", "") if isinstance(donor.get("title"), dict) else donor.get("title", ""))[:40]
        content     = _lk_raw(donor)
        new_content = _lk_insert(content, find_text, turl)

        if new_content == content:
            continue

        r = requests.post(f"{WP_BASE}/posts/{did}", auth=wp_auth(),
                          json={"content": new_content}, timeout=30)
        if r.status_code == 200:
            if isinstance(donor.get("content"), dict):
                donor["content"]["raw"] = new_content
            else:
                donor["content"] = new_content
            w(f"✅ #{tid} '{title[:45]}'\n   ← link fra #{did} '{dtitle}'\n")
            added += 1
        else:
            w(f"❌ Gem fejlede for #{did} (HTTP {r.status_code})\n")

        import time as _t; _t.sleep(0.4)

    w(f"\n{'='*50}")
    w(f"Færdig: {added} nye links tilføjet")


def gsc_fix_ctr_stream(wfile, url):
    """
    Henter top-søgeord for en side fra GSC, henter nuværende meta fra WP,
    kalder Gemini for at rewrite meta title + beskrivelse, gemmer tilbage til WP.
    Streamer log til wfile.
    """
    import re as _re
    import json as _json
    from datetime import date, timedelta

    def w(msg):
        try:
            wfile.write((msg + "\n").encode())
            wfile.flush()
        except Exception:
            pass

    # Ekstraher slug fra URL
    slug_m = _re.search(r'mirapass\.dk/([^/]+)/?$', url)
    slug = slug_m.group(1) if slug_m else ''
    w(f"Side: {url}")
    w(f"Slug: {slug}\n")

    # Hent top-5 søgeord for siden (approximeret via query-data + slug)
    end_d   = date.today() - timedelta(days=1)
    start_d = date.today() - timedelta(days=29)
    w("Henter søgeord fra GSC…")
    query_data = gsc_fetch(
        "https://mirapass.dk/",
        start_d.isoformat(), end_d.isoformat(),
        ["query"]
    )
    query_rows = query_data.get("rows", [])

    # Match søgeord til siden via slug-ord
    slug_words = [w2 for w2 in slug.split('-') if len(w2) > 3]
    matched = []
    for r in query_rows:
        q = r["keys"][0].lower()
        score = sum(1 for sw in slug_words if sw in q)
        if score > 0:
            matched.append((score, r))
    matched.sort(key=lambda x: (-x[0], -x[1]["impressions"]))
    top_queries = [r["keys"][0] for _, r in matched[:5]]
    if not top_queries:
        # Fallback: bare top-5 queries generelt
        top_queries = [r["keys"][0] for r in query_rows[:5]]
    w(f"Top søgeord: {', '.join(top_queries)}\n")

    # Hent nuværende meta fra WP
    w("Henter nuværende meta fra WordPress…")
    try:
        resp = requests.get(
            f"{WP_BASE}/posts",
            auth=wp_auth(),
            params={"slug": slug, "context": "edit", "status": "publish,future"},
            timeout=20,
        )
        posts = resp.json()
    except Exception as e:
        w(f"Fejl ved WP-opslag: {e}")
        return

    if not posts or not isinstance(posts, list):
        w(f"Ingen WP-indlæg fundet for slug '{slug}'")
        return

    post = posts[0]
    pid  = post["id"]
    title_rendered = post.get("title", {}).get("rendered", "") if isinstance(post.get("title"), dict) else post.get("title", "")
    m    = post.get("meta", {}) or {}
    cur_mt  = (m.get("_yoast_wpseo_title",    "") or "").strip()
    cur_md  = (m.get("_yoast_wpseo_metadesc", "") or "").strip()
    w(f"Titel: {title_rendered}")
    w(f"Nuv. meta title: {cur_mt or '(mangler)'}")
    w(f"Nuv. meta desc: {cur_md or '(mangler)'}\n")

    # Kald Gemini
    w("Kalder Gemini for CTR-optimering…")
    gemini_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    api_key = _gemini_key()

    prompt = f"""Du er SEO-specialist for mirapass.dk (dansk blog om Claude AI).
En side har lav CTR (under 3%) trods mange visninger.

Side-info:
- Titel: {title_rendered}
- Slug: {slug}
- Nuværende meta title: {cur_mt or '(ingen)'}
- Nuværende meta beskrivelse: {cur_md or '(ingen)'}

Søgeord folk faktisk bruger for at finde siden:
{chr(10).join('- ' + q for q in top_queries)}

Skriv en mere klikvenlig meta title og meta beskrivelse.
Returner KUN valid JSON med disse to felter:
{{
  "meta_title": "max 60 tegn inkl. ' | Mirapass'",
  "meta_desc": "præcis 120-155 tegn, overbevisende og klikvenlig, inkluder vigtigste søgeord"
}}

Regler:
- Brug de faktiske søgeord fra listen naturligt
- Meta title max 60 tegn inkl. ' | Mirapass'
- Meta desc: 120-155 tegn — tæl grundigt!
- Dansk, professionelt men tilgængeligt
- Returner KUN JSON"""

    try:
        r = requests.post(
            f"{gemini_url}?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.5}},
            timeout=30,
        )
        raw_resp = r.json()
        text = raw_resp["candidates"][0]["content"]["parts"][0]["text"]
        text = _re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=_re.MULTILINE)
        text = _re.sub(r'\s*```$', '', text.strip(), flags=_re.MULTILINE)
        generated = _json.loads(text.strip())
    except Exception as e:
        w(f"Gemini fejl: {e}")
        return

    new_mt = generated.get("meta_title", "")
    new_md = generated.get("meta_desc", "")
    w(f"\nNy meta title ({len(new_mt)} tegn): {new_mt}")
    w(f"Ny meta desc  ({len(new_md)} tegn): {new_md}\n")

    # Gem til WordPress
    w("Gemmer til WordPress…")
    save = requests.post(
        f"{WP_BASE}/posts/{pid}",
        auth=wp_auth(),
        json={"meta": {
            "_yoast_wpseo_title":    new_mt,
            "_yoast_wpseo_metadesc": new_md,
        }},
        timeout=30,
    )
    if save.status_code == 200:
        w(f"✅ Gemt! (#{pid})")
    else:
        w(f"❌ Gem fejlede (HTTP {save.status_code}): {save.text[:200]}")


def build_opportunities():
    """Kombinerer GSC + GA data per side og beregner muligheds-score."""
    from datetime import date, timedelta
    end   = (date.today() - timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=29)).isoformat()

    # GSC page data
    gsc = gsc_fetch("https://mirapass.dk/", start, end, ["page"])
    gsc_rows = gsc.get("rows", [])

    # GA organic page data
    prop = _ga_property_id()
    ga = ga_fetch(prop, start, end,
        ["pagePath"],
        ["sessions","activeUsers","bounceRate","averageSessionDuration","screenPageViews"],
        {"filter": {"fieldName":"sessionDefaultChannelGrouping","stringFilter":{"matchType":"EXACT","value":"Organic Search"}}}) if prop else {}
    ga_rows = ga.get("rows", [])

    # Index GA by path
    ga_by_path = {}
    for r in ga_rows:
        path = r["dimensionValues"][0]["value"]
        ga_by_path[path] = {
            "sessions": int(r["metricValues"][0]["value"]),
            "users":    int(r["metricValues"][1]["value"]),
            "bounce":   float(r["metricValues"][2]["value"]),
            "duration": float(r["metricValues"][3]["value"]),
        }

    results = []
    for r in gsc_rows:
        url  = r["keys"][0]
        path = url.replace("https://mirapass.dk", "")
        ga_d = ga_by_path.get(path, {})

        impressions = r.get("impressions", 0)
        clicks      = r.get("clicks", 0)
        ctr         = r.get("ctr", 0)
        position    = r.get("position", 99)
        sessions    = ga_d.get("sessions", 0)
        bounce      = ga_d.get("bounce", None)
        duration    = ga_d.get("duration", None)

        # Opportunity score: high impressions, bad position/CTR, low engagement = most urgent
        pos_score  = max(0, (20 - position) / 20 * 40)
        ctr_gap    = max(0, (0.05 - ctr) / 0.05 * 30)
        impr_score = min(20, impressions / 10)
        eng_gap    = (1 - min(1, (duration or 0) / 120)) * 10 if duration is not None else 5
        opportunity = round(pos_score + ctr_gap + impr_score + eng_gap, 1)

        # Action type
        if position > 15:
            action = "content"
        elif ctr < 0.02:
            action = "meta"
        elif bounce and bounce > 0.6:
            action = "engagement"
        else:
            action = "links"

        results.append({
            "url":         url,
            "path":        path,
            "impressions": impressions,
            "clicks":      clicks,
            "ctr":         round(ctr * 100, 1),
            "position":    round(position, 1),
            "sessions":    sessions,
            "bounce":      round(bounce * 100, 1) if bounce is not None else None,
            "duration":    round(duration, 0) if duration is not None else None,
            "opportunity": opportunity,
            "action":      action,
        })

    results.sort(key=lambda x: -x["opportunity"])
    return results


def autofix_stream(wfile, url, action):
    """
    Auto-fix en side baseret på action type:
    - meta: hent GSC søgeord + GA data -> Gemini omskriver meta title + beskrivelse
    - content: Gemini forbedrer intro-afsnit baseret på søgehensigt
    - engagement: Gemini tilføjer TL;DR + bedre struktur
    - links: find og tilføj interne links
    """
    import re as _re, json as _json
    from datetime import date, timedelta

    def w(msg):
        try: wfile.write((msg+"\n").encode()); wfile.flush()
        except Exception: pass

    end   = (date.today() - timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=29)).isoformat()

    slug = url.replace("https://mirapass.dk/","").strip("/")
    w(f"Analyserer: /{slug}/")

    # Find WP post
    resp = requests.get(f"{WP_BASE}/posts", auth=wp_auth(),
        params={"slug": slug, "context": "edit"}, timeout=15)
    posts = resp.json()
    if not posts:
        w("Indlaeg ikke fundet i WordPress"); return
    post  = posts[0]
    pid   = post["id"]
    title = post.get("title",{}).get("rendered","")
    raw   = post.get("content",{}).get("raw","")
    plain = _re.sub(r'<[^>]+>',' ', raw)
    plain = _re.sub(r'\s+', ' ', plain).strip()[:1500]
    m     = post.get("meta",{}) or {}
    cur_mt = (m.get("_yoast_wpseo_title","") or "").strip()
    cur_md = (m.get("_yoast_wpseo_metadesc","") or "").strip()

    # Get GSC query data for this page
    gsc_q = gsc_fetch("https://mirapass.dk/", start, end, ["query","page"])
    top_queries = [r["keys"][0] for r in gsc_q.get("rows",[])
                   if slug in r.get("keys",["",""])[1]][:8]
    if not top_queries:
        gsc_g = gsc_fetch("https://mirapass.dk/", start, end, ["query"])
        top_queries = [r["keys"][0] for r in gsc_g.get("rows",[])[:5]]

    w(f"Top soegeord: {', '.join(top_queries[:5]) or 'ingen fundet'}")

    api_key = _gemini_key()
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    if action in ("meta", "engagement", "content"):
        w(f"\nGenererer forbedret meta (action: {action})...")

        focus = "klikfrekvens — skriv en meta title og beskrivelse der er uimodstaelig at klikke paa" if action == "meta" \
           else "soegehensigt — brugere forlader siden hurtigt, meta skal matche hvad de leder efter bedre"

        prompt = f"""Du er SEO-specialist for mirapass.dk (dansk blog om Claude AI).

Side: {url}
Nuvaerende titel: {title}
Nuvaerende meta title: {cur_mt or '(ingen)'}
Nuvaerende meta beskrivelse: {cur_md or '(ingen)'}

Top soegeord der finder denne side:
{chr(10).join('- ' + q for q in top_queries) or '(ingen data)'}

Indhold (uddrag): {plain[:800]}

Problem: {focus}

Returner KUN valid JSON:
{{
  "meta_title": "Ny SEO-titel max 60 tegn, slut med | Mirapass",
  "meta_desc": "Ny beskrivelse praecis 120-155 tegn, klikvenlig og praecis",
  "reasoning": "Kort forklaring paa hvad du aendrede og hvorfor (max 100 tegn)"
}}"""

        try:
            r = requests.post(f"{gemini_url}?key={api_key}",
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.5}}, timeout=30)
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = _re.sub(r'^```(?:json)?\s*','',text.strip(),flags=_re.MULTILINE)
            text = _re.sub(r'\s*```$','',text.strip(),flags=_re.MULTILINE)
            gen  = _json.loads(text.strip())
        except Exception as e:
            w(f"Gemini fejl: {e}"); return

        w(f'  meta title:  "{gen.get("meta_title","")}\"  ({len(gen.get("meta_title",""))} tegn)')
        w(f'  meta desc:   "{gen.get("meta_desc","")[:80]}..."  ({len(gen.get("meta_desc",""))} tegn)')
        w(f'  begrundelse: {gen.get("reasoning","")}')

        new_mt = gen.get("meta_title","").strip()
        new_md = gen.get("meta_desc","").strip()
        save = requests.post(f"{WP_BASE}/posts/{pid}", auth=wp_auth(),
            json={"meta": {
                "_yoast_wpseo_title":    new_mt,
                "_yoast_wpseo_metadesc": new_md,
            }}, timeout=30)
        if save.status_code != 200:
            w(f"Gem fejlede (HTTP {save.status_code}): {save.text[:200]}\n")
        else:
            # Verificer at felterne faktisk landede
            verify = requests.get(f"{WP_BASE}/posts/{pid}", auth=wp_auth(),
                params={"context":"edit"}, timeout=15)
            vm = (verify.json().get("meta") or {}) if verify.status_code == 200 else {}
            saved_mt = (vm.get("_yoast_wpseo_title","") or "").strip()
            saved_md = (vm.get("_yoast_wpseo_metadesc","") or "").strip()
            mt_ok = saved_mt == new_mt
            md_ok = saved_md == new_md
            if mt_ok and md_ok:
                w("Gemt og verificeret i WordPress ✓\n")
            elif not mt_ok and not md_ok:
                w(f"ADVARSEL: felterne ser ikke ud til at vaere gemt!\n")
                w(f"  Forventet title:  '{new_mt[:60]}'\n")
                w(f"  Gemt title:       '{saved_mt[:60]}'\n")
                w(f"  (WP returnerede 200, men meta kan vaere skrivebeskyttet)\n")
            else:
                w(f"Delvist gemt: title={'OK' if mt_ok else 'FEJL'}, desc={'OK' if md_ok else 'FEJL'}\n")
            w("NB: GSC/GA-scoren afspejler historisk data — forbedring ses over 2-4 uger.\n")

    elif action == "links":
        w("\nSoeger link-muligheder...")
        all_posts = _lk_fetch_all()
        target    = next((p for p in all_posts if p.get("slug") == slug), None)
        if not target:
            w("Post ikke fundet til linking"); return
        result = _lk_find_donor(target, all_posts)
        if not result:
            w("Ingen egnet donor fundet"); return
        donor, find_text = result
        did    = donor["id"]
        dtitle = (donor.get("title",{}).get("rendered","") if isinstance(donor.get("title"),dict) else donor.get("title",""))[:45]
        content     = _lk_raw(donor)
        new_content = _lk_insert(content, find_text, url)
        if new_content == content:
            w("Kunne ikke indsaette link"); return
        r2 = requests.post(f"{WP_BASE}/posts/{did}", auth=wp_auth(),
            json={"content": new_content}, timeout=30)
        if r2.status_code == 200:
            if isinstance(donor.get("content"),dict): donor["content"]["raw"] = new_content
            w(f"Link tilfojet fra #{did} '{dtitle}'\n")
        else:
            w(f"Gem fejlede\n")

    w("="*40)
    w("Faerdig")


def pages_seo_fix_stream(wfile, page_id):
    import re as _re, json as _json
    def w(msg):
        try: wfile.write((msg+"\n").encode()); wfile.flush()
        except Exception: pass

    # Fetch page
    resp = requests.get(f"{WP_BASE}/pages/{page_id}", auth=wp_auth(),
        params={"context":"edit"}, timeout=15)
    if resp.status_code != 200:
        w(f"Kunne ikke hente side #{page_id}"); return
    page = resp.json()
    title   = (page.get("title") or {}).get("rendered","")
    raw     = (page.get("content") or {}).get("raw","")
    plain   = _re.sub(r'<[^>]+>',' ', raw)
    plain   = _re.sub(r'\s+', ' ', plain).strip()[:1500]
    m       = page.get("meta") or {}
    cur_mt  = (m.get("_yoast_wpseo_title","") or "").strip()
    cur_md  = (m.get("_yoast_wpseo_metadesc","") or "").strip()
    cur_kw  = (m.get("_yoast_wpseo_focuskw","") or "").strip()
    slug    = page.get("slug","")

    w(f"Side: {title} (#{page_id})")
    w(f"Nuv. meta title:  '{cur_mt or '(ingen)'}'")
    w(f"Nuv. meta beskr.: '{cur_md[:60] + '...' if len(cur_md)>60 else cur_md or '(ingen)'}'")
    w(f"Nuv. focus kw:    '{cur_kw or '(ingen)'}'")
    w("")

    api_key = _gemini_key()
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    prompt = f"""Du er SEO-specialist for mirapass.dk (dansk blog/hjemmeside om Claude AI).

WordPress-side: /{slug}/
Sidetitel: {title}
Nuværende meta title: {cur_mt or '(ingen)'}
Nuværende meta beskrivelse: {cur_md or '(ingen)'}
Nuværende focus keyword: {cur_kw or '(ingen)'}

Sideindhold (uddrag):
{plain[:1000]}

Opgave: Generer optimerede SEO-felter til denne WordPress-side.

Krav:
- meta_title: max 60 tegn, indeholder primært søgeord, slutter med "| Mirapass"
- meta_desc: præcis 120-155 tegn, klikvenlig, inkluderer søgeord naturligt
- focus_kw: ét primært søgeord (2-4 ord), dansk, høj søgevolumen
- Returner KUN valid JSON uden forklaring

{{
  "meta_title": "...",
  "meta_desc": "...",
  "focus_kw": "...",
  "reasoning": "Kort begrundelse max 100 tegn"
}}"""

    try:
        r = requests.post(f"{gemini_url}?key={api_key}",
            json={"contents":[{"parts":[{"text":prompt}]}],
                  "generationConfig":{"temperature":0.4}}, timeout=30)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = _re.sub(r'^```(?:json)?\s*','',text.strip(),flags=_re.MULTILINE)
        text = _re.sub(r'\s*```$','',text.strip(),flags=_re.MULTILINE)
        gen  = _json.loads(text.strip())
    except Exception as e:
        w(f"Gemini fejl: {e}"); return

    new_mt = gen.get("meta_title","").strip()
    new_md = gen.get("meta_desc","").strip()
    new_kw = gen.get("focus_kw","").strip()

    w(f"Genereret meta title:  '{new_mt}' ({len(new_mt)} tegn)")
    w(f"Genereret meta beskr.: '{new_md}' ({len(new_md)} tegn)")
    w(f"Genereret focus kw:    '{new_kw}'")
    w(f"Begrundelse: {gen.get('reasoning','')}")
    w("")

    # Save to WordPress
    save = requests.post(f"{WP_BASE}/pages/{page_id}", auth=wp_auth(),
        json={"meta": {
            "_yoast_wpseo_title":    new_mt,
            "_yoast_wpseo_metadesc": new_md,
            "_yoast_wpseo_focuskw":  new_kw,
        }}, timeout=30)

    if save.status_code != 200:
        w(f"Gem fejlede (HTTP {save.status_code})"); return

    # Verify
    verify = requests.get(f"{WP_BASE}/pages/{page_id}", auth=wp_auth(),
        params={"context":"edit"}, timeout=15)
    vm = (verify.json().get("meta") or {}) if verify.status_code == 200 else {}
    mt_ok = (vm.get("_yoast_wpseo_title","") or "").strip() == new_mt
    md_ok = (vm.get("_yoast_wpseo_metadesc","") or "").strip() == new_md
    if mt_ok and md_ok:
        w("Gemt og verificeret i WordPress ✓")
    else:
        w("ADVARSEL: Kunne ikke verificere gem — tjek manuelt")
    w("=" * 40)
    w("Færdig")


def fetch_posts():
    resp = requests.get(
        f"{WP_BASE}/posts",
        auth=wp_auth(),
        params={"per_page": 100, "context": "edit", "status": "publish,future"},
        timeout=30,
    )
    posts = resp.json()
    return [
        {
            "id": p["id"],
            "title": p["title"]["rendered"],
            "slug": p["slug"],
            "status": p["status"],
            "date": p["date"],
            "meta": p.get("meta", {}),
            "content": p["content"]["raw"],
            "featured_media": p.get("featured_media", 0),
            "excerpt": p.get("excerpt", {}).get("raw", ""),
        }
        for p in posts
    ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif path == "/api/posts":
            try:
                body = json.dumps(fetch_posts()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'{"error":"intern fejl"}')
        elif path == "/api/pages":
            try:
                pages, page_n = [], 1
                while True:
                    r = requests.get(f"{WP_BASE}/pages", auth=wp_auth(),
                        params={"per_page":100,"page":page_n,"context":"edit","status":"any"}, timeout=20)
                    batch = r.json()
                    if not batch or isinstance(batch, dict): break
                    pages.extend(batch)
                    if len(batch) < 100: break
                    page_n += 1
                result = [{
                    "id":       p["id"],
                    "title":    (p.get("title") or {}).get("rendered",""),
                    "slug":     p.get("slug",""),
                    "link":     p.get("link",""),
                    "status":   p.get("status",""),
                    "parent":   p.get("parent",0),
                    "modified": p.get("modified",""),
                    "meta":     p.get("meta") or {},
                    "content":  (p.get("content") or {}).get("raw",""),
                    "featured_media": p.get("featured_media",0),
                } for p in pages]
                body = json.dumps(result).encode()
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
            except Exception:
                self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"intern fejl"}')
        elif path == "/auth/gsc":
            url = gsc_auth_url()
            self.send_response(302)
            self.send_header("Location", url)
            self.end_headers()
        elif path == "/oauth2callback":
            qs     = parse_qs(urlparse(self.path).query)
            code   = qs.get("code",  [""])[0]
            state  = qs.get("state", [""])[0]
            error  = qs.get("error", [""])[0]
            if error or not code:
                html = f"<h2>Fejl: {error or 'ingen kode'}</h2><a href='/'>← Tilbage</a>"
            elif gsc_handle_callback(code, state):
                html = "<h2>✅ Google Search Console forbundet!</h2><p>Du kan lukke denne fane og genindlæse dashboardet.</p><script>setTimeout(()=>window.location='/',2000)</script>"
            else:
                html = "<h2>❌ Token-udveksling fejlede</h2><p>Prøv igen fra dashboardet.</p><a href='/'>← Tilbage</a>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif path == "/api/gsc/status":
            token = _gsc_token()
            body = json.dumps({"connected": token is not None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/gsc/data":
            qs        = parse_qs(urlparse(self.path).query)
            start     = qs.get("start", [""])[0]
            end       = qs.get("end",   [""])[0]
            dims      = qs.get("dims",  ["query"])[0].split(",")
            data      = gsc_fetch("https://mirapass.dk/", start, end, dims)
            body      = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/linking/audit":
            try:
                body = json.dumps(linking_audit()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'{"error":"intern fejl"}')
        elif path == "/api/ga/status":
            prop = _ga_property_id()
            token = _ga_token()
            body = json.dumps({"connected": token is not None, "property": prop}).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/ga/properties":
            props = ga_list_properties()
            body = json.dumps(props).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/ga/data":
            qs = parse_qs(urlparse(self.path).query)
            prop = _ga_property_id()
            if not prop:
                body = json.dumps({"error":"ingen_property"}).encode()
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
            else:
                start = qs.get("start",["30daysAgo"])[0]
                end   = qs.get("end",  ["yesterday"])[0]
                dtype = qs.get("type", ["overview"])[0]
                if dtype == "pages":
                    data = ga_fetch(prop, start, end,
                        ["pagePath","pageTitle"],
                        ["sessions","activeUsers","bounceRate","averageSessionDuration","screenPageViews"],
                        {"filter": {"fieldName":"sessionDefaultChannelGrouping","stringFilter":{"matchType":"EXACT","value":"Organic Search"}}})
                elif dtype == "channels":
                    data = ga_fetch(prop, start, end,
                        ["sessionDefaultChannelGrouping"],
                        ["sessions","activeUsers","bounceRate","averageSessionDuration"])
                else:  # overview
                    data = ga_fetch(prop, start, end,
                        ["date"],
                        ["sessions","activeUsers","newUsers"],
                        {"filter": {"fieldName":"sessionDefaultChannelGrouping","stringFilter":{"matchType":"EXACT","value":"Organic Search"}}})
                body = json.dumps(data).encode()
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
        elif path == "/api/opportunities":
            try:
                body = json.dumps(build_opportunities()).encode()
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
            except Exception:
                self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"intern fejl"}')
        elif path == "/api/content-score":
            try:
                opps = build_opportunities()
                opp_by_path = {o["path"]: o for o in opps}
                wp_posts = fetch_posts()
                scored = []
                import re as _re
                for p in wp_posts:
                    slug  = p.get("slug","")
                    pp    = f"/{slug}/"
                    opp   = opp_by_path.get(pp, {})
                    wc    = len(_re.sub(r'<[^>]+',' ', p.get("content","")).split())
                    m     = p.get("meta",{}) or {}
                    has_mt  = bool((m.get("_yoast_wpseo_title","") or "").strip())
                    has_md  = bool((m.get("_yoast_wpseo_metadesc","") or "").strip())
                    has_exc = bool((p.get("excerpt","") or "").strip())
                    seo_base  = (has_mt + has_md + has_exc) / 3 * 30
                    wc_score  = min(30, wc / 40)
                    opp_score = opp.get("opportunity", 0)
                    total     = round(seo_base + wc_score + opp_score, 1)
                    scored.append({
                        "id":       p["id"],
                        "title":    p["title"],
                        "slug":     slug,
                        "wc":       wc,
                        "has_mt":   has_mt,
                        "has_md":   has_md,
                        "has_exc":  has_exc,
                        "position": opp.get("position"),
                        "impressions": opp.get("impressions",0),
                        "ctr":      opp.get("ctr",0),
                        "sessions": opp.get("sessions",0),
                        "action":   opp.get("action","content"),
                        "score":    total,
                    })
                scored.sort(key=lambda x: -x["score"])
                body = json.dumps(scored[:30]).encode()
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
            except Exception:
                self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"intern fejl"}')
        else:
            self.send_response(404)
            self.end_headers()

    def _csrf_ok(self):
        """Tjekker at POST kommer fra dashboardet selv (ikke cross-origin)."""
        origin  = self.headers.get("Origin",  "")
        referer = self.headers.get("Referer", "")
        allowed = f"http://localhost:{PORT}"
        if origin  and not origin.startswith(allowed):  return False
        if referer and not referer.startswith(allowed): return False
        return True

    def _send_stream_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def _write(self, msg):
        try: self.wfile.write(msg.encode())
        except Exception: pass

    def do_POST(self):
        if not self._csrf_ok():
            self.send_response(403)
            self.end_headers()
            return

        parsed = urlparse(self.path)
        path   = parsed.path
        self._send_stream_headers()

        if path == "/api/seo/generate":
            try:
                seo_generate_stream(self.wfile)
            except Exception:
                self._write("\nIntern fejl — se server-log\n")

        elif path == "/api/linking/fix":
            try:
                linking_fix_stream(self.wfile)
            except Exception:
                self._write("\nIntern fejl — se server-log\n")

        elif path == "/api/linking/build":
            try:
                qs    = parse_qs(parsed.query)
                limit = max(1, min(100, int(qs.get("limit", ["10"])[0])))
                linking_build_stream(self.wfile, limit=limit)
            except Exception:
                self._write("\nIntern fejl — se server-log\n")

        elif path == "/api/gsc/fix-ctr":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length) if length else b"{}"
                data   = json.loads(body)
                url    = data.get("url", "")
                if not url.startswith("https://mirapass.dk/"):
                    self._write("Fejl: ugyldig URL\n")
                else:
                    gsc_fix_ctr_stream(self.wfile, url)
            except Exception:
                self._write("\nIntern fejl — se server-log\n")

        elif path == "/api/ga/set-property":
            try:
                length = int(self.headers.get("Content-Length",0))
                body = self.rfile.read(length) if length else b"{}"
                data = json.loads(body)
                prop_id = data.get("property","")
                if prop_id.startswith("properties/"):
                    _ga_save_property(prop_id)
                    self._write("OK\n")
                else:
                    self._write("Ugyldig property ID\n")
            except Exception:
                self._write("Intern fejl\n")

        elif path == "/api/autofix":
            try:
                length = int(self.headers.get("Content-Length",0))
                body   = self.rfile.read(length) if length else b"{}"
                data   = json.loads(body)
                url    = data.get("url","")
                action = data.get("action","meta")
                if not url.startswith("https://mirapass.dk/"):
                    self._write("Fejl: ugyldig URL\n")
                else:
                    autofix_stream(self.wfile, url, action)
            except Exception:
                self._write("Intern fejl\n")

        elif path == "/api/pages/seo-fix":
            try:
                length = int(self.headers.get("Content-Length",0))
                body   = self.rfile.read(length) if length else b"{}"
                data   = json.loads(body)
                page_id = int(data.get("id", 0))
                if not page_id:
                    self._write("Fejl: manglende side-ID\n")
                else:
                    pages_seo_fix_stream(self.wfile, page_id)
            except Exception:
                self._write("Intern fejl\n")

        else:
            self._write("404\n")


PORT = 7771


def open_browser():
    time.sleep(0.4)
    webbrowser.open(f"http://localhost:{PORT}")


print(f"Starter server på http://localhost:{PORT} …")
threading.Thread(target=open_browser, daemon=True).start()

try:
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nServer stoppet.")
