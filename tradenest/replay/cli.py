from __future__ import annotations

import argparse

from .runner import run_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay CSV signals through TradeNest webhook.")
    parser.add_argument("--file", required=True, help="CSV file to replay")
    parser.add_argument("--target", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--path-token", required=True, help="Webhook URL path token")
    parser.add_argument("--payload-token", required=True, help="Webhook payload auth_token")
    parser.add_argument("--speed", type=float, default=0, help="Time compression factor; 0 disables sleeps")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without posting")
    parser.add_argument("--limit", type=int, default=None, help="Replay only the first N filtered rows")
    parser.add_argument("--symbol", default=None, help="Only replay one symbol")
    parser.add_argument("--strategy", default=None, help="Only replay one strategy")
    parser.add_argument("--summary-file", default=None, help="Optional JSON summary output path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_replay(
        csv_path=args.file,
        target=args.target,
        path_token=args.path_token,
        payload_token=args.payload_token,
        speed=args.speed,
        dry_run=args.dry_run,
        limit=args.limit,
        symbol=args.symbol,
        strategy=args.strategy,
        summary_path=args.summary_file,
    )


if __name__ == "__main__":
    main()
