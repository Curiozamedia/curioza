"""Génération des idées, textes de slides, prompts d'image et légendes (API Claude).

Chaque carrousel passe par deux appels :
  1. rédaction (structure Opulancia : accroche, slides, question, légende en 3 appels à l'action)
  2. relecture : vérification des faits + règles (pas de personnes réelles, pas de marques)
Sans ANTHROPIC_API_KEY, un petit jeu de contenus de démonstration est utilisé.
"""
from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path

import requests
import yaml

from .config import DOSSIER_PLANNING

PAYS_SERIE = ["Japon", "Italie", "Suisse", "Espagne", "Canada", "Allemagne", "Portugal", "Norvège", "Corée du Sud",
              "Australie", "Grèce", "Pays-Bas", "Maroc", "Islande", "Mexique", "Irlande", "Belgique", "Danemark"]


# ------------------------------------------------------------------ radar Reddit


def radar_reddit(cfg: dict) -> list[str]:
    """Titres des posts les plus populaires de la semaine (inspiration uniquement, jamais copiés)."""
    rr = cfg.get("radar_reddit", {})
    if not rr.get("actif"):
        return []
    titres: list[str] = []
    entetes = {"User-Agent": "curioza-radar/1.0 (inspiration de sujets)"}
    for sub in rr.get("subreddits", []):
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/top/.rss?t=week", headers=entetes, timeout=20)
            if r.ok:
                titres += re.findall(r"<title>([^<]{8,200})</title>", r.text)[1:12]
        except requests.RequestException:
            continue
    random.shuffle(titres)
    return titres[: rr.get("nb_titres", 40)]


# ------------------------------------------------------------------ historique


def sujets_deja_traites(limite: int = 200) -> list[str]:
    sujets = []
    for f in sorted(DOSSIER_PLANNING.glob("*.yaml"), reverse=True):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for p in data.get("posts", []):
            if p.get("sujet"):
                sujets.append(p["sujet"])
    return sujets[:limite]


def prochain_pays(recents: list[str] | None = None) -> str:
    """Un pays différent à chaque épisode : on évite tous ceux déjà vus (semaine en cours + historique)."""
    deja = [s for s in (list(recents or []) + sujets_deja_traites(500)) if "France vs" in s]
    restants = [p for p in PAYS_SERIE if not any(p in s for s in deja)]
    if restants:
        return restants[0]
    # tous faits : on reprend le pays le moins récemment traité
    dernier = {p: max((i for i, s in enumerate(reversed(deja)) if p in s), default=-1) for p in PAYS_SERIE}
    return min(PAYS_SERIE, key=lambda p: dernier[p])


# ------------------------------------------------------------------ appel Claude


def _claude(cfg: dict, systeme: str, message: str, max_tokens: int = 4000) -> str:
    import anthropic

    client = anthropic.Anthropic()
    rep = client.messages.create(
        model=cfg["ia_texte"]["modele"],
        max_tokens=max_tokens,
        system=systeme,
        messages=[{"role": "user", "content": message}],
    )
    return "".join(b.text for b in rep.content if getattr(b, "type", "") == "text")


def _json(texte: str) -> dict:
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0:
        raise ValueError("Pas de JSON dans la réponse")
    return json.loads(texte[debut:fin + 1])


_TEXTE = {"type": "string"}
SCHEMA_CARROUSEL = {
    "type": "object",
    "properties": {
        "sujet": _TEXTE, "titre_couverture": _TEXTE, "sous_titre": _TEXTE, "prompt_couverture": _TEXTE,
        "slides": {"type": "array", "items": {"type": "object", "properties": {
            "titre": _TEXTE, "texte": _TEXTE, "prompt_image": _TEXTE},
            "required": ["titre", "texte", "prompt_image"]}},
        "question_fin": _TEXTE,
        "legende": {"type": "object", "properties": {
            "accroche": _TEXTE, "developpement": _TEXTE, "teaser": _TEXTE, "question": _TEXTE,
            "raison_enregistrer": _TEXTE, "raison_partager": _TEXTE},
            "required": ["accroche", "developpement", "teaser", "question", "raison_enregistrer", "raison_partager"]},
        "hashtags": {"type": "array", "items": _TEXTE},
    },
    "required": ["sujet", "titre_couverture", "sous_titre", "prompt_couverture", "slides", "question_fin",
                 "legende", "hashtags"],
}


