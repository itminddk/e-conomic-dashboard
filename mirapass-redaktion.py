#!/usr/bin/env python3
"""
Kør: python3 mirapass-redaktion.py
Åbner automatisk http://localhost:7771 i browseren.
"""

import json, os, webbrowser, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests

CREDS_FILE = os.path.expanduser("~/.config/mirapass/wp.credentials")
WP_BASE = "https://mirapass.dk/wp-json/wp/v2"


def wp_auth() -> tuple:
    with open(CREDS_FILE) as f:
        user, password = f.read().strip().split(":", 1)
    return (user, password)

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
</div>

<div id="pane-timeline" class="pane active">
  <div class="loading"><div class="loading-spinner"></div>Indlæser…</div>
</div>
<div id="pane-seo" class="pane"></div>

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

loadPosts();
</script>
</body>
</html>"""


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
        else:
            self.send_response(404)
            self.end_headers()


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
