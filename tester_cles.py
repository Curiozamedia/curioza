"""Vérifie que chaque clé branchée fonctionne (sans rien publier).

Affiche OK / ÉCHEC pour chaque service et enregistre une image de test par fournisseur d'images
dans le dossier test_cles/ (récupérable dans l'onglet Actions → le passage → Artifacts).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from curioza import images
from curioza.config import charger_config

SORTIE = Path("test_cles")
PROMPT = ("A giant golden retriever wearing a tiny chef hat, cooking pancakes in a cozy 1990s French kitchen, "
          "morning light")


def tester_anthropic(cfg) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "absente"
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model=cfg["ia_texte"]["modele"], max_tokens=30,
        messages=[{"role": "user", "content": "Réponds juste : OK"}])
    return "OK — " + r.content[0].text.strip()[:40]


def tester_image(nom, fonction) -> str:
    try:
        img = fonction()
    except Exception as e:  # on affiche l'erreur sans jamais afficher la clé
        if "daily free allocation" in str(e) or isinstance(e, images.QuotaEpuise):
            return "OK — quota gratuit du jour déjà utilisé (revient à 2 h, heure de Paris)"
        return f"ÉCHEC — {str(e)[:300]}"
    SORTIE.mkdir(exist_ok=True)
    img.convert("RGB").save(SORTIE / f"{nom}.jpg", quality=92)
    return f"OK — image {img.size[0]}x{img.size[1]}"


def main() -> None:
    cfg = charger_config()
    resultats = {}
    try:
        resultats["Claude (textes)"] = tester_anthropic(cfg)
    except Exception as e:
        resultats["Claude (textes)"] = f"ÉCHEC — {str(e)[:300]}"

    if images._cloudflare_dispo():
        resultats["Cloudflare (images gratuites)"] = tester_image(
            "cloudflare", lambda: images._cloudflare(PROMPT, "@cf/black-forest-labs/flux-1-schnell"))
    else:
        resultats["Cloudflare (images gratuites)"] = "absente"

    if images._google_dispo():
        resultats["Google (Nano Banana)"] = tester_image(
            "google", lambda: images._google(PROMPT, "gemini-2.5-flash-image", "4:5"))
    else:
        resultats["Google (Nano Banana)"] = "absente (pas encore branchée)"

    # Diagnostic de forme (jamais la valeur) : aide à repérer un mauvais copier-coller.
    for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "GEMINI_API_KEY"):
        v = os.environ.get(k, "")
        if v:
            lignes = v.splitlines()
            resultats[f"forme {k}"] = (f"{len(v)} caractères, {len(lignes)} ligne(s), "
                                       f"longueurs par ligne {[len(l) for l in lignes][:6]}, "
                                       f"commence par une commande : {v.lower().startswith(('curl', 'http'))}")

    if images._vertex_dispo():
        resultats["Vertex AI (crédit 300 $)"] = tester_image(
            "vertex", lambda: images._vertex(PROMPT, "gemini-2.5-flash-image", "4:5"))
    else:
        resultats["Vertex AI (crédit 300 $)"] = "absente (pas encore branchée)"

    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN"):
        resultats[k] = "présent" if os.environ.get(k) else "absent (pas encore branché)"

    print("\n===== TEST DES CLÉS =====")
    for service, etat in resultats.items():
        print(f"{service:32s} {etat}")
    print("=========================\n")
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if resume:
        with open(resume, "a", encoding="utf-8") as f:
            f.write("## Test des clés\n\n| Service | État |\n|---|---|\n")
            for service, etat in resultats.items():
                f.write(f"| {service} | {etat} |\n")
    if any(v.startswith("ÉCHEC") for v in resultats.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
