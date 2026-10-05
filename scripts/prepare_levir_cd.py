from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image


DATASET_REPOSITORY = "ericyu/LEVIRCD_Cropped_256"
DATASET_REVISION = "70f91f6cc678c6c64516b37a48ec1374e2d52a5b"
BASE_URL = f"https://huggingface.co/datasets/{DATASET_REPOSITORY}/resolve/{DATASET_REVISION}/data"
PARQUET_FILES = {
    "train": "train-00000-of-00001-737f96f51caac8cd.parquet",
    "val": "val-00000-of-00001-d09d88a7419f2427.parquet",
    "test": "test-00000-of-00001-31d7c3e3444e5b5d.parquet",
}
EXPECTED_COUNTS = {"train": 7120, "val": 1024, "test": 2048}
COLUMNS = {"imageA": "A", "imageB": "B", "label": "label"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "TianshanSentinel/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(destination)


def _extension(blob: bytes) -> str:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith((b"II*\x00", b"MM\x00*")):
        return ".tif"
    raise ValueError("Unsupported image encoding in Parquet image column")


def _image_bytes(value: object) -> bytes:
    if not isinstance(value, dict) or not isinstance(value.get("bytes"), bytes):
        raise ValueError("Expected a Hugging Face Image cell containing embedded bytes")
    return value["bytes"]


def _write_image(blob: bytes, directory: Path, stem: str, is_label: bool) -> None:
    if is_label:
        with Image.open(BytesIO(blob)) as image:
            mask = image.convert("L").point([0] * 128 + [255] * 128)
            mask.save(directory / f"{stem}.png")
        return
    (directory / f"{stem}{_extension(blob)}").write_bytes(blob)


def _extract_split(parquet_path: Path, output_root: Path, split: str) -> int:
    parquet = pq.ParquetFile(parquet_path)
    if parquet.metadata.num_rows != EXPECTED_COUNTS[split]:
        raise ValueError(
            f"Unexpected {split} row count: {parquet.metadata.num_rows}; "
            f"expected {EXPECTED_COUNTS[split]}"
        )
    for directory in COLUMNS.values():
        (output_root / split / directory).mkdir(parents=True, exist_ok=True)

    index = 0
    for batch in parquet.iter_batches(batch_size=128, columns=list(COLUMNS)):
        for row in range(batch.num_rows):
            stem = f"{index:06d}"
            for column_index, directory in enumerate(COLUMNS.values()):
                blob = _image_bytes(batch.column(column_index)[row].as_py())
                _write_image(blob, output_root / split / directory, stem, directory == "label")
            index += 1
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare the cropped LEVIR-CD dataset")
    parser.add_argument("--parquet-dir", default="data/LEVIR-CD-parquet")
    parser.add_argument("--output-root", default="data/LEVIR-CD")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    parquet_dir = Path(args.parquet_dir)
    output_root = Path(args.output_root)
    records: dict[str, object] = {
        "dataset": "LEVIR-CD cropped 256x256",
        "repository": DATASET_REPOSITORY,
        "revision": DATASET_REVISION,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "splits": {},
    }

    for split, filename in PARQUET_FILES.items():
        parquet_path = parquet_dir / f"{split}.parquet"
        if not args.skip_download:
            _download(f"{BASE_URL}/{filename}?download=true", parquet_path)
        if not parquet_path.is_file():
            raise FileNotFoundError(parquet_path)
        count = _extract_split(parquet_path, output_root, split)
        records["splits"][split] = {
            "samples": count,
            "parquet_sha256": _sha256(parquet_path),
            "source_file": filename,
        }
        print(f"{split}: {count} image triplets")

    manifest = output_root / "dataset_manifest.json"
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
