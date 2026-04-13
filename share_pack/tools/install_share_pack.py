from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the ACL-X hybrid share pack")
    parser.add_argument("--pack-root", required=True)
    parser.add_argument("--python", default="python")
    parser.add_argument("--source-home")
    parser.add_argument("--install-root")
    return parser.parse_args(argv)


def extract_runtime_payload(pack_root: Path, install_root: Path) -> Path:
    payload_zip = pack_root / "payload" / "aclx_runtime_payload.zip"
    runtime_root = install_root / "runtime" / "aclx_repo"
    if install_root.exists():
        shutil.rmtree(install_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload_zip) as archive:
        archive.extractall(runtime_root)
    return runtime_root


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pack_root = Path(args.pack_root).resolve()
    install_root = Path(args.install_root).resolve() if args.install_root else (Path.home() / ".aclx-hybrid-share" / "current")
    runtime_root = extract_runtime_payload(pack_root, install_root)
    for candidate in (runtime_root, runtime_root / "src"):
        text = str(candidate)
        if text not in sys.path:
            sys.path.insert(0, text)
    from aclx.share_pack import install_extracted_share_pack

    result = install_extracted_share_pack(
        pack_root=pack_root,
        install_root=install_root,
        runtime_root=runtime_root,
        python_executable=args.python,
        source_home=Path(args.source_home).resolve() if args.source_home else None,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
