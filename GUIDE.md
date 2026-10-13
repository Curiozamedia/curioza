# CURIOZA — guide de mise en route

Ce dossier contient **tout le système** : génération des idées, des légendes, des images, des carrousels et des Reels,
calendrier à une semaine, et publication automatique aux mêmes heures qu'Opulancia.
Il ne reste qu'à **brancher tes comptes** (environ 1 heure, une seule fois).

---

## 1. Comment ça marche (en 30 secondes)

```
Chaque NUIT à 3h       → le système complète les 7 prochains jours (textes, images, vidéos)
                          et met à jour ton calendrier en ligne : toujours une semaine d’avance.
Pendant la semaine     → tu regardes le calendrier sur ton téléphone, tu valides (ou refuses) les posts.
Aux heures prévues     → les posts validés partent tout seuls sur Instagram, à la minute près.
```

| Phase | Carrousels | Reels |
|---|---|---|
| Démarrage (désactivé par défaut, `semaines_demarrage: 0`) | 8h, 11h, 17h | 21h (devinette) |
| Rythme Opulancia (dès le lancement) | 8h, 11h, 14h, 17h, 20h | 13h (devinette) + 21h (diaporama) |

**Reels en semi-automatique (comme Opulancia).** L'API d'Instagram ne donne pas accès aux sons tendance, et un tube
mis directement dans la vidéo serait coupé pour droits d'auteur. Le système prépare donc chaque Reel **sans musique** ;
à l'heure prévue, tu ouvres le calendrier sur ton téléphone, tu touches le Reel, **Télécharger la vidéo**, puis dans
Instagram tu ajoutes un son marqué d'une flèche ↗ (tendance), tu colles la légende (**Copier la légende**) et tu publies.
Environ 30 secondes par Reel. Un son conseillé est indiqué pour chacun. Mets une alarme sur ton téléphone à 13h et 21h.
Pour tout automatiser quand même : `reels_publication: "auto"` dans `config.yaml` (musique libre de droits, moins de portée).

Tout se règle dans `config.yaml` (nom, couleurs, heures, catégories, validation…).

**Ce que l'IA crée chaque semaine :**
- **Carrousels** dans 5 catégories qui marchent chez Opulancia : absurde, nostalgie, anecdotes, France vs un pays
  (série avec les deux mêmes personnages), leçons de vie. Chaque carrousel est rédigé, puis **relu par une deuxième IA**
  qui vérifie les faits et enlève personnes réelles et marques.
