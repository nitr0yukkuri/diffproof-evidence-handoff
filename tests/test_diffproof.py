import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diffproof.py"
sys.path.insert(0, str(SCRIPT.parent))
import diffproof  # noqa: E402


class StatusTests(unittest.TestCase):
    def test_observed_success_and_failure(self):
        self.assertEqual(diffproof.classify_observation(launched=True, exit_code=0)["status"], "PASS")
        self.assertEqual(diffproof.classify_observation(launched=True, exit_code=3)["status"], "FAIL")

    def test_unavailable_skipped_and_unknown_are_distinct(self):
        absent = diffproof.classify_observation(launched=False, launch_error="Executable unavailable.")
        skipped = diffproof.classify_observation(launched=False, skip_reason="Not applicable on this platform.")
        unknown = diffproof.classify_observation(launched=True, exit_code=None)
        self.assertEqual(absent["status"], "NOT RUN")
        self.assertEqual(skipped["status"], "SKIPPED")
        self.assertEqual(unknown["status"], "UNKNOWN")

    def test_no_observation_never_passes(self):
        self.assertEqual(diffproof.classify_observation(launched=False)["status"], "NOT RUN")

    def test_real_child_exit_and_missing_executable_are_classified_from_observation(self):
        failed = subprocess.run([sys.executable, "-c", "raise SystemExit(4)"], capture_output=True, check=False)
        self.assertEqual(diffproof.classify_observation(launched=True, exit_code=failed.returncode)["status"], "FAIL")
        try:
            subprocess.run(["diffproof-command-absent-test"], capture_output=True, check=False)
        except FileNotFoundError as error:
            missing = diffproof.classify_observation(launched=False, launch_error=type(error).__name__)
        else:
            self.fail("The intentionally absent test executable unexpectedly existed.")
        self.assertEqual(missing["status"], "NOT RUN")


class DiscoveryTests(unittest.TestCase):
    def test_four_ecosystems_and_make_are_discovered_without_execution(self):
        root = Path(__file__).parent / "fixtures"
        result = diffproof.discover_candidates(root)
        ecosystems = {item["ecosystem"] for item in result["verification_candidates"]}
        self.assertTrue({"Node.js", "Go", "Python", "Rust", "Make"}.issubset(ecosystems))
        self.assertTrue(all(item["status"] == "NOT RUN" for item in result["verification_candidates"]))
        self.assertIn("Candidates only", result["execution_policy"])
        self.assertIn(".github/workflows/ci.yml", result["workflow_files"])

    def test_missing_commands_are_not_run(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            (root / "package.json").write_text(json.dumps({"scripts": {"start": "node app.js"}}), encoding="utf-8")
            result = diffproof.discover_candidates(root)
            self.assertEqual(result["verification_candidates"], [])
            self.assertIn("package.json", result["manifests_found"])

    def test_malformed_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            (root / "package.json").write_text("{bad", encoding="utf-8")
            result = diffproof.discover_candidates(root)
            self.assertEqual(result["verification_candidates"], [])
            self.assertTrue(any("malformed" in warning for warning in result["warnings"]))

    def test_risky_target_is_flagged_for_review_not_run(self):
        flags = diffproof._risk_flags("deploy", "run deployment task")
        self.assertIn("inspect-script-for-side-effects", flags)

    def test_external_symlink_manifest_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            external = Path(temp) / "outside.json"
            external.write_text(json.dumps({"scripts": {"test": "node --test"}}), encoding="utf-8")
            try:
                (root / "package.json").symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are not available in this environment.")
            result = diffproof.discover_candidates(root)
            self.assertEqual(result["verification_candidates"], [])
            self.assertTrue(any("ignored" in warning for warning in result["warnings"]))

    def test_external_workflow_directory_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            base = Path(temp)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            (outside / "workflows").mkdir(parents=True)
            (outside / "workflows" / "ci.yml").write_text("name: outside\n", encoding="utf-8")
            try:
                (root / ".github").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlinks are not available in this environment.")
            result = diffproof.discover_candidates(root)
            self.assertEqual(result["workflow_files"], [])
            self.assertTrue(any("outside the repository" in warning for warning in result["warnings"]))


class GitInspectionTests(unittest.TestCase):
    def init_repo(self, root: Path) -> None:
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True, text=True)

    def test_clean_repo_reports_no_change_and_only_actual_inspection_passes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            self.init_repo(root)
            result = diffproof.inspect_repository(root)
            self.assertFalse(result["changes_detected"])
            self.assertEqual(result["change_summary"], "NO CHANGE DETECTED")
            self.assertEqual([check["status"] for check in result["executed_inspection_checks"]], ["PASS", "PASS", "SKIPPED"])

    def test_whitespace_failure_is_reported(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            self.init_repo(root)
            (root / "changed.txt").write_text("trailing space  \n", encoding="utf-8")
            result = diffproof.inspect_repository(root)
            self.assertTrue(result["changes_detected"])
            self.assertIn("FAIL", {check["status"] for check in result["executed_inspection_checks"]})

    def test_non_git_directory_is_unknown_and_does_not_claim_checks_passed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            result = diffproof.inspect_repository(Path(temp))
            self.assertEqual(result["repository_status"], "UNKNOWN")
            self.assertIsNone(result["changes_detected"])
            self.assertNotIn("executed_inspection_checks", result)


if __name__ == "__main__":
    unittest.main()
