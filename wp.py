#!/usr/bin/env python3
"""
wp.py — Mirapass WordPress API framework
=========================================
Genbrugelige funktioner til alle operationer mod mirapass.dk REST API.

Brug:
    from wp import WP
    wp = WP()
    post_id = wp.create_post(title="Min titel", content="<p>Indhold</p>", ...)
    wp.set_seo(post_id, "post", desc="Min metabeskrivelse", focuskw="nøgleord")

Credentials læses automatisk fra ~/.config/mirapass/wp.credentials (format: user:password)
Yoast-meta kræver at Code Snippet #9 er aktiv på siden (register_rest_field for guide CPT).
"""

import os, re, time, base64
from typing import Union
import requests

WP_BASE   = "https://mirapass.dk/wp-json/wp/v2"
CREDS     = os.path.expanduser("~/.config/mirapass/wp.credentials")
GEMINI    = os.path.expanduser("~/.config/mirapass/gemini.key")
IMAGEN    = "imagen-4.0-generate-001"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _auth() -> tuple[str, str]:
    with open(CREDS) as f:
        user, pw = f.read().strip().split(":", 1)
    return (user, pw)

def _gemini_key() -> str:
    with open(GEMINI) as f:
        return f.read().strip()


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _post(endpoint: str, data: dict, timeout=60) -> dict:
    r = requests.post(f"{WP_BASE}/{endpoint}", auth=_auth(), json=data, timeout=timeout)
    return r.json()

def _get(endpoint: str, params: dict = None, timeout=30) -> Union[dict, list]:
    r = requests.get(f"{WP_BASE}/{endpoint}", auth=_auth(), params=params, timeout=timeout)
    return r.json()


# ── Posts ─────────────────────────────────────────────────────────────────────

def create_post(
    title:      str,
    content:    str,
    excerpt:    str    = "",
    slug:       str    = "",
    status:     str    = "publish",
    categories: list   = None,
    tags:       list   = None,
    seo_title:  str    = "",
    seo_desc:   str    = "",
    focus_kw:   str    = "",
) -> int:
    """
    Opretter et blogindlæg. Returnerer WP post-ID.
    Sætter automatisk Yoast-meta hvis seo_desc er angivet.
    """
    data = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": status,
    }
    if slug:        data["slug"]       = slug
    if categories:  data["categories"] = categories
    if tags:        data["tags"]       = tags

    result = _post("posts", data)
    pid = result.get("id")
    if not pid:
        raise RuntimeError(f"create_post fejlede: {str(result)[:300]}")

    if seo_desc or seo_title or focus_kw:
        set_seo(pid, "post", title=seo_title, desc=seo_desc, focuskw=focus_kw)

    return pid


def update_post(post_id: int, **fields) -> dict:
    """Opdaterer et eksisterende blogindlæg. Understøtter samme felter som create_post."""
    seo_title = fields.pop("seo_title", "")
    seo_desc  = fields.pop("seo_desc",  "")
    focus_kw  = fields.pop("focus_kw",  "")

    result = _post(f"posts/{post_id}", fields)
    if seo_desc or seo_title or focus_kw:
        set_seo(post_id, "post", title=seo_title, desc=seo_desc, focuskw=focus_kw)
    return result


# ── Guide CPT ─────────────────────────────────────────────────────────────────

def create_guide(
    title:     str,
    content:   str,
    excerpt:   str  = "",
    slug:      str  = "",
    order:     int  = 0,
    status:    str  = "publish",
    seo_title: str  = "",
    seo_desc:  str  = "",
    focus_kw:  str  = "",
) -> int:
    """
    Opretter et guide-indlæg under CPT 'guide'. Returnerer WP post-ID.
    Kræver at Code Snippet #9 er aktiv (Yoast meta REST fields for Guide CPT).
    """
    data = {
        "title":      title,
        "content":    content,
        "excerpt":    excerpt,
        "status":     status,
        "menu_order": order,
    }
    if slug: data["slug"] = slug

    result = _post("guide", data)
    pid = result.get("id")
    if not pid:
        raise RuntimeError(f"create_guide fejlede: {str(result)[:300]}")

    if seo_desc or seo_title or focus_kw:
        set_seo(pid, "guide", title=seo_title, desc=seo_desc, focuskw=focus_kw)

    return pid


def update_guide(guide_id: int, **fields) -> dict:
    """Opdaterer et eksisterende guide-indlæg."""
    seo_title = fields.pop("seo_title", "")
    seo_desc  = fields.pop("seo_desc",  "")
    focus_kw  = fields.pop("focus_kw",  "")

    result = _post(f"guide/{guide_id}", fields)
    if seo_desc or seo_title or focus_kw:
        set_seo(guide_id, "guide", title=seo_title, desc=seo_desc, focuskw=focus_kw)
    return result


# ── Pages ─────────────────────────────────────────────────────────────────────

