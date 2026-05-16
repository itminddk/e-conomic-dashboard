#!/usr/bin/env python3
"""
Genererer featured images til alle mirapass.dk-opslag via Imagen 4.0.
Bruger excerpt fra hvert opslag som kontekst i prompt.
Koen: python3 generer-billeder.py
"""

import json, base64, time, os
import requests

WP_BASE  = "https://mirapass.dk/wp-json/wp/v2"
CREDS_FILE  = os.path.expanduser("~/.config/mirapass/wp.credentials")
GEMINI_FILE = os.path.expanduser("~/.config/mirapass/gemini.key")
MODEL    = "imagen-4.0-generate-001"


def load_credentials(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def wp_auth() -> tuple[str, str]:
    creds = load_credentials(CREDS_FILE)
    user, password = creds.split(":", 1)
    return (user, password)


PROMPT_TEMPLATE = (
    "Create a clean, modern editorial illustration for a tech blog article. "
    "Context from the article: {excerpt} "
    "Style requirements: Minimalist and sophisticated design. "
    "Soft gradient background in cool blues and purples. "
    "Flat design with subtle depth and shadows. "
    "Professional tech/AI aesthetic. "
    "NO text, NO letters, NO words, NO numbers, NO typography — purely visual. "
    "16:9 widescreen format. "
    "Visual direction: Abstract representation of the article's core concept. "
    "Use geometric shapes, flowing lines, or glowing elements. "
    "Clean white space, uncluttered composition. "
    "Modern SaaS / editorial blog feel. "
    "Color palette: Deep navy, electric blue, soft violet, white accents."
)


def make_prompt(excerpt: str, title: str) -> str:
    summary = excerpt.strip() if excerpt.strip() else title
    return PROMPT_TEMPLATE.format(excerpt=summary[:300])


# ── API calls ─────────────────────────────────────────────────────

def generate_image(prompt: str, retries: int = 3) -> bytes:
    key = load_credentials(GEMINI_FILE)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
    }
    for attempt in range(retries):
        resp = requests.post(url, params={"key": key}, json=payload, timeout=60)
        data = resp.json()
        if "predictions" in data:
            return base64.b64decode(data["predictions"][0]["bytesBase64Encoded"])
        code = data.get("error", {}).get("code", 0)
        if code == 503 and attempt < retries - 1:
            print(f"         503 – venter 6s ({attempt+2}/{retries})...")
            time.sleep(6)
        else:
            raise RuntimeError(data.get("error", {}).get("message", str(data)[:200]))


def upload_to_wp(img_bytes: bytes, filename: str) -> int:
    resp = requests.post(
        f"{WP_BASE}/media",
        auth=wp_auth(),
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "image/png",
        },
        data=img_bytes,
        timeout=60,
    )
    res = resp.json()
    if "id" not in res:
        raise RuntimeError(str(res)[:200])
    return res["id"]


def set_alt_text(media_id: int, alt: str):
    requests.post(
        f"{WP_BASE}/media/{media_id}",
        auth=wp_auth(),
        json={"alt_text": alt, "title": alt},
        timeout=30,
    )


def set_featured(post_id: int, media_id: int):
    requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=wp_auth(),
        json={"featured_media": media_id},
        timeout=30,
    )


def get_posts() -> list:
    resp = requests.get(
        f"{WP_BASE}/posts",
        auth=wp_auth(),
        params={"per_page": 100, "context": "edit", "status": "publish,future"},
        timeout=30,
    )
    return resp.json()


# ── Main ──────────────────────────────────────────────────────────

def main():
    posts = get_posts()
    needs = [p for p in posts if not p.get("featured_media")]
    total = len(needs)
    print(f"Opslag uden featured image: {total} / {len(posts)}\n")

    ok, errors = 0, []

    for i, p in enumerate(needs, 1):
        pid     = p["id"]
        title   = p["title"]["rendered"]
        slug    = p["slug"]
        excerpt = p.get("excerpt", {}).get("raw", "").strip()
        alt     = f"Illustration til artiklen: {title}"
        prompt  = make_prompt(excerpt, title)

        print(f"[{i}/{total}] #{pid}  {title[:52]}")
        print(f"         Kontekst: {(excerpt or title)[:80]}...")

        try:
            img = generate_image(prompt)
            mid = upload_to_wp(img, f"mirapass-{slug[:38]}.png")
            set_alt_text(mid, alt)
            set_featured(pid, mid)
            print(f"         OK  Media #{mid}\n")
            ok += 1
        except Exception as e:
            print(f"         FEJL: {e}\n")
            errors.append((pid, title, str(e)))

        if i < total:
            time.sleep(2)

    print(f"Faerdig: {ok}/{total} billeder genereret og uploadet.")
    if errors:
        print(f"\nFejl ({len(errors)}):")
        for pid, title, err in errors:
            print(f"  #{pid}  {title[:50]}: {err}")


if __name__ == "__main__":
    main()
