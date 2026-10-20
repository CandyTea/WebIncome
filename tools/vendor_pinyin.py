"""Vendor a pinned pinyin-pro release without running package install scripts.

Run from the project root with Python 3. Downloaded npm bytes are checked against
the release integrity before the unchanged UMD code is wrapped as a local ESM.
"""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

VERSION = "3.29.5"
URL = f"https://registry.npmjs.org/pinyin-pro/-/pinyin-pro-{VERSION}.tgz"
INTEGRITY = "Fk5YoRmtdHqJWqAuzYVG/NzvzeCbaG+ZEwbY6Nbps3QAIrvQQEtcm49frcyCM8i2b5najnzPDtYqrHRYTTiuwQ=="
ROOT = Path(__file__).resolve().parents[1]


def vendor(contents):
    if base64.b64encode(hashlib.sha512(contents).digest()).decode("ascii") != INTEGRITY:
        raise ValueError("pinyin-pro package integrity mismatch")
    with tarfile.open(fileobj=io.BytesIO(contents), mode="r:gz") as archive:
        code = archive.extractfile("package/dist/index.js").read().decode("utf-8")
        license_text = archive.extractfile("package/LICENSE").read().decode("utf-8")
    # Keep the upstream UMD artifact unchanged; its CommonJS branch writes only
    # to these module-local objects, so no browser globals or CDN are needed.
    wrapper = (
        f"/*! pinyin-pro {VERSION} | MIT | See licenses/pinyin-pro.txt and tools/vendor_pinyin.py. */\n"
        "const exports = {};\nconst module = { exports };\n"
        + code + "\nconst { pinyin } = module.exports;\nexport { pinyin };\n"
    )
    (ROOT / "dist" / "pinyin-pro.mjs").write_text(wrapper, encoding="utf-8", newline="\n")
    license_dir = ROOT / "licenses"
    license_dir.mkdir(exist_ok=True)
    (license_dir / "pinyin-pro.txt").write_text(license_text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    with urllib.request.urlopen(URL, timeout=30) as response:
        vendor(response.read(2 * 1024 * 1024))
    print(f"Vendored pinyin-pro {VERSION}; SHA-512 verified.")
