"""Génération des images IA.

Chaque type d'image a sa chaîne de modèles dans config.yaml (ia_image) : le premier disponible
est utilisé, les suivants servent de secours.
  - Cloudflare Workers AI : gratuit jusqu'à ~170 images/jour (CF_ACCOUNT_ID + CF_API_TOKEN)
  - Vertex AI (Google Cloud) : même Nano Banana, payé avec le crédit d'essai de 300 $ (VERTEX_API_KEY)
  - Google (Gemini API) : Nano Banana ~0,039 $ l'image, qualité haut de gamme (GEMINI_API_KEY)
  - Replicate : facultatif, mêmes modèles via un intermédiaire (REPLICATE_API_TOKEN)
Sans aucune clé : fonds d'aperçu procéduraux (mode démo).
"""
from __future__ import annotations

import base64
import io
import os
import time

import requests
from PIL import Image

from . import rendu

STYLE_COMMUN = (
    "photorealistic, cinematic lighting, ultra detailed, vivid saturated colors, shallow depth of field, "
    "shot on 35mm, dramatic composition, vertical 4:5 framing, main subject in the upper two thirds, "
    "empty darker area at the bottom for a caption, no text, no letters, no watermark, no logo"
)
STYLE_DEVINETTE = (
    "photorealistic, natural light, clean simple composition, smartphone photo look, vertical 9:16, no watermark"
)


def _cloudflare_dispo() -> bool:
    return bool(os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"))


def _replicate_dispo() -> bool:
    return bool(os.environ.get("REPLICATE_API_TOKEN"))


def _google_dispo() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _vertex_dispo() -> bool:
    return bool(os.environ.get("VERTEX_API_KEY") or os.environ.get("VERTEX_SA_JSON")
                or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


_jeton_vertex: dict = {}


def _entetes_vertex() -> tuple[dict, str]:
    """Renvoie (en-têtes d'authentification, identifiant du projet).
    Deux façons : clé de compte de service JSON (VERTEX_SA_JSON) ou clé API (VERTEX_API_KEY)."""
    brut = os.environ.get("VERTEX_SA_JSON", "").strip()
    if brut:
        import json
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        infos = json.loads(brut)
        if not _jeton_vertex.get("cred"):
            _jeton_vertex["cred"] = service_account.Credentials.from_service_account_info(
                infos, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        cred = _jeton_vertex["cred"]
        if not cred.valid:
            cred.refresh(Request())
        return {"Authorization": f"Bearer {cred.token}"}, os.environ.get("VERTEX_PROJECT", "").strip() or infos["project_id"]
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and not os.environ.get("VERTEX_API_KEY"):
        # Fédération d'identité GitHub → Google (sans clé) : identifiants fournis par google-github-actions/auth.
        import google.auth
        from google.auth.transport.requests import Request
        if not _jeton_vertex.get("cred"):
            cred, projet = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            _jeton_vertex["cred"], _jeton_vertex["projet"] = cred, projet
        cred = _jeton_vertex["cred"]
        if not cred.valid:
            cred.refresh(Request())
        projet = (os.environ.get("VERTEX_PROJECT", "").strip() or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
                  or _jeton_vertex.get("projet") or "")
        return {"Authorization": f"Bearer {cred.token}"}, projet
    return {"x-goog-api-key": os.environ["VERTEX_API_KEY"]}, os.environ.get("VERTEX_PROJECT", "").strip()


def _extraire_image(r: requests.Response, nom: str) -> Image.Image:
    for cand in r.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            donnees = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if donnees:
                return Image.open(io.BytesIO(base64.b64decode(donnees)))
    raise RuntimeError(f"Pas d'image dans la réponse {nom} : {r.text[:300]}")


def _vertex(prompt: str, modele: str, ratio: str, patience: tuple = (0, 15, 30)) -> Image.Image:
    """Nano Banana via Vertex AI (Google Cloud) : utilise le crédit d'essai de 300 $.
    VERTEX_SA_JSON = contenu du fichier JSON du compte de service (ou VERTEX_API_KEY = clé API liée)."""
    entetes, projet = _entetes_vertex()
    region = os.environ.get("VERTEX_REGION", "global").strip() or "global"
    hote = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    chemin = (f"projects/{projet}/locations/{region}/publishers/google/models/{modele}" if projet
              else f"publishers/google/models/{modele}")
    corps = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}}}
    # Les comptes d'essai ont un débit limité par minute : en cas de 429 on patiente et on réessaie.
    for attente in patience:
        if attente:
            time.sleep(attente)
        r = requests.post(f"https://{hote}/v1/{chemin}:generateContent",
                          headers=entetes, json=corps, timeout=180)
        if r.status_code not in (429, 500, 503):
            break
    if not r.ok:
        raise RuntimeError(f"Vertex {r.status_code} : {r.text[:400]}")
    return _extraire_image(r, "Vertex")


