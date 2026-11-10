"""Compile actual helpers and the unchanged complete SDK against a host-boundary shim."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("this regression uses the native macOS frameworks")
    root = args.source_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    executable = output / "string-ownership"
    sources = [
        root / "4D Plugin API/4DPluginAPI.c",
        root / "support/4DPlugin-JSON.cpp",
        root / "4D Plugin API/Classes/ARRAY_TEXT.cpp",
        root / "4D Plugin API/Classes/C_TEXT.cpp",
        root / "4D Plugin API/Classes/C_LONGINT.cpp",
        root / "4DPlugin-RENAME.cpp",
        ROOT / ".github/tests/string_ownership.cpp",
    ]
    subprocess.run([
        "clang++", "-std=c++11", "-x", "objective-c++", "-g", "-O1",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-Wno-deprecated-declarations", "-Wno-extern-c-compat",
        "-I", str(root), "-I", str(root / "support"),
        "-I", str(root / "4D Plugin API"),
        "-I", str(root / "4D Plugin API/Classes"),
        *map(str, sources), "-framework", "Cocoa", "-framework", "CoreGraphics",
        "-o", str(executable),
    ], check=True)
    failures = []
    for empty in ("allocated", "null"):
        for case in ("setters-narrow", "setters-wide", "setters-unicode",
                     "pictures", "getters", "arrays", "scalars"):
            result = subprocess.run(
                [str(executable), empty, case], cwd=output,
                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1",
                     "UBSAN_OPTIONS": "halt_on_error=1"},
            )
            if result.returncode:
                failures.append(f"{case}/{empty}")
    if failures:
        print("FAILED: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("All 14 ownership cases passed (ASan/UBSan and allocation/reference accounting).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
