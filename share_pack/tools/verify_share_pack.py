from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the ACL-X hybrid share pack installation")
    parser.add_argument("--pack-root", required=True)
    parser.add_argument("--python", default="python")
    parser.add_argument("--install-root")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    install_root = Path(args.install_root).resolve() if args.install_root else (Path.home() / ".aclx-hybrid-share" / "current")
    runtime_root = install_root / "runtime" / "aclx_repo"
    for candidate in (runtime_root, runtime_root / "src"):
        text = str(candidate)
        if text not in sys.path:
            sys.path.insert(0, text)
    from aclx.share_pack import verify_installed_share_pack

    result = verify_installed_share_pack(
        install_root=install_root,
        runtime_root=runtime_root,
        python_executable=args.python,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
