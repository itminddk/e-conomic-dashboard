# Mirapass.dk — Claude-arbejdsmiljø

## Hvad projektet er
WordPress-blog på **mirapass.dk** om Claude AI. Indhold på dansk.
- Blogindlæg (CPT: `post`) — `/wp-json/wp/v2/posts`
- Guide-serie (CPT: `guide`) — `/wp-json/wp/v2/guide`
- Sider (CPT: `page`) — `/wp-json/wp/v2/pages`

## Framework: wp.py
Brug altid `wp.py` til alle WordPress-operationer. Importer det øverst i ethvert script:

```python
import sys
sys.path.insert(0, '/Users/jan/Documents/Code/.claude/worktrees/intelligent-ishizaka-62ab56')
from wp import create_post, create_guide, set_seo, upload_image, publish_batch, quick_post
```

### Hyppige operationer

**Opret ét blogindlæg med SEO:**
```python
pid = create_post(
    title="Min overskrift",
    content="<p>Indhold i HTML</p>",
    excerpt="Kort beskrivelse",
    slug="min-url-slug",
    seo_desc="Meta-beskrivelse, 120–155 tegn",
    focus_kw="fokus nøgleord",
    categories=[5],   # kategori-ID
    tags=[12, 14],    # tag-ID'er
)
```

**Hurtigt indlæg (auto-excerpt, ingen kategorier):**
```python
pid = quick_post("Titel", "<p>Indhold</p>", seo_desc="Meta...", focus_kw="kw")
```

**Opret guide-indlæg:**
```python
pid = create_guide(
    title="Del 1: Introduktion",
    content="<p>...</p>",
    slug="guide-del-1",
    order=1,
    seo_desc="Meta-beskrivelse",
    focus_kw="claude skills",
)
```

**Opdater kun SEO på eksisterende indlæg:**
```python
set_seo(post_id=42, cpt="post", title="SEO-titel", desc="Meta-beskrivelse", focuskw="kw")
set_seo(post_id=503, cpt="guide", desc="Meta-beskrivelse", focuskw="kw")
```

**Massepublicering (liste af indlæg):**
```python
indlaeg = [
    {"title": "...", "content": "...", "seo_desc": "...", "focus_kw": "..."},
    {"title": "...", "content": "...", "seo_desc": "...", "focus_kw": "..."},
]
results = publish_batch(indlaeg, cpt="post")
```

**Upload billede og sæt som featured:**
```python
from wp import upload_image, set_featured_image
media_id = upload_image(img_bytes, "filnavn.png", alt_text="Beskrivelse")
set_featured_image(post_id, media_id, cpt="post")
```

**Generer AI-billede (Imagen 4.0) og upload:**
```python
from wp import generate_ai_image, upload_image, set_featured_image
img = generate_ai_image("Illustration af AI-koncepter, minimalistisk, blå toner, 16:9")
mid = upload_image(img, f"mirapass-{slug}.png", alt_text=f"Illustration til: {title}")
set_featured_image(pid, mid)
```

## Credentials
- WP: `~/.config/mirapass/wp.credentials` (format: `user:password`, chmod 600)
- Gemini: `~/.config/mirapass/gemini.key` (chmod 600)
- `wp.py` håndterer alt credential-loading automatisk

## Yoast SEO-noter
- `post` og `pages` CPT: bruger standard `meta` objekt med `_yoast_wpseo_metadesc` etc.
- `guide` CPT: bruger `register_rest_field` via **Code Snippet #9** på WP-sitet
  - Felter: `yoast_metadesc`, `yoast_title`, `yoast_focuskw`
  - `set_seo()` håndterer dette automatisk

## Eksisterende scripts
| Script | Funktion |
|--------|----------|
| `mirapass-redaktion.py` | Lokal dashboard til at se og redigere opslag (kør: `python3 mirapass-redaktion.py`) |
| `generer-billeder.py` | Genererer featured images til alle opslag uden billede via Imagen 4.0 |
| `wp.py` | **Framework** — importeres af andre scripts |

## Nyttige WP-ID'er
| Ressource | ID/Slug |
|-----------|---------|
| Kategori: Claude AI | (hent via `get_categories()`) |
| Ordbog-side | 487 — `/claude-ai-ordbog/` |
| Guide-serie | IDs 502–507 |

## Indholdsregler
- Sprog: **dansk**, professionelt men tilgængeligt
- Ingen AI-afsløring i brødteksten
- Semantisk HTML: `<h2>`, `<h3>`, `<p>`, `<ul>`, `<ol>`, `<strong>`
- Meta-beskrivelser: 120–155 tegn
- SEO-titler: max 60 tegn, slut med "| Mirapass"
- Focus keyword: ét primært søgeord per indlæg
- Interne links: brug `replace_first()` fra `wp.py` — aldrig mere end 1 link til samme URL per indlæg

## Kør scripts direkte
```bash
python3 /Users/jan/Documents/Code/.claude/worktrees/intelligent-ishizaka-62ab56/wp.py
python3 /tmp/mit_script.py
```
