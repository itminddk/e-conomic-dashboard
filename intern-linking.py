#!/usr/bin/env python3
"""
intern-linking.py — Automatisk intern linking audit og fix for mirapass.dk
===========================================================================
Kør: python3 intern-linking.py

Hvad scriptet gør:
  1. Henter alle publicerede indlæg
  2. Finder forældreløse indlæg (nul indgående interne links)
  3. Finder automatisk den bedste donor-post for hvert forældreløst indlæg
  4. Tilføjer ét naturligt inline-link per indlæg
  5. Rapporterer resultat

Flags:
  --dry-run    Vis hvad der ville ske uden at gemme noget
  --audit      Kun rapport — ingen ændringer
  --min-words N  Minimum antal ord i donor-paragraf (default: 20)
"""

import sys, os, re, argparse, time, subprocess
from typing import Optional, Tuple
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
WP_BASE    = "https://mirapass.dk/wp-json/wp/v2"
_CREDS_FILE = os.path.expanduser("~/.config/mirapass/wp.credentials")


# ── Auth ──────────────────────────────────────────────────────────────────────

def auth():
    """Henter WP-credentials fra macOS Keychain (eller fil som fallback)."""
    try:
        cmd = ["security", "find-generic-password", "-s", "mirapass-wp", "-g"]
        r = subprocess.run(cmd, capture_output=True, text=True)
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
    with open(_CREDS_FILE) as f:
        u, p = f.read().strip().split(":", 1)
    return (u, p)


# ── WordPress helpers ─────────────────────────────────────────────────────────

def fetch_all_posts():
    """Henter alle publicerede indlæg med fuldt rå indhold."""
    posts, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=auth(), params={
            "per_page": 100, "page": page,
            "context": "edit", "status": "publish",
        }, timeout=30)
        batch = r.json()
        if not batch or isinstance(batch, dict):
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts


def save_content(post_id: int, content: str) -> bool:
    r = requests.post(f"{WP_BASE}/posts/{post_id}", auth=auth(),
                      json={"content": content}, timeout=30)
    return r.status_code == 200


# ── Link helpers ──────────────────────────────────────────────────────────────

def raw_content(post: dict) -> str:
    return post.get("content", {}).get("raw", "")


def count_incoming(target: dict, all_posts: list) -> int:
    slug = target.get("slug", "")
    return sum(1 for p in all_posts
               if p["id"] != target["id"] and slug in raw_content(p))


def extract_keywords(post: dict) -> list[str]:
    """Udtrækker søgeord fra titel og slug (2+ bogstaver, ikke stopord)."""
    STOP = {
        "og", "er", "en", "et", "de", "den", "det", "til", "med", "for",
        "på", "fra", "af", "om", "ved", "som", "der", "hvad", "kan", "du",
        "din", "dit", "din", "i", "at", "ikke", "af", "en", "hvornår",
        "hvilken", "sådan", "aldrig", "bedre", "mere", "alle", "hver",
        "the", "and", "for", "with", "how", "your", "from", "into",
    }
    title = post.get("title", {}).get("rendered", "")
    slug = post.get("slug", "").replace("-", " ")
    text = f"{title} {slug}".lower()
    words = re.findall(r"[a-zæøåA-ZÆØÅ]{3,}", text)
    seen, result = set(), []
    for w in words:
        if w.lower() not in STOP and w.lower() not in seen:
            seen.add(w.lower())
            result.append(w)
    return result[:12]


def find_linkable_paragraph(content: str, keywords: list,
                             min_words: int = 20) -> Optional[Tuple[str, str]]:
    """
    Finder den bedste paragraf i content der:
    - Indeholder mindst ét keyword
    - Ikke allerede indeholder et <a>-tag til target
    - Har mindst min_words ord
    Returnerer (find_text, keyword_found) eller None.
    """
    paras = re.findall(r'<p>(.*?)</p>', content, re.DOTALL)
    best = None
    best_score = 0

    for para in paras:
        # Spring over hvis paragraffen allerede er et link
        if '<a ' in para:
            continue
        clean = re.sub(r'<[^>]+>', '', para).strip()
        words_in_para = len(clean.split())
        if words_in_para < min_words:
            continue

        for kw in keywords:
            # Tjek om keyword optræder som et helt ord (case insensitive)
            match = re.search(r'\b' + re.escape(kw) + r'\b', clean, re.IGNORECASE)
            if match:
                # Score: foretruk kortere keywords der er mere specifikke
                score = words_in_para - len(kw)
                if score < best_score or best is None:
                    best_score = score
                    best = (match.group(0), kw)
                break  # ét keyword per paragraf er nok

    return best


