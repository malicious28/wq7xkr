"""Immutable, content-addressed raw snapshots.

Each fetched chunk is stored verbatim as gzipped JSON. A manifest records the
request, row count and SHA-256 of every file; ``data_version`` is a hash over
the manifest's file hashes. Everything downstream is a pure function of the
snapshot, so the same ``data_version`` always yields the same numbers.

Gzip is written with ``mtime=0`` so identical content yields identical bytes
(and therefore identical hashes) on every machine.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from windesk.ingest.elexon import Chunk, RawRow

MANIFEST = "manifest.json"


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    key: str
    dataset: str
    start: str
    end: str
    path: str
    rows: int
    sha256: str


@dataclass(slots=True)
class Manifest:
    source: str
    files: list[SnapshotFile] = field(default_factory=list)
    fetched_at: str = ""

    @property
    def data_version(self) -> str:
        digest = hashlib.sha256()
        for f in sorted(self.files, key=lambda f: f.key):
            digest.update(f"{f.key}:{f.sha256}\n".encode())
        return digest.hexdigest()[:12]

    def to_json(self) -> str:
        body = asdict(self)
        body["data_version"] = self.data_version
        return json.dumps(body, indent=2, sort_keys=True) + "\n"

    @classmethod
    def load(cls, seed_dir: Path) -> Manifest:
        body = json.loads((seed_dir / MANIFEST).read_text(encoding="utf-8"))
        files = [SnapshotFile(**f) for f in body["files"]]
        return cls(source=body["source"], files=files, fetched_at=body["fetched_at"])


def _encode(rows: list[RawRow]) -> bytes:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def write_chunk(seed_dir: Path, chunk: Chunk, rows: list[RawRow]) -> SnapshotFile:
    rel = Path(chunk.dataset.lower()) / f"{chunk.key}.json.gz"
    target = seed_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    blob = _encode(rows)
    target.write_bytes(blob)
    return SnapshotFile(
        key=chunk.key,
        dataset=chunk.dataset,
        start=chunk.start.isoformat(),
        end=chunk.end.isoformat(),
        path=rel.as_posix(),
        rows=len(rows),
        sha256=hashlib.sha256(blob).hexdigest(),
    )


def write_manifest(seed_dir: Path, manifest: Manifest) -> None:
    manifest.fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    (seed_dir / MANIFEST).write_text(manifest.to_json(), encoding="utf-8")


def read_rows(seed_dir: Path, f: SnapshotFile, *, verify: bool = True) -> list[RawRow]:
    blob = (seed_dir / f.path).read_bytes()
    if verify and hashlib.sha256(blob).hexdigest() != f.sha256:
        msg = f"Snapshot file {f.path} does not match its manifest hash; refusing to load."
        raise ValueError(msg)
    rows: list[RawRow] = json.loads(gzip.decompress(blob))
    return rows
