"""Moteur de mise en page des visuels (carrousels et images de Reels).

Balisage des titres :
  [mot]  -> mot dans un encadré doré, texte noir
  *mot*  -> mot écrit en doré
Le reste est en blanc. Tout est mis en majuscules, police condensée très grasse.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import RACINE

# ------------------------------------------------------------------ outils


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _police(chemin: str, taille: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(RACINE / chemin), taille)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


def ajuster_cadre(img: Image.Image, taille: tuple[int, int]) -> Image.Image:
    """Recadre l'image au centre pour remplir exactement `taille` (comme 'cover' en CSS)."""
    return ImageOps.fit(img.convert("RGB"), taille, method=Image.LANCZOS, centering=(0.5, 0.4))


def degrade_bas(taille: tuple[int, int], part: float, opacite_max: int = 245) -> Image.Image:
    """Calque noir transparent -> opaque vers le bas."""
    l, h = taille
    debut = int(h * (1 - part))
    alpha = Image.new("L", (1, h), 0)
    for y in range(debut, h):
        t = (y - debut) / max(1, h - debut)
        alpha.putpixel((0, y), int(opacite_max * min(1.0, t ** 0.9 * 1.15)))
    calque = Image.new("RGBA", taille, (0, 0, 0, 0))
    calque.putalpha(alpha.resize(taille))
    return calque


def degrade_haut(taille: tuple[int, int], part: float = 0.18, opacite_max: int = 150) -> Image.Image:
    l, h = taille
    fin = int(h * part)
    alpha = Image.new("L", (1, h), 0)
    for y in range(fin):
        alpha.putpixel((0, y), int(opacite_max * (1 - y / fin)))
    calque = Image.new("RGBA", taille, (0, 0, 0, 0))
    calque.putalpha(alpha.resize(taille))
    return calque


# ------------------------------------------------------------------ titres balisés


@dataclass
class Mot:
    texte: str
    style: str  # "normal" | "or" | "encadre"
    colle: bool = False  # collé au mot précédent (ponctuation après un mot balisé)
    groupe: int = -1     # mots d'un même *groupe doré* : on évite de les séparer


PONCTUATION_HAUTE = {"?", "!", ":", ";", "»", "%"}


_EMOJIS = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\uFE0F\u200D\u2B00-\u2BFF]")


def typo_fr(texte: str) -> str:
    """Typographie française propre : apostrophe courbe, points de suspension.
    Les emojis sont retirés des visuels (les polices n'en ont pas : ils s'afficheraient en carré vide)."""
    texte = _EMOJIS.sub("", texte)
    texte = re.sub(r"[ \t]{2,}", " ", texte).strip()
    return texte.replace("'", "’").replace("...", "…")


def _accrocher_ponctuation(mots: list[Mot]) -> list[Mot]:
    """« ? », « ! », « : »… ne partent jamais seuls à la ligne : collés au mot précédent (espace fine)."""
    res: list[Mot] = []
    for m in mots:
        if res and m.texte in PONCTUATION_HAUTE:
            if res[-1].style == "encadre":
                res.append(Mot(m.texte, "normal", True))   # hors de la boîte dorée, petite espace
            else:
                res[-1] = Mot(res[-1].texte + "\u202f" + m.texte, res[-1].style, res[-1].colle, res[-1].groupe)
        else:
            res.append(m)
    return res


def analyser_titre(titre: str) -> list[Mot]:
    titre = typo_fr(titre)
    mots: list[Mot] = []
    fin_precedente = " "
    for bloc in re.finditer(r"\[([^\]]+)\]|\*([^*]+)\*|([^\[\]*]+)", titre):
        if bloc.group(1):
            style, contenu = "encadre", bloc.group(1)
        elif bloc.group(2):
            style, contenu = "or", bloc.group(2)
        else:
            style, contenu = "normal", bloc.group(3)
        # un encadré de plusieurs mots reste un seul bloc doré (jamais coupé en deux boîtes)
        morceaux = [" ".join(contenu.split())] if style == "encadre" else contenu.split()
        groupe = bloc.start() if style == "or" else -1
        for i, m in enumerate(morceaux):
            colle = bool(i == 0 and mots and not contenu[:1].isspace() and not fin_precedente[-1:].isspace())
            mots.append(Mot(m.upper(), style, colle, groupe))
        fin_precedente = contenu
    return _accrocher_ponctuation(mots)


