#!/usr/bin/env python3
"""
gsc_setup.py — Engangsopsætning af Google Search Console OAuth2
===============================================================
Kør: python3 gsc_setup.py

Åbner browser til Google-login, gemmer refresh token i macOS Keychain.
Efterfølgende kald behøver ikke brugergodkendelse.
"""

import json, subprocess, sys
from pathlib import Path

CREDS_FILE = Path.home() / ".config/mirapass/gsc_client.json"
SCOPES     = ["https://www.googleapis.com/auth/webmasters.readonly"]
SERVICE    = "mirapass-gsc"

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
except ImportError:
    sys.exit("Mangler biblioteker. Kør: pip3 install google-auth-oauthlib google-api-python-client")

if not CREDS_FILE.exists():
    sys.exit(f"Credentials-fil ikke fundet: {CREDS_FILE}")

# Læs client secret
with open(CREDS_FILE) as f:
    raw = json.load(f)

# Understøtter både "web" og "installed" type
cred_type = list(raw.keys())[0]
client_config = raw[cred_type]

# Kør OAuth-flow med lokal server (åbner browser automatisk)
print("Åbner browser til Google-login...")
print("Log ind med den Google-konto der har adgang til mirapass.dk i Search Console.\n")

flow = InstalledAppFlow.from_client_config(
    {"installed": {
        "client_id":     client_config["client_id"],
        "client_secret": client_config["client_secret"],
        "auth_uri":      client_config.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri":     client_config.get("token_uri", "https://oauth2.googleapis.com/token"),
        "redirect_uris": ["http://localhost"],
    }},
    scopes=SCOPES,
)

creds = flow.run_local_server(port=0, open_browser=True)

# Gem tokens i Keychain
token_data = json.dumps({
    "token":         creds.token,
    "refresh_token": creds.refresh_token,
    "client_id":     creds.client_id,
    "client_secret": creds.client_secret,
    "token_uri":     creds.token_uri,
    "scopes":        list(creds.scopes),
})

r = subprocess.run(
    ["security", "add-generic-password", "-s", SERVICE, "-a", "oauth2", "-w", token_data, "-U"],
    capture_output=True, text=True,
)
if r.returncode != 0:
    print(f"Keychain-fejl: {r.stderr}")
    sys.exit(1)

print("\n✅ Autoriseret og gemt i Keychain!")
print(f"   Refresh token: {creds.refresh_token[:20]}…")
print("\nDu kan nu bruge Google Search Console-data i dashboardet.")
