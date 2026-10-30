"""python -m app.ml.cli train --plants plant01 [--horizon 60] | list | approve <version> --by you@example.com"""
import argparse
import json

from app.db.database import init_db
from app.ml import registry
from app.ml.dataset import InsufficientData
from app.ml.train import train


def main():
    p = argparse.ArgumentParser(prog="greetopia-ml")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train"); t.add_argument("--plants", nargs="+", required=True); t.add_argument("--horizon", type=int, default=60)
    sub.add_parser("list")
    a = sub.add_parser("approve"); a.add_argument("version"); a.add_argument("--by", required=True)
    args = p.parse_args()
    init_db()
    if args.cmd == "train":
        try:
            m = train(args.plants, args.horizon)
            print(json.dumps({"version": m["version"], "selected": m["selected_model"], "test_metrics": m["metrics"]["test"], "status": m["status"]}, indent=2))
        except InsufficientData as e:
            print(f"UNAVAILABLE: not enough real data to train an honest model: {e}")
            raise SystemExit(2)
    elif args.cmd == "list":
        print(json.dumps(registry.list_versions(), indent=2))
    else:
        print(json.dumps({"approved": registry.approve(args.version, args.by)["version"]}))


if __name__ == "__main__":
    main()