def _couper_lignes(mots: list[Mot], police, largeur_max: int, espace: int, marge_box: int) -> list[list[Mot]]:
    lignes, courante, larg = [], [], 0
    for m in mots:
        lm = police.getlength(m.texte) + (2 * marge_box if m.style == "encadre" else 0)
        ajout = lm if not courante else lm + (0 if m.colle else espace)
        if courante and larg + ajout > largeur_max and not m.colle:
            lignes.append(courante)
            courante, larg = [m], lm
        else:
            courante.append(m)
            larg += ajout
    if courante:
        lignes.append(courante)
    return lignes


def _score_lignes(largeurs: list[float], nb_mots_derniere: int, nb_mots: int,
                  fins: list[str] | None = None) -> float:
    """Plus c'est bas, mieux c'est : lignes de longueurs proches, pas de mot seul en dernière ligne,
    pas de petit mot (à, de, on, le…) abandonné en fin de ligne."""
    veuve = 1000 if (len(largeurs) > 1 and nb_mots_derniere == 1 and nb_mots > 2) else 0
    petits = sum(400 for f in (fins or [])[:-1] if len(f.strip("…,.’'").replace("\u202f", "")) <= 2)
    return veuve + petits + (max(largeurs) - min(largeurs))


def _lignes_equilibrees(mots, police, largeur_max, espace, marge_box, lignes_max: int = 4):
    base = _couper_lignes(mots, police, largeur_max, espace, marge_box)
    if len(base) < 2:
        return base

    def larg(ligne):
        return (sum(police.getlength(m.texte) + (2 * marge_box if m.style == "encadre" else 0) for m in ligne)
                + espace * sum(1 for m in ligne[1:] if not m.colle))

    def fins(ls):
        return [l[-1].texte for l in ls]

    meilleur, meilleur_score = base, _score_lignes([larg(l) for l in base], len(base[-1]), len(mots), fins(base))
    for pct in range(97, 55, -3):
        essai = _couper_lignes(mots, police, largeur_max * pct / 100, espace, marge_box)
        if len(essai) not in (len(base), len(base) + 1) or len(essai) > lignes_max:
            continue
        sc = _score_lignes([larg(l) for l in essai], len(essai[-1]), len(mots), fins(essai))
        sc += 250 * (len(essai) - len(base))   # une ligne de plus seulement si ça évite un vrai défaut
        if sc < meilleur_score:
            meilleur, meilleur_score = essai, sc
    return meilleur


PETITS_MOTS = {"À", "A", "AU", "DE", "DU", "LE", "LA", "LES", "UN", "UNE", "ET", "OU", "EN", "ON", "Y", "SE", "NE",
               "CE", "SA", "SON", "SES", "DES", "QUE", "QUI", "TU", "IL", "JE", "MA", "MON", "TA", "TON", "PAR",
               "SUR", "POUR", "AVEC", "D’", "L’", "QU’"}


