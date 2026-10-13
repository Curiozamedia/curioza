"""Génère le logo CURIOZA (photo de profil Instagram) en plusieurs variantes."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

T = 1080
OR_CLAIR, OR_FONCE = (0xF4, 0xB4, 0x00), (0xF4, 0xB4, 0x00)  # même jaune doré que les posts (#F4B400)


def degrade_or(taille):
    g = Image.new("RGB", (1, taille))
    for y in range(taille):
        t = y / taille
        g.putpixel((0, y), tuple(int(OR_CLAIR[i] * (1 - t) + OR_FONCE[i] * t) for i in range(3)))
    return g.resize((taille, taille))


def logo(police, variation, sortie, taille_lettre=640, decalage=(0, 0), anneau=True, point=False):
    img = Image.new("RGB", (T, T), (0, 0, 0))
    d = ImageDraw.Draw(img)
    # fond : noir profond avec léger halo central
    halo = Image.new("L", (T, T), 0)
    ImageDraw.Draw(halo).ellipse([200, 200, T - 200, T - 200], fill=40)
    img.paste((30, 26, 18), mask=halo.filter(ImageFilter.GaussianBlur(160)))
    masque = Image.new("L", (T, T), 0)
    dm = ImageDraw.Draw(masque)
    if anneau:  # fin cercle doré intérieur, visible dans la découpe ronde d'Instagram
        dm.ellipse([110, 110, T - 110, T - 110], outline=255, width=10)
    f = ImageFont.truetype(f"assets/fonts/{police}", taille_lettre)
    try:
        f.set_variation_by_name(variation)
    except Exception:
        pass
    bb = dm.textbbox((0, 0), "C", font=f)
    x = (T - (bb[2] - bb[0])) / 2 - bb[0] + decalage[0]
    y = (T - (bb[3] - bb[1])) / 2 - bb[1] + decalage[1]
    dm.text((x, y), "C", font=f, fill=255)
    if point:  # petit point doré : la "curiosité" (comme le point d'un ?)
        bt = dm.textbbox((x, y), "C", font=f)
        cx, cy = bt[2] + 48, bt[3] - 30
        dm.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=255)
    ombre = masque.filter(ImageFilter.GaussianBlur(18))
    img.paste((70, 50, 10), mask=ombre.point(lambda v: v // 2))
    img.paste(degrade_or(T), mask=masque)
    img.save(sortie, quality=95)
    return sortie


if __name__ == "__main__":
    logo("Cinzel.ttf", "Bold", "assets/logo/curioza-logo-1.png", 660, (0, -10))
    logo("PlayfairDisplay.ttf", "Bold", "assets/logo/curioza-logo-2.png", 700, (0, -30))
    logo("Cinzel.ttf", "Bold", "assets/logo/curioza-logo-3.png", 600, (-45, -10), point=True)
    logo("PlayfairDisplay.ttf", "Bold", "assets/logo/curioza-logo-4.png", 660, (-40, -30), point=True)
