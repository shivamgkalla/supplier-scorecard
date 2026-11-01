"""Command line: generate demo data and score a file without running the API.

    python -m scorecard.cli generate --out data/orders.csv
    python -m scorecard.cli score --input data/orders.csv --out report.xlsx
"""

from __future__ import annotations

import argparse
import sys

from .features import InputError, build_features, load_orders
from .generate import generate_orders
from .report import build_report
from .scoring import load_config, score_suppliers, tier_counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scorecard")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="write synthetic purchase orders")
    gen.add_argument("--out", required=True)
    gen.add_argument("--suppliers", type=int, default=200)
    gen.add_argument("--seed", type=int, default=7)

    sc = sub.add_parser("score", help="score a purchase-order CSV into an Excel report")
    sc.add_argument("--input", required=True)
    sc.add_argument("--out", required=True)
    sc.add_argument("--config", default=None)

    args = parser.parse_args(argv)
    if args.command == "generate":
        df = generate_orders(args.suppliers, args.seed)
        df.to_csv(args.out, index=False)
        print(f"Wrote {len(df):,} orders for {df['supplier_id'].nunique()} suppliers to {args.out}")
        return 0

    cfg = load_config(args.config) if args.config else load_config()
    try:
        orders = load_orders(args.input)
    except InputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    scored = score_suppliers(build_features(orders), cfg)
    with open(args.out, "wb") as fh:
        fh.write(build_report(scored, cfg))
    print(f"Scored {len(scored)} suppliers -> {args.out}")
    for tier, n in tier_counts(scored, cfg).items():
        print(f"  {tier:<18}{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
