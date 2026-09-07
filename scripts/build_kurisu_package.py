"""Build the curated role using the existing App's v1 package format."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "characters/kurisu_amadeus"
OUTPUT = ROOT / "characters/kurisu_amadeus.amadues"


def build():
    entries = []
    directories = set()
    payloads = {}
    for path in sorted(SOURCE.rglob("*")):
        if path.is_symlink():
            raise ValueError("Role source must not contain symlinks")
        relative = path.relative_to(SOURCE).as_posix()
        if path.is_dir():
            directories.add(relative)
            continue
        data = path.read_bytes()
        if path.suffix == ".json":
            json.loads(data)
        entries.append(dict(path=relative, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
        payloads[f"brain/{relative}"] = data
    manifest = dict(format="amadues.character-package", version=1,
                    exported_at="2026-09-07T00:00:00Z", brain_id=SOURCE.name,
                    root="brain", directories=sorted(directories), files=entries)
    payloads["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 9, 7, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    print(f"Built {OUTPUT.name}: {len(entries)} files, {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    build()
