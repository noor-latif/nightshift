"""Verify: oracle-first ladder.

1. Run the candidate's unit tests (exact oracle).
2. Scenario probes: boot candidate, run HTTP assertions, teardown by PID file.
3. Provenance: /health revision must equal candidate `git rev-parse HEAD`;
   refuses if FACTORY_RUNTIME_CANDIDATE leaks into the environment.

Every verdict is per-assertion evidence. An unavailable check is a HOLD,
never a pass (P9).
"""

import http.client
import json
import os
import signal
import subprocess
import time
import urllib.request

from settings import PROVENANCE_ENV, READY_TIMEOUT_S, SCENARIO_PORT_RANGE


class Hold(Exception):
    """A check that cannot run. Never a pass."""


def run_unit_tests(cwd):
    """Oracle 1: the candidate's own suite. Returns (ok, output)."""
    r = subprocess.run(
        ["python3", "-m", "unittest", "discover", "-s", "tests"],
        cwd=cwd, capture_output=True, text=True, timeout=600,
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-8000:]


def free_port(prefer=None):
    lo, hi = SCENARIO_PORT_RANGE
    import socket

    candidates = [prefer] if prefer else range(lo, hi)
    for p in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise Hold("no free port in scenario range")


def boot_candidate(cwd, port, pid_file, env_extra=None):
    """Boot `python3 app.py` with cwd = candidate checkout, PID-file ownership."""
    env = dict(os.environ)
    env.pop(PROVENANCE_ENV, None)
    env["FACTORY_PORT"] = str(port)
    if env_extra:
        env.update(env_extra)
    out = open(pid_file + ".log", "w")
    proc = subprocess.Popen(
        ["python3", "app.py"], cwd=cwd, env=env,
        stdout=out, stderr=subprocess.STDOUT,
    )
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))
    return proc


def stop_candidate(pid_file):
    """Teardown by PID file only — never pkill."""
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def wait_ready(port, deadline_s=READY_TIMEOUT_S):
    """Bounded readiness loop; last probe is /health."""
    deadline = time.time() + deadline_s
    last_err = None
    while time.time() < deadline:
        try:
            status, _ = http_req("GET", "127.0.0.1", port, "/health")
            if status == 200:
                return True
            last_err = "health status %d" % status
        except OSError as e:
            last_err = str(e)
        time.sleep(0.2)
    raise Hold("candidate never became ready: %s" % last_err)


def http_req(method, host, port, path, body=None, raw_body=None):
    conn = http.client.HTTPConnection(host, port, timeout=10)
    payload = None
    headers = {}
    if raw_body is not None:
        payload = raw_body.encode()
    elif body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, payload, headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8", errors="replace")
    conn.close()
    return resp.status, data


def check_provenance(health_body, repo_cwd):
    """/health revision must equal the candidate's HEAD; env leak = refuse."""
    if PROVENANCE_ENV in os.environ:
        raise Hold("provenance refused: %s is set in the environment" % PROVENANCE_ENV)
    reported = json.loads(health_body).get("revision")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_cwd,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return reported == head, {"reported": reported, "head": head}


