"""Chargement de la configuration et chemins du projet."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_PLANNING = RACINE / "planning"
# Site publié par GitHub Pages (calendrier + médias). Sur GitHub Actions, il vit dans la branche « site »,
# récrite à chaque passage (sans historique) pour que le dépôt reste léger.
DOSSIER_SITE = Path(os.environ["SITE_DIR"]) if os.environ.get("SITE_DIR") else RACINE / "docs"
DOSSIER_MEDIAS = DOSSIER_SITE / "medias"


def charger_config() -> dict:
    with open(RACINE / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Permet de surcharger l'URL Pages via une variable d'environnement (GitHub Actions)
    if os.environ.get("URL_PAGES"):
        cfg["url_pages"] = os.environ["URL_PAGES"]
    return cfg


def fuseau(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg.get("fuseau", "Europe/Paris"))


def maintenant(cfg: dict) -> datetime:
    return datetime.now(fuseau(cfg))


def lundi_de(jour: date) -> date:
    return jour - timedelta(days=jour.weekday())


def horaires_semaine(cfg: dict, lundi: date) -> dict:
    """Renvoie les horaires (carrousels / reels) applicables à la semaine qui commence `lundi`."""
    r = cfg["rythme"]
    lancement = date.fromisoformat(str(r["date_lancement"]))
    semaines_ecoulees = (lundi - lundi_de(lancement)).days // 7
    phase = "demarrage" if semaines_ecoulees < int(r.get("semaines_demarrage", 0)) else "normal"
    return {"phase": phase, **r[phase]}
