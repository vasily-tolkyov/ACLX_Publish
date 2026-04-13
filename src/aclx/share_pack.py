from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from .hybrid import infer_hybrid_tier
from .strategy_lock import verify_strategy_lock
from .supervisor import ACLXSupervisor
from .transcoder import ACLXTranscoder


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARE_PACK_ROOT = REPO_ROOT / "share_pack"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "share_pack"
DEFAULT_INSTALL_ROOT = Path.home() / ".aclx-hybrid-share" / "current"
DEFAULT_ISOLATED_HOME_NAME = "codex_home"
DEFAULT_RUNTIME_RELATIVE = Path("runtime") / "aclx_repo"
DEFAULT_VENV_RELATIVE = Path("runtime") / ".venv"
DEFAULT_REQUIRED_PYTHON = ">=3.11"
DEFAULT_INSTALL_MODE = "isolated-home"
DEFAULT_STABLE_HOME_ITEMS = ("auth.json", "config.toml", "agents", "skills", "memory.md")
PACK_NAME = "aclx_hybrid_share_pack"
RUNTIME_PAYLOAD_NAME = "aclx_runtime_payload.zip"
VENDORED_SKILLS = ("codex-subagent-router", "aclx-runtime", "acl-x-protocol")
AGENTS_TEMPLATE_NAME = "AGENTS.md.tmpl"
RUNTIME_SKILL_TEMPLATE_NAME = "aclx-runtime.SKILL.md.tmpl"
RUNTIME_INCLUDE = (
    "AGENTS.md",
    "README.md",
    "RUNTIME_GUIDE.md",
    "pyproject.toml",
    "configs",
    "ctx",
    "src/aclx",
)
AGENTS_TEMPLATE_REPLACEMENTS = (
    (
        (
            "Use an adaptive ACL-X runtime in this workspace.",
            "Use adaptive ACL-X routing in this workspace.",
        ),
        "Use an adaptive ACL-X runtime installed at `{{RUNTIME_ROOT}}`.",
    ),
    ("`ctx/session.py`", "`{{SESSION_PATH}}`"),
    ("`ctx/tool_summary.py`", "`{{TOOL_SUMMARY_PATH}}`"),
)
RUNTIME_SKILL_TEMPLATE_REPLACEMENTS = (
    (
        "Use this skill only after the current run actually needs reusable ACL-X machine state.",
        "Use this skill only after the current run actually needs reusable ACL-X machine state from `{{RUNTIME_ROOT}}`.",
    ),
)


