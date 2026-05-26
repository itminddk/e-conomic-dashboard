#!/usr/bin/env python3
"""
Kør: python3 mirapass-redaktion.py
Åbner automatisk http://localhost:7771 i browseren.
"""

import json, os, subprocess, webbrowser, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
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
  <button class="tab active" onclick="showTab('timeline',this)">Tidslinje</button>
  <button class="tab" onclick="showTab('table',this)">Alle opslag</button>
  <button class="tab" onclick="showTab('seo',this)">SEO Analyse</button>
  <button class="tab" onclick="showLinking(this)">Intern Linking</button>
</div>

<div id="pane-timeline" class="pane active">
  <div class="loading"><div class="loading-spinner"></div>Indlæser…</div>
</div>
<div id="pane-seo" class="pane"></div>
<div id="pane-linking" class="pane"></div>

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
    return `<tr>
      <td style="text-align:center"><div class="seo-score ${sc}">${pct}%</div></td>
      <td>${priorityLabel(score, maxScore)}</td>
      <td style="font-size:.85rem"><a href="https://mirapass.dk/${p.slug}/" target="_blank" style="color:var(--text);text-decoration:none;font-weight:500">${p.title}</a></td>
      <td style="font-size:.78rem;color:var(--muted)">${wc.toLocaleString('da-DK')}</td>
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
        <th style="width:80px">${sortBtn('wc','Ord')}</th>
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
      <td>${p.title}</td>
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
      <td>${p.title}</td>
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
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif path == "/api/linking/audit":
            try:
                body = json.dumps(linking_audit()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if path == "/api/seo/generate":
            try:
                seo_generate_stream(self.wfile)
            except Exception as e:
                try: self.wfile.write(f"\nFejl: {e}\n".encode())
                except Exception: pass
        elif path == "/api/linking/fix":
            try:
                linking_fix_stream(self.wfile)
            except Exception as e:
                try: self.wfile.write(f"\nFejl: {e}\n".encode())
                except Exception: pass
        elif path == "/api/linking/build":
            try:
                from urllib.parse import parse_qs
                qs    = parse_qs(parsed.query)
                limit = int(qs.get("limit", ["10"])[0])
                linking_build_stream(self.wfile, limit=limit)
            except Exception as e:
                try: self.wfile.write(f"\nFejl: {e}\n".encode())
                except Exception: pass
        else:
            try: self.wfile.write(b"404\n")
            except Exception: pass


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
