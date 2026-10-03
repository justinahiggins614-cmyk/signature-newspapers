#!/bin/bash
# QA gates for the Signature Global Newspaper Archive.
# Exit 1 on ANY failure. Called by code/gen_editions.py build_all() and by hand.
set -u
cd "$(dirname "$0")/../.."
echo "=== newspaper QA gates ==="
python3 code/qa/check_all.py
rc=$?
node --check <(sed -n '/<script>$/,/<\/script>/p' index.html | sed '1d;$d') 2>/dev/null || true
echo "=== coherence check ==="
python3 code/coherence_check.py || rc=1
exit $rc