def create_page(
    title:     str,
    content:   str,
    slug:      str = "",
    status:    str = "publish",
    parent:    int = 0,
    seo_title: str = "",
    seo_desc:  str = "",
    focus_kw:  str = "",
) -> int:
    """Opretter en WordPress-side. Returnerer WP post-ID."""
    data = {"title": title, "content": content, "status": status}
    if slug:   data["slug"]   = slug
    if parent: data["parent"] = parent

    result = _post("pages", data)
    pid = result.get("id")
    if not pid:
        raise RuntimeError(f"create_page fejlede: {str(result)[:300]}")

    if seo_desc or seo_title or focus_kw:
        set_seo(pid, "pages", title=seo_title, desc=seo_desc, focuskw=focus_kw)

    return pid


def update_page(page_id: int, **fields) -> dict:
    """Opdaterer en eksisterende side."""
    seo_title = fields.pop("seo_title", "")
    seo_desc  = fields.pop("seo_desc",  "")
    focus_kw  = fields.pop("focus_kw",  "")

    result = _post(f"pages/{page_id}", fields)
    if seo_desc or seo_title or focus_kw:
        set_seo(page_id, "pages", title=seo_title, desc=seo_desc, focuskw=focus_kw)
    return result


# ── SEO (Yoast) ───────────────────────────────────────────────────────────────

def set_seo(
    post_id:  int,
    cpt:      str,          # "post", "posts", "guide", "pages"
    title:    str = "",
    desc:     str = "",
    focuskw:  str = "",
    canonical: str = "",
) -> bool:
    """
    Sætter Yoast SEO-meta på et indlæg.
    - For 'post'/'posts': bruger standard meta-felter
    - For 'guide': bruger register_rest_field (kræver Code Snippet #9)
    - For 'pages': bruger standard meta-felter
    Returnerer True ved succes.
    """
    endpoint_map = {"post": "posts", "posts": "posts", "guide": "guide", "page": "pages", "pages": "pages"}
    ep = endpoint_map.get(cpt, cpt)

    if ep in ("posts", "pages"):
        # Standard Yoast meta via 'meta' object
        meta = {}
        if desc:      meta["_yoast_wpseo_metadesc"]  = desc
        if title:     meta["_yoast_wpseo_title"]      = title
        if focuskw:   meta["_yoast_wpseo_focuskw"]    = focuskw
        if canonical: meta["_yoast_wpseo_canonical"]  = canonical
        r = requests.post(
            f"{WP_BASE}/{ep}/{post_id}",
            auth=_auth(), json={"meta": meta}, timeout=30
        )
        saved = r.json().get("meta", {})
        return bool(saved.get("_yoast_wpseo_metadesc") or saved.get("_yoast_wpseo_title"))

    elif ep == "guide":
        # Yoast meta via register_rest_field (Code Snippet #9)
        payload = {}
        if desc:    payload["yoast_metadesc"] = desc
        if title:   payload["yoast_title"]    = title
        if focuskw: payload["yoast_focuskw"]  = focuskw
        r = requests.post(
            f"{WP_BASE}/guide/{post_id}",
            auth=_auth(), json=payload, timeout=30
        )
        saved = r.json()
        return "yoast_metadesc" in saved

    return False


# ── Media ─────────────────────────────────────────────────────────────────────

def upload_image(img_bytes: bytes, filename: str, alt_text: str = "") -> int:
    """Uploader et billede til WordPress-mediebiblioteket. Returnerer media-ID."""
    r = requests.post(
        f"{WP_BASE}/media",
        auth=_auth(),
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "image/png",
        },
        data=img_bytes,
        timeout=60,
    )
    res = r.json()
    if "id" not in res:
        raise RuntimeError(f"upload_image fejlede: {str(res)[:200]}")
    media_id = res["id"]
    if alt_text:
        requests.post(f"{WP_BASE}/media/{media_id}", auth=_auth(),
                      json={"alt_text": alt_text, "title": alt_text}, timeout=30)
    return media_id


def set_featured_image(post_id: int, media_id: int, cpt: str = "posts") -> bool:
    """Sætter featured image på et indlæg."""
    endpoint_map = {"post": "posts", "posts": "posts", "guide": "guide", "page": "pages", "pages": "pages"}
    ep = endpoint_map.get(cpt, cpt)
    r = requests.post(f"{WP_BASE}/{ep}/{post_id}", auth=_auth(),
                      json={"featured_media": media_id}, timeout=30)
    return r.json().get("featured_media") == media_id


