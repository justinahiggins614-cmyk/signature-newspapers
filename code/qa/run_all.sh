#!/bin/bash
# QA gates for the Signature Global Newspaper Archive.
# Exit 1 on ANY failure. Called by code/gen_editions.py build_all() and by hand.
set -u
cd "$(dirname "$0")/../.."
echo "=== newspaper QA gates ==="
python3 code/qa/check_all.py
rc=$?
echo "=== inline JS syntax (each inline block checked separately) ==="
python3 - <<'PYEOF'
import re, subprocess, sys
html = open("index.html", encoding="utf-8").read()
blocks = re.findall(r"^<script>$\n(.*?)^</script>$", html, re.M | re.S)
rc = 0
for i, b in enumerate(blocks):
    p = "/tmp/news_inline_check_%d.js" % i
    open(p, "w", encoding="utf-8").write(b)
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    if r.returncode != 0:
        print("SYNTAX FAIL in inline block %d:" % i)
        print(r.stderr[-2000:])
        rc = 1
print("checked %d inline block(s): %s" % (len(blocks), "OK" if rc == 0 else "FAIL"))
sys.exit(rc)
PYEOF
rc=$?; [ $rc -ne 0 ] && rc=1
echo "=== functional harness (real shipped JS vs real data) ==="
node code/qa/harness_news.js || rc=1
echo "=== coherence check ==="
python3 code/coherence_check.py || rc=1
exit $rc
