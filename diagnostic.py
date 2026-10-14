"""Diagnostic : quels modèles Veo existent sur ce projet, et pourquoi une devinette Nano Banana échouerait.
Les tests Veo envoient volontairement une durée invalide : réponse 400 = le modèle existe (rien n'est facturé),
404 = le modèle n'existe pas."""
from __future__ import annotations

import os
import requests

from curioza import devinettes, idees, images
from curioza.config import charger_config

cfg = charger_config()
entetes, projet = images._entetes_vertex()
print("Projet :", projet)
CANDIDATS = ["veo-3.1-fast-generate-001", "veo-3.1-fast-generate-preview", "veo-3.1-generate-001",
             "veo-3.1-generate-preview", "veo-3.0-fast-generate-001", "veo-3.0-fast-generate-preview",
             "veo-3.0-generate-001", "veo-2.0-generate-001"]
for region in ("us-central1", "global"):
    hote = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    for m in CANDIDATS:
        url = f"https://{hote}/v1/projects/{projet}/locations/{region}/publishers/google/models/{m}:predictLongRunning"
        r = requests.post(url, headers=entetes, json={"instances": [{"prompt": "test"}],
                                                      "parameters": {"durationSeconds": 99, "sampleCount": 1}}, timeout=60)
        print(f"VEO {region:12s} {m:32s} {r.status_code} {r.text[:140].replace(chr(10), ' ')}")

os.makedirs("test_cles", exist_ok=True)
d = devinettes.generer("diagnostic-1")
print("Devinette :", d["expression"])
for essai in range(2):
    try:
        img = images.generer(d["scene"] + ", the written equation exactly in the vertical center of the frame", cfg,
                             graine=f"diag{essai}", ratio="9:16", role="couverture", devinette=True, texte_dans_image=True)
        img.save(f"test_cles/devinette_{essai}.jpg", quality=90)
        import anthropic, base64, io
        b = io.BytesIO(); img.convert("RGB").resize((img.width // 2, img.height // 2)).save(b, format="JPEG")
        rep = anthropic.Anthropic().messages.create(model=cfg["ia_texte"]["modele"], max_tokens=60, messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}},
            {"type": "text", "text": "Recopie exactement le calcul écrit dans l'image, tel quel, sans le résoudre."}]}])
        lu = "".join(x.text for x in rep.content if getattr(x, "type", "") == "text")
        print(f"Essai {essai} : lu = {lu!r} → {idees._normaliser_calcul(lu)!r} vs {idees._normaliser_calcul(d['expression'])!r}")
    except Exception as e:
        print(f"Essai {essai} : ERREUR {type(e).__name__}: {str(e)[:300]}")