def _coupure_optimale(mots: list[Mot], police, largeur_max: float, espace: int, marge_box: int,
                      lignes_max: int) -> list[list[Mot]] | None:
    """Coupure des lignes comme un typographe : on teste toutes les coupures possibles et on garde la meilleure.
    Pénalités : petit mot (à, de, on…) en fin de ligne, mot seul en dernière ligne, lignes trop inégales,
    ligne qui commence par une ponctuation ; bonus pour une coupure après « … , ? ! : »."""
    n = len(mots)
    largeurs = [police.getlength(m.texte) + (2 * marge_box if m.style == "encadre" else 0) for m in mots]

    def larg(i, j):  # mots i..j-1
        return sum(largeurs[i:j]) + espace * sum(1 for m in mots[i + 1:j] if not m.colle)

    INF = float("inf")
    # meilleur[k][j] = (coût, coupure précédente) pour j premiers mots en k lignes
    meilleur = [[(INF, -1)] * (n + 1) for _ in range(lignes_max + 1)]
    meilleur[0][0] = (0, -1)
    for k in range(1, lignes_max + 1):
        for j in range(1, n + 1):
            if j < n and mots[j].colle:      # on ne coupe jamais avant une ponctuation collée
                continue
            for i in range(j - 1, -1, -1):
                w = larg(i, j)
                if w > largeur_max:
                    break
                prec = meilleur[k - 1][i][0]
                if prec == INF:
                    continue
                cout = ((largeur_max * 0.92 - w) / 10) ** 2 * (0.4 if j == n else 1)
                fin = mots[j - 1].texte.replace("\u202f", "")
                if j < n:
                    if fin.rstrip("…,.!?:") in PETITS_MOTS:
                        cout += 900
                    if mots[j - 1].groupe >= 0 and mots[j - 1].groupe == mots[j].groupe:
                        cout += 1100             # ne pas couper « PIEDS / HUMAINS »
                    if fin[-1:] in "…,!?:":
                        cout -= 250
                elif j - i == 1 and n > 2:
                    cout += 1200                 # mot seul en dernière ligne
                total = prec + cout + 120        # légère préférence pour moins de lignes
                if total < meilleur[k][j][0]:
                    meilleur[k][j] = (total, i)
    k_best = min(range(1, lignes_max + 1), key=lambda k: meilleur[k][n][0])
    if meilleur[k_best][n][0] == INF:
        return None
    lignes, j, k = [], n, k_best
    while j > 0:
        i = meilleur[k][j][1]
        lignes.append(mots[i:j]); j, k = i, k - 1
    _coupure_optimale.dernier_cout = meilleur[k_best][n][0]
    return lignes[::-1]


