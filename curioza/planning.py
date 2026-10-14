"""Planning hebdomadaire : création de la semaine, lecture/écriture des fichiers YAML."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import devinettes, idees, images, rendu, reel
from .config import DOSSIER_MEDIAS, DOSSIER_PLANNING, horaires_semaine

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
STATUTS = ["a_valider", "ok", "refuse", "publie", "erreur"]


def fichier_semaine(lundi: date) -> Path:
    return DOSSIER_PLANNING / f"{lundi.isoformat()}.yaml"


def lire(lundi: date) -> dict | None:
    f = fichier_semaine(lundi)
    if not f.exists():
        return None
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def ecrire(data: dict) -> Path:
    f = fichier_semaine(date.fromisoformat(data["semaine"]))
    f.parent.mkdir(parents=True, exist_ok=True)
    entete = (
        "# PLANNING DE LA SEMAINE — à vérifier avant publication\n"
        "# Pour chaque post, change la ligne 'statut' :\n"
        "#   a_valider -> pas encore vérifié (NE SERA PAS publié si validation_requise: true)\n"
        "#   ok        -> validé, sera publié automatiquement à l'heure prévue\n"
        "#   refuse    -> ne sera jamais publié\n"
        "# Raccourci : mets 'tout_valider: true' pour valider d'un coup tous les posts 'a_valider'.\n"
        "# Tu peux aussi modifier 'legende' ou 'heure' directement ici.\n\n"
    )
    f.write_text(entete + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    return f


def toutes_les_semaines() -> list[dict]:
    res = []
    for f in sorted(DOSSIER_PLANNING.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        if d and d.get("posts") is not None:
            res.append(d)
    return res


# ------------------------------------------------------------------ construction d'une semaine


def _categories_semaine(cfg: dict, n: int, graine: str) -> list[str]:
    rnd = random.Random(graine)
    sac = [c for c, v in cfg["categories"].items() for _ in range(int(v["poids"]))]
    res: list[str] = []
    while len(res) < n:
        rnd.shuffle(sac)
        for c in sac:
            if len(res) >= n:
                break
            if res and res[-1] == c:
                continue
            res.append(c)
    return res


def creer_semaine(cfg: dict, lundi: date, journal=print, jours: list[date] | None = None,
                  existant: dict | None = None) -> dict:
    """Génère les posts de la semaine. `jours` = ne générer que ces dates (les autres sont conservées
    depuis `existant`). Si le quota d'images gratuit est atteint, les jours restants sont laissés vides
    pour être générés au prochain passage (lendemain)."""
    h = horaires_semaine(cfg, lundi)
    creneaux = []
    for j in range(7):
        jour = lundi + timedelta(days=j)
        for heure in h["carrousels"]:
            creneaux.append((jour, heure, "carrousel"))
        for i, heure in enumerate(h["reels"]):
            creneaux.append((jour, heure, "reel_devinette" if i == 0 else "reel_diaporama"))
    creneaux.sort(key=lambda c: (c[0], c[1]))

    nb_carrousels = sum(1 for c in creneaux if c[2] == "carrousel")
    categories = _categories_semaine(cfg, nb_carrousels, lundi.isoformat())
    a_faire = set(jours) if jours is not None else {c[0] for c in creneaux}
    conserves = [p for p in (existant or {}).get("posts", []) if date.fromisoformat(p["date"]) not in a_faire]
    deja = ([p.get("concept", "") for p in conserves if p.get("concept")] + [p.get("sujet", "") for p in conserves]
            + idees.sujets_deja_traites())
    inspiration = idees.radar_reddit(cfg) if not idees.mode_demo() else []
    journal(f"Semaine du {lundi} — phase {h['phase']} — jours générés : "
            f"{', '.join(sorted(d.isoformat() for d in a_faire))} "
            f"({'DÉMO, sans clé API' if idees.mode_demo() else 'IA'})")

    posts = list(conserves)
    k = 0
    carrousels_du_jour: dict[str, list[dict]] = {}
    jour_en_cours, posts_du_jour, arret = None, [], False
    for jour, heure, typ in creneaux:
        if typ == "carrousel":
            cat = categories[k]; k += 1
        if jour not in a_faire or arret:
            continue
        if jour != jour_en_cours and temps_ecoule():
            journal(f"  Temps de génération écoulé : {jour} et la suite seront faits au prochain passage.")
            arret = True
            continue
        if jour != jour_en_cours:
            posts += posts_du_jour
            jour_en_cours, posts_du_jour = jour, []
        ident = f"{jour.isoformat()}_{heure.replace(':', '')}_{typ.split('_')[-1][:5]}"
        dossier = DOSSIER_MEDIAS / lundi.isoformat() / ident
        base = {"id": ident, "jour": JOURS[jour.weekday()], "date": jour.isoformat(), "heure": heure, "type": typ,
                "statut": "a_valider"}
        try:
            if typ == "carrousel":
                post = {**base, **_construire_carrousel(cfg, cat, k, deja, inspiration, dossier, ident)}
                deja.insert(0, post["sujet"])
                if post.get("concept"):
                    deja.insert(0, post["concept"])
                carrousels_du_jour.setdefault(jour.isoformat(), []).append(post)
            elif typ == "reel_devinette":
                post = {**base, **_construire_devinette(cfg, dossier, ident)}
            else:
                source = _choisir_source_diaporama(carrousels_du_jour.get(jour.isoformat(), []))
                post = {**base, **_construire_diaporama(cfg, source, dossier, ident)}
        except Exception as e:  # on n'arrête pas toute la semaine pour un post raté
            if "QuotaEpuise" in type(e).__name__ or "neurons" in str(e).lower():
                journal(f"  Quota d'images gratuit atteint : {jour} et la suite seront générés au prochain passage.")
                import shutil
                for p_ in posts_du_jour:
                    shutil.rmtree(DOSSIER_MEDIAS / lundi.isoformat() / p_["id"], ignore_errors=True)
                posts_du_jour, arret = [], True
                continue
            post = {**base, "statut": "erreur", "sujet": "(génération échouée)", "erreur": str(e)[:300],
                    "medias": [], "legende": ""}
            if typ == "carrousel":
                post["categorie"] = cat
        journal(f"  {post['date']} {post['heure']} {typ:15} {post.get('sujet', '')}")
        posts_du_jour.append(post)
    posts += posts_du_jour
    posts.sort(key=lambda p: (p["date"], p["heure"]))

    return {"semaine": lundi.isoformat(), "phase": h["phase"],
            "tout_valider": (existant or {}).get("tout_valider", False),
            "genere_le": datetime.now().isoformat(timespec="minutes"), "posts": posts}


def jours_manquants(cfg: dict, debut: date, fin: date) -> dict[date, list[date]]:
    """Jours entre debut et fin (inclus) sans aucun post planifié, regroupés par semaine (lundi)."""
    from .config import lundi_de
    res: dict[date, list[date]] = {}
    d = debut
    while d <= fin:
        data = lire(lundi_de(d)) or {}
        if not any(p["date"] == d.isoformat() for p in data.get("posts", [])):
            res.setdefault(lundi_de(d), []).append(d)
        d += timedelta(days=1)
    return res


import os as _os
import time as _time

_DEBUT = _time.time()


def temps_ecoule() -> bool:
    """Budget de temps par passage (GENERATION_MINUTES, 150 par défaut) : on s'arrête proprement entre deux jours
    pour toujours enregistrer ce qui est fait ; la suite est générée au passage suivant."""
    return (_time.time() - _DEBUT) / 60 > float(_os.environ.get("GENERATION_MINUTES", "150"))


def reparer_erreurs(cfg: dict, debut: date, fin: date, journal=print) -> None:
    """Regénère automatiquement les posts restés en « erreur » entre debut et fin (inclus)."""
    from .config import lundi_de
    lundi = lundi_de(debut)
    while lundi <= fin:
        data = lire(lundi)
        if data:
            rates = [p["id"] for p in data["posts"] if p.get("statut") == "erreur"
                     and debut.isoformat() <= p["date"] <= fin.isoformat()]
            # les diaporamas en dernier : ils réutilisent les carrousels du jour
            rates.sort(key=lambda i: ("diapo" in i, i))
            for ident in rates:
                if temps_ecoule():
                    journal("  Temps écoulé : réparations reportées au prochain passage.")
                    return
                try:
                    data = creer_semaine_partielle(cfg, lundi, data, ident)
                    journal(f"  Réparé : {ident}")
                except Exception as e:
                    journal(f"  Toujours en échec : {ident} ({str(e)[:120]})")
                ecrire(data)
        lundi += timedelta(days=7)


def creer_semaine_partielle(cfg: dict, lundi: date, data: dict, ident: str) -> dict:
    """Régénère un seul post (nouveau sujet / nouvelles images) dans une semaine existante."""
    import shutil
    posts = data["posts"]
    p = next((x for x in posts if x["id"] == ident), None)
    if not p:
        raise SystemExit(f"Post {ident} introuvable")
    dossier = DOSSIER_MEDIAS / lundi.isoformat() / ident
    shutil.rmtree(dossier, ignore_errors=True)
    base = {k: p[k] for k in ("id", "jour", "date", "heure", "type")}
    base["statut"] = "a_valider"
    graine = ident + datetime.now().isoformat()
    if p["type"] == "carrousel":
        deja = ([x.get("concept", "") for x in posts if x.get("concept")] + [x.get("sujet", "") for x in posts]
                + idees.sujets_deja_traites())
        force = p.get("sujet") if p.get("garder_sujet") else None
        neuf = _construire_carrousel(cfg, p.get("categorie") or "absurde", random.randint(0, 99), deja, [], dossier,
                                     graine, concept_force=force)
    elif p["type"] == "reel_devinette":
        neuf = _construire_devinette(cfg, dossier, graine)
    else:
        jour = [x for x in posts if x["date"] == p["date"] and x["type"] == "carrousel"]
        neuf = _construire_diaporama(cfg, _choisir_source_diaporama(jour), dossier, graine)
    posts[posts.index(p)] = {**base, **neuf}
    return data


SONS = {
    "devinette": "son tendance rythmé ou suspense (type « phonk », « slowed », compte à rebours)",
    "absurde": "son tendance drôle ou décalé, ou un « slowed » mystérieux",
    "nostalgie": "son tendance nostalgique (tube des années 90-2000 de la bibliothèque Instagram)",
    "pays": "son tendance léger et voyage",
    "anecdote": "piano ou cinématique émouvant (comme les Reels d'Opulancia)",
    "vie": "piano émotion ou cinématique",
}


def _infos_reel(cfg: dict, categorie: str | None) -> dict:
    if cfg.get("reels_publication", "manuel") != "manuel":
        return {}
    return {"publication": "manuelle",
            "son_conseille": SONS.get(categorie or "", SONS["absurde"]) +
            " — dans l'app : choisis un son marqué d'une flèche ↗ (tendance)"}


def _garder_fond(img, dossier: Path, i: int) -> None:
    """Garde l'image IA sans texte : permet de refaire la mise en page plus tard sans tout régénérer."""
    (dossier / "fonds").mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dossier / "fonds" / f"{i:02d}.jpg", quality=90)


