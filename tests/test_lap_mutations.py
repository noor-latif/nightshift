import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lap  # noqa: E402

def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

def mut(file, find, replace):
    return {"file": file, "find": find, "replace": replace}

class TestExtractMutations(unittest.TestCase):
    def test_valid_bare_array(self):
        payload = '[{"file": "app.py", "find": "x = 1", "replace": "x = 2"}]'
        m, err = lap.extract_mutations("Sure.\n" + payload)
        self.assertIsNone(err)
        self.assertEqual(m, [mut("app.py", "x = 1", "x = 2")])

    def test_fenced_json_stripped(self):
        payload = '[{"file": "app.py", "find": "a", "replace": "b"}]'
        m, err = lap.extract_mutations("```json\n%s\n```" % payload)
        self.assertIsNone(err)
        self.assertEqual(len(m), 1)

    def test_prose_fence_rejected_loud(self):
        m, err = lap.extract_mutations("I would change x. ```\nnot json\n```")
        self.assertIsNone(m)
        self.assertIn("mutation-parse", err)

    def test_malformed_json_error_names_parse_failure(self):
        m, err = lap.extract_mutations('[{"file": "app.py", "find": ]')
        self.assertIsNone(m)
        self.assertIn("invalid JSON", err)

    def test_non_array_rejected(self):
        m, err = lap.extract_mutations('{"file": "app.py"}')
        self.assertIsNone(m)
        self.assertIn("array", err)

    def test_missing_and_wrong_type_keys_rejected(self):
        m, err = lap.extract_mutations('[{"file": "app.py", "find": "a"}]')
        self.assertIsNone(m)
        self.assertIn("missing keys", err)
        m, err = lap.extract_mutations('[{"file": 1, "find": "a", "replace": "b"}]')
        self.assertIsNone(m)
        self.assertIn("must be a string", err)

    def test_empty_anchor_rejected(self):
        m, err = lap.extract_mutations('[{"file": "app.py", "find": "", "replace": "b"}]')
        self.assertIsNone(m)
        self.assertIn("empty find anchor", err)

    def test_unknown_file_rejected(self):
        m, err = lap.extract_mutations('[{"file": "evil.py", "find": "a", "replace": "b"}]',
                                       allowed_files={"app.py"})
        self.assertIsNone(m)
        self.assertIn("not in the provided checkout", err)
        m, err = lap.extract_mutations('[{"file": "app.py", "find": "a", "replace": "b"}]',
                                       allowed_files={"app.py"})
        self.assertIsNone(err)

    def test_empty_array_rejected(self):
        m, err = lap.extract_mutations("[]")
        self.assertIsNone(m)
        self.assertIn("empty", err)

    def test_dsml_leak_dies_here(self):
        m, err = lap.extract_mutations('<|DSML| invoke name="bash">rm -rf /')
        self.assertIsNone(m)
        self.assertTrue(err)

