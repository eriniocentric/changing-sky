#!/usr/bin/env bash
# Regenerate the published pages from the single source template.
# index.html = main site (tiled multi-night viewer); explore.html = same page with noindex (old test URL kept working).
set -e; cd "$(dirname "$0")/.."
python pipeline/make_explore.py pipeline/site_template.html explore.html
python pipeline/make_explore.py pipeline/site_template.html index.html
python - <<'PY'
s=open('index.html').read(); open('index.html','w').write(s.replace('<meta name="robots" content="noindex">','',1))
PY