def dessiner_titre(img: Image.Image, titre: str, cfg: dict, *, bas: int, taille_max: int,
                   lignes_max: int = 4, largeur_max: int | None = None, centre: bool = True) -> int:
    """Dessine le titre balisé centré, aligné pour que sa dernière ligne finisse à `bas`.
    Renvoie la coordonnée y du haut du bloc."""
    st = cfg["style"]
    l, _ = img.size
    largeur_max = largeur_max or int(l * 0.86)
    mots = analyser_titre(titre)
    # On essaie plusieurs tailles : une taille un peu plus petite est acceptée si elle donne
    # des coupures nettement plus belles (ex. « IL Y A 30 ANS, / ON TROUVAIT ÇA NORMAL »).
    meilleur_choix = None
    taille = taille_max
    while taille >= 40:
        police = _police(st["police_titre"], taille)
        espace = int(taille * 0.22)
        marge_box = int(taille * 0.12)
        essai = _coupure_optimale(mots, police, largeur_max, espace, marge_box, lignes_max)
        if essai is not None:
            cout = _coupure_optimale.dernier_cout + (taille_max - taille) * 55
            if meilleur_choix is None or cout < meilleur_choix[0]:
                meilleur_choix = (cout, taille, essai)
            if taille < taille_max * 0.84:
                break
        taille -= 4
    if meilleur_choix is None:
        taille = 40
        police = _police(st["police_titre"], taille)
        espace, marge_box = int(taille * 0.22), int(taille * 0.12)
        lignes = _lignes_equilibrees(mots, police, largeur_max, espace, marge_box, lignes_max)
    else:
        _, taille, lignes = meilleur_choix
        police = _police(st["police_titre"], taille)
        espace, marge_box = int(taille * 0.22), int(taille * 0.12)
    # Hauteur des capitales (sans accents) : toutes les boîtes ont la même hauteur, alignées sur la ligne.
    cap_haut, cap_bas = police.getbbox("H")[1], police.getbbox("H")[3]
    pad_v = int(taille * 0.09)
    a_boite = any(m.style == "encadre" for m in mots)
    # interligne : assez d'air pour que boîtes, accents et cédilles ne touchent jamais la ligne voisine
    interligne = int(taille * (1.24 if a_boite else 1.12))
    haut = bas - interligne * (len(lignes) - 1) - cap_bas - pad_v
    d = ImageDraw.Draw(img)
    or_ = _hex(st["couleur_accent"])
    blanc = _hex(st["couleur_texte"])
    noir = _hex(st["couleur_texte_encadre"])

    def positions(ligne):
        larg = sum(police.getlength(m.texte) + (2 * marge_box if m.style == "encadre" else 0) for m in ligne)
        larg += espace * sum(1 for m in ligne[1:] if not m.colle)
        x = (l - larg) / 2 if centre else (l - largeur_max) / 2
        res = []
        for i, m in enumerate(ligne):
            if m.colle and i > 0:
                x -= espace - (int(taille * 0.12) if m.texte in PONCTUATION_HAUTE else 0)
            lm = police.getlength(m.texte)
            largeur_mot = lm + (2 * marge_box if m.style == "encadre" else 0)
            res.append((m, x, lm))
            x += largeur_mot + espace
        return res

    # passe 1 : les boîtes dorées (sous tout le texte)
    y = haut
    for ligne in lignes:
        for m, x, lm in positions(ligne):
            if m.style == "encadre":
                d.rounded_rectangle([x, y + cap_haut - pad_v, x + lm + 2 * marge_box, y + cap_bas + pad_v],
                                    radius=int(taille * 0.07), fill=or_)
        y += interligne
    # passe 2 : ombres puis textes
    y = haut
    for ligne in lignes:
        for m, x, lm in positions(ligne):
            if m.style == "encadre":
                d.text((x + marge_box, y), m.texte, font=police, fill=noir)
            else:
                d.text((x + 3, y + 4), m.texte, font=police, fill=(0, 0, 0))
                d.text((x, y), m.texte, font=police, fill=or_ if m.style == "or" else blanc)
        y += interligne
    return haut


def dessiner_texte_paragraphe(img: Image.Image, texte: str, cfg: dict, *, haut: int, taille: int = 38,
                              largeur_max: int | None = None, couleur: str | None = None) -> int:
    """Paragraphe en Montserrat, centré. Les *mots* sont en doré. Renvoie le y de fin."""
    st = cfg["style"]
    l, _ = img.size
    largeur_max = largeur_max or int(l * 0.84)
    police = _police(st["police_texte"], taille, "SemiBold")
    police_g = _police(st["police_texte"], taille, "ExtraBold")
    texte = typo_fr(texte)
    brut = re.finditer(r"\*([^*]+)\*|([^*]+)", texte)
    mots = []
    fin_precedente = " "
    for b in brut:
        style, contenu = ("or", b.group(1)) if b.group(1) else ("normal", b.group(2))
        for i, w in enumerate(contenu.split()):
            # collé au mot précédent seulement s'il n'y avait vraiment aucun espace (« *bon*. »)
            colle = bool(i == 0 and mots and not contenu[:1].isspace() and not fin_precedente[-1:].isspace())
            mots.append(Mot(w, style, colle))
        fin_precedente = contenu
    mots = _accrocher_ponctuation(mots)
    espace = max(int(taille * 0.30), int(police.getlength(" ")) + 2)

    def couper(lmax):
        res, cour, larg = [], [], 0
        for m in mots:
            lm = (police_g if m.style == "or" else police).getlength(m.texte)
            esp = 0 if m.colle else espace
            if cour and larg + esp + lm > lmax and not m.colle:
                res.append(cour); cour, larg = [m], lm
            else:
                larg += (esp if cour else 0) + lm; cour.append(m)
        if cour:
            res.append(cour)
        return res

    def largeur(ligne):
        return (sum((police_g if m.style == "or" else police).getlength(m.texte) for m in ligne)
                + espace * sum(1 for m in ligne[1:] if not m.colle))

    lignes = couper(largeur_max)
    if len(lignes) > 1:
        meilleur = _score_lignes([largeur(x) for x in lignes], len(lignes[-1]), len(mots), [x[-1].texte for x in lignes])
        for pct in range(97, 60, -3):
            essai = couper(largeur_max * pct / 100)
            if len(essai) != len(lignes):
                continue
            sc = _score_lignes([largeur(x) for x in essai], len(essai[-1]), len(mots), [x[-1].texte for x in essai])
            if sc < meilleur:
                lignes, meilleur = essai, sc
    d = ImageDraw.Draw(img)
    y = haut
    inter = int(taille * 1.35)
    for ligne in lignes:
        x = (l - largeur(ligne)) / 2
        for i, m in enumerate(ligne):
            if m.colle and i > 0:
                x -= espace
            p = police_g if m.style == "or" else police
            c = _hex(st["couleur_accent"]) if m.style == "or" else _hex(couleur or st["couleur_texte"])
            d.text((x + 2, y + 3), m.texte, font=p, fill=(0, 0, 0))
            d.text((x, y), m.texte, font=p, fill=c)
            x += p.getlength(m.texte) + espace
        y += inter
    return y