class TestApplyMutations(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        git(self.dir, "init", "-q")
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("x = 1\ny = 1\n")
        git(self.dir, "add", "-A")
        git(self.dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

    def test_exact_anchor_applies(self):
        ok, detail, results = lap.apply_mutations(
            [mut("app.py", "x = 1", "x = 2")], self.dir)
        self.assertTrue(ok, detail)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 2\ny = 1\n")
        self.assertEqual(results[0]["anchor_count"], 1)
        self.assertTrue(results[0]["applied"])

    def test_anchor_miss_fails_loud_naming_file_and_prefix(self):
        ok, detail, results = lap.apply_mutations(
            [mut("app.py", "x = 42", "x = 2")], self.dir)
        self.assertFalse(ok)
        self.assertIn("app.py", detail)
        self.assertIn("0 times", detail)
        self.assertIn("x = 42", detail)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 1\ny = 1\n")
        self.assertEqual(results[0]["applied"], False)

    def test_ambiguous_anchor_fails_loud(self):
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "= 1", "= 2")], self.dir)
        self.assertFalse(ok)
        self.assertIn("2 times", detail)

    def test_trailing_whitespace_drift_tolerated_both_directions(self):
        # model's anchor carries trailing spaces the file lacks…
        ok, _, _ = lap.apply_mutations(
            [mut("app.py", "x = 1   \n", "x = 2")], self.dir)
        self.assertTrue(ok)
        # …and the file has trailing spaces the anchor lacks
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("x = 1   \n")
        ok, _, _ = lap.apply_mutations(
            [mut("app.py", "x = 1\n", "x = 3")], self.dir)
        self.assertTrue(ok)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 3   \n")

    def test_ordered_application_on_previous_result(self):
        # mutation 2 anchors on text created by mutation 1
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "x = 1", "x = 7"),
             mut("app.py", "x = 7", "x = 9")], self.dir)
        self.assertTrue(ok, detail)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 9\ny = 1\n")

    def test_multi_line_anchor_with_indentation(self):
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("def f():\n    return 1\n")
        ok, _, _ = lap.apply_mutations(
            [mut("app.py", "    return 1", "    return 2")], self.dir)
        self.assertTrue(ok)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(),
                         "def f():\n    return 2\n")

    def test_newline_terminated_anchor_consumes_newline(self):
        with open(os.path.join(self.dir, "app.py"), "wb") as f:
            f.write(b"A\nB\nC\n")
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "A\nB\n", "X\n")], self.dir)
        self.assertTrue(ok, detail)
        with open(os.path.join(self.dir, "app.py"), "rb") as f:
            self.assertEqual(f.read(), b"X\nC\n")

    def test_nothing_written_when_any_anchor_misses(self):
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "x = 1", "x = 2"),
             mut("app.py", "z = 9", "z = 8")], self.dir)
        self.assertFalse(ok)
        # mutation 1 matched but must not be half-applied to disk
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 1\ny = 1\n")

    def test_postcondition_missing_from_git_status_fails_loud(self):
        # porcelain post-condition: a mutation equal to current content leaves
        # the file unmodified in git status → apply_incomplete (L-008 shape)
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "x = 1", "x = 1")], self.dir)
        self.assertFalse(ok)
        self.assertIn("apply_incomplete", detail)

    def test_per_mutation_results_recorded_incl_failures(self):
        # L-014 lesson: every mutation's evidence survives, not just the failure
        _, _, results = lap.apply_mutations(
            [mut("app.py", "y = 1", "y = 2"),
             mut("app.py", "nope", "z")], self.dir)
        self.assertEqual(results[0]["applied"], True)
        self.assertEqual(results[0]["anchor_count"], 1)
        self.assertEqual(results[1]["applied"], False)
        self.assertIn(results[1]["error"], ("anchor not found", "anchor occurs 0 times"))
class TestCheckoutFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # pin the default view: the suite must be invariant to the launch
        # env (a self-run sets CODE_PATHS; unit-oracle runs inherit it)
        self._p = unittest.mock.patch.object(lap, "CODE_PATHS", ["*.py"])
        self._p.start()
        self.addCleanup(self._p.stop)

    def write(self, name, content):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(content)

    def test_nonstandard_names_included(self):
        self.write("server.py", "s = 1\n")
        self.write("server_test.py", "t = 1\n")
        got = lap.checkout_files(self.dir)
        self.assertEqual(len(got), 2)
        self.assertIn("=== server.py ===", got[0])
        self.assertIn("=== server_test.py ===", got[1])

    def test_dotdirs_and_factory_excluded(self):
        self.write("app.py", "x = 1\n")
        os.makedirs(os.path.join(self.dir, ".factory"))
        with open(os.path.join(self.dir, ".factory", "leak.py"), "w") as f:
            f.write("secret\n")
        got = lap.checkout_files(self.dir)
        self.assertEqual([g for g in got if "app.py" in g], got)
        self.assertNotIn("secret", "".join(got))

    def test_char_cap_stops_at_whole_files_deterministically(self):
        self.write("a.py", "x" * 600)
        self.write("b.py", "y" * 600)
        self.write("c.py", "z" * 600)
        got = lap.checkout_files(self.dir, char_budget=1000)
        self.assertEqual(len(got), 1)
        self.assertIn("a.py", got[0])
        self.assertNotIn("b.py", got[0])

