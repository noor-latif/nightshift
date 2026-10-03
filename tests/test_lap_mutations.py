import json
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

    def test_near_miss_localizes_first_divergence(self):
        actual = 'state["issues"][str(claim["issue"])] ["disposition"] = "merged"'
        anchor = actual.replace(')] ["disposition"]', ')]["disposition"]')
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("header\\n" + actual + "\\nfooter\\n")
        ok, detail, results = lap.apply_mutations(
            [mut("app.py", "header\\n" + anchor + "\\nfooter\\n", "ignored")], self.dir)
        self.assertFalse(ok)
        self.assertIn("first divergence", detail)
        self.assertIn("expected line", detail)
        self.assertIn("actual file line", detail)
        self.assertIn("first divergence", results[0]["diagnosis"])
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(),
                         "header\\n" + actual + "\\nfooter\\n")

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

    def test_newline_terminated_anchor_keeps_the_line_break(self):
        # K3: find="A\nB\n" on "A\nB\nC\n" must replace exactly those two
        # lines — the anchor's final newline is content, not a boundary.
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
class TestAnchorFeedback(unittest.TestCase):
    def test_previous_apply_diagnosis_reaches_retry_prompt(self):
        result_path = os.path.join(tempfile.mkdtemp(), "lap-result.json")
        with unittest.mock.patch.object(lap, "RESULT_PATH", result_path), \
             unittest.mock.patch.object(lap.agent, "implementer_prompt",
                                        return_value="base prompt"):
            lap._save_implementer_feedback(
                19, "first divergence at anchor offset 513; actual file line differs", [])
            prompt = lap._implementer_prompt(
                {"title": "t", "body": "b"}, "criteria", 19, [])
        self.assertIn("first divergence at anchor offset 513", prompt)
        self.assertIn("Correct this mutation-apply failure", prompt)


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

