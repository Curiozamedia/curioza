"""Prépare une semaine complète de posts à l'avance et met à jour le calendrier.

Usage :
  python planifier.py                    # complète les 7 prochains jours (mode quotidien)
  python planifier.py --semaine 2026-10-19
  python planifier.py --refaire 2026-10-19_1100_carro   # régénère un seul post
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from curioza import calendrier, planning
from curioza.config import charger_config, lundi_de, maintenant


def main() -> None:
    cfg = charger_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--semaine", help="lundi de la semaine à préparer (AAAA-MM-JJ)")
    ap.add_argument("--forcer", action="store_true", help="écrase une semaine déjà planifiée")
    ap.add_argument("--refaire", help="id d'un post à régénérer")
    ap.add_argument("--calendrier-seul", action="store_true")
    ap.add_argument("--remettre-en-page", action="store_true",
                    help="recompose tous les carrousels à venir avec la mise en page actuelle (sans régénérer)")
    a = ap.parse_args()

    if a.remettre_en_page:
        import glob
        for f in sorted(glob.glob(str(planning.DOSSIER_PLANNING / "*.yaml"))):
            data = planning.lire(date.fromisoformat(Path(f).stem))
            n = sum(planning.remettre_en_page(cfg, p) for p in data["posts"] if p.get("statut") != "publie")
            print(f"{Path(f).stem} : {n} carrousels remis en page")
        print(calendrier.generer(cfg))
        return

    if a.calendrier_seul:
        print(calendrier.generer(cfg))
        return

    if a.refaire:
        lundi = lundi_de(date.fromisoformat(a.refaire[:10]))
        data = planning.lire(lundi)
        neuve = planning.creer_semaine_partielle(cfg, lundi, data, a.refaire)
        planning.ecrire(neuve)
        print(calendrier.generer(cfg))
        return

    if a.semaine:
        lundi = lundi_de(date.fromisoformat(a.semaine))
        if planning.lire(lundi) and not a.forcer:
            print(f"La semaine du {lundi} est déjà planifiée (utilise --forcer pour la refaire).")
        else:
            planning.ecrire(planning.creer_semaine(cfg, lundi))
    else:
        # Mode normal (tous les jours) : on remplit les 7 prochains jours qui ne sont pas encore prêts.
        # Le quota gratuit de Cloudflare (~170 images/jour) suffit pour ~4 jours d'un coup,
        # puis ~1 jour par passage : on garde toujours une semaine d'avance.
        lancement = date.fromisoformat(str(cfg["rythme"]["date_lancement"]))
        debut = max(maintenant(cfg).date() + timedelta(days=1), lancement)
        manquants = planning.jours_manquants(cfg, debut, debut + timedelta(days=6))
        if not manquants:
            print("Les 7 prochains jours sont déjà prêts.")
        for lundi, jours in sorted(manquants.items()):
            # jour par jour, enregistré à chaque fois : rien n'est perdu si le passage est interrompu
            for jour in jours:
                if planning.temps_ecoule():
                    break
                data = planning.creer_semaine(cfg, lundi, jours=[jour], existant=planning.lire(lundi))
                planning.ecrire(data)
        # Puis on retente les posts ratés (quota, réseau…) pour ne jamais laisser de trou.
        planning.reparer_erreurs(cfg, debut, debut + timedelta(days=6))
    print("Calendrier :", calendrier.generer(cfg))


if __name__ == "__main__":
    main()