def dessiner_entete(img: Image.Image, cfg: dict, y: int = 46) -> None:
    """Nom du compte en petit, centré en haut, lettres espacées (+ signature)."""
    st = cfg["style"]
    l, _ = img.size
    nom = cfg["compte"]["nom"].upper()
    police = _police(st["police_texte"], 26, "Bold")
    espacement = 7
    largeur = sum(police.getlength(c) for c in nom) + espacement * (len(nom) - 1)
    x = (l - largeur) / 2
    d = ImageDraw.Draw(img)
    for c in nom:
        d.text((x + 1, y + 2), c, font=police, fill=(0, 0, 0))
        d.text((x, y), c, font=police, fill=(255, 255, 255))
        x += police.getlength(c) + espacement
    if st.get("signature") == "bande":
        lb = 46
        d.rectangle([(l - lb) / 2, y + 40, (l + lb) / 2, y + 43], fill=_hex(st["couleur_accent"]))


def dessiner_fleche(img: Image.Image, cfg: dict) -> None:
    """Petite flèche cerclée en bas à droite : invite à swiper."""
    l, h = img.size
    d = ImageDraw.Draw(img)
    r = 26
    cx, cy = l - 58, h - 58
    or_ = _hex(cfg["style"]["couleur_accent"])
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=or_, width=4)
    d.line([cx - 11, cy, cx + 10, cy], fill=or_, width=5)
    d.line([cx + 2, cy - 9, cx + 11, cy], fill=or_, width=5)
    d.line([cx + 2, cy + 9, cx + 11, cy], fill=or_, width=5)


# ------------------------------------------------------------------ blocs mesurés
# Chaque texte est d'abord rendu sur un calque transparent puis recadré au pixel près
# (accents, cédilles, ombres compris). Les blocs sont ensuite empilés avec des espacements
# exacts : aucun chevauchement possible, quelle que soit la longueur du texte.

MARGE_BAS = 112      # reste au-dessus de la zone des points du carrousel et de la flèche
ECART = 30           # espace entre deux blocs de texte


def _recadrer(calque: Image.Image) -> tuple[Image.Image, int]:
    bb = calque.getbbox() or (0, 0, 1, 1)
    return calque.crop(bb), bb[0]


def bloc_titre(titre: str, cfg: dict, largeur: int, taille_max: int, lignes_max: int) -> tuple[Image.Image, int]:
    calque = Image.new("RGBA", (largeur, 1800), (0, 0, 0, 0))
    dessiner_titre(calque, titre, cfg, bas=1700, taille_max=taille_max, lignes_max=lignes_max)
    return _recadrer(calque)


