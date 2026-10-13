"""Système de contenu Instagram automatisé (nom provisoire : CURIOZA)."""

import os as _os

# Les clés collées dans GitHub gardent souvent un espace ou un retour à la ligne à la fin :
# on les nettoie une fois pour toutes, sinon les en-têtes HTTP sont refusés.
for _cle in ("ANTHROPIC_API_KEY", "CF_ACCOUNT_ID", "CF_API_TOKEN", "GEMINI_API_KEY", "REPLICATE_API_TOKEN",
             "IG_USER_ID", "IG_ACCESS_TOKEN", "GH_PAT", "URL_PAGES"):
    if _os.environ.get(_cle):
        _os.environ[_cle] = _os.environ[_cle].strip()
