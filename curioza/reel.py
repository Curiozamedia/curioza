"""Montage automatique des Reels (ffmpeg).

Deux formats :
  - devinette : décor IA + opération écrite au marqueur + bandeau d'accroche en haut (style Opulancia)
  - diaporama : les slides d'un carrousel en vidéo, avec léger zoom (réutilise les images, coût 0)
Musique : un fichier au hasard dans assets/musique/ (musique libre de droits que tu ajoutes),
sinon une nappe d'ambiance synthétisée (libre de droits par construction).
"""
from __future__ import annotations

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import rendu
from .config import RACINE

FPS = 30


def _ffmpeg(*args: str) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    subprocess.run(cmd, check=True)


def _musique(duree: float, graine: str, dossier: Path) -> Path:
    pistes = sorted((RACINE / "assets" / "musique").glob("*.mp3"))
    sortie = dossier / "audio.m4a"
    if pistes:
        piste = random.Random(graine).choice(pistes)
        _ffmpeg("-i", str(piste), "-t", f"{duree}", "-af",
                f"afade=t=in:d=0.5,afade=t=out:st={duree - 1.2}:d=1.2,volume=0.8", "-c:a", "aac", "-b:a", "160k", str(sortie))
        return sortie
    # nappe synthétique : accord doux + pulsation lente
    rnd = random.Random(graine)
    base = rnd.choice([110.0, 123.47, 130.81, 146.83])
    freqs = [base, base * 1.5, base * 2, base * 2.52]
    entrees = []
    for f in freqs:
        entrees += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={duree}"]
    filtre = (f"amix=inputs={len(freqs)}:normalize=1,lowpass=f=900,tremolo=f=0.25:d=0.35,"
              f"afade=t=in:d=1.5,afade=t=out:st={duree - 1.5}:d=1.5,volume=0.9")
    _ffmpeg(*entrees, "-filter_complex", filtre, "-c:a", "aac", "-b:a", "128k", str(sortie))
    return sortie


# Mise en page des Reels devinettes (comme Opulancia) :
#   bande noire en haut (nom + accroche) / image pleine largeur au centre / bande noire en bas (appel à commenter)
HAUT_NOIR = 600
BAS_NOIR = 440


def _police_marqueur(taille: int):
    from PIL import ImageFont
    return ImageFont.truetype(str(RACINE / "assets/fonts/PermanentMarker-Regular.ttf"), taille)


