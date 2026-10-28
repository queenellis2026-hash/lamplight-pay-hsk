"""Compile contracts with solcx and save artifacts to build/.

Usage: .venv/bin/python scripts/compile.py
Requires: py-solc-x (installs solc 0.8.24 on first run).
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import solcx  # noqa: E402

SOLC_VERSION = "0.8.24"


def main() -> None:
    try:
        solcx.get_installed_solc_versions()
    except Exception:
        pass
    if SOLC_VERSION not in {str(v) for v in solcx.get_installed_solc_versions()}:
        print(f"installing solc {SOLC_VERSION} ...")
        solcx.install_solc(SOLC_VERSION)
    solcx.set_solc_version(SOLC_VERSION)

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    for name in ("MockUSDC", "AgentEscrow", "FeeToken", "NoBoolToken", "BlocklistToken", "HookToken", "HookAfterToken", "MalformedReturnToken", "VanishingToken", "PartialHookToken"):
        src = ROOT / "contracts" / f"{name}.sol"
        compiled = solcx.compile_source(
            src.read_text(), output_values=["abi", "bin"], solc_version=SOLC_VERSION
        )
        key = next(k for k in compiled if k.endswith(f":{name}"))
        artifact = {"contract": name, "abi": compiled[key]["abi"], "bin": compiled[key]["bin"]}
        (build_dir / f"{name}.json").write_text(json.dumps(artifact, indent=2))
        print(f"{name}: abi {len(artifact['abi'])} entries, bytecode {len(artifact['bin']) // 2} bytes -> build/{name}.json")


if __name__ == "__main__":
    main()
