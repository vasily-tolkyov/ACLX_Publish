from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.release_validation_ab as release_validation_ab


class ReleaseValidationABTests(unittest.TestCase):
    def test_prepare_home_can_build_t0_minimal_hybrid_home_without_agents_or_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_home = root / "current_home"
            current_home.mkdir(parents=True, exist_ok=True)
            (current_home / "auth.json").write_text("{}", encoding="utf-8")
            (current_home / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")
            plugin_root = root / "plugin"
            dest_home = root / "dest_home"

            with patch.object(release_validation_ab, "CURRENT_CODEX_HOME", current_home), patch.object(
                release_validation_ab, "PLUGIN_SKILL_ROOT", plugin_root
            ):
                release_validation_ab.prepare_home(
                    dest_home,
                    hybrid=True,
                    agents_text="t0-only\n",
                    copy_agents=False,
                    copy_skills=False,
                )

            self.assertTrue((dest_home / "auth.json").exists())
            self.assertTrue((dest_home / "config.toml").exists())
            self.assertEqual((dest_home / "AGENTS.md").read_text(encoding="utf-8"), "t0-only\n")
            self.assertFalse((dest_home / "agents").exists())
            self.assertFalse((dest_home / "skills").exists())

    def test_run_gate_tests_includes_contract_and_formal_matrix_checks(self) -> None:
        with patch.object(release_validation_ab.subprocess, "run") as run_mock:
            run_mock.return_value = unittest.mock.Mock(returncode=0, stdout="", stderr="")
            release_validation_ab.run_gate_tests()
        command = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args.args[0]
        self.assertIn("tests.test_contract", command)
        self.assertIn("tests.test_formal_heavy_matrix", command)


if __name__ == "__main__":
    unittest.main()
