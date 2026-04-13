from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from aclx.share_pack import (
    SHARE_PACK_ROOT,
    build_agents_template,
    build_runtime_payload,
    build_runtime_skill_template,
    build_share_pack,
    copy_stable_codex_home,
    install_extracted_share_pack,
    sync_share_pack_assets,
    verify_installed_share_pack,
)


class SharePackTests(unittest.TestCase):
    def test_build_share_pack_contains_scaffold_and_trimmed_runtime_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_share_pack(output_root=tmp)
            zip_path = Path(result["zip_path"])
            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                prefix = zip_path.stem + "/"
                self.assertIn(prefix + "install.ps1", names)
                self.assertIn(prefix + "verify.ps1", names)
                self.assertIn(prefix + "INSTALL_TASK.md", names)
                self.assertIn(prefix + "pack_manifest.json", names)
                self.assertIn(prefix + "skills/codex-subagent-router/SKILL.md", names)
                self.assertIn(prefix + "templates/AGENTS.md.tmpl", names)
                self.assertEqual(
                    archive.read(prefix + "templates/AGENTS.md.tmpl").decode("utf-8"),
                    build_agents_template(),
                )
                self.assertEqual(
                    archive.read(prefix + "templates/aclx-runtime.SKILL.md.tmpl").decode("utf-8"),
                    build_runtime_skill_template(),
                )

                payload_bytes = archive.read(prefix + "payload/aclx_runtime_payload.zip")
            with zipfile.ZipFile(io.BytesIO(payload_bytes)) as payload:
                payload_names = set(payload.namelist())
                self.assertIn("src/aclx/share_pack.py", payload_names)
                self.assertIn("ctx/session.py", payload_names)
                self.assertIn("configs/strategy_lock.json", payload_names)
                self.assertIn("pyproject.toml", payload_names)
                self.assertNotIn("tests/test_share_pack.py", payload_names)
                self.assertFalse(any(name.startswith("artifacts/") for name in payload_names))
                self.assertFalse(any(name.startswith("backups/") for name in payload_names))
                self.assertFalse(any(name.startswith("share_pack/") for name in payload_names))

    def test_install_extracted_share_pack_copies_only_stable_home_and_renders_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_home = root / "source_home"
            source_home.mkdir(parents=True, exist_ok=True)
            (source_home / "auth.json").write_text("{}", encoding="utf-8")
            (source_home / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")
            (source_home / "memory.md").write_text("remember\n", encoding="utf-8")
            (source_home / "agents").mkdir()
            (source_home / "agents" / "custom.toml").write_text("name = 'custom'\n", encoding="utf-8")
            (source_home / "skills").mkdir()
            (source_home / "skills" / "existing").mkdir()
            (source_home / "skills" / "existing" / "SKILL.md").write_text("# Existing\n", encoding="utf-8")
            (source_home / "plugins" / "cache").mkdir(parents=True)
            (source_home / "plugins" / "cache" / "ignore.txt").write_text("ignore\n", encoding="utf-8")
            (source_home / ".sandbox-bin").mkdir()
            (source_home / ".sandbox-bin" / "codex.exe").write_text("binary\n", encoding="utf-8")

            install_root = root / "install_root"
            runtime_root = install_root / "runtime" / "aclx_repo"
            runtime_root.mkdir(parents=True, exist_ok=True)

            result = install_extracted_share_pack(
                pack_root=SHARE_PACK_ROOT,
                install_root=install_root,
                runtime_root=runtime_root,
                python_executable=sys.executable,
                source_home=source_home,
                install_dependencies=False,
            )

            isolated_home = install_root / "codex_home"
            self.assertTrue((isolated_home / "auth.json").exists())
            self.assertTrue((isolated_home / "config.toml").exists())
            self.assertTrue((isolated_home / "memory.md").exists())
            self.assertTrue((isolated_home / "agents" / "custom.toml").exists())
            self.assertTrue((isolated_home / "skills" / "existing" / "SKILL.md").exists())
            self.assertFalse((isolated_home / "plugins").exists())
            self.assertFalse((isolated_home / ".sandbox-bin").exists())

            agents_text = (isolated_home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(str(runtime_root), agents_text)
            runtime_skill = (isolated_home / "skills" / "aclx-runtime" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(str(runtime_root), runtime_skill)
            launcher_text = (install_root / "start_hybrid_codex.ps1").read_text(encoding="utf-8")
            self.assertIn("$env:CODEX_HOME = $TargetHome", launcher_text)
            self.assertIn(str(isolated_home), launcher_text)
            self.assertEqual(result["source_home"], str(source_home.resolve()))

    def test_sync_share_pack_assets_copies_current_sources_and_regenerates_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            share_pack_root = root / "share_pack"
            (share_pack_root / "skills").mkdir(parents=True, exist_ok=True)
            (share_pack_root / "templates").mkdir(parents=True, exist_ok=True)

            agents_source = root / "AGENTS.md"
            agents_source.write_text(
                "# Local ACL-X Runtime\n\n"
                "Use an adaptive ACL-X runtime in this workspace.\n\n"
                "- use `ctx/session.py`\n"
                "- use `ctx/tool_summary.py`\n",
                encoding="utf-8",
            )

            router_source = root / "sources" / "codex-subagent-router"
            (router_source / "references").mkdir(parents=True, exist_ok=True)
            (router_source / "SKILL.md").write_text("router-current\n", encoding="utf-8")
            (router_source / "references" / "routing-matrix.md").write_text("router-ref\n", encoding="utf-8")

            runtime_source = root / "sources" / "aclx-runtime"
            (runtime_source / "agents").mkdir(parents=True, exist_ok=True)
            (runtime_source / "SKILL.md").write_text(
                "---\nname: aclx-runtime\n---\n\n"
                "# ACL-X Runtime\n\n"
                "Use this skill only after the current run actually needs reusable ACL-X machine state.\n",
                encoding="utf-8",
            )
            (runtime_source / "agents" / "openai.yaml").write_text("runtime-agent\n", encoding="utf-8")

            protocol_source = root / "sources" / "acl-x-protocol"
            (protocol_source / "references").mkdir(parents=True, exist_ok=True)
            (protocol_source / "SKILL.md").write_text("protocol-current\n", encoding="utf-8")
            (protocol_source / "references" / "protocol.md").write_text("protocol-ref\n", encoding="utf-8")

            result = sync_share_pack_assets(
                share_pack_root=share_pack_root,
                skill_sources={
                    "codex-subagent-router": router_source,
                    "aclx-runtime": runtime_source,
                    "acl-x-protocol": protocol_source,
                },
                agents_source=agents_source,
            )

            self.assertEqual((share_pack_root / "skills" / "codex-subagent-router" / "SKILL.md").read_text(encoding="utf-8"), "router-current\n")
            self.assertEqual(
                (share_pack_root / "skills" / "codex-subagent-router" / "references" / "routing-matrix.md").read_text(encoding="utf-8"),
                "router-ref\n",
            )
            self.assertEqual((share_pack_root / "skills" / "acl-x-protocol" / "SKILL.md").read_text(encoding="utf-8"), "protocol-current\n")
            self.assertEqual(
                (share_pack_root / "templates" / "AGENTS.md.tmpl").read_text(encoding="utf-8"),
                build_agents_template(agents_source=agents_source),
            )
            self.assertEqual(
                (share_pack_root / "templates" / "aclx-runtime.SKILL.md.tmpl").read_text(encoding="utf-8"),
                build_runtime_skill_template(runtime_skill_source=runtime_source / "SKILL.md"),
            )
            self.assertEqual(result["skill_sources"]["aclx-runtime"], str(runtime_source.resolve()))

    def test_verify_installed_share_pack_reports_success_for_trimmed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_root = root / "install_root"
            runtime_root = install_root / "runtime" / "aclx_repo"
            runtime_root.mkdir(parents=True, exist_ok=True)
            payload_zip = root / "runtime_payload.zip"
            build_runtime_payload(payload_zip)
            with zipfile.ZipFile(payload_zip) as archive:
                archive.extractall(runtime_root)

            isolated_home = install_root / "codex_home"
            isolated_home.mkdir(parents=True, exist_ok=True)
            (isolated_home / "auth.json").write_text("{}", encoding="utf-8")
            (isolated_home / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")

            scripts_dir = install_root / "runtime" / ".venv" / "Scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            aclx_cmd = scripts_dir / "aclx.cmd"
            aclx_cmd.write_text("@echo off\r\necho ACL-X CLI\r\n", encoding="utf-8")

            result = verify_installed_share_pack(
                install_root=install_root,
                runtime_root=runtime_root,
                python_executable=sys.executable,
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["checks"]["aclx_cli"]["ok"])
            self.assertTrue(result["checks"]["tier_routing"]["ok"])
            self.assertTrue(result["checks"]["transcoder_round_trip"]["ok"])
            self.assertTrue(result["checks"]["supervisor_smoke"]["ok"])


if __name__ == "__main__":
    unittest.main()