def _claude_json(cfg: dict, systeme: str, message: str, schema: dict, max_tokens: int = 6000) -> dict:
    """Réponse structurée garantie : Claude remplit un « outil » au schéma imposé (plus de JSON mal formé).
    3 essais en cas de souci réseau ou de réponse incomplète."""
    import anthropic
    import time

    client = anthropic.Anthropic()
    derniere = None
    for essai in range(3):
        try:
            rep = client.messages.create(
                model=cfg["ia_texte"]["modele"], max_tokens=max_tokens, system=systeme,
                tools=[{"name": "enregistrer", "description": "Enregistre le contenu final.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": "enregistrer"},
                messages=[{"role": "user", "content": message}],
            )
            for b in rep.content:
                if getattr(b, "type", "") == "tool_use" and isinstance(b.input, dict) and b.input.get("slides"):
                    return b.input
            derniere = ValueError(f"Réponse incomplète ({rep.stop_reason})")
        except Exception as e:
            derniere = e
        time.sleep(5 * (essai + 1))
    raise derniere


SYSTEME = """Tu es le rédacteur en chef d'un compte Instagram français de divertissement « culture G & curiosités »,
sans visage, entièrement illustré par IA. Ton style : accrocheur, simple, drôle, un peu provocateur, tutoiement.

Mise en forme des titres (affichés en MAJUSCULES, police très grasse) :
- [mot] = mot dans un encadré doré (1 seul par titre, le mot le plus fort)
- *mot* = mot écrit en doré (1 à 3 mots-clés)
- titres courts : 6 à 14 mots pour la couverture, 3 à 8 mots pour les slides.

Règles absolues :
- aucune personne réelle identifiable (célébrités, politiques, patrons), aucune marque, aucun logo, aucune mascotte ou
  personnage protégé, dans les textes ET dans les prompts d'image ;
- aucun fait inventé : n'écris que des faits connus, solides et vérifiables ; dans le doute, formule-le comme une
  idée, une question ou une opinion, jamais comme un fait ;
- pas de statistiques inventées ;
- pas de violence graphique, rien de sexuel, rien sur des drames réels.

Les prompts d'image sont en ANGLAIS, très visuels, décrivent une seule scène photoréaliste et cinématique,
sans aucun texte dans l'image. Ils doivent rendre le concept compréhensible en une seconde."""

FORMAT_JSON = """Réponds UNIQUEMENT avec un objet JSON de cette forme :
{
  "sujet": "résumé du sujet en 6 mots",
  "titre_couverture": "titre balisé avec [encadré] et *doré*",
  "sous_titre": "petite ligne optionnelle sous le titre ou chaîne vide",
  "prompt_couverture": "prompt image en anglais",
  "slides": [
    {"titre": "titre balisé court", "texte": "1 à 2 phrases (max 25 mots), *mots* importants en doré", "prompt_image": "prompt en anglais"}
  ],
  "question_fin": "question balisée qui pousse à commenter (ex : Lequel t'a mis le plus *mal à l'aise* ?)",
  "legende": {
    "accroche": "1 ligne + 1 emoji",
    "developpement": "2 à 3 phrases qui donnent envie de swiper",
    "teaser": "1 phrase de suspense sur les dernières slides + emoji 👀",
    "question": "question pour les commentaires + emoji",
    "raison_enregistrer": "fin de phrase après 'Enregistre ce carrousel pour…'",
    "raison_partager": "fin de phrase après 'Partage-le à un ami,…'"
  },
  "hashtags": ["5 hashtags français pertinents sans #"]
}"""


def choisir_concept(cfg: dict, categorie: str, deja: list[str]) -> str | None:
    """Tire un concept de la banque (config.yaml › concepts). Les formats « inspirés » pèsent moins lourd,
    et on évite ceux dont les mots ressemblent aux derniers sujets traités."""
    import random
    liste = (cfg.get("concepts") or {}).get(categorie) or []
    if not liste:
        return None
    recents = " ".join(deja[:15]).lower()
    choix, poids = [], []
    for c in liste:
        texte = c["texte"] if isinstance(c, dict) else str(c)
        p = 0.35 if isinstance(c, dict) and c.get("inspire") else 1.0
        mots = [m for m in texte.lower().split() if len(m) > 5][:4]
        if mots and sum(m in recents for m in mots) >= 2:
            p *= 0.15
        choix.append(texte); poids.append(p)
    # jamais deux fois le même concept dans la même semaine
    libres = [(c, p) for c, p in zip(choix, poids) if c not in deja]
    if libres:
        choix, poids = [c for c, _ in libres], [p for _, p in libres]
    return random.choices(choix, weights=poids, k=1)[0]


def rediger_carrousel(cfg: dict, categorie: str, nb_slides_contenu: int, deja: list[str], inspiration: list[str]) -> dict:
    desc = cfg["categories"][categorie]["description"]
    consigne = f"Catégorie : {categorie} — {desc}\n"
    if categorie == "pays":
        pays = prochain_pays(deja)
        perso = cfg["personnages_serie_pays"]
        consigne += (f"Épisode de la série « Le duel » : France vs {pays}, sur UNE habitude précise du quotidien "
                     f"(jamais « où vivre » ni « ce que {pays} fait mieux »). Le sujet commence par 'Le duel France vs {pays}'. "
                     f"Chaque prompt d'image met en scène les deux mêmes personnages : le Français = {perso['francais']} ; "
                     f"l'autre = {perso['etranger']} (adapté au {pays}). Compare des choses du quotidien, avec humour, "
                     f"sans clichés blessants.\n")
    if categorie == "absurde" and inspiration:
        consigne += ("Pour t'inspirer (NE COPIE RIEN, invente ton propre concept) voici ce qui fait le buzz cette semaine "
                     "sur Reddit : " + " | ".join(inspiration[:15]) + "\n")
    concept = choisir_concept(cfg, categorie, deja)
    if concept:
        consigne += f"Concept imposé pour ce carrousel : {concept}. Trouve un angle et des exemples à toi, surprenants.\n"
    consigne += ("ORIGINALITÉ : titres et exemples écrits par toi ; ne recopie jamais mot pour mot un titre vu ailleurs "
                 "sur Instagram.\n")
    consigne += (f"Nombre de slides de contenu : exactement {nb_slides_contenu}.\n"
                 f"Sujets déjà traités (à NE PAS refaire) : {'; '.join(deja[:120]) or 'aucun'}\n\n{FORMAT_JSON}")
    brouillon = _claude_json(cfg, SYSTEME, consigne, SCHEMA_CARROUSEL)
    brouillon["concept"] = concept or ""

    relecture = (
        "Relis ce carrousel comme un rédacteur exigeant. Corrige : faits douteux (reformule-les en opinion ou supprime-les), "
        "personnes réelles, marques, logos, statistiques inventées, fautes d'orthographe, titres trop longs, balisage "
        "([…] un seul par titre). Garde le ton. Enregistre la version complète corrigée.\n\n"
        + json.dumps(brouillon, ensure_ascii=False)
    )
    try:
        corrige = _claude_json(cfg, SYSTEME, relecture, SCHEMA_CARROUSEL)
        corrige["concept"] = concept or ""
        return corrige if len(corrige.get("slides", [])) >= len(brouillon["slides"]) - 1 else brouillon
    except Exception:
        return brouillon


def legende_carrousel(cfg: dict, c: dict) -> str:
    lg = c["legende"]
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in c.get("hashtags", [])[: cfg["hashtags_par_post"]])
    return (
        f"{lg['accroche']}\n\n{lg['developpement']}\n\n{lg['teaser']}\n\n{lg['question']}\n\n"
        f"💾 Enregistre ce carrousel pour {lg['raison_enregistrer'].rstrip('.')}.\n\n"
        f"📤 Partage-le à un ami, {lg['raison_partager'].rstrip('.')}.\n\n"
        f"👉 Abonne-toi à @{cfg['compte']['pseudo']} : de nouvelles curiosités chaque jour !\n\n"
        f"{tags}"
    )