def bloc_texte(texte: str, cfg: dict, largeur: int, taille: int) -> tuple[Image.Image, int]:
    calque = Image.new("RGBA", (largeur, 1200), (0, 0, 0, 0))
    dessiner_texte_paragraphe(calque, texte, cfg, haut=60, taille=taille)
    return _recadrer(calque)


def bloc_numero(numero: str, cfg: dict) -> tuple[Image.Image, int]:
    p = _police(cfg["style"]["police_titre"], 52)
    bb = p.getbbox(numero)
    lt, ht = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = 24, 14
    calque = Image.new("RGBA", (lt + 2 * pad_x, ht + 2 * pad_y), (0, 0, 0, 0))
    d = ImageDraw.Draw(calque)
    d.rounded_rectangle([0, 0, calque.width - 1, calque.height - 1], radius=14, fill=_hex(cfg["style"]["couleur_accent"]))
    d.text((pad_x - bb[0], pad_y - bb[1]), numero, font=p, fill=_hex(cfg["style"]["couleur_texte_encadre"]))
    return calque, -1  # -1 = à centrer


def empiler_bas(img: Image.Image, blocs: list, bas: int, ecarts: list[int] | None = None) -> int:
    """Empile des blocs du bas vers le haut, centrés. Renvoie le y du haut du dernier bloc posé."""
    l = img.width
    y = bas
    ecarts = ecarts or [ECART] * len(blocs)
    for (bloc, x), ecart in zip(reversed(blocs), reversed(ecarts)):
        y -= bloc.height
        xx = (l - bloc.width) // 2 if x < 0 else x
        img.alpha_composite(bloc, (int(xx), int(y)))
        y -= ecart
    return y + ecarts[0]


def _assombrir_sous_le_texte(img: Image.Image, haut_texte: int, base: float) -> None:
    """Dégradé qui démarre toujours au moins 220 px au-dessus du texte le plus haut."""
    l, h = img.size
    part = min(0.9, max(base, (h - haut_texte + 220) / h))
    img.alpha_composite(degrade_bas((l, h), part))


# ------------------------------------------------------------------ slides


def slide_couverture(fond: Image.Image, titre: str, cfg: dict, sous_titre: str | None = None) -> Image.Image:
    taille = tuple(cfg["style"]["format"])
    l, h = taille
    img = ajuster_cadre(fond, taille).convert("RGBA")
    blocs = [bloc_titre(titre, cfg, l, taille_max=112, lignes_max=4)]
    ecarts = [0]
    if sous_titre:
        blocs.append(bloc_texte(sous_titre, cfg, l, taille=40))
        ecarts.append(ECART)
    hauteur = sum(b.height for b, _ in blocs) + sum(ecarts)
    _assombrir_sous_le_texte(img, h - MARGE_BAS - hauteur, cfg["style"]["hauteur_degrade"])
    img.alpha_composite(degrade_haut(taille))
    dessiner_entete(img, cfg)
    empiler_bas(img, blocs, h - MARGE_BAS, ecarts)
    dessiner_fleche(img, cfg)
    return img.convert("RGB")


def slide_contenu(fond: Image.Image, titre: str, texte: str, cfg: dict, numero: str | None = None,
                  fleche: bool = True) -> Image.Image:
    taille = tuple(cfg["style"]["format"])
    l, h = taille
    img = ajuster_cadre(fond, taille).convert("RGBA")
    blocs, ecarts = [], []
    if numero:
        blocs.append(bloc_numero(numero, cfg)); ecarts.append(0)
    blocs.append(bloc_titre(titre, cfg, l, taille_max=88, lignes_max=3)); ecarts.append(24 if numero else 0)
    blocs.append(bloc_texte(texte, cfg, l, taille=40)); ecarts.append(26)
    hauteur = sum(b.height for b, _ in blocs) + sum(ecarts)
    _assombrir_sous_le_texte(img, h - MARGE_BAS - hauteur, 0.6)
    img.alpha_composite(degrade_haut(taille))
    dessiner_entete(img, cfg)
    empiler_bas(img, blocs, h - MARGE_BAS, ecarts)
    if fleche:
        dessiner_fleche(img, cfg)
    return img.convert("RGB")


