"""Day-2 Phase A: run the five scenario probes against the LIVE rig on :8642.

Oracle-verification only — no candidate, no boot. Save extraction mirrors
verify.evaluate_assertion (JSON "id" field, numeric regex fallback).
"""
import json
import re
import subprocess
import sys

sys.path.insert(0, "src")
from verify import http_req  # noqa: E402

PORT = 8642
head = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd="/home/noor/factory-lab/toy-product", capture_output=True, text=True,
).stdout.strip()

results = {}
with open("scenarios/toy-product.json") as f:
    scenarios = json.load(f)

for sc in scenarios:
    saved = {}
    ok_all = True
    for a in sc["assertions"]:
        url = a["url"].replace("{{port}}", str(PORT))
        for k, v in saved.items():
            url = url.replace("{{%s}}" % k, str(v))
        url = url.replace("{{revision}}", head)
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        frag = a.get("expect_body_fragment")
        if frag:
            frag = str(frag).replace("{{port}}", str(PORT))
            frag = frag.replace("{{revision}}", head)
            for k, v in saved.items():
                frag = frag.replace("{{%s}}" % k, str(v))
        status, body = http_req(
            a["method"], "127.0.0.1", PORT, "/" + path,
            body=a.get("body"), raw_body=a.get("raw_body"),
        )
        found = (frag in body) if frag else None
        if a.get("save"):
            try:
                saved[a["save"]] = json.loads(body)["id"]
            except (ValueError, KeyError, TypeError):
                m = re.search(r"\d+", body)
                saved[a["save"]] = m.group(0) if m else body.strip().strip('"')
        passed = status == a["expected_status"] and (found in (None, True))
        ok_all = ok_all and passed
        label = "%s: %s %s -> %s (want %s)" % (
            sc["name"], a["method"], path[:44], status, a["expected_status"])
        if found is not None:
            label += " frag=%s" % found
        print(label, "PASS" if passed else "FAIL")
    results[sc["name"]] = ok_all

total = sum(results.values())
print("LIVE-RIG ORACLE: %d/5 %s" % (total, "PASS" if total == 5 else "STOP-WORTHY FAIL: %s" % results))
sys.exit(0 if total == 5 else 1)
