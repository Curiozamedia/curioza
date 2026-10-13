#!/usr/bin/env bash
# Récupère / republie la branche « site » (calendrier + médias) sans historique.
set -euo pipefail
case "$1" in
  recuperer)
    if git ls-remote --exit-code --heads origin site >/dev/null 2>&1; then
      git clone --depth 1 --branch site "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" _site
      rm -rf _site/.git
    else
      mkdir -p _site
    fi
    ;;
  publier)
    cd _site
    touch .nojekyll
    git init -q -b site
    git config user.name "curioza-bot"
    git config user.email "curioza-bot@users.noreply.github.com"
    git add -A
    git commit -q -m "Site : calendrier et médias" || true
    git push -f -q "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" site
    ;;
esac
