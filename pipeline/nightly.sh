#!/usr/bin/env bash
# Nightly job and site publishing for Changing Sky, called by .github/workflows/daily.yml.
#
# Branches:  main      = code and static pages only (nothing is added to it by this job)
#            raw       = raw and cross-match tables for the newest RAW_KEEP nights (for rebuilds)
#            site-data = the published window of nights (data/nights.json, data/n/<night>/...)
# Both data branches are replaced by a single fresh commit on every run, so the repository does not grow.
# Fink keeps the full alert history; older alerts are reached through Fink's cone search, not stored here.
#
# Usage: bash main/pipeline/nightly.sh <event>   (event 'push' = only re-publish the site after a code change)
# Needs: GH_TOKEN and GITHUB_REPOSITORY in the environment; PY = python with requests, numpy, pandas, pyarrow.
set -euo pipefail
EVENT="${1:-workflow_dispatch}"
RAW_KEEP="${RAW_KEEP:-1}"
PY="${PY:-python3}"
REPO_URL="${REPO_URL:-https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}"   # REPO_URL may be overridden for local tests

fetch_branch() {  # branch dir
  git clone -q --depth 1 --branch "$1" "$REPO_URL" "$2" 2>/dev/null || mkdir -p "$2"
}
squash_push() {   # dir branch message
  ( cd "$1"
    rm -rf .git
    git init -q -b "$2"
    git config user.name "changing-sky-bot"
    git config user.email "changing-sky-bot@users.noreply.github.com"
    git add -A
    git commit -q --allow-empty -m "$3"
    git push -q -f "$REPO_URL" "HEAD:$2" )
}

fetch_branch raw raw
fetch_branch site-data sitedata
mkdir -p sitedata/data

status=0
if [ "$EVENT" != "push" ]; then
  "$PY" main/pipeline/daily.py --raw raw --site sitedata --keep-raw "$RAW_KEEP" || status=$?
  # Save the raw tables even if the build failed, so the night can be rebuilt later.
  squash_push raw raw "Raw tables for the newest ${RAW_KEEP} nights ($(date -u +%F))"
  if [ "$status" -ne 0 ]; then echo "Nightly build failed (exit $status); the published site is left unchanged."; exit "$status"; fi
  squash_push sitedata site-data "Published window of nights ($(date -u +%F))"
fi

# Assemble the site: pages and static files from main, plus the window of nights.
rm -rf _site && mkdir _site
tar -C main --exclude=.git --exclude=.github --exclude=pipeline --exclude=README.md -cf - . | tar -C _site -xf -
mkdir -p _site/data && cp -R sitedata/data/. _site/data/
echo "Site assembled: $(du -sh _site | cut -f1), nights: $(ls sitedata/data/n 2>/dev/null | tr '\n' ' ')"