def remettre_en_page(cfg: dict, post: dict) -> bool:
    """Recompose les slides d'un carrousel avec la mise en page actuelle (mêmes images, mêmes textes)."""
    from PIL import Image
    c = post.get("contenu")
    if post.get("type") != "carrousel" or not c or not post.get("medias"):
        return False
    dossier = DOSSIER_MEDIAS.parent / Path(post["medias"][0]).parent
    fonds = sorted((dossier / "fonds").glob("*.jpg"))
    if len(fonds) < 1 + len(c["slides"]):
        return False
    ouvrir = lambda f: Image.open(f).convert("RGB")
    rendu.enregistrer_jpeg(rendu.slide_couverture(ouvrir(fonds[0]), c["titre_couverture"], cfg,
                                                  c.get("sous_titre") or None), dossier / "01.jpg")
    numerote = post.get("categorie") in ("nostalgie", "pays", "vie", "anecdote")
    for i, s in enumerate(c["slides"], start=2):
        rendu.enregistrer_jpeg(rendu.slide_contenu(ouvrir(fonds[i - 1]), s["titre"], s["texte"], cfg,
                                                   numero=str(i - 1) if numerote else None), dossier / f"{i:02d}.jpg")
    rendu.enregistrer_jpeg(rendu.slide_fin(ouvrir(fonds[len(c["slides"])]), cfg, c["question_fin"]),
                           dossier / f"{len(c['slides']) + 2:02d}.jpg")
    return True


