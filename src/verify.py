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
import re
import shutil
import signal
import subprocess
import time
import urllib.request
import tempfile
from settings import DEPLOY_MODE, PROVENANCE_ENV, READY_TIMEOUT_S, SCENARIO_PORT_RANGE


class Hold(Exception):
    """A check that cannot run. Never a pass."""


def run_unit_tests(cwd):
    """Oracle 1: the candidate's own suite. Returns (ok, output).

    Repos without a tests/ dir (toy-product) discover *_test.py from the
    root — the calibration harness's exact invocation. Zero tests discovered
    is a FAIL, never a vacuous pass (L-004: an oracle that sees nothing is
    not green).
    """
    if os.path.isdir(os.path.join(cwd, "tests")):
        cmd = ["python3", "-m", "unittest", "discover", "-s", "tests"]
    else:
        cmd = ["python3", "-m", "unittest", "discover", "-s", ".", "-p", "*_test.py"]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    out = (r.stdout + r.stderr)[-8000:]
    m = re.search(r"Ran (\d+) test", out)
    ran = int(m.group(1)) if m else 0
    return r.returncode == 0 and ran > 0, out


def free_port(prefer=None):
    lo, hi = SCENARIO_PORT_RANGE
    import socket

    candidates = [prefer] if prefer else range(lo, hi)
    for p in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # SO_REUSEADDR: a just-closed candidate's TIME_WAIT sockets must
            # not make the probe (or the next boot on that port) fail —
            # back-to-back laps otherwise exhaust the 11-port range.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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


def wait_ready(port, deadline_s=READY_TIMEOUT_S, path="/health"):
    """Bounded readiness loop; last probe is the ready path (default /health).
    A scenario whose assertion targets the ready endpoint itself (issue #18:
    /health outside a git repo crashes on main — that crash IS the RED) must
    probe readiness elsewhere via the scenario's ready_path."""
    deadline = time.time() + deadline_s
    last_err = None
    while time.time() < deadline:
        try:
            status, _ = http_req("GET", "127.0.0.1", port, path)
            if status == 200:
                return True
            last_err = "%s status %d" % (path, status)
        except OSError as e:
            last_err = str(e)
        time.sleep(0.2)
    raise Hold("candidate never became ready: %s" % last_err)


def http_req(method, host, port, path, body=None, raw_body=None, headers=None,
             chunked=False):
    conn = http.client.HTTPConnection(host, port, timeout=10)
    payload = None
    hdrs = dict(headers or {})
    if chunked:
        # Transfer-Encoding: chunked on the wire: http.client encodes the
        # iterable itself (terminating chunk included); no Content-Length
        # is sent (issue #19's repro shape)
        if raw_body is not None:
            payload = (raw_body.encode(),)
        else:
            hdrs.setdefault("Content-Type", "application/json")
            payload = (json.dumps(body).encode(),)
        conn.request(method, path, body=iter(payload), headers=hdrs,
                     encode_chunked=True)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", errors="replace")
        conn.close()
        return resp.status, data
    if raw_body is not None:
        payload = raw_body.encode()
    elif body is not None:
        payload = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    conn.request(method, path, payload, hdrs)
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
            headers=assertion.get("headers"),
            chunked=assertion.get("chunked"),
        )
    except ConnectionRefusedError as e:
        # nothing is listening: the check could not run
        return {"assertion": assertion["url"], "status": "HOLD", "detail": str(e)}
    except (http.client.RemoteDisconnected, ConnectionResetError) as e:
        # the server accepted the request and died answering it — that IS
        # the observation (issue #18's empty-reply crash). The assertion
        # ran; the candidate's behavior failed it. Never a hold, never a
        # pass; the crash is the evidence.
        return {"assertion": "%s %s" % (assertion["method"], url),
                "expected_status": assertion["expected_status"],
                "observed_status": None, "status": "fail",
                "detail": "server closed connection without response: %s" % e}
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

def evaluate_exec_assertion(assertion, cwd):
    """`kind: "exec"` assertion: run argv with cwd = the candidate checkout,
    pass on expected_exit match (+ stdout fragment if given). argv is the
    scenario author's problem — the oracle is a dumb exec+match, no path
    munging, no PYTHONPATH magic. HOLD only on harness-level inability
    (spawn failure, timeout); a wrong exit code is a candidate FAIL.
    """
    result = {
        "assertion": "exec %s" % " ".join(assertion["argv"]),
        "expected_exit": assertion["expected_exit"],
    }
    try:
        r = subprocess.run(assertion["argv"], cwd=cwd,
                            capture_output=True, text=True, timeout=600)
    except OSError as e:
        return dict(result, status="HOLD", detail="cannot run: %s" % e)
    except subprocess.TimeoutExpired as e:
        return dict(result, status="HOLD",
                    detail="timed out after %ss" % e.timeout)
    result["observed_exit"] = r.returncode
    frag = assertion.get("expect_stdout_fragment")
    if frag:
        result["expected_fragment"] = frag
        result["fragment_found"] = frag in r.stdout
        ok = r.returncode == assertion["expected_exit"] and result["fragment_found"]
    else:
        ok = r.returncode == assertion["expected_exit"]
    if not ok:
        result["detail"] = (r.stdout + r.stderr)[-1000:]
    result["status"] = "pass" if ok else "fail"
    return result