def composer_devinette(fond: Image.Image, d: dict, cfg: dict) -> tuple[Image.Image, Image.Image]:
    """Renvoie (cadre, zone) : le cadre noir 1080x1920 avec les textes, et l'image centrale avec l'opération."""
    l, h = cfg["style"]["format_reel"]
    zone_taille = (l, h - HAUT_NOIR - BAS_NOIR)

    # --- image centrale : décor IA plein cadre + opération au marqueur
    zone = rendu.ajuster_cadre(fond, zone_taille).convert("RGBA")
    taille = 150
    police = _police_marqueur(taille)
    texte = d["expression"]
    while police.getlength(texte) > l * 0.78 and taille > 60:
        taille -= 6
        police = _police_marqueur(taille)
    lm = police.getlength(texte)
    cy = zone_taille[1] / 2
    halo = Image.new("RGBA", zone_taille, (0, 0, 0, 0))
    ImageDraw.Draw(halo).rounded_rectangle(
        [(l - lm) / 2 - 50, cy - taille * 0.75, (l + lm) / 2 + 50, cy + taille * 0.85],
        radius=40, fill=(255, 255, 255, 220))
    zone.alpha_composite(halo.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(zone).text(((l - lm) / 2, cy - taille * 0.62), texte, font=police, fill=(20, 20, 30))

    # --- cadre noir : accroche en haut, appel à commenter en bas
    cadre = Image.new("RGBA", (l, h), (0, 0, 0, 255))
    rendu.dessiner_entete(cadre, cfg, y=170)
    rendu.dessiner_titre(cadre, d["bandeau"], cfg, bas=HAUT_NOIR - 50, taille_max=92, lignes_max=3)
    rendu.dessiner_texte_paragraphe(cadre, "Ta réponse en *commentaire*", cfg, haut=h - BAS_NOIR + 60, taille=46)
    return cadre, zone.convert("RGB")


def image_devinette(fond: Image.Image, d: dict, cfg: dict) -> Image.Image:
    """Image fixe complète (couverture du Reel)."""
    cadre, zone = composer_devinette(fond, d, cfg)
    img = cadre.copy()
    img.paste(zone, (0, HAUT_NOIR))
    return img.convert("RGB")


def _avec_musique(cfg: dict) -> bool:
    return cfg.get("reels_publication", "manuel") == "auto"


def video_devinette(fond: Image.Image, d: dict, cfg: dict, sortie: Path, graine: str, duree: float = 9.0) -> Path:
    """Cadre noir fixe ; seule l'image centrale zoome doucement. Musique selon la config."""
    cadre, zone = composer_devinette(fond, d, cfg)
    l, h = cfg["style"]["format_reel"]
    zl, zh = zone.size
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f_cadre, f_zone = tmp / "cadre.png", tmp / "zone.png"
        cadre.convert("RGB").save(f_cadre)
        zone.save(f_zone)
        n = int(duree * FPS)
        filtre = (f"[1:v]scale={zl * 2}:-1,zoompan=z='min(1+0.07*on/{n},1.07)':x='iw/2-(iw/zoom/2)'"
                  f":y='ih/2-(ih/zoom/2)':d={n}:s={zl}x{zh}:fps={FPS}[z];"
                  f"[0:v][z]overlay=0:{HAUT_NOIR},format=yuv420p[v]")
        sortie.parent.mkdir(parents=True, exist_ok=True)
        if _avec_musique(cfg):
            audio = ["-i", str(_musique(duree, graine, tmp))]
        else:  # piste muette : le son tendance sera ajouté dans l'app Instagram
            audio = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        _ffmpeg("-loop", "1", "-framerate", str(FPS), "-i", str(f_cadre), "-loop", "1", "-i", str(f_zone), *audio,
                "-filter_complex", filtre, "-map", "[v]", "-map", "2:a", "-t", f"{duree}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-r", str(FPS),
                "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(sortie))
    return sortie


def video_diaporama(slides: list[Path], cfg: dict, sortie: Path, graine: str, par_slide: float = 2.4) -> Path:
    """Les slides 4:5 posées sur un fond flou 9:16, enchaînées avec un léger zoom."""
    l, h = cfg["style"]["format_reel"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        segments = []
        n = int(par_slide * FPS)
        for i, s in enumerate(slides):
            im = Image.open(s).convert("RGB")
            fond = rendu.ajuster_cadre(im, (l, h)).filter(ImageFilter.GaussianBlur(30))
            fond = Image.blend(fond, Image.new("RGB", (l, h)), 0.35)
            larg = l
            haut = int(im.height * larg / im.width)
            fond.paste(im.resize((larg, haut)), (0, (h - haut) // 2))
            cadre = tmp / f"cadre{i}.png"
            fond.save(cadre)
            seg = tmp / f"seg{i}.mp4"
            filtre = (f"scale=2160:-1,zoompan=z='1+0.04*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d={n}:s={l}x{h}:fps={FPS},format=yuv420p")
            _ffmpeg("-loop", "1", "-i", str(cadre), "-vf", filtre, "-t", f"{par_slide}", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "20", str(seg))
            segments.append(seg)
        liste = tmp / "liste.txt"
        liste.write_text("".join(f"file '{p}'\n" for p in segments))
        video = tmp / "video.mp4"
        _ffmpeg("-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(video))
        duree = par_slide * len(slides)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        if _avec_musique(cfg):
            audio = ["-i", str(_musique(duree, graine, tmp))]
        else:
            audio = ["-f", "lavfi", "-t", f"{duree}", "-i", "anullsrc=r=44100:cl=stereo"]
        _ffmpeg("-i", str(video), *audio, "-c:v", "copy", "-c:a", "aac", "-shortest",
                "-movflags", "+faststart", str(sortie))
    return sortie


def calque_accroche(accroche: str, cfg: dict) -> Image.Image:
    """Accroche du Reel vidéo : en haut, dans la zone sûre d'Instagram, avec un dégradé sombre pour la lisibilité."""
    l, h = cfg["style"]["format_reel"]
    calque = Image.new("RGBA", (l, h), (0, 0, 0, 0))
    calque.alpha_composite(rendu.degrade_haut((l, h), part=0.36, opacite_max=200))
    rendu.dessiner_entete(calque, cfg, y=150)
    bloc, _ = rendu.bloc_titre(accroche, cfg, l, taille_max=86, lignes_max=3, taille_min=74)
    calque.alpha_composite(bloc, ((l - bloc.width) // 2, 260))
    return calque


def _detecter_bandes(clip: Path) -> str:
    """Renvoie un filtre « crop=…, » qui enlève les bandes noires détectées (ou une chaîne vide)."""
    import re
    r = subprocess.run(["ffmpeg", "-i", str(clip), "-vf", "cropdetect=24:2:0", "-t", "4", "-f", "null", "-"],
                       capture_output=True, text=True)
    trouves = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not trouves:
        return ""
    w, hh, x, y = map(int, trouves[-1])
    return f"crop={w}:{hh}:{x}:{y}," if w > 100 and hh > 100 else ""


def video_ia(clips: list[Path], accroche: str, cfg: dict, sortie: Path) -> Path:
    """Enchaîne les plans vidéo IA (9:16), ajoute l'accroche en haut et une piste muette
    (le son tendance est choisi dans l'app Instagram)."""
    l, h = cfg["style"]["format_reel"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        normes = []
        for i, c in enumerate(clips):
            n = tmp / f"n{i}.mp4"
            # retire d'éventuelles bandes noires incrustées par le modèle vidéo, puis remplit tout l'écran 9:16
            rogne = _detecter_bandes(Path(c))
            _ffmpeg("-i", str(c), "-vf", f"{rogne}scale={l}:{h}:force_original_aspect_ratio=increase,crop={l}:{h},fps={FPS},format=yuv420p",
                    "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19", str(n))
            normes.append(n)
        liste = tmp / "liste.txt"
        liste.write_text("".join(f"file '{p}'\n" for p in normes))
        brut = tmp / "brut.mp4"
        _ffmpeg("-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(brut))
        texte = tmp / "accroche.png"
        calque_accroche(accroche, cfg).save(texte)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg("-i", str(brut), "-i", str(texte), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", "[0:v][1:v]overlay=0:0,format=yuv420p[v]", "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-shortest",
                "-movflags", "+faststart", str(sortie))
    return sortie


def calques_devinette_scene(d: dict, cfg: dict) -> Image.Image:
    """Textes posés sur la scène plein cadre : nom + accroche en haut, appel à commenter en bas, sur dégradés."""
    l, h = cfg["style"]["format_reel"]
    calque = Image.new("RGBA", (l, h), (0, 0, 0, 0))
    calque.alpha_composite(rendu.degrade_haut((l, h), part=0.34, opacite_max=215))
    calque.alpha_composite(rendu.degrade_bas((l, h), 0.22, opacite_max=220))
    rendu.dessiner_entete(calque, cfg, y=150)
    bloc, _ = rendu.bloc_titre(d["bandeau"], cfg, l, taille_max=86, lignes_max=3, taille_min=74)
    calque.alpha_composite(bloc, ((l - bloc.width) // 2, 260))
    bas, _ = rendu.bloc_texte("Ta réponse en *commentaire* 👇".replace("👇", ""), cfg, l, taille=46)
    calque.alpha_composite(bas, ((l - bas.width) // 2, h - 300))
    return calque


def image_devinette_scene(scene: Image.Image, d: dict, cfg: dict) -> Image.Image:
    l, h = cfg["style"]["format_reel"]
    img = rendu.ajuster_cadre(scene, (l, h)).convert("RGBA")
    img.alpha_composite(calques_devinette_scene(d, cfg))
    return img.convert("RGB")


def video_devinette_scene(scene: Image.Image, d: dict, cfg: dict, sortie: Path, duree: float = 9.0) -> Path:
    """La scène zoome lentement vers l'opération ; les textes restent fixes."""
    l, h = cfg["style"]["format_reel"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        f_scene, f_textes = tmp / "scene.png", tmp / "textes.png"
        rendu.ajuster_cadre(scene, (l, h)).convert("RGB").save(f_scene)
        calques_devinette_scene(d, cfg).save(f_textes)
        n = int(duree * FPS)
        filtre = (f"[0:v]scale={l * 2}:-1,zoompan=z='min(1+0.10*on/{n},1.10)':x='iw/2-(iw/zoom/2)'"
                  f":y='ih/2-(ih/zoom/2)':d={n}:s={l}x{h}:fps={FPS}[z];[z][1:v]overlay=0:0,format=yuv420p[v]")
        sortie.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg("-loop", "1", "-framerate", str(FPS), "-i", str(f_scene), "-loop", "1", "-i", str(f_textes),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", filtre, "-map", "[v]", "-map", "2:a", "-t", f"{duree}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
                "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(sortie))
    return sortie
