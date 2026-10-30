#!/usr/bin/env python3
"""Build lambda.zip deterministically from an installed package directory.

usage: package_lambda.py PACKAGE_DIR OUT_ZIP

Fixed timestamps, sorted entries, no bytecode. The same inputs always produce the same
bytes, so Terraform's source_code_hash is stable between the reviewed plan and the apply.
"""
import os
import sys
import zipfile

FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def collect(root: str) -> list[str]:
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if not name.endswith(".pyc"):
                paths.append(os.path.join(dirpath, name))
    return sorted(paths)


def build(root: str, out: str) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in collect(root):
            info = zipfile.ZipInfo(os.path.relpath(path, root).replace(os.sep, "/"), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = os.stat(path).st_mode & 0o111
            info.external_attr = (0o755 if executable else 0o644) << 16
            with open(path, "rb") as fh:
                zf.writestr(info, fh.read())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
