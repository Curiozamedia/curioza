"""Publie sur Instagram les posts validés dont l'heure arrive.

Lancé par GitHub Actions toutes les heures à hh:40. Si un post est prévu dans les 25 minutes,
le script prépare les conteneurs Instagram à l'avance puis attend l'heure pile pour publier.
Un post en retard (jusqu'à 90 min, si GitHub a démarré tard) est publié tout de suite.

Usage :
  python publier.py                 # mode normal
  python publier.py --simulation    # montre ce qui serait publié, sans rien envoyer
  python publier.py --maintenant ID # publie immédiatement un post précis (test)
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timedelta

from curioza import calendrier, instagram, planning
from curioza.config import DOSSIER_MEDIAS, charger_config, fuseau, maintenant

AVANCE_MAX = timedelta(minutes=25)
RETARD_MAX = timedelta(minutes=90)


def _instant(cfg, p) -> datetime:
    return datetime.fromisoformat(f"{p['date']}T{p['heure']}").replace(tzinfo=fuseau(cfg))


def _publiable(cfg, semaine, p) -> bool:
    st = p.get("statut")
    if st in ("publie", "refuse", "erreur") or not p.get("medias"):
        return False
    if p.get("publication") == "manuelle":
        return False  # Reel à publier depuis l'app avec un son tendance
    if st == "ok":
        return True
    if st == "a_valider":
        return bool(semaine.get("tout_valider")) or not cfg.get("validation_requise", True)
    return False


def _url(cfg, chemin: str) -> str:
    return cfg["url_pages"].rstrip("/") + "/" + chemin


def _preparer(cfg, p) -> str:
    if p["type"] == "carrousel":
        return instagram.preparer_carrousel([_url(cfg, m) for m in p["medias"]], p["legende"])
    return instagram.preparer_reel(_url(cfg, p["medias"][0]), p["legende"],
                                   _url(cfg, p["couverture"]) if p.get("couverture") else None)


def nettoyer_medias(cfg, semaines, jours: int = 14) -> None:
    """Supprime les médias des posts publiés depuis plus de `jours` jours (garde le dépôt léger)."""
    limite = maintenant(cfg).date() - timedelta(days=jours)
    for s in semaines:
        for p in s["posts"]:
            if p.get("statut") == "publie" and p["date"] < limite.isoformat() and not p.get("medias_supprimes"):
                shutil.rmtree(DOSSIER_MEDIAS / s["semaine"] / p["id"], ignore_errors=True)
                p["medias_supprimes"] = True


def main() -> None:
    cfg = charger_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulation", action="store_true")
    ap.add_argument("--maintenant", help="id d'un post à publier tout de suite")
    a = ap.parse_args()

    semaines = planning.toutes_les_semaines()
    now = maintenant(cfg)
    a_faire = []
    for s in semaines:
        for p in s["posts"]:
            if a.maintenant:
                if p["id"] == a.maintenant:
                    a_faire.append((s, p, now))
                continue
            t = _instant(cfg, p)
            if now - RETARD_MAX <= t <= now + AVANCE_MAX and _publiable(cfg, s, p):
                a_faire.append((s, p, t))
    a_faire.sort(key=lambda x: x[2])

    if not a_faire:
        print(f"{now:%d/%m %H:%M} — rien à publier dans cette fenêtre.")
    for s, p, t in a_faire:
        print(f"→ {p['id']} ({p['type']}) prévu à {t:%H:%M} : {p.get('sujet')}")
        if a.simulation:
            print("   [simulation] médias :", [_url(cfg, m) for m in p["medias"]][:3], "…")
            continue
        try:
            cid = _preparer(cfg, p)
            attente = (t - maintenant(cfg)).total_seconds()
            if attente > 0:
                print(f"   conteneur prêt, attente de {int(attente)} s jusqu'à l'heure pile…")
                time.sleep(attente)
            p["ig_id"] = instagram.publier(cid)
            p["statut"] = "publie"
            p["publie_le"] = maintenant(cfg).isoformat(timespec="seconds")
            p.pop("erreur", None)
            print(f"   ✅ publié (id {p['ig_id']})")
        except Exception as e:
            p["statut"] = "erreur"
            p["erreur"] = str(e)[:500]
            print(f"   ❌ {e}", file=sys.stderr)
        planning.ecrire(s)  # on enregistre après chaque post

    if not a.simulation:
        nettoyer_medias(cfg, semaines)
        for s in semaines:
            planning.ecrire(s)
        calendrier.generer(cfg)
    if any(p.get("statut") == "erreur" for _, p, _ in a_faire):
        sys.exit(1)  # GitHub t'envoie un e-mail en cas d'échec


if __name__ == "__main__":
    main()
