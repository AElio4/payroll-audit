"""Fail if any image or PDF is tracked in git, by extension OR by file contents.

Photos of invoices carry customer names, addresses and GPS metadata, so this
repo holds none. .gitignore stops the common cases; this catches renamed files.
"""

import subprocess
import sys

BLOCKED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
MAGIC = [b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"%PDF", b"RIFF", b"II*\x00", b"MM\x00*"]


def main() -> int:
    files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.split(b"\0")
    bad = []
    for raw in filter(None, files):
        name = raw.decode()
        if any(name.lower().endswith(e) for e in BLOCKED_EXT):
            bad.append(name)
            continue
        with open(name, "rb") as f:
            head = f.read(12)
        if any(head.startswith(m) for m in MAGIC) or head[4:12] in (b"ftypheic", b"ftypmif1"):
            bad.append(name)
    for name in bad:
        print(f"image or PDF tracked in git: {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