def _rel(p: Path) -> str:
    return p.relative_to(DOSSIER_MEDIAS.parent).as_posix()


def _construire_carrousel(cfg, categorie, numero, deja, inspiration, dossier: Path, ident: str,
                          concept_force: str | None = None) -> dict:
    mini, maxi = cfg["slides_par_carrousel"]
    nb_contenu = random.Random(ident).randint(mini - 2, maxi - 2)  # - couverture - slide finale
    if idees.mode_demo():
        c = idees.contenu_demo(categorie, numero)
    else:
        c = idees.rediger_carrousel(cfg, categorie, nb_contenu, deja, inspiration, concept_force)
    fichiers = []
    fond = images.generer(c["prompt_couverture"], cfg, graine=ident + "c", role="couverture")
    _garder_fond(fond, dossier, 1)
    fichiers.append(rendu.enregistrer_jpeg(rendu.slide_couverture(fond, c["titre_couverture"], cfg, c.get("sous_titre") or None),
                                           dossier / "01.jpg"))
    dernier_fond = fond
    for i, s in enumerate(c["slides"], start=2):
        f = images.generer(s["prompt_image"], cfg, graine=f"{ident}{i}", role="slide")
        _garder_fond(f, dossier, i)
        dernier_fond = f
        fichiers.append(rendu.enregistrer_jpeg(
            rendu.slide_contenu(f, s["titre"], s["texte"], cfg,
                                numero=str(i - 1) if categorie in ("nostalgie", "pays", "vie", "anecdote") else None),
            dossier / f"{i:02d}.jpg"))
    fichiers.append(rendu.enregistrer_jpeg(rendu.slide_fin(dernier_fond, cfg, c["question_fin"]),
                                           dossier / f"{len(fichiers) + 1:02d}.jpg"))
    contenu = {"titre_couverture": c["titre_couverture"], "sous_titre": c.get("sous_titre") or "",
               "slides": [{"titre": x["titre"], "texte": x["texte"]} for x in c["slides"]],
               "question_fin": c["question_fin"]}
    return {"categorie": categorie, "concept": c.get("concept", ""), "contenu": contenu, "sujet": c["sujet"], "legende": idees.legende_carrousel(cfg, c),
            "medias": [_rel(p) for p in fichiers], "couverture": _rel(fichiers[0])}


