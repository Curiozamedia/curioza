"""Publication via l'API Instagram officielle (« Instagram API with Instagram Login »).

Variables d'environnement (secrets GitHub) :
  IG_USER_ID       identifiant de ton compte Instagram professionnel
  IG_ACCESS_TOKEN  jeton longue durée (permission instagram_business_content_publish)
Les médias doivent être accessibles par une URL publique (ici : GitHub Pages).
"""
from __future__ import annotations

import os
import time

import requests

API = "https://graph.instagram.com/v25.0"


class ErreurInstagram(RuntimeError):
    pass


def _jeton() -> str:
    t = os.environ.get("IG_ACCESS_TOKEN")
    if not t:
        raise ErreurInstagram("IG_ACCESS_TOKEN manquant")
    return t


def _uid() -> str:
    u = os.environ.get("IG_USER_ID")
    if not u:
        raise ErreurInstagram("IG_USER_ID manquant")
    return u


def _post(chemin: str, **params) -> dict:
    params["access_token"] = _jeton()
    r = requests.post(f"{API}/{chemin}", data=params, timeout=120)
    data = r.json() if r.content else {}
    if not r.ok or "error" in data:
        raise ErreurInstagram(f"{chemin} : {data.get('error', r.text)}")
    return data


def _get(chemin: str, **params) -> dict:
    params["access_token"] = _jeton()
    r = requests.get(f"{API}/{chemin}", params=params, timeout=60)
    data = r.json() if r.content else {}
    if not r.ok or "error" in data:
        raise ErreurInstagram(f"{chemin} : {data.get('error', r.text)}")
    return data


def attendre_conteneur(cid: str, max_minutes: int = 10) -> None:
    fin = time.time() + max_minutes * 60
    while time.time() < fin:
        statut = _get(cid, fields="status_code").get("status_code")
        if statut in ("FINISHED", "PUBLISHED"):
            return
        if statut in ("ERROR", "EXPIRED"):
            raise ErreurInstagram(f"conteneur {cid} en statut {statut}")
        time.sleep(15)
    raise ErreurInstagram(f"conteneur {cid} toujours en traitement après {max_minutes} min")


def preparer_carrousel(urls_images: list[str], legende: str) -> str:
    """Crée les conteneurs (sans publier). Renvoie l'id du conteneur carrousel."""
    if not 2 <= len(urls_images) <= 10:
        raise ErreurInstagram("un carrousel doit contenir de 2 à 10 images")
    enfants = []
    for u in urls_images:
        enfants.append(_post(f"{_uid()}/media", image_url=u, is_carousel_item="true")["id"])
    for e in enfants:
        attendre_conteneur(e, 5)
    cid = _post(f"{_uid()}/media", media_type="CAROUSEL", children=",".join(enfants), caption=legende)["id"]
    attendre_conteneur(cid, 5)
    return cid


def preparer_reel(url_video: str, legende: str, url_couverture: str | None = None) -> str:
    params = dict(media_type="REELS", video_url=url_video, caption=legende, share_to_feed="true")
    if url_couverture:
        params["cover_url"] = url_couverture
    try:
        cid = _post(f"{_uid()}/media", **params)["id"]
    except ErreurInstagram:
        params.pop("cover_url", None)  # si la couverture pose problème, on publie sans
        cid = _post(f"{_uid()}/media", **params)["id"]
    attendre_conteneur(cid, 10)
    return cid


def publier(cid: str) -> str:
    return _post(f"{_uid()}/media_publish", creation_id=cid)["id"]


def quota_restant() -> int | None:
    try:
        d = _get(f"{_uid()}/content_publishing_limit", fields="quota_usage,config")
        item = d["data"][0]
        return int(item["config"]["quota_total"]) - int(item["quota_usage"])
    except Exception:
        return None


def rafraichir_jeton() -> str:
    """Prolonge le jeton longue durée de 60 jours (à faire au moins tous les 50 jours)."""
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": _jeton()}, timeout=60)
    data = r.json()
    if "access_token" not in data:
        raise ErreurInstagram(f"rafraîchissement impossible : {data}")
    return data["access_token"]