def legende_devinette(cfg: dict, d: dict) -> str:
    return (
        f"{d['accroche_legende']}\n\n"
        "Prends 5 secondes, calcule de tête… et écris ta réponse en commentaire 👇\n\n"
        "📤 Envoie-la à ton pote qui se croit fort en calcul.\n\n"
        f"👉 Abonne-toi à @{cfg['compte']['pseudo']} pour le défi de demain !\n\n"
        "#defi #calculmental #enigme #casse-tete #culturegenerale"
    )


# ------------------------------------------------------------------ démo (sans clé API)

DEMO = [
    {
        "categorie": "absurde",
        "sujet": "Oiseaux avec des pieds humains",
        "titre_couverture": "On a donné des *pieds humains* à des [oiseaux]… on a regretté direct",
        "sous_titre": "",
        "prompt_couverture": "a pigeon standing on a Paris sidewalk with realistic human bare feet instead of bird feet",
        "slides": [
            {"titre": "Le *pigeon* version [marathonien]", "texte": "Il ne vole plus. Il *trottine* entre les terrasses en te fixant.", "prompt_image": "a pigeon running on a Paris street with human feet wearing running socks"},
            {"titre": "La *mouette* en [tongs]", "texte": "Elle vient voler tes frites… et repart en *traînant les pieds*.", "prompt_image": "a seagull on a beach wearing flip-flops on human feet"},
            {"titre": "Le *flamant rose* sur [un pied]", "texte": "Toujours en équilibre. Mais avec un *orteil* qui dépasse.", "prompt_image": "a pink flamingo standing on one long human leg in a lagoon at sunset"},
            {"titre": "Le *poussin* qui fait du [bruit]", "texte": "Des petits pas lourds dans le couloir à *3 h du matin*.", "prompt_image": "a fluffy chick with tiny human feet walking on a wooden floor at night"},
            {"titre": "Le *hibou* [pieds nus]", "texte": "Il te regarde. Il remue les orteils. *Personne* ne dort.", "prompt_image": "an owl on a branch with human feet gripping the branch, moonlight"},
        ],
        "question_fin": "Lequel t'a mis le plus *mal à l'aise* ?",
        "legende": {"accroche": "Tu ne regarderas plus jamais un pigeon pareil… 😂🦶", "developpement": "On a juste changé un détail : leurs pattes. Résultat : ton cerveau refuse complètement l'image.", "teaser": "Attends de voir le dernier… il est bien pire 👀", "question": "Lequel est le plus dérangeant ? 😅", "raison_enregistrer": "le montrer à quelqu'un qui a peur des oiseaux", "raison_partager": "sa réaction vaut le détour"},
        "hashtags": ["insolite", "humour", "animaux", "ia", "curiosites"],
    },
    {
        "categorie": "nostalgie",
        "sujet": "Gestes normaux il y a 30 ans",
        "titre_couverture": "Il y a *30 ans*, on trouvait ça [normal]",
        "sous_titre": "Tu en as fait combien ?",
        "prompt_couverture": "a 1990s French child bedroom, a kid sitting on the carpet in front of a bulky CRT television, warm nostalgic light",
        "slides": [
            {"titre": "Rembobiner une *cassette* au [stylo]", "texte": "Pour *économiser les piles* du baladeur. Tout le monde le faisait.", "prompt_image": "close-up of a hand rewinding an audio cassette tape with a ballpoint pen, 1990s"},
            {"titre": "Souffler dans les *cartouches* de [jeux]", "texte": "Ça ne servait sans doute à rien… mais on y *croyait* tous.", "prompt_image": "a kid blowing into a generic grey video game cartridge, 1990s living room"},
            {"titre": "Attendre que la *photo* soit [développée]", "texte": "Une semaine d'attente pour découvrir que tu avais *les yeux fermés*.", "prompt_image": "a stack of printed photos in a paper envelope on a kitchen table, 1990s"},
            {"titre": "Connaître les *numéros* [par cœur]", "texte": "Celui des copains, de mamie, des voisins. *Sans répertoire*.", "prompt_image": "an old beige landline telephone with a curly cord on a wooden hallway table"},
            {"titre": "Regarder la télé à *heure* [fixe]", "texte": "Rater son dessin animé, c'était l'avoir raté *pour de bon*.", "prompt_image": "children sitting on a sofa watching a bulky CRT TV on a Wednesday morning, 1990s"},
        ],
        "question_fin": "Tu en as fait *combien* sur 5 ?",
        "legende": {"accroche": "Si tu as fait les 5, tu as officiellement grandi dans les années 90 📼", "developpement": "Ces gestes paraissaient totalement normaux. Aujourd'hui, ils ressemblent à une autre époque.", "teaser": "Le dernier va réveiller des souvenirs 👀", "question": "Ton score sur 5 ? 😄", "raison_enregistrer": "la prochaine soirée nostalgie", "raison_partager": "il a forcément fait le numéro 2"},
        "hashtags": ["nostalgie", "annees90", "souvenirs", "enfance", "culturegenerale"],
    },
    {
        "categorie": "pays",
        "sujet": "France vs Japon : où vivre",
        "titre_couverture": "*France* vs [Japon] : où choisirais-tu de vivre ?",
        "sous_titre": "",
        "prompt_couverture": "two smiling 30 year old men side by side, a French man with a black beret and a baguette, a Japanese man in an elegant shirt holding a cup of tea, Paris and Tokyo blended background",
        "slides": [
            {"titre": "Le *repas* du [midi]", "texte": "Ici, on prend *son temps* à table. Là-bas, la rapidité est un art.", "prompt_image": "the two same men eating lunch, one at a French bistro terrace, the other at a busy ramen counter"},
            {"titre": "Les *transports* [en commun]", "texte": "Là-bas, le *silence* dans le train est presque sacré.", "prompt_image": "the two same men in a quiet, spotless commuter train, the French man looking amazed"},
            {"titre": "La *politesse* au [quotidien]", "texte": "On se *salue* en s'inclinant… et le Français cherche encore comment faire.", "prompt_image": "the Japanese man bowing politely, the French man awkwardly trying to bow too, street in Tokyo"},
            {"titre": "Le *pain* et les [desserts]", "texte": "Sur ce point-là, la France ne compte pas *perdre le match*.", "prompt_image": "the French man proudly showing a tray of croissants, the Japanese man tasting one with delight"},
        ],
        "question_fin": "Alors, *France* ou [Japon] ?",
        "legende": {"accroche": "Deux pays, deux façons de vivre 🇫🇷🇯🇵", "developpement": "On a comparé le quotidien : repas, transports, politesse… Le résultat est plus serré qu'on le pense.", "teaser": "La dernière slide va faire débat 👀", "question": "Tu choisis lequel ? 🤔", "raison_enregistrer": "ton prochain voyage", "raison_partager": "celui qui rêve de partir au Japon"},
        "hashtags": ["japon", "france", "voyage", "expatriation", "cultures"],
    },
]


def contenu_demo(categorie: str, numero: int) -> dict:
    candidats = [d for d in DEMO if d["categorie"] == categorie] or DEMO
    c = json.loads(json.dumps(candidats[numero % len(candidats)]))
    c["sujet"] = f"[DÉMO] {c['sujet']}"
    return c


def mode_demo() -> bool:
    return not os.environ.get("ANTHROPIC_API_KEY")