def _construire_devinette(cfg, dossier: Path, ident: str) -> dict:
    d = devinettes.generer(ident)
    fond = images.generer(d["decor"], cfg, graine=ident, ratio="9:16", devinette=True)
    img = reel.image_devinette(fond, d, cfg)
    couverture = rendu.enregistrer_jpeg(img, dossier / "couverture.jpg")
    video = reel.video_devinette(fond, d, cfg, dossier / "reel.mp4", ident)
    return {**_infos_reel(cfg, "devinette"), "categorie": "devinette", "sujet": f"Devinette : {d['expression']}",
            "reponse": f"{d['reponse']} (piège : {d['piege']})", "legende": idees.legende_devinette(cfg, d),
            "medias": [_rel(video)], "couverture": _rel(couverture)}


def _choisir_source_diaporama(carrousels: list[dict]) -> dict:
    valides = [c for c in carrousels if c.get("medias")]
    if not valides:
        raise RuntimeError("aucun carrousel ce jour-là pour faire le diaporama")
    absurdes = [c for c in valides if c.get("categorie") == "absurde"]
    return (absurdes or valides)[0]


def _construire_diaporama(cfg, source: dict, dossier: Path, ident: str) -> dict:
    slides = [DOSSIER_MEDIAS.parent / m for m in source["medias"]]
    video = reel.video_diaporama(slides, cfg, dossier / "reel.mp4", ident)
    legende = source["legende"].replace("Enregistre ce carrousel", "Enregistre cette vidéo")
    return {**_infos_reel(cfg, source.get("categorie")), "categorie": source.get("categorie"),
            "sujet": f"Version Reel : {source['sujet']}", "legende": legende,
            "medias": [_rel(video)], "couverture": source["couverture"], "source": source["id"]}
