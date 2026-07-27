#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "scnet_results_bundle.tar.gz"
LARGE_SUFFIXES = (".wfn", ".restart", ".cube")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def task_attempt(relative: Path) -> tuple[str, str]:
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "runs":
        return parts[1], parts[2] if len(parts) >= 3 and parts[2].startswith("attempt_") else ""
    return "", ""


def main() -> int:
    large = []
    candidates = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path == BUNDLE or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        lower = path.name.lower()
        is_large_optional = lower.endswith(LARGE_SUFFIXES) or "wfn" in lower
        if is_large_optional:
            task, attempt = task_attempt(relative)
            large.append({
                "absolute_path": str(path.resolve()), "relative_path": relative.as_posix(),
                "file_type": path.suffix.lower().lstrip(".") or "WFN",
                "size_bytes": path.stat().st_size, "sha256": digest(path),
                "task_id": task, "attempt": attempt,
            })
            continue
        if relative.parts and relative.parts[0] in {".git", ".venv"}:
            continue
        scheduler_log = relative.parent == Path(".") and relative.name.startswith("scnet_") and relative.suffix in {".out", ".err"}
        if scheduler_log or relative.name in {"upload_manifest.txt"} or relative.parts[0] in {"runs", "results", "plots", "scripts", "inputs"} or relative.suffix in {".py", ".sh", ".md", ".json", ".csv", ".slurm"}:
            candidates.append(path)
    manifest = ROOT / "large_optional_files_manifest.txt"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        fields = ["absolute_path", "relative_path", "file_type", "size_bytes", "sha256", "task_id", "attempt"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(large)
    candidates.append(manifest)
    hashes = ROOT / "results/bundle_sha256.txt"
    hashes.write_text("".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in sorted(set(candidates))), encoding="ascii")
    candidates.append(hashes)
    with tarfile.open(BUNDLE, "w:gz") as archive:
        for path in sorted(set(candidates)):
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    print(BUNDLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
