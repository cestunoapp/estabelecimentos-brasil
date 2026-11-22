#!/usr/bin/env bash
# Publica a página de busca (pasta site/ + dados da versão) no ramo gh-pages, que o GitHub Pages serve.
# Uso: bash scripts/publicar-pagina.sh <pasta com UF.csv.gz e indice.json>
# O ramo gh-pages é refeito do zero a cada vez (sem histórico): o repositório não cresce todo mês.
set -euo pipefail
entrada="${1:?pasta com os arquivos da versão}"
python3 scripts/pagina.py --entrada "$entrada" --site site --repo "${GITHUB_REPOSITORY:-cestunoapp/estabelecimentos-brasil}"
pub="$(mktemp -d)"
cp -r site/. "$pub/"
touch "$pub/.nojekyll"
cd "$pub"
git init -q -b gh-pages
git add -A
git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit -q -m "Página de busca ($(python3 -c 'import json;print(json.load(open("dados/indice.json"))["versao"])'))"
git push -q --force "https://x-access-token:${GH_TOKEN:?}@github.com/${GITHUB_REPOSITORY:?}.git" gh-pages
echo "Página publicada no ramo gh-pages."