class TestCreateMutations(unittest.TestCase):
    """Explicit new-file creation: opt-in, allowlisted, never overwriting.

    The historical edit-only contract is unchanged when FACTORY_NEW_FILES is
    empty (the default); these cover the one new write shape.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        git(self.dir, "init", "-q")
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(self.dir, "add", "-A")
        git(self.dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self._p = unittest.mock.patch.object(lap, "NEW_FILES", ["index.html"])
        self._p.start()
        self.addCleanup(self._p.stop)

    def create(self, file, content):
        return {"file": file, "find": "", "replace": content, "create": True}

    def test_create_writes_allowlisted_new_file(self):
        ok, detail, results = lap.apply_mutations(
            [self.create("index.html", "<h1>hi</h1>\n")], self.dir)
        self.assertTrue(ok, detail)
        self.assertEqual(open(os.path.join(self.dir, "index.html")).read(), "<h1>hi</h1>\n")
        self.assertIn("index.html", lap.applied_files(self.dir))
        self.assertTrue(results[0]["create"])

    def test_create_rejected_when_path_not_allowlisted(self):
        m, err = lap.extract_mutations(json.dumps([self.create("evil.html", "x")]),
                                       allowed_files=set())
        self.assertIsNone(m)
        self.assertIn("FACTORY_NEW_FILES", err)

    def test_create_rejected_when_file_already_in_checkout(self):
        m, err = lap.extract_mutations(json.dumps([self.create("index.html", "x")]),
                                       allowed_files={"index.html"})
        self.assertIsNone(m)
        self.assertIn("already", err)

    def test_create_rejects_non_boolean_flag_and_non_string_content(self):
        bad = [{"file": "index.html", "find": "", "replace": "x", "create": "yes"},
               {"file": "index.html", "find": "", "replace": 3, "create": True},
               {"file": "index.html", "find": "anchor", "replace": "x", "create": True}]
        for payload in bad:
            m, err = lap.extract_mutations(json.dumps([payload]), allowed_files=set())
            self.assertIsNone(m, payload)
            self.assertIn("mutation-parse", err)

    def test_create_path_validator_rejects_escape_shapes(self):
        for bad in ("../index.html", "/tmp/index.html", "sub/../index.html",
                    "a\\b.html", "./index.html"):
            with unittest.mock.patch.object(lap, "NEW_FILES", [bad]):
                self.assertIsNotNone(lap._create_path_error(bad, self.dir), bad)

    def test_create_rejects_symlinked_parent_escaping_checkout(self):
        outside = tempfile.mkdtemp()
        os.symlink(outside, os.path.join(self.dir, "link"))
        with unittest.mock.patch.object(lap, "NEW_FILES", ["link/evil.html"]):
            err = lap._create_path_error("link/evil.html", self.dir)
        self.assertIn("outside the checkout", err)
        self.assertEqual(os.listdir(outside), [])

    def test_duplicate_create_of_one_path_rejected(self):
        ok, detail, _ = lap.apply_mutations(
            [self.create("index.html", "a"), self.create("index.html", "b")], self.dir)
        self.assertFalse(ok)
        self.assertIn("duplicate", detail)

    def test_create_never_overwrites_an_existing_file(self):
        # simulate the target appearing between validation and write: the
        # exclusive open must refuse rather than clobber
        with open(os.path.join(self.dir, "index.html"), "w") as f:
            f.write("keep me\n")
        with unittest.mock.patch.object(lap, "_create_path_error", return_value=None):
            ok, detail, _ = lap.apply_mutations(
                [self.create("index.html", "new")], self.dir)
        self.assertFalse(ok)
        self.assertIn("cannot create", detail)
        self.assertEqual(open(os.path.join(self.dir, "index.html")).read(), "keep me\n")

    def test_edit_and_create_combine_in_one_set(self):
        ok, detail, _ = lap.apply_mutations(
            [mut("app.py", "x = 1", "x = 2"), self.create("index.html", "<p>ok</p>")],
            self.dir)
        self.assertTrue(ok, detail)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 2\n")
        self.assertEqual(open(os.path.join(self.dir, "index.html")).read(), "<p>ok</p>")

    def test_glob_entry_authorizes_matching_create_end_to_end(self):
        with unittest.mock.patch.object(lap, "NEW_FILES", ["page*.js"]):
            ok, detail, results = lap.apply_mutations(
                [self.create("page.js", "console.log(1)\n")], self.dir)
            self.assertTrue(ok, detail)
            self.assertTrue(results[0]["applied"])
            # the existing-file rejection applies to a glob-authorized name too
            self.assertIn("already exists", lap._create_path_error("page.js", self.dir))
        self.assertEqual(open(os.path.join(self.dir, "page.js")).read(),
                         "console.log(1)\n")

    def test_glob_entry_authorizes_subdirectory_path(self):
        os.makedirs(os.path.join(self.dir, "assets"))
        with unittest.mock.patch.object(lap, "NEW_FILES", ["assets/*"]):
            self.assertIsNone(lap._create_path_error("assets/logo.svg", self.dir))
            m, err = lap.extract_mutations(
                json.dumps([self.create("assets/logo.svg", "x")]), allowed_files=set())
        self.assertIsNone(err)
        self.assertEqual(m[0]["file"], "assets/logo.svg")

    def test_glob_char_class_and_question_mark(self):
        with unittest.mock.patch.object(lap, "NEW_FILES", ["img[12].png", "page?.js"]):
            self.assertIsNone(lap._create_path_error("img1.png", self.dir))
            self.assertIsNone(lap._create_path_error("page1.js", self.dir))
            self.assertIsNotNone(lap._create_path_error("img3.png", self.dir))
            self.assertIsNotNone(lap._create_path_error("page10.js", self.dir))

    def test_glob_entry_rejects_non_matching_path(self):
        with unittest.mock.patch.object(lap, "NEW_FILES", ["assets/*"]):
            err = lap._create_path_error("evil.html", self.dir)
            m, perr = lap.extract_mutations(
                json.dumps([self.create("evil.html", "x")]), allowed_files=set())
        self.assertIn("FACTORY_NEW_FILES", err)
        self.assertIsNone(m)
        self.assertIn("FACTORY_NEW_FILES", perr)

    def test_glob_entry_still_rejects_dotdot_abs_and_backslash(self):
        # '*' matches every one of these strings, so only the lexical gate
        # stands between a pattern and an escape
        with unittest.mock.patch.object(lap, "NEW_FILES", ["assets/*", "*"]):
            for bad in ("assets/../evil.html", "../evil.html", "/tmp/evil.html",
                        "a\\b.html", "./evil.html", "assets//evil.html"):
                self.assertIsNotNone(lap._create_path_error(bad, self.dir), bad)
            ok, detail, _ = lap.apply_mutations(
                [self.create("assets/../evil.html", "x")], self.dir)
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "evil.html")))

    def test_glob_entry_rejects_symlinked_parent_escape(self):
        outside = tempfile.mkdtemp()
        os.symlink(outside, os.path.join(self.dir, "link"))
        with unittest.mock.patch.object(lap, "NEW_FILES", ["link/*"]):
            err = lap._create_path_error("link/evil.html", self.dir)
        self.assertIn("outside the checkout", err)
        self.assertEqual(os.listdir(outside), [])

    def test_bare_star_authorizes_any_plain_relative_create(self):
        # documented consequence: '*' crosses '/', so a bare '*' entry is the
        # whole plain-relative create surface
        with unittest.mock.patch.object(lap, "NEW_FILES", ["*"]):
            self.assertIsNone(lap._create_path_error("index.html", self.dir))
            self.assertIsNone(lap._create_path_error("deep/nested/new.txt", self.dir))

    def test_literal_entry_stays_exact(self):
        with unittest.mock.patch.object(lap, "NEW_FILES", ["index.html"]):
            self.assertIsNotNone(lap._create_path_error("index.html.bak", self.dir))
            self.assertIsNotNone(lap._create_path_error("assets/logo.svg", self.dir))

class TestLocalTaskFile(unittest.TestCase):
    """A trusted operator task file replaces gh for laps whose task is not a
    GitHub issue; malformed input must never reach a paid call."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "task.json")

    def test_reads_local_task_instead_of_gh(self):
        with open(self.path, "w") as f:
            json.dump({"title": "Local task", "body": "Acceptance criteria:\n- one"}, f)
        def boom(*_a, **_k):
            raise AssertionError("gh must not be called when a task file is set")
        with unittest.mock.patch.object(lap, "TASK_FILE", self.path), \
             unittest.mock.patch.object(lap, "_gh", boom):
            data = lap.issue_data(9001)
        self.assertEqual(data, {"title": "Local task",
                                "body": "Acceptance criteria:\n- one"})

    def test_malformed_task_file_fails_loud(self):
        for payload in ({"title": "t"}, {"body": "b"}, {"title": "", "body": "b"},
                        {"title": "t", "body": "   "}, {"title": 1, "body": "b"},
                        [1, 2], "text"):
            with open(self.path, "w") as f:
                json.dump(payload, f)
            with unittest.mock.patch.object(lap, "TASK_FILE", self.path):
                with self.assertRaises(ValueError):
                    lap.issue_data(9001)

    def test_gh_path_unchanged_when_no_task_file(self):
        with unittest.mock.patch.object(lap, "TASK_FILE", ""), \
             unittest.mock.patch.object(lap, "_gh",
                                        lambda _args: json.dumps({"title": "T", "body": "B"})):
            self.assertEqual(lap.issue_data(7), {"title": "T", "body": "B"})

if __name__ == "__main__":
    unittest.main()
