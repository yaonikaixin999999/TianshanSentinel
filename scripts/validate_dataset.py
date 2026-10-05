from __future__ import annotations

import argparse
import json

from tianshan_sentinel.dataset import validate_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    print(json.dumps(validate_dataset(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