def insert_link(content: str, find_text: str, url: str, anchor: str) -> str:
    """
    Indsætter et link i første paragraf der indeholder find_text.
    Springer over hvis teksten allerede er linket.
    """
    pattern = re.compile(
        r'(<p>(?:(?!<a\s).)*?\b)(' + re.escape(find_text) + r')(\b(?:(?!</p>).)*?</p>)',
        re.DOTALL | re.IGNORECASE
    )
    new_content, n = pattern.subn(
        lambda m: m.group(1) + f'<a href="{url}">{anchor or m.group(2)}</a>' + m.group(3),
        content, count=1
    )
    return new_content if n else content


# ── Core logic ────────────────────────────────────────────────────────────────

def find_best_donor(target: dict, all_posts: list,
                    min_words: int = 20) -> Optional[tuple]:
    """
    Finder den bedste donor-post til et forældreløst indlæg.
    Returnerer (donor_post, find_text, anchor_text) eller None.
    """
    target_url  = target.get("link", "")
    target_slug = target.get("slug", "")
    keywords    = extract_keywords(target)
    if not keywords:
        return None

    candidates = []
    for donor in all_posts:
        if donor["id"] == target["id"]:
            continue
        # Donor må ikke allerede linke til target
        if target_slug in raw_content(donor):
            continue
        content = raw_content(donor)
        result = find_linkable_paragraph(content, keywords, min_words)
        if result:
            find_text, matched_kw = result
            # Score donors: foretruk indlæg med mange indgående links (autoritet)
            incoming = count_incoming(donor, all_posts)
            candidates.append((incoming, donor, find_text, matched_kw))

    if not candidates:
        return None

    # Vælg donor med flest indgående links (mest autoritativ)
    candidates.sort(key=lambda x: -x[0])
    _, donor, find_text, matched_kw = candidates[0]
    return donor, find_text, find_text  # (donor, find_text, anchor_text)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Intern linking audit og fix")
    parser.add_argument("--dry-run", action="store_true",
                        help="Vis ændringer uden at gemme")
    parser.add_argument("--audit",   action="store_true",
                        help="Kun rapport, ingen ændringer")
    parser.add_argument("--min-words", type=int, default=20,
                        help="Minimum ord i donor-paragraf (default: 20)")
    args = parser.parse_args()

    print("Henter alle indlæg...")
    all_posts = fetch_all_posts()
    print(f"Fandt {len(all_posts)} indlæg\n")

    # Find forældreløse
    orphans = [p for p in all_posts if count_incoming(p, all_posts) == 0]
    linked  = len(all_posts) - len(orphans)

    print(f"{'─'*60}")
    print(f"Med indgående links : {linked}/{len(all_posts)}")
    print(f"Uden indgående links: {len(orphans)}/{len(all_posts)}")
    print(f"{'─'*60}\n")

    if args.audit or not orphans:
        if orphans:
            print("Forældreløse indlæg:")
            for p in sorted(orphans, key=lambda x: x["id"]):
                print(f"  #{p['id']:<5} {p['title']['rendered'][:65]}")
        else:
            print("✅ Ingen forældreløse indlæg!")
        return

    # Fix forældreløse
    ok, skipped = 0, []
    for i, target in enumerate(orphans, 1):
        tid   = target["id"]
        title = target["title"]["rendered"][:55]
        turl  = target.get("link", "")
        print(f"[{i}/{len(orphans)}] #{tid} {title}")

        result = find_best_donor(target, all_posts, args.min_words)
        if not result:
            print(f"  ⚠️  Ingen egnet donor fundet\n")
            skipped.append((tid, title))
            continue

        donor, find_text, anchor = result
        did   = donor["id"]
        dtitle = donor["title"]["rendered"][:45]

        if args.dry_run:
            print(f"  → ville linke fra #{did} '{dtitle}'")
            print(f"     via tekst: '{find_text[:50]}'\n")
            ok += 1
            continue

        # Tilføj link
        content = raw_content(donor)
        new_content = insert_link(content, find_text, turl, find_text)

        if new_content == content:
            print(f"  ⚠️  insert_link fandt ikke '{find_text[:40]}' i #{did}\n")
            skipped.append((tid, title))
            continue

        if save_content(did, new_content):
            # Opdater donor i all_posts så efterfølgende runs er korrekte
            donor["content"]["raw"] = new_content
            print(f"  ✅ Link fra #{did} '{dtitle[:35]}'\n")
            ok += 1
        else:
            print(f"  ❌ Gem fejlede for #{did}\n")
            skipped.append((tid, title))

        time.sleep(0.5)

    # Rapport
    print(f"\n{'='*60}")
    action = "ville tilføje" if args.dry_run else "tilføjet"
    print(f"Færdig: {ok}/{len(orphans)} links {action}")
    if skipped:
        print(f"\nSprunget over ({len(skipped)}) — kræver manuel review:")
        for tid, title in skipped:
            print(f"  #{tid} {title}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
