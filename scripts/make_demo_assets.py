from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


PANEL_SIZE = 256
HEADER_HEIGHT = 58


def extract_pair(source: Path) -> tuple[Image.Image, Image.Image]:
    with Image.open(source) as montage:
        montage = montage.convert("RGB")
        required_size = (PANEL_SIZE * 4, HEADER_HEIGHT + PANEL_SIZE)
        if montage.size != required_size:
            raise ValueError(f"Expected a {required_size[0]}x{required_size[1]} montage, got {montage.size}")
        before = montage.crop((0, HEADER_HEIGHT, PANEL_SIZE, HEADER_HEIGHT + PANEL_SIZE))
        after = montage.crop((PANEL_SIZE, HEADER_HEIGHT, PANEL_SIZE * 2, HEADER_HEIGHT + PANEL_SIZE))
    return before, after


def make_icon() -> Image.Image:
    icon = Image.new("RGB", (64, 64), "#17211D")
    draw = ImageDraw.Draw(icon)
    draw.ellipse((9, 9, 55, 55), outline="#55B08C", width=4)
    draw.line((18, 42, 32, 18, 46, 42), fill="#F4F6F4", width=5)
    return icon


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the web demo from a verified LEVIR-CD result montage")
    parser.add_argument("--source", type=Path, default=Path("artifacts/examples/case_high.png"))
    parser.add_argument("--output", type=Path, default=Path("frontend/public/demo"))
    args = parser.parse_args()

    if not args.source.is_file():
        raise FileNotFoundError(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    before, after = extract_pair(args.source)
    before.save(args.output / "before.png", optimize=True)
    after.save(args.output / "after.png", optimize=True)
    make_icon().save(args.output / "favicon.png", optimize=True)
    print(f"source={args.source.resolve()}")
    print(f"saved={args.output.resolve()}")


if __name__ == "__main__":
    main()
