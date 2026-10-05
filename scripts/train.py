from __future__ import annotations

import argparse
import json

from tianshan_sentinel.config import load_config
from tianshan_sentinel.training import train_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Tianshan Sentinel on a paired change dataset")
    parser.add_argument("--config", default="configs/levir_cd.yaml")
    parser.add_argument("--device", default=None, help="cuda, cuda:0 or cpu")
    parser.add_argument("--init-checkpoint", default=None, help="Initialize from an existing .pt checkpoint")
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.no_pretrained:
        config.model.pretrained = False
    if args.init_checkpoint:
        config.train.init_checkpoint = args.init_checkpoint
    print(json.dumps(train_experiment(config, args.device), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