def build_share_pack(output_root: str | Path | None = None) -> dict[str, Any]:
    verify_strategy_lock(project_root=REPO_ROOT)
    pack_version = _project_version(REPO_ROOT / "pyproject.toml")
    source_revision = _source_revision()
    output_dir = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_dir_name = f"{PACK_NAME}_{pack_version}"
    zip_path = output_dir / f"{pack_dir_name}.zip"
    manifest_path = output_dir / f"{pack_dir_name}.manifest.json"

    with tempfile.TemporaryDirectory(prefix="aclx-share-pack-") as tmp:
        temp_root = Path(tmp)
        stage_root = temp_root / pack_dir_name
        stage_root.mkdir(parents=True, exist_ok=True)
        payload_dir = stage_root / "payload"
        payload_dir.mkdir(parents=True, exist_ok=True)
        runtime_payload_zip = payload_dir / RUNTIME_PAYLOAD_NAME
        build_runtime_payload(runtime_payload_zip)
        _copy_tree(SHARE_PACK_ROOT / "skills", stage_root / "skills")
        _copy_tree(SHARE_PACK_ROOT / "tools", stage_root / "tools")
        _copy_tree(SHARE_PACK_ROOT / "templates", stage_root / "templates")
        write_dynamic_templates(stage_root / "templates")
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "install.ps1",
            stage_root / "install.ps1",
            {},
        )
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "verify.ps1",
            stage_root / "verify.ps1",
            {},
        )
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "start_hybrid_codex.ps1",
            stage_root / "start_hybrid_codex.ps1",
            {},
        )
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "uninstall.ps1",
            stage_root / "uninstall.ps1",
            {},
        )
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "INSTALL_TASK.md.tmpl",
            stage_root / "INSTALL_TASK.md",
            {"PACK_VERSION": pack_version},
        )
        payload_hashes = {
            relative_path.as_posix(): sha256_file(stage_root / relative_path)
            for relative_path in _stage_files(stage_root)
        }
        manifest = {
            "pack_name": "aclx-hybrid-share-pack",
            "pack_version": pack_version,
            "source_version": pack_version,
            "source_revision": source_revision,
            "required_python": DEFAULT_REQUIRED_PYTHON,
            "install_mode": DEFAULT_INSTALL_MODE,
            "generated_at": _timestamp(),
            "skills": list(VENDORED_SKILLS),
            "strategy_lock_sha256": sha256_file(REPO_ROOT / "configs" / "strategy_lock.json"),
            "payload_files": payload_hashes,
        }
        _render_template_to_file(
            SHARE_PACK_ROOT / "templates" / "pack_manifest.json.tmpl",
            stage_root / "pack_manifest.json",
            {
                "PACK_VERSION": manifest["pack_version"],
                "SOURCE_VERSION": manifest["source_version"],
                "SOURCE_REVISION": manifest["source_revision"],
                "REQUIRED_PYTHON": manifest["required_python"],
                "INSTALL_MODE": manifest["install_mode"],
                "GENERATED_AT": manifest["generated_at"],
                "SKILLS_JSON": json.dumps(manifest["skills"], ensure_ascii=True),
                "STRATEGY_LOCK_SHA256": manifest["strategy_lock_sha256"],
                "PAYLOAD_FILES_JSON": json.dumps(manifest["payload_files"], ensure_ascii=True, indent=2),
            },
        )
        if zip_path.exists():
            zip_path.unlink()
        _zip_dir(stage_root, zip_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    return {
        "pack_version": pack_version,
        "zip_path": str(zip_path),
        "manifest_path": str(manifest_path),
    }


def build_runtime_payload(destination_zip: str | Path) -> None:
    destination = Path(destination_zip)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in runtime_payload_paths():
            source = REPO_ROOT / relative
            if source.is_dir():
                for file_path in sorted(source.rglob("*")):
                    if not file_path.is_file() or _skip_runtime_path(file_path.relative_to(REPO_ROOT)):
                        continue
                    archive.write(file_path, arcname=file_path.relative_to(REPO_ROOT).as_posix())
            else:
                archive.write(source, arcname=relative.as_posix())


def runtime_payload_paths() -> list[Path]:
    return [Path(value) for value in RUNTIME_INCLUDE]


def sync_share_pack_assets(
    *,
    share_pack_root: str | Path | None = None,
    skill_sources: dict[str, str | Path] | None = None,
    agents_source: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(share_pack_root).resolve() if share_pack_root is not None else SHARE_PACK_ROOT
    (root / "skills").mkdir(parents=True, exist_ok=True)
    (root / "templates").mkdir(parents=True, exist_ok=True)
    synced_sources: dict[str, str] = {}
    for skill_name in VENDORED_SKILLS:
        source_skill = _resolve_skill_source(skill_name, skill_sources=skill_sources, env=env)
        _copy_tree(source_skill, root / "skills" / skill_name)
        synced_sources[skill_name] = str(source_skill)
    write_dynamic_templates(root / "templates", agents_source=agents_source, runtime_skill_source=root / "skills" / "aclx-runtime" / "SKILL.md")
    return {
        "share_pack_root": str(root),
        "agents_source": str((Path(agents_source) if agents_source is not None else REPO_ROOT / "AGENTS.md").resolve()),
        "skill_sources": synced_sources,
        "templates": {
            AGENTS_TEMPLATE_NAME: str((root / "templates" / AGENTS_TEMPLATE_NAME).resolve()),
            RUNTIME_SKILL_TEMPLATE_NAME: str((root / "templates" / RUNTIME_SKILL_TEMPLATE_NAME).resolve()),
        },
    }


def install_extracted_share_pack(
    *,
    pack_root: str | Path,
    install_root: str | Path,
    runtime_root: str | Path,
    python_executable: str,
    source_home: str | Path | None = None,
    install_dependencies: bool = True,
) -> dict[str, Any]:
    pack_root = Path(pack_root).resolve()
    install_root = Path(install_root).resolve()
    runtime_root = Path(runtime_root).resolve()
    source_home_path = Path(source_home).resolve() if source_home is not None else detect_codex_home()
    isolated_home = install_root / DEFAULT_ISOLATED_HOME_NAME
    venv_root = install_root / DEFAULT_VENV_RELATIVE

    ensure_python_311_plus(python_executable)
    copied_items = copy_stable_codex_home(source_home_path, isolated_home)
    if install_dependencies:
        create_virtualenv(python_executable, venv_root)
        install_runtime_editable(venv_python(venv_root), runtime_root)
    merge_vendored_skills(pack_root, isolated_home / "skills", runtime_root)
    (isolated_home / "AGENTS.md").write_text(
        render_installed_agents(runtime_root, template_root=pack_root / "templates"),
        encoding="utf-8",
    )
    launcher_path = write_installed_launcher(install_root, isolated_home, runtime_root, venv_root)
    install_info = {
        "success": True,
        "install_root": str(install_root),
        "isolated_home": str(isolated_home),
        "runtime_root": str(runtime_root),
        "venv_root": str(venv_root),
        "launcher_path": str(launcher_path),
        "source_home": str(source_home_path),
        "copied_items": copied_items,
    }
    (install_root / "install_info.json").write_text(json.dumps(install_info, ensure_ascii=True, indent=2), encoding="utf-8")
    return install_info


def verify_installed_share_pack(
    *,
    install_root: str | Path,
    runtime_root: str | Path,
    python_executable: str,
) -> dict[str, Any]:
    install_root = Path(install_root).resolve()
    runtime_root = Path(runtime_root).resolve()
    isolated_home = install_root / DEFAULT_ISOLATED_HOME_NAME
    venv_root = install_root / DEFAULT_VENV_RELATIVE
    checks: dict[str, Any] = {}

    try:
        verify_strategy_lock(project_root=runtime_root)
        checks["strategy_lock"] = {"ok": True}
    except Exception as exc:  # pragma: no cover - surfaced in JSON
        checks["strategy_lock"] = {"ok": False, "error": str(exc)}

    cli_result = run_cli_help(isolated_home, runtime_root, venv_root)
    checks["aclx_cli"] = cli_result

    expected_tiers = {"t0": "t0", "t1": "t1", "t2": "t2", "t3": "t3"}
    tier_results = {
        "t0": infer_hybrid_tier("Summarize the current task briefly.", profile="review"),
        "t1": infer_hybrid_tier("Delegate once to one reviewer pass and return the merged result.", profile="review"),
        "t2": infer_hybrid_tier(
            "Coordinate reusable shared state across the next phase.",
            profile="implement",
            shared_state=True,
            expected_handoffs=1,
        ),
        "t3": infer_hybrid_tier(
            "Run the verification loop, checkpoint and resume until the review is clean.",
            profile="review",
        ),
    }
    checks["tier_routing"] = {"ok": tier_results == expected_tiers, "results": tier_results}

    transcoder = ACLXTranscoder()
    encoded = transcoder.nl_to_aclx("Please plan the task and report the result.")
    decoded = transcoder.aclx_to_frame(encoded)
    round_trip = transcoder.codec.encode(decoded)
    checks["transcoder_round_trip"] = {
        "ok": encoded == round_trip and bool(transcoder.aclx_to_nl_gloss(encoded).strip()),
        "encoded_prefix": encoded.split("~", 1)[0],
    }

    supervisor = ACLXSupervisor()
    t2_payload = supervisor.build_payload(
        "Coordinate reusable shared state across the next phase.",
        cwd=str(runtime_root),
        outputs=[r"runtime\shared_state.aclx", r"reports\review_notes.md"],
        constraints=["review notes keep Risk and Evidence sections"],
        next_actions=["write shared state", "run tests"],
        stop_conditions=["missing shared artifact"],
        shared_state=True,
    )
    t3_payload = supervisor.build_payload(
        "Run the verification loop, checkpoint and resume until the review is clean.",
        cwd=str(runtime_root),
        outputs=[r"runtime\checkpoints\checkpoint_01.aclx", r"target_skill\SKILL.md"],
        constraints=["preserve generator critic refiner roles", "keep strict mode wording"],
        stop_conditions=["scope drift"],
        next_actions=["revise skill", "persist checkpoint"],
    )
    checks["supervisor_smoke"] = {
        "ok": (
            t2_payload.tier == "t2"
            and "Machine contract:" in t2_payload.codex_prompt
            and t3_payload.tier == "t3"
            and "Loop invariants:" in t3_payload.codex_prompt
        ),
        "t2_tier": t2_payload.tier,
        "t3_tier": t3_payload.tier,
    }

    success = all(check.get("ok") for check in checks.values())
    return {
        "success": success,
        "install_root": str(install_root),
        "isolated_home": str(isolated_home),
        "runtime_root": str(runtime_root),
        "python_executable": python_executable,
        "checks": checks,
    }


def detect_codex_home(env: dict[str, str] | None = None) -> Path:
    values = env or os.environ
    override = values.get("CODEX_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def copy_stable_codex_home(source_home: str | Path, destination_home: str | Path) -> list[str]:
    source = Path(source_home).resolve()
    destination = Path(destination_home).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    required = {"auth.json", "config.toml"}
    for item in DEFAULT_STABLE_HOME_ITEMS:
        source_path = source / item
        if not source_path.exists():
            if item in required:
                raise FileNotFoundError(f"Missing required Codex home item: {source_path}")
            continue
        target_path = destination / item
        if source_path.is_dir():
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.copytree(source_path, target_path)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        copied.append(item)
    return copied


def render_installed_agents(runtime_root: str | Path, *, template_root: str | Path | None = None) -> str:
    root = Path(runtime_root).resolve()
    return render_template(
        _templates_root(template_root) / AGENTS_TEMPLATE_NAME,
        {
            "RUNTIME_ROOT": str(root),
            "SESSION_PATH": str(root / "ctx" / "session.py"),
            "TOOL_SUMMARY_PATH": str(root / "ctx" / "tool_summary.py"),
        },
    )


def render_installed_runtime_skill(runtime_root: str | Path, *, template_root: str | Path | None = None) -> str:
    return render_template(
        _templates_root(template_root) / RUNTIME_SKILL_TEMPLATE_NAME,
        {"RUNTIME_ROOT": str(Path(runtime_root).resolve())},
    )


def merge_vendored_skills(pack_root: str | Path, skills_dir: str | Path, runtime_root: str | Path) -> None:
    pack = Path(pack_root).resolve()
    destination = Path(skills_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for skill_name in VENDORED_SKILLS:
        source_skill = pack / "skills" / skill_name
        target_skill = destination / skill_name
        _copy_tree(source_skill, target_skill)
        if skill_name == "aclx-runtime":
            (target_skill / "SKILL.md").write_text(
                render_installed_runtime_skill(runtime_root, template_root=pack / "templates"),
                encoding="utf-8",
            )


def write_installed_launcher(
    install_root: str | Path,
    isolated_home: str | Path,
    runtime_root: str | Path,
    venv_root: str | Path,
) -> Path:
    install_path = Path(install_root).resolve()
    isolated_path = Path(isolated_home).resolve()
    runtime_path = Path(runtime_root).resolve()
    scripts_dir = venv_scripts(venv_root)
    launcher_path = install_path / "start_hybrid_codex.ps1"
    text = (
        "param(\n"
        "    [Parameter(ValueFromRemainingArguments = $true)]\n"
        "    [string[]]$CodexArgs\n"
        ")\n\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"$TargetHome = '{isolated_path}'\n"
        f"$RuntimeRoot = '{runtime_path}'\n"
        f"$VenvScripts = '{scripts_dir}'\n"
        "$PreviousCodeHome = $env:CODEX_HOME\n"
        "$PreviousRuntimeRoot = $env:ACLX_RUNTIME_ROOT\n"
        "$PreviousPath = $env:PATH\n"
        "$env:CODEX_HOME = $TargetHome\n"
        "$env:ACLX_RUNTIME_ROOT = $RuntimeRoot\n"
        "$env:PATH = $VenvScripts + ';' + $env:PATH\n"
        "$Command = $null\n"
        "foreach ($Candidate in @('codex.cmd', 'codex.exe', 'codex')) {\n"
        "    try {\n"
        "        $Resolved = Get-Command $Candidate -ErrorAction Stop\n"
        "        $Command = $Resolved.Source\n"
        "        break\n"
        "    } catch {\n"
        "    }\n"
        "}\n"
        "if (-not $Command) {\n"
        "    throw 'codex executable not found in PATH.'\n"
        "}\n"
        "& $Command @CodexArgs\n"
        "$ExitCode = $LASTEXITCODE\n"
        "if ($null -ne $PreviousCodeHome) { $env:CODEX_HOME = $PreviousCodeHome } else { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue }\n"
        "if ($null -ne $PreviousRuntimeRoot) { $env:ACLX_RUNTIME_ROOT = $PreviousRuntimeRoot } else { Remove-Item Env:ACLX_RUNTIME_ROOT -ErrorAction SilentlyContinue }\n"
        "$env:PATH = $PreviousPath\n"
        "exit $ExitCode\n"
    )
    launcher_path.write_text(text, encoding="utf-8")
    return launcher_path


def run_cli_help(isolated_home: str | Path, runtime_root: str | Path, venv_root: str | Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(Path(isolated_home).resolve())
    env["ACLX_RUNTIME_ROOT"] = str(Path(runtime_root).resolve())
    env["PATH"] = str(venv_scripts(venv_root)) + os.pathsep + env.get("PATH", "")
    command = resolve_aclx_command(venv_root)
    argv = [str(command), "--help"]
    if command.suffix.lower() in {".cmd", ".bat"}:
        argv = ["cmd", "/c", str(command), "--help"]
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return {
        "ok": result.returncode == 0 and "ACL-X CLI" in output,
        "returncode": result.returncode,
        "output_snippet": output[:200],
    }


def create_virtualenv(python_executable: str, venv_root: str | Path) -> None:
    target = Path(venv_root).resolve()
    if target.exists():
        shutil.rmtree(target)
    subprocess.run([python_executable, "-m", "venv", str(target)], check=True)


def install_runtime_editable(venv_python_path: str | Path, runtime_root: str | Path) -> None:
    python_path = str(Path(venv_python_path).resolve())
    subprocess.run([python_path, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([python_path, "-m", "pip", "install", "-e", str(Path(runtime_root).resolve())], check=True)


def ensure_python_311_plus(python_executable: str) -> None:
    result = subprocess.run(
        [python_executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    version_text = (result.stdout or "").strip()
    major, minor = (int(part) for part in version_text.split(".")[:2])
    if (major, minor) < (3, 11):
        raise RuntimeError(f"Python 3.11+ is required, got {version_text}")


def venv_python(venv_root: str | Path) -> Path:
    return Path(venv_root).resolve() / "Scripts" / "python.exe"


def venv_scripts(venv_root: str | Path) -> Path:
    return Path(venv_root).resolve() / "Scripts"


def render_template(path: str | Path, values: dict[str, str]) -> str:
    text = Path(path).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def build_agents_template(*, agents_source: str | Path | None = None) -> str:
    source_path = Path(agents_source).resolve() if agents_source is not None else REPO_ROOT / "AGENTS.md"
    text = source_path.read_text(encoding="utf-8")
    return _apply_required_replacements(text, AGENTS_TEMPLATE_REPLACEMENTS, source_path=source_path)


def build_runtime_skill_template(*, runtime_skill_source: str | Path | None = None) -> str:
    source_path = (
        Path(runtime_skill_source).resolve()
        if runtime_skill_source is not None
        else SHARE_PACK_ROOT / "skills" / "aclx-runtime" / "SKILL.md"
    )
    text = source_path.read_text(encoding="utf-8")
    return _apply_required_replacements(text, RUNTIME_SKILL_TEMPLATE_REPLACEMENTS, source_path=source_path)


def write_dynamic_templates(
    template_root: str | Path,
    *,
    agents_source: str | Path | None = None,
    runtime_skill_source: str | Path | None = None,
) -> None:
    template_dir = Path(template_root).resolve()
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / AGENTS_TEMPLATE_NAME).write_text(
        build_agents_template(agents_source=agents_source),
        encoding="utf-8",
        newline="\n",
    )
    (template_dir / RUNTIME_SKILL_TEMPLATE_NAME).write_text(
        build_runtime_skill_template(runtime_skill_source=runtime_skill_source),
        encoding="utf-8",
        newline="\n",
    )


def _templates_root(template_root: str | Path | None) -> Path:
    if template_root is None:
        return SHARE_PACK_ROOT / "templates"
    return Path(template_root).resolve()


def sha256_file(path: str | Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _resolve_skill_source(
    skill_name: str,
    *,
    skill_sources: dict[str, str | Path] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    if skill_sources is not None and skill_name in skill_sources:
        return Path(skill_sources[skill_name]).resolve()
    for candidate in _skill_source_candidates(skill_name, env=env):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Unable to resolve local source for share-pack skill: {skill_name}")


def _skill_source_candidates(skill_name: str, *, env: dict[str, str] | None = None) -> list[Path]:
    home = _user_home(env)
    codex_home = detect_codex_home(env)
    candidates: list[Path] = []
    if skill_name == "codex-subagent-router":
        candidates.extend(
            (
                codex_home / "skills" / skill_name,
                home / ".codex" / "skills" / skill_name,
            )
        )
    elif skill_name == "aclx-runtime":
        candidates.extend(
            (
                home / "plugins" / "aclx-runtime" / "skills" / "aclx-runtime",
                home / ".codex" / "plugins" / "aclx-runtime" / "skills" / "aclx-runtime",
                codex_home / "skills" / skill_name,
                home / ".codex" / "skills" / skill_name,
            )
        )
    elif skill_name == "acl-x-protocol":
        candidates.extend(
            (
                codex_home / "skills" / skill_name,
                home / ".codex" / "skills" / skill_name,
                home / "skills" / skill_name,
            )
        )
    else:
        raise KeyError(f"Unknown vendored skill: {skill_name}")
    return _dedupe_paths(candidates)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        unique.append(Path(key))
    return unique


def _user_home(env: dict[str, str] | None = None) -> Path:
    values = env or os.environ
    home = values.get("USERPROFILE") or values.get("HOME")
    if home:
        return Path(home).expanduser().resolve()
    return Path.home().resolve()


def _apply_required_replacements(
    text: str,
    replacements: tuple[tuple[str | tuple[str, ...], str], ...],
    *,
    source_path: Path,
) -> str:
    updated = text
    for old, new in replacements:
        if isinstance(old, tuple):
            matched = next((candidate for candidate in old if candidate in updated), "")
            if not matched:
                raise RuntimeError(f"Expected to find one of {old!r} in {source_path}")
            updated = updated.replace(matched, new)
            continue
        if old not in updated:
            raise RuntimeError(f"Expected to find {old!r} in {source_path}")
        updated = updated.replace(old, new)
    return updated


def _project_version(pyproject_path: Path) -> str:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8-sig"))
    return str(data["project"]["version"])


def _source_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        return "unavailable"
    return (result.stdout or "").strip() or "unavailable"


def _render_template_to_file(template_path: Path, output_path: Path, values: dict[str, str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_template(template_path, values), encoding="utf-8")


def _stage_files(stage_root: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in sorted(stage_root.rglob("*")):
        if file_path.is_file() and file_path.name != "pack_manifest.json":
            files.append(file_path.relative_to(stage_root))
    return files


def _zip_dir(stage_root: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(stage_root.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(stage_root.parent).as_posix())


def _skip_runtime_path(relative_path: Path) -> bool:
    parts = set(relative_path.parts)
    if "__pycache__" in parts:
        return True
    if relative_path.suffix == ".pyc":
        return True
    return False


def _timestamp() -> str:
    import time

    return time.strftime("%Y-%m-%d %H:%M:%S")


def resolve_aclx_command(venv_root: str | Path) -> Path:
    scripts_dir = venv_scripts(venv_root)
    for name in ("aclx.exe", "aclx.cmd", "aclx.bat", "aclx"):
        candidate = scripts_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"aclx command not found under {scripts_dir}")