class TestCheckoutFilesCodePaths(unittest.TestCase):
    """CODE_PATHS globs replace the hardcoded root *.py view; default stays
    byte-identical. A path appearing in two globs appears once."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._p = unittest.mock.patch.object(lap, "CODE_PATHS", ["*.py"])
        self._p.start()
        self.addCleanup(self._p.stop)

    def write(self, name, content):
        p = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
    def test_default_matches_root_py_byte_identical(self):
        self.write("a.py", "x = 1\n")
        self.write("b.py", "y = 2\n")
        self.write("notes.txt", "t\n")
        os.makedirs(os.path.join(self.dir, "sub"))
        self.write("sub/c.py", "z = 3\n")  # not root: excluded by default
        self.assertEqual("\n".join(lap.checkout_files(self.dir)),
                         "=== a.py ===\nx = 1\n\n=== b.py ===\ny = 2\n")

    def test_subdir_glob_selects_nested_files(self):
        self.write("src/lap.py", "x = 1\n")
        self.write("src/verify.py", "y = 2\n")
        self.write("app.py", "root\n")
        self._p.stop()
        self._p2 = unittest.mock.patch.object(lap, "CODE_PATHS", ["src/*.py"])
        self._p2.start()
        self.addCleanup(self._p2.stop)
        got = lap.checkout_files(self.dir)
        self.assertEqual(len(got), 2)
        self.assertIn("=== src/lap.py ===", got[0])
        self.assertIn("=== src/verify.py ===", got[1])
        self.assertNotIn("app.py", "".join(got))

    def test_overlapping_globs_dedup(self):
        self.write("a.py", "x = 1\n")
        self._p.stop()
        self._p2 = unittest.mock.patch.object(lap, "CODE_PATHS", ["*.py", "a.py", "**/*.py"])
        self._p2.start()
        self.addCleanup(self._p2.stop)
        got = lap.checkout_files(self.dir)
        self.assertEqual(len(got), 1)
        self.assertIn("=== a.py ===", got[0])

    def test_char_budget_still_bounds_multi_glob_checkout(self):
        self.write("src/a.py", "x" * 600)
        self.write("src/b.py", "y" * 600)
        self.write("src/c.py", "z" * 600)
        self._p.stop()
        self._p2 = unittest.mock.patch.object(lap, "CODE_PATHS", ["src/*.py"])
        self._p2.start()
        self.addCleanup(self._p2.stop)
        got = lap.checkout_files(self.dir, char_budget=1000)
        self.assertEqual(len(got), 1)
        self.assertIn("src/a.py", got[0])

    def test_header_keeps_relative_path_for_subdirs(self):
        # run() derives mutation allowed_files from the block header; the
        # header must stay the worktree-relative path, not the basename
        self.write("src/lap.py", "x = 1\n")
        self._p.stop()
        self._p2 = unittest.mock.patch.object(lap, "CODE_PATHS", ["src/*.py"])
        self._p2.start()
        self.addCleanup(self._p2.stop)
        self.assertTrue(lap.checkout_files(self.dir)[0].startswith("=== src/lap.py ==="))

    def test_dotdir_still_excluded_under_wildcard_glob(self):
        self.write("src/a.py", "ok\n")
        os.makedirs(os.path.join(self.dir, ".factory"))
        with open(os.path.join(self.dir, ".factory", "leak.py"), "w") as f:
            f.write("secret\n")
        self._p.stop()
        self._p2 = unittest.mock.patch.object(lap, "CODE_PATHS", ["**/*.py"])
        self._p2.start()
        self.addCleanup(self._p2.stop)
        got = lap.checkout_files(self.dir)
        self.assertEqual(len(got), 1)
        self.assertNotIn("secret", "".join(got))

if __name__ == "__main__":
    unittest.main()