def evaluate_assertion(assertion, port, saved, revision=None):
    """One assertion = method + URL (with {{port}}/saved values) + expected."""
    url = assertion["url"].replace("{{port}}", str(port))
    for k, v in saved.items():
        url = url.replace("{{%s}}" % k, str(v))
    if revision:
        url = url.replace("{{revision}}", revision)
    # split URL into host/port/path for http.client (no external network beyond localhost)
    rest = url.split("://", 1)[1]
    hostport, path = rest.split("/", 1)
    path = "/" + path
    if ":" in hostport:
        host, p = hostport.rsplit(":", 1)
        p = int(p)
    else:
        host, p = hostport, 80
    try:
        status, body = http_req(
            assertion["method"], host, p, path,
            body=assertion.get("body"), raw_body=assertion.get("raw_body"),
        )
    except OSError as e:
        return {"assertion": assertion["url"], "status": "HOLD", "detail": str(e)}
    result = {
        "assertion": "%s %s" % (assertion["method"], url),
        "expected_status": assertion["expected_status"],
        "observed_status": status,
    }
    frag = assertion.get("expect_body_fragment")
    if frag:
        frag = str(frag).replace("{{port}}", str(port))
        if revision:
            frag = frag.replace("{{revision}}", revision)
        for k, v in saved.items():
            frag = frag.replace("{{%s}}" % k, str(v))
        result["expected_fragment"] = frag
        result["fragment_found"] = frag in body
        result["status"] = "pass" if (status == assertion["expected_status"] and result["fragment_found"]) else "fail"
    else:
        result["status"] = "pass" if status == assertion["expected_status"] else "fail"
    if result["status"] == "pass" and assertion.get("save"):
        # JSON bodies carry the id in an "id" field; numeric-run regex is
        # fallback for non-JSON bodies (base64url ids may start with letters).
        try:
            saved[assertion["save"]] = json.loads(body)["id"]
        except (ValueError, KeyError, TypeError):
            import re
            m = re.search(r"\d+", body)
            saved[assertion["save"]] = m.group(0) if m else body.strip().strip('"')
    return result


def run_scenario(scenario, checkout_cwd, pid_file, port=None):
    """Boot candidate, run all assertions, tear down. Evidence = per-assertion."""
    results = {"scenario": scenario["name"], "checks": []}
    saved = {}
    port = free_port(port)
    # provenance-clean revision: candidate HEAD, only when env is not leaking
    if PROVENANCE_ENV in os.environ:
        results["checks"].append({"assertion": "provenance", "status": "HOLD",
                                  "detail": "%s is set" % PROVENANCE_ENV})
        results["verdict"] = "hold"
        return results
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout_cwd,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        boot_candidate(checkout_cwd, port, pid_file)
        wait_ready(port)
        for a in scenario["assertions"]:
            results["checks"].append(evaluate_assertion(a, port, saved, revision))
    finally:
        stop_candidate(pid_file)
    results["verdict"] = (
        "pass" if all(c["status"] == "pass" for c in results["checks"]) and results["checks"]
        else ("hold" if any(c["status"] == "HOLD" for c in results["checks"]) else "fail")
    )
    return results


def verify_candidate(checkout_cwd, pid_file, scenarios_dir):
    """Oracle-first ladder. Green only if every check ran and passed."""
    evidence = {"unit": {}, "scenarios": [], "provenance": {}}
    ok, out = run_unit_tests(checkout_cwd)
    evidence["unit"] = {"status": "pass" if ok else "fail", "output": out}
    if not ok:
        evidence["verdict"] = "fail"
        return evidence
    for name in sorted(os.listdir(scenarios_dir)):
        if name.endswith(".json"):
            with open(os.path.join(scenarios_dir, name)) as f:
                evidence["scenarios"].append(run_scenario(json.load(f), checkout_cwd, pid_file))
    # provenance uses the health check already captured by the scenario runner
    try:
        port = free_port()
        boot_candidate(checkout_cwd, port, pid_file)
        wait_ready(port)
        _, health = http_req("GET", "127.0.0.1", port, "/health")
        ok, detail = check_provenance(health, checkout_cwd)
        evidence["provenance"] = {"status": "pass" if ok else "fail", "detail": detail}
    except Hold as e:
        evidence["provenance"] = {"status": "HOLD", "detail": str(e)}
    finally:
        stop_candidate(pid_file)
    all_checks = [evidence["unit"]] + [c for s in evidence["scenarios"] for c in s["checks"]] + [evidence["provenance"]]
    statuses = {c["status"] for c in all_checks}
    evidence["verdict"] = "HOLD" if "HOLD" in statuses else ("pass" if statuses <= {"pass"} else "fail")
    return evidence
