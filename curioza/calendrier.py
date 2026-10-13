"""Génère docs/index.html : le calendrier de publication consultable sur téléphone (GitHub Pages)."""
from __future__ import annotations

import json
import os
from datetime import datetime

from .config import DOSSIER_SITE
from .planning import toutes_les_semaines

MODELE = r"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NOM__ · Calendrier</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Montserrat:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root{color-scheme:dark;--fond:#0b0b0d;--carte:#16161a;--carte2:#1f1f25;--ligne:#2a2a31;--texte:#f3f3f5;--doux:#9a9aa6;--or:#F4B400;
--ok:#3ecf8e;--attente:#f4b400;--refus:#ef5b5b;--publie:#5b9cff;--erreur:#ff7a45}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 Montserrat,system-ui,sans-serif}
header{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:rgba(11,11,13,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--ligne);padding:14px 16px}
.marque{font:22px Anton,sans-serif;letter-spacing:.12em}.marque span{color:var(--or)}
.barre{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
select,button,a.bouton{background:var(--carte2);color:var(--texte);border:1px solid var(--ligne);border-radius:10px;padding:8px 12px;font:600 14px Montserrat,sans-serif;text-decoration:none;cursor:pointer}
a.bouton.or{background:var(--or);color:#111;border-color:var(--or)}
.compteurs{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.puce{font-size:12px;font-weight:800;padding:3px 9px;border-radius:99px;background:var(--carte2);border:1px solid var(--ligne)}
main{padding-inline:16px;padding-block:16px;max-width:1500px;margin:auto}
.aide{color:var(--doux);font-size:13px;margin:0 0 14px}
.grille{display:grid;grid-template-columns:repeat(7,minmax(180px,1fr));gap:12px;overflow-x:auto}
@media(max-width:900px){.grille{grid-template-columns:1fr}}
.jour h2{font:18px Anton,sans-serif;letter-spacing:.05em;margin:0 0 8px;text-transform:uppercase}.jour h2 small{color:var(--doux);font:600 12px Montserrat}
.post{background:var(--carte);border:1px solid var(--ligne);border-radius:14px;margin-bottom:10px;overflow:hidden;cursor:pointer}
.post img.vignette{width:100%;aspect-ratio:4/5;object-fit:cover;display:block;background:#222}
.post .meta{padding:9px 10px}
.ligne1{display:flex;justify-content:space-between;align-items:center;gap:6px}
.heure{font:20px Anton,sans-serif}.type{font-size:11px;font-weight:800;color:var(--doux);text-transform:uppercase;letter-spacing:.06em}
.sujet{font-weight:600;font-size:13px;margin-top:4px}
.statut{font-size:11px;font-weight:800;padding:2px 8px;border-radius:99px;color:#111}
.s-ok{background:var(--ok)}.s-a_valider{background:var(--attente)}.s-refuse{background:var(--refus)}.s-publie{background:var(--publie)}.s-erreur{background:var(--erreur)}
dialog{background:var(--carte);color:var(--texte);border:1px solid var(--ligne);border-radius:16px;max-width:760px;width:calc(100% - 24px);padding:0}
dialog::backdrop{background:rgba(0,0,0,.7)}
.dlg-tete{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--ligne)}
.dlg-corps{padding:16px}
.defile{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:8px}
.defile img{height:420px;max-width:85vw;border-radius:10px;scroll-snap-align:start}
video{width:100%;max-height:70vh;border-radius:10px;background:#000}
pre{white-space:pre-wrap;font:14px/1.5 Montserrat,sans-serif;background:var(--carte2);border-radius:10px;padding:12px}
.vide{color:var(--doux);padding:40px;text-align:center}
.manuel{background:var(--carte2);border:1px solid var(--or);border-radius:12px;padding:12px 14px;margin:12px 0}
.manuel ol{margin:6px 0 10px;padding-left:20px}.actions{display:flex;gap:8px;flex-wrap:wrap}
</style></head><body>
<header>
  <div class="marque">__NOM__ <span>· calendrier</span></div>
  <div class="barre">
    <select id="semaine" aria-label="Semaine"></select>
    <a class="bouton or" id="modifier" target="_blank" rel="noopener">✏️ Valider / modifier cette semaine</a>
  </div>
  <div class="compteurs" id="compteurs"></div>
</header>
<main>
  <p class="aide">Touche un post pour voir toutes les slides et la légende. Pour valider, ouvre « Valider / modifier » et passe
  <b>statut: a_valider</b> en <b>statut: ok</b> (ou mets <b>tout_valider: true</b> en haut du fichier). Mis à jour le __MAJ__.</p>
  <div class="grille" id="grille"></div>
</main>
<dialog id="dlg"><div class="dlg-tete"><b id="dlg-titre"></b><button onclick="dlg.close()">Fermer</button></div><div class="dlg-corps" id="dlg-corps"></div></dialog>
<script>
const DONNEES = __DONNEES__;
const DEPOT = "__DEPOT__";
const NOMS = {a_valider:"à valider", ok:"validé", refuse:"refusé", publie:"publié", erreur:"erreur"};
const TYPES = {carrousel:"Carrousel", reel_devinette:"Reel devinette", reel_diaporama:"Reel diaporama"};
const sel = document.getElementById('semaine'), grille = document.getElementById('grille'), dlg = document.getElementById('dlg');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function statutEffectif(s, p){ return (s.tout_valider && p.statut === 'a_valider') ? 'ok' : p.statut; }
DONNEES.forEach((s, i) => { const o = document.createElement('option'); o.value = i; o.textContent = 'Semaine du ' +
  new Date(s.semaine + 'T12:00').toLocaleDateString('fr-FR', {day:'numeric', month:'long'}) + (s.phase === 'demarrage' ? ' · démarrage' : ''); sel.appendChild(o); });
const aujourdhui = new Date().toISOString().slice(0,10);
let idx = DONNEES.findIndex(s => s.posts.some(p => p.date >= aujourdhui)); if (idx < 0) idx = DONNEES.length - 1;
sel.value = idx; sel.onchange = () => afficher(+sel.value);
function afficher(i){
  const s = DONNEES[i]; grille.innerHTML = '';
  if (!s){ grille.innerHTML = '<div class="vide">Aucune semaine planifiée pour l’instant.</div>'; return; }
  document.getElementById('modifier').href = DEPOT ? `https://github.com/${DEPOT}/edit/main/planning/${s.semaine}.yaml` : '#';
  const c = {}; s.posts.forEach(p => { const st = statutEffectif(s, p); c[st] = (c[st]||0) + 1; });
  document.getElementById('compteurs').innerHTML = Object.entries(c).map(([k,v]) => `<span class="puce">${v} ${NOMS[k]||k}</span>`).join('');
  const jours = {}; s.posts.forEach(p => (jours[p.date] ||= []).push(p));
  Object.entries(jours).forEach(([d, posts]) => {
    const col = document.createElement('section'); col.className = 'jour';
    const dt = new Date(d + 'T12:00');
    col.innerHTML = `<h2>${dt.toLocaleDateString('fr-FR',{weekday:'long'})} <small>${dt.toLocaleDateString('fr-FR',{day:'numeric',month:'short'})}</small></h2>`;
    posts.sort((a,b) => a.heure.localeCompare(b.heure)).forEach(p => {
      const st = statutEffectif(s, p);
      const el = document.createElement('article'); el.className = 'post';
      el.innerHTML = `${p.couverture ? `<img class="vignette" loading="lazy" src="${esc(p.couverture)}" alt="">` : ''}
        <div class="meta"><div class="ligne1"><span class="heure">${esc(p.heure)}</span><span class="statut s-${st}">${p.publication === 'manuelle' && st !== 'publie' ? '📱 à la main' : (NOMS[st]||st)}</span></div>
        <div class="type">${TYPES[p.type]||p.type}${p.categorie ? ' · ' + esc(p.categorie) : ''}</div><div class="sujet">${esc(p.sujet)}</div></div>`;
      el.onclick = () => ouvrir(p, st); col.appendChild(el);
    });
    grille.appendChild(col);
  });
}
function ouvrir(p, st){
  document.getElementById('dlg-titre').textContent = `${p.jour} ${p.heure} · ${NOMS[st]||st}`;
  let m = '';
  if (p.type === 'carrousel') m = `<div class="defile">${(p.medias||[]).map(u => `<img src="${esc(u)}" loading="lazy" alt="">`).join('')}</div>`;
  else if (p.medias && p.medias[0]) m = `<video src="${esc(p.medias[0])}" controls playsinline poster="${esc(p.couverture||'')}"></video>`;
  const rep = p.reponse ? `<p><b>Réponse :</b> ${esc(p.reponse)}</p>` : '';
  const man = p.publication === 'manuelle' ? `<div class="manuel"><p><b>📱 À publier depuis l'app Instagram à ${esc(p.heure)}</b></p>
    <ol><li>Télécharge la vidéo sur ton téléphone.</li><li>Instagram → + → Reel → choisis la vidéo.</li>
    <li>Ajoute un son : ${esc(p.son_conseille)}.</li><li>Colle la légende, publie.</li></ol>
    <p class="actions"><a class="bouton or" href="${esc(p.medias[0])}" download>⬇ Télécharger la vidéo</a>
    <button type="button" id="copier">📋 Copier la légende</button></p></div>` : '';
  const err = p.erreur ? `<p style="color:var(--erreur)"><b>Erreur :</b> ${esc(p.erreur)}</p>` : '';
  document.getElementById('dlg-corps').innerHTML = `${m}${man}${rep}${err}<h3>Légende</h3><pre id="leg">${esc(p.legende)}</pre>`;
  const b = document.getElementById('copier');
  if (b) b.onclick = () => navigator.clipboard.writeText(p.legende).then(() => b.textContent = '✅ Copiée',
    () => { const r = document.createRange(); r.selectNodeContents(document.getElementById('leg'));
            const s = getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = 'Texte sélectionné : copie-le'; });
  dlg.showModal();
}
afficher(idx);
</script></body></html>"""


def generer(cfg: dict) -> str:
    semaines = toutes_les_semaines()
    donnees = json.dumps(semaines, ensure_ascii=False, default=str).replace("</", "<\\/")
    depot = os.environ.get("GITHUB_REPOSITORY") or cfg.get("depot_github", "")
    if "TON-PSEUDO" in depot:
        depot = ""
    html = (MODELE.replace("__NOM__", cfg["compte"]["nom"]).replace("__DEPOT__", depot)
            .replace("__MAJ__", datetime.now().strftime("%d/%m/%Y à %H:%M")).replace("__DONNEES__", donnees))
    DOSSIER_SITE.mkdir(parents=True, exist_ok=True)
    (DOSSIER_SITE / "index.html").write_text(html, encoding="utf-8")
    (DOSSIER_SITE / ".nojekyll").write_text("")
    return str(DOSSIER_SITE / "index.html")