- **Reels devinettes** : une opération piège (« La réponse n'est pas 66 ! »). Elles sont **calculées et vérifiées par
  le programme**, donc la bonne réponse est toujours juste. C'est le format qui a fait 744 000 vues chez lui.
- **Reels diaporamas** : les slides du carrousel « absurde » du jour en vidéo, sans coût supplémentaire.
- **Radar Reddit** : chaque semaine, le système lit ce qui buzze (r/aivideo, r/midjourney…) pour s'en inspirer
  (jamais de copie).

---

## 2. Ce qu'il te faut (comptes à créer toi-même)

| Service | Pourquoi | Coût |
|---|---|---|
| **GitHub** (github.com) | fait tourner le système + héberge les images et le calendrier | gratuit |
| **Claude API** (console.anthropic.com) | écrit les textes | quelques centimes par semaine |
| **Google AI Studio** (aistudio.google.com) | images haut de gamme (Nano Banana) pour les carrousels | ~0,039 $ l’image |
| **Cloudflare** (cloudflare.com) | décors des devinettes + secours | **gratuit** jusqu’à ~170 images/jour |
| **Instagram pro + app Meta** (developers.facebook.com) | publication | gratuit |

Budget total estimé : **≈ 40 € par mois** en qualité maximale (≈ 250 images Nano Banana par semaine). Mode « couvertures premium + slides gratuites » (ligne à changer dans `config.yaml`) : **≈ 8 € par mois**.

---

## 3. Mise en route pas à pas

### Étape A — Instagram
1. Crée ton nouveau compte Instagram dédié, complète la bio et la photo.
2. Paramètres → *Type de compte et outils* → **Passer à un compte professionnel** (Créateur).
3. Utilise le compte normalement 3 ou 4 jours avant de lancer l'automatisation.

### Étape B — L'app Meta (la plus longue, je te guide en direct si tu veux)

*Meta renomme régulièrement ses menus : si un intitulé diffère, je te guide écran par écran dans le navigateur.*

1. Va sur **developers.facebook.com** → *Mes apps* → **Créer une app** → cas d'usage
   **« Gérer les messages et le contenu sur Instagram »** (Instagram API avec connexion Instagram).
2. Dans *Instagram* → *Configuration de l'API avec connexion Instagram* :
   ajoute ton compte Instagram comme **testeur**, puis accepte l'invitation dans l'app Instagram
   (Paramètres → *Apps et sites web* → *Invitations de testeur*).
3. Clique **Générer un jeton** pour ton compte, avec la permission `instagram_business_content_publish`.
4. Note deux valeurs : le **jeton d'accès** (longue chaîne) et l'**identifiant du compte Instagram** (nombre).
   Garde-les secrets : ce sont les clés de ton compte.

### Étape C — Les clés IA
1. **console.anthropic.com** → *API Keys* → *Create key* → ajoute 5 € de crédit.
2. **dash.cloudflare.com** → crée un compte gratuit (aucune carte demandée) → note ton **Account ID** (menu *Workers AI* ou page d’accueil du compte) → *Mon profil* → *Jetons API* → **Créer un jeton** avec le modèle « Workers AI » → copie le jeton.
3. **aistudio.google.com** → connecte-toi avec ton compte Google → *Get API key* → **Créer une clé** → active la facturation (carte bancaire) sur le projet. Fixe une **alerte de budget** à 50 € pour garder le contrôle.

### Étape D — GitHub
1. Crée un compte GitHub, puis un **nouveau dépôt public** nommé `curioza`.
   *(Public = gratuit et illimité. Seuls les visuels de la semaine à venir sont visibles ; tes clés restent secrètes.)*
2. Envoie tous les fichiers de ce dossier dans le dépôt (*Add file → Upload files*, glisse tout le contenu du dossier).
3. **Paramètres du dépôt → Secrets and variables → Actions → New repository secret**, crée :
   - `ANTHROPIC_API_KEY` → la clé Claude
   - `CF_ACCOUNT_ID` → l’Account ID Cloudflare
   - `CF_API_TOKEN` → le jeton Cloudflare
   - `GEMINI_API_KEY` → la clé Google AI Studio
   - `IG_USER_ID` → l'identifiant Instagram
   - `IG_ACCESS_TOKEN` → le jeton Instagram
4. Même page, onglet **Variables** → `URL_PAGES` = `https://TON-PSEUDO.github.io/curioza/`
5. **Paramètres → Pages** → *Source : Deploy from a branch* → branche `main`, dossier **`/docs`** → Save.
   Ton calendrier sera à l'adresse `https://TON-PSEUDO.github.io/curioza/`.
6. Dans `config.yaml`, remplace `TON-PSEUDO-GITHUB`, le nom du compte et ton @, puis la `date_lancement`.
7. **Paramètres → Actions → General → Workflow permissions** → *Read and write permissions* → Save.

### Étape E — Premier lancement
1. Onglet **Actions** → *Préparer la semaine suivante* → **Run workflow** (laisse les champs vides).
   Compte 20 à 40 minutes : toute la semaine est générée.
2. Ouvre ton calendrier en ligne, regarde chaque post.
3. Pour un premier test réel : *Actions* → *Publier sur Instagram* → **Run workflow** en indiquant l'id d'un post validé.

---

## 4. Valider la semaine (2 minutes par jour)

Sur le calendrier, touche **« Valider / modifier cette semaine »**. Le fichier du planning s'ouvre sur GitHub
(ça marche depuis le téléphone). Pour chaque post :

```yaml
statut: a_valider   →   statut: ok        # sera publié
statut: a_valider   →   statut: refuse    # ne sera jamais publié
```

Raccourci : en haut du fichier, `tout_valider: true` valide tout d'un coup.
Tu peux aussi corriger la `legende` ou changer l'`heure` directement. Clique **Commit changes** pour enregistrer.

**Un post ne te plaît pas ?** *Actions* → *Préparer la semaine suivante* → *Run workflow* → champ **refaire** = l'id du
post (ex. `2026-10-21_1700_carro`). Il est régénéré avec un nouveau sujet.

Quand la qualité est stable, mets `validation_requise: false` dans `config.yaml` : tout ce qui n'est pas « refuse »
partira automatiquement.

---

## 5. Entretien

- **Jeton Instagram** : il expire tous les 60 jours. Le workflow *Prolonger le jeton Instagram* le prolonge le 1er et
  le 15 du mois. Pour qu'il mette aussi le secret à jour tout seul, crée un jeton GitHub
  (*Settings → Developer settings → Fine-grained token*, droit **Secrets : read and write** sur le dépôt) et ajoute-le en
  secret `GH_PAT`. Sinon, regénère le jeton dans l'app Meta tous les ~50 jours.
- **Musique** (seulement si `reels_publication: "auto"`) : ajoute des mp3 libres de droits dans `assets/musique/`.
- **En cas d'erreur** : GitHub t'envoie un e-mail ; le post passe en statut `erreur` avec l'explication, visible dans
  le calendrier.
- **Espace** : les visuels des posts publiés depuis plus de 14 jours sont supprimés automatiquement.

---

## 6. Règles intégrées (pour protéger le compte)

- Aucune personne réelle, aucune marque ni mascotte dans les textes et les images.
- Aucune vidéo ou image d'autres créateurs : tout est généré pour toi.
- Pas de mention IA dans la légende : la transparence passe par l'étiquette officielle « Infos IA » d'Instagram
  (ajoutée automatiquement quand l'image le signale, ou à cocher dans *Paramètres avancés* pour les Reels publiés à la main).
- 7 posts par jour maximum, très en dessous de la limite de l'API (100 par 24 h).

---

## 7. Commandes (si tu travailles sur ton ordinateur)

```bash
pip install -r requirements.txt          # + ffmpeg installé
python planifier.py                      # prépare la semaine prochaine
python planifier.py --semaine 2026-10-19 --forcer
python planifier.py --refaire 2026-10-21_1700_carro
python publier.py --simulation           # montre ce qui partirait maintenant
```

Sans clés, `planifier.py` fonctionne en **mode démo** (textes d'exemple, fonds flous) pour tester la mise en page.