def run_scenario(scenario, checkout_cwd, pid_file, port=None):
    """Boot candidate, run all assertions, tear down. Evidence = per-assertion.

    scenario["boot_cwd"] == "no-git" boots a plain copy of the checkout
    WITHOUT .git (issue #18: the server must serve /health outside a git
    repo). The provenance revision is still captured from checkout_cwd —
    the real worktree — so non-git boots never corrupt provenance evidence.
    """
    results = {"scenario": scenario["name"], "checks": []}
    saved = {}
    # provenance-clean revision: candidate HEAD, only when env is not leaking
    if PROVENANCE_ENV in os.environ:
        results["checks"].append({"assertion": "provenance", "status": "HOLD",
                                  "detail": "%s is set" % PROVENANCE_ENV})
        results["verdict"] = "hold"
        return results
    # a scenario whose assertions are ALL exec-kind has nothing to boot and
    # needs no port — repos with no app.py run their oracle as plain argv
    if scenario["assertions"] and all(a.get("kind") == "exec" for a in scenario["assertions"]):
        for a in scenario["assertions"]:
            results["checks"].append(evaluate_exec_assertion(a, checkout_cwd))
        results["verdict"] = (
            "pass" if all(c["status"] == "pass" for c in results["checks"]) and results["checks"]
            else ("hold" if any(c["status"] == "HOLD" for c in results["checks"]) else "fail")
        )
        return results
    port = free_port(port)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout_cwd,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    boot_dir = checkout_cwd
    tmp_boot = None
    if scenario.get("boot_cwd") == "no-git":
        tmp_boot = tempfile.mkdtemp(prefix="factory-nogit-")
        for name in os.listdir(checkout_cwd):
            if name == ".git" or name.startswith(".factory"):
                continue
            src = os.path.join(checkout_cwd, name)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(tmp_boot, name))
            else:
                shutil.copytree(src, os.path.join(tmp_boot, name))
        boot_dir = tmp_boot
    try:
        boot_candidate(boot_dir, port, pid_file)
        wait_ready(port, path=scenario.get("ready_path", "/health"))
        for a in scenario["assertions"]:
            if a.get("kind") == "exec":
                results["checks"].append(evaluate_exec_assertion(a, checkout_cwd))
            else:
                results["checks"].append(evaluate_assertion(a, port, saved, revision))
    finally:
        stop_candidate(pid_file)
        if tmp_boot:
            shutil.rmtree(tmp_boot, ignore_errors=True)
    results["verdict"] = (
        "pass" if all(c["status"] == "pass" for c in results["checks"]) and results["checks"]
        else ("hold" if any(c["status"] == "HOLD" for c in results["checks"]) else "fail")
    )
    return results


def scenario_paths(scenarios_dir, issue=None):
    """Files for this lap: global .json always, plus issue-<n>.json when it matches.

    Per-issue oracles must not run against candidates that don't address them;
    a missing issue-<n>.json means the lap runs global scenarios only.
    """
    names = sorted(n for n in os.listdir(scenarios_dir) if n.endswith(".json"))
    return [os.path.join(scenarios_dir, n) for n in names
            if not n.startswith("issue-")
            or (issue is not None and n == "issue-%d.json" % issue)]

def verify_candidate(checkout_cwd, pid_file, scenarios_dir, issue=None):
    """Oracle-first ladder. Green only if every check ran and passed."""
    evidence = {"unit": {}, "scenarios": [], "provenance": {}}
    ok, out = run_unit_tests(checkout_cwd)
    evidence["unit"] = {"status": "pass" if ok else "fail", "output": out}
    if not ok:
        evidence["verdict"] = "fail"
        return evidence
    for path in scenario_paths(scenarios_dir, issue):
        with open(path) as f:
            data = json.load(f)
        # a file may hold one scenario or a list of scenarios
        for scenario in (data if isinstance(data, list) else [data]):
            evidence["scenarios"].append(run_scenario(scenario, checkout_cwd, pid_file))
    # provenance uses the health check already captured by the scenario runner.
    # DEPLOY_MODE="none" (library repos) has no bootable candidate and no
    # live rig: there is nothing to compare identity against — skipped, and
    # a skip is not a pass (it is absent from all_checks entirely).
    if DEPLOY_MODE == "none":
        evidence["provenance"] = {"status": "skip", "detail": "DEPLOY_MODE=none"}
        all_checks = [evidence["unit"]] + [c for s in evidence["scenarios"] for c in s["checks"]]
    else:
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