def generate_ai_image(prompt: str, retries: int = 3) -> bytes:
    """Genererer et billede via Imagen 4.0. Returnerer PNG-bytes."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGEN}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
    }
    for attempt in range(retries):
        r = requests.post(url, params={"key": _gemini_key()}, json=payload, timeout=60)
        data = r.json()
        if "predictions" in data:
            return base64.b64decode(data["predictions"][0]["bytesBase64Encoded"])
        code = data.get("error", {}).get("code", 0)
        if code == 503 and attempt < retries - 1:
            time.sleep(6)
        else:
            raise RuntimeError(data.get("error", {}).get("message", str(data)[:200]))


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def get_posts(status: str = "publish", per_page: int = 100) -> list:
    """Henter blogindlæg. Returnerer liste af post-dicts."""
    return _get("posts", {"per_page": per_page, "context": "edit", "status": status})

def get_guides(per_page: int = 50) -> list:
    """Henter guide-indlæg."""
    return _get("guide", {"per_page": per_page, "context": "edit"})

def get_pages(per_page: int = 50) -> list:
    """Henter sider."""
    return _get("pages", {"per_page": per_page, "context": "edit"})

def get_categories() -> dict:
    """Returnerer {navn: id} for alle kategorier."""
    cats = _get("categories", {"per_page": 100})
    return {c["name"]: c["id"] for c in cats}

def get_tags() -> dict:
    """Returnerer {navn: id} for alle tags."""
    tags = _get("tags", {"per_page": 100})
    return {t["name"]: t["id"] for t in tags}

def get_or_create_tag(name: str) -> int:
    """Finder eller opretter et tag og returnerer ID."""
    tags = get_tags()
    if name in tags:
        return tags[name]
    r = _post("tags", {"name": name})
    if "id" in r:
        return r["id"]
    # WordPress returnerer term_exists fejl hvis tagget allerede eksisterer
    # (race condition eller case-mismatch) — hent ID fra fejlresponsen
    if r.get("code") == "term_exists":
        return int(r["data"]["term_id"])
    # Prøv at finde tagget med en bredere søgning
    all_tags = _get("tags", {"per_page": 100, "search": name})
    if isinstance(all_tags, list) and all_tags:
        return all_tags[0]["id"]
    raise RuntimeError(f"get_or_create_tag fejlede for '{name}': {str(r)[:200]}")


# ── Content helpers ───────────────────────────────────────────────────────────

def strip_tags(html: str) -> str:
    """Fjerner HTML-tags fra en streng."""
    return re.sub(r"<[^>]+>", "", html).strip()

def auto_excerpt(html: str, max_chars: int = 160) -> str:
    """Genererer et automatisk excerpt fra HTML-indhold."""
    text = strip_tags(html)
    return text[:max_chars].rsplit(" ", 1)[0] + "…" if len(text) > max_chars else text

def replace_first(content: str, find: str, link_url: str, link_text: str = "") -> str:
    """
    Erstatter første forekomst af 'find' i <p>-tags med et link.
    Springer over forekomster der allerede er i et <a>-tag.
    Returnerer uændret indhold hvis intet matchede.
    """
    anchor = f'<a href="{link_url}">{link_text or find}</a>'
    # Match kun inde i <p>-tags, ikke i eksisterende <a>-tags
    pattern = rf'(<p>[^<]*?)(?<!</a>)\b({re.escape(find)})\b(?![^<]*?</a>)'
    new_content, n = re.subn(pattern, rf'\1{anchor}', content, count=1)
    return new_content if n else content


# ── Batch helpers ─────────────────────────────────────────────────────────────

def publish_batch(posts: list[dict], cpt: str = "post", delay: float = 1.5) -> list[dict]:
    """
    Opretter flere indlæg på én gang.

    posts = [
      {
        "title": "...", "content": "...", "excerpt": "...", "slug": "...",
        "seo_title": "...", "seo_desc": "...", "focus_kw": "...",
        # post-only: "categories": [...], "tags": [...]
        # guide-only: "order": 1
      },
      ...
    ]

    Returnerer liste af {"id": ..., "title": ..., "link": ..., "ok": True/False}
    """
    results = []
    total = len(posts)
    fn = create_guide if cpt == "guide" else create_post

    for i, p in enumerate(posts, 1):
        title = p.get("title", f"Indlæg {i}")
        print(f"[{i}/{total}] {title[:60]}")
        try:
            pid = fn(**p)
            link = f"https://mirapass.dk/{'guide' if cpt == 'guide' else '?p=' + str(pid)}"
            print(f"  ✅ #{pid}")
            results.append({"id": pid, "title": title, "ok": True})
        except Exception as e:
            print(f"  ❌ FEJL: {e}")
            results.append({"id": None, "title": title, "ok": False, "error": str(e)})

        if i < total:
            time.sleep(delay)

    ok = sum(1 for r in results if r["ok"])
    print(f"\nFærdig: {ok}/{total} indlæg oprettet.")
    return results


# ── Quick-publish shortcut ────────────────────────────────────────────────────

def quick_post(title: str, content: str, seo_desc: str = "", focus_kw: str = "",
               categories: list = None, tags: list = None, slug: str = "") -> int:
    """
    Hurtig oprettelse af ét blogindlæg med auto-excerpt og valgfri SEO.
    Returnerer post-ID.
    """
    return create_post(
        title=title,
        content=content,
        excerpt=auto_excerpt(content),
        slug=slug,
        seo_desc=seo_desc or auto_excerpt(content, 155),
        focus_kw=focus_kw,
        categories=categories or [],
        tags=tags or [],
    )


if __name__ == "__main__":
    # Smoke test
    print("wp.py loaded OK")
    print(f"Auth user: {_auth()[0]}")
    posts = get_posts(per_page=3)
    print(f"Antal indlæg (sample 3): {len(posts)}")
    for p in posts:
        print(f"  #{p['id']} {p['title']['rendered'][:50]}")
