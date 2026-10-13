"""Système de contenu Instagram automatisé (nom provisoire : CURIOZA)."""

import os as _os

# Les clés collées dans GitHub gardent souvent un espace ou un retour à la ligne à la fin :
# on les nettoie une fois pour toutes, sinon les en-têtes HTTP sont refusés.
for _cle in ("ANTHROPIC_API_KEY", "CF_ACCOUNT_ID", "CF_API_TOKEN", "GEMINI_API_KEY", "REPLICATE_API_TOKEN",
             "IG_USER_ID", "IG_ACCESS_TOKEN", "GH_PAT", "URL_PAGES"):
    if _os.environ.get(_cle):
        _os.environ[_cle] = _os.environ[_cle].strip()

# Si c'est la commande de test de Cloudflare qui a été collée (« curl … Bearer <jeton> »), on en extrait le jeton.
import re as _re
for _cle in ("CF_API_TOKEN", "IG_ACCESS_TOKEN", "GEMINI_API_KEY"):
    _v = _os.environ.get(_cle, "")
    _m = _re.search(r"Bearer\s+([A-Za-z0-9_\-\.]+)", _v)
    if _m and ("\n" in _v or " " in _v):
        _os.environ[_cle] = _m.group(1)