def slide_fin(fond: Image.Image, cfg: dict, question: str) -> Image.Image:
    """Dernière slide : question pour les commentaires, appels à l'action, abonnement."""
    taille = tuple(cfg["style"]["format"])
    l, h = taille
    img = ajuster_cadre(fond, taille).filter(ImageFilter.GaussianBlur(16)).convert("RGBA")
    img.alpha_composite(Image.new("RGBA", taille, (0, 0, 0, 175)))
    dessiner_entete(img, cfg)

    # bas : abonnement + pseudo
    pseudo = cfg["compte"].get("pseudo", "")
    bas_blocs = [bloc_titre(f"ABONNE-TOI À [{cfg['compte']['nom']}]", cfg, l, taille_max=74, lignes_max=2)]
    bas_ecarts = [0]
    if pseudo:
        bas_blocs.append(bloc_texte(f"*@{pseudo}*", cfg, l, taille=36)); bas_ecarts.append(18)
    haut_bas = empiler_bas(img, bas_blocs, h - MARGE_BAS, bas_ecarts)

    # centre : question + invitation à commenter + enregistrer / partager, centrés verticalement
    centre = [bloc_titre(question, cfg, l, taille_max=100, lignes_max=4),
              bloc_texte("Dis-le en *commentaire*", cfg, l, taille=44),
              bloc_texte("*Enregistre* ce post  •  *Partage-le* à un ami", cfg, l, taille=34)]
    ecarts = [0, 34, 56]
    hauteur = sum(b.height for b, _ in centre) + sum(ecarts)
    zone_haut, zone_bas = 150, haut_bas - 90
    bas_centre = zone_haut + (zone_bas - zone_haut + hauteur) // 2
    empiler_bas(img, centre, bas_centre, ecarts)
    return img.convert("RGB")


# ------------------------------------------------------------------ fonds d'aperçu (sans IA)


def fond_apercu(graine: str, taille=(1080, 1350), libelle: str | None = None) -> Image.Image:
    """Fond procédural cinématique pour tester la mise en page sans clé API."""
    rnd = random.Random(graine)
    palettes = [((18, 32, 64), (210, 120, 40)), ((10, 40, 45), (90, 200, 190)), ((40, 15, 50), (230, 90, 120)),
                ((20, 20, 20), (240, 190, 60)), ((15, 35, 20), (150, 210, 90)), ((50, 25, 10), (250, 160, 90))]
    c1, c2 = rnd.choice(palettes)
    l, h = taille
    img = Image.new("RGB", taille, c1)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (l, y)], fill=tuple(int(c1[i] * (1 - t * 0.6) + c2[i] * t * 0.35) for i in range(3)))
    calque = Image.new("RGB", taille, (0, 0, 0))
    dc = ImageDraw.Draw(calque)
    for _ in range(26):
        r = rnd.randint(40, 260)
        x, y = rnd.randint(0, l), rnd.randint(0, int(h * 0.8))
        teinte = tuple(min(255, int(c2[i] * rnd.uniform(0.6, 1.2))) for i in range(3))
        dc.ellipse([x - r, y - r, x + r, y + r], fill=teinte)
    calque = calque.filter(ImageFilter.GaussianBlur(70))
    img = Image.blend(img, calque, 0.55)
    if libelle:
        d = ImageDraw.Draw(img)
        p = _police("assets/fonts/Montserrat.ttf", 30, "Medium")
        lm = p.getlength(libelle)
        d.text(((l - lm) / 2, h * 0.30), libelle, font=p, fill=(255, 255, 255, 180))
    return img


def enregistrer_jpeg(img: Image.Image, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(chemin, "JPEG", quality=88, optimize=True, progressive=True)
    return chemin