def _google(prompt: str, modele: str, ratio: str) -> Image.Image:
    """Nano Banana directement chez Google (Gemini API, clé créée sur aistudio.google.com)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
    corps = {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}}}
    r = requests.post(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, json=corps, timeout=180)
    if r.status_code == 429:
        time.sleep(20)
    r.raise_for_status()
    return _extraire_image(r, "Google")


def mode_apercu() -> bool:
    return not (_cloudflare_dispo() or _replicate_dispo() or _google_dispo() or _vertex_dispo())


class QuotaEpuise(RuntimeError):
    pass


_cloudflare_epuise = False  # une fois le quota gratuit du jour atteint, on passe directement au secours


def _cloudflare(prompt: str, modele: str) -> Image.Image:
    url = (f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}"
           f"/ai/run/{modele}")
    r = requests.post(url, headers={"Authorization": f"Bearer {os.environ['CF_API_TOKEN']}"},
                      json={"prompt": prompt[:2000], "steps": 4}, timeout=120)
    if r.status_code == 429 or "neurons" in r.text.lower() and not r.ok:
        raise QuotaEpuise(r.text[:200])
    r.raise_for_status()
    data = r.json()
    if not data.get("success", True):
        raise RuntimeError(str(data.get("errors"))[:300])
    img_b64 = data["result"]["image"]
    return Image.open(io.BytesIO(base64.b64decode(img_b64)))


def _entree_modele(modele: str, prompt: str, ratio: str) -> dict:
    if "flux" in modele:
        return {"prompt": prompt, "aspect_ratio": ratio, "output_format": "jpg", "output_quality": 95,
                "num_outputs": 1, "go_fast": True}
    # nano-banana et modèles similaires
    return {"prompt": prompt, "aspect_ratio": ratio, "output_format": "jpg"}


def _vers_image(sortie) -> Image.Image:
    if isinstance(sortie, (list, tuple)):
        sortie = sortie[0]
    if hasattr(sortie, "read"):
        return Image.open(io.BytesIO(sortie.read()))
    url = str(sortie)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))


def _replicate(prompt: str, modele: str, ratio: str) -> Image.Image:
    import replicate  # importé ici pour que le mode démo fonctionne sans la librairie
    sortie = replicate.run(modele, input=_entree_modele(modele, prompt, ratio))
    return _vers_image(sortie)


def chaine_pour(cfg: dict, role: str) -> list[str]:
    """Liste ordonnée « fournisseur:modèle » pour un rôle (couverture, slide, devinette)."""
    ia = cfg["ia_image"]
    return ia.get(role) or ia.get("slide") or ["cloudflare:@cf/black-forest-labs/flux-1-schnell"]


def generer(prompt: str, cfg: dict, *, graine: str, ratio: str = "4:5", devinette: bool = False,
            texte_dans_image: bool = False, role: str | None = None) -> Image.Image:
    """Renvoie une image PIL. Sans aucune clé : fond d'aperçu procédural.
    `role` choisit la chaîne de modèles : « couverture » (qualité maximale), « slide », « devinette »."""
    taille = tuple(cfg["style"]["format_reel" if ratio == "9:16" else "format"])
    if mode_apercu():
        return rendu.fond_apercu(graine, taille, libelle="aperçu — l'image IA viendra ici")

    role = role or ("devinette" if devinette else "slide")
    style = STYLE_DEVINETTE if devinette else STYLE_COMMUN
    if texte_dans_image:
        style = style.replace("no text, no letters, ", "")
    if ratio == "9:16":
        style = style.replace("vertical 4:5 framing", "vertical 9:16 framing")
    prompt_complet = f"{prompt}. {style}"
    derniere_erreur = None

    global _cloudflare_epuise
    for entree in chaine_pour(cfg, role):
        fournisseur, _, modele = entree.partition(":")
        if fournisseur == "cloudflare" and (not _cloudflare_dispo() or _cloudflare_epuise):
            continue
        if fournisseur == "replicate" and not _replicate_dispo():
            continue
        if fournisseur == "google" and not _google_dispo():
            continue
        if fournisseur == "vertex" and not _vertex_dispo():
            continue
        for essai in range(3):
            try:
                if fournisseur == "cloudflare":
                    return _cloudflare(prompt_complet, modele).convert("RGB")
                if fournisseur == "google":
                    return _google(prompt_complet, modele, ratio).convert("RGB")
                if fournisseur == "vertex":
                    # Couverture = la slide qui fait arrêter le scroll : on patiente plus longtemps pour Nano Banana.
                    patience = (0, 20, 40, 60, 90) if role == "couverture" else (0, 15, 30)
                    return _vertex(prompt_complet, modele, ratio, patience).convert("RGB")
                return _replicate(prompt_complet, modele, ratio).convert("RGB")
            except QuotaEpuise as e:
                _cloudflare_epuise = True
                derniere_erreur = e
                break
            except Exception as e:  # modèle indisponible, filtre, réseau…
                derniere_erreur = e
                if "429" in str(e)[:20]:
                    break  # limite de débit : on passe tout de suite au fournisseur de secours
                time.sleep(4 * (essai + 1))
    if isinstance(derniere_erreur, QuotaEpuise):
        raise derniere_erreur
    raise RuntimeError(f"Génération d'image impossible avec tous les fournisseurs : {derniere_erreur}")


# ------------------------------------------------------------------ vidéo IA (Veo, Vertex AI)


def video_dispo() -> bool:
    return _vertex_dispo()


def generer_video(prompt: str, image: Image.Image, sortie, cfg: dict, duree: int = 8) -> "Path":
    """Anime une image fixe 9:16 en un plan vidéo de `duree` secondes avec Veo (image vers vidéo, sans son :
    le son tendance est ajouté dans l'app Instagram). Payé par le crédit Google Cloud."""
    from pathlib import Path
    modele = (cfg.get("ia_video") or {}).get("modele", "veo-3.0-fast-generate-001")
    region = (cfg.get("ia_video") or {}).get("region", "us-central1")
    entetes, projet = _entetes_vertex()
    if not projet:
        raise RuntimeError("Projet Google Cloud inconnu pour Veo")
    base = (f"https://{region}-aiplatform.googleapis.com/v1/projects/{projet}/locations/{region}"
            f"/publishers/google/models/{modele}")
    tampon = io.BytesIO()
    image.convert("RGB").save(tampon, format="JPEG", quality=92)
    corps = {
        "instances": [{"prompt": prompt,
                       "image": {"bytesBase64Encoded": base64.b64encode(tampon.getvalue()).decode(),
                                 "mimeType": "image/jpeg"}}],
        "parameters": {"aspectRatio": "9:16", "sampleCount": 1, "durationSeconds": duree,
                       "generateAudio": False, "resolution": "1080p", "personGeneration": "allow_adult"},
    }
    for attente in (0, 30, 60, 90):
        if attente:
            time.sleep(attente)
        r = requests.post(f"{base}:predictLongRunning", headers=entetes, json=corps, timeout=120)
        if r.status_code not in (429, 500, 503):
            break
    if not r.ok:
        raise RuntimeError(f"Veo {r.status_code} : {r.text[:300]}")
    operation = r.json()["name"]
    debut = time.time()
    while time.time() - debut < 600:
        time.sleep(15)
        rr = requests.post(f"{base}:fetchPredictOperation", headers=_entetes_vertex()[0],
                           json={"operationName": operation}, timeout=120)
        if not rr.ok:
            continue
        etat = rr.json()
        if not etat.get("done"):
            continue
        if etat.get("error"):
            raise RuntimeError(f"Veo : {str(etat['error'])[:300]}")
        videos = (etat.get("response") or {}).get("videos") or []
        if not videos or not videos[0].get("bytesBase64Encoded"):
            raise RuntimeError(f"Veo : vidéo refusée ou vide ({str(etat.get('response'))[:200]})")
        sortie = Path(sortie)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        sortie.write_bytes(base64.b64decode(videos[0]["bytesBase64Encoded"]))
        return sortie
    raise RuntimeError("Veo : délai dépassé")
