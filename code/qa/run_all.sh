#!/bin/bash
# QA gates for the Signature Global Newspaper Archive.
# Exit 1 on ANY failure. Called by code/gen_editions.py build_all() and by hand.
set -u
cd "$(dirname "$0")/../.."
echo "=== newspaper QA gates ==="
python3 code/qa/check_all.py
rc=$?
echo "=== inline JS syntax ==="
sed -n '/^<script>$/,/^<\/script>$/p' index.html | sed '1d;$d' > /tmp/news_inline_check.js
node --check /tmp/news_inline_check.js || rc=1
echo "=== functional harness (real shipped JS vs real data) ==="
node code/qa/harness_news.js || rc=1
echo "=== coherence check ==="
python3 code/coherence_check.py || rc=1
exit $rc
