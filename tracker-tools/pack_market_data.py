#!/usr/bin/env python3
"""Pack OHLCV CSV into the compact shared market snapshot used by both sites."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path


def number(value: str) -> float:
    try:
        return float(str(value or "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", default="Vnstock / VNDIRECT-compatible exporter")
    parser.add_argument("--is-demo", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    grouped: dict[str, dict[str, object]] = {}
    rows_by_ticker: dict[str, dict[str, list[object]]] = {}

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "date", "open", "high", "low", "close", "volume"}
        missing = required - {str(x or "").strip().lower() for x in (reader.fieldnames or [])}
        if missing:
            raise SystemExit(f"Missing required columns: {', '.join(sorted(missing))}")
        for raw in reader:
            ticker = str(raw.get("ticker") or raw.get("symbol") or "").strip().upper()
            date = str(raw.get("date") or "").strip()[:10]
            if not ticker or not date or len(date) != 10:
                continue
            exchange = str(raw.get("exchange") or "UNKNOWN").strip().upper()
            sector = str(raw.get("sector") or "Chưa phân loại").strip()
            grouped.setdefault(ticker, {"ticker": ticker, "exchange": exchange, "sector": sector})
            grouped[ticker]["exchange"] = exchange or grouped[ticker]["exchange"]
            grouped[ticker]["sector"] = sector or grouped[ticker]["sector"]
            rows_by_ticker.setdefault(ticker, {})[date] = [
                date,
                number(raw.get("open")),
                number(raw.get("high")),
                number(raw.get("low")),
                number(raw.get("close")),
                number(raw.get("volume")),
            ]

    symbols = []
    for ticker in sorted(grouped):
        item = grouped[ticker]
        rows = list(rows_by_ticker.get(ticker, {}).values())
        rows.sort(key=lambda row: row[0])
        symbols.append({
            "ticker": item["ticker"],
            "exchange": item["exchange"],
            "sector": item["sector"],
            "rows": rows,
        })

    dates = [row[0] for ticker_rows in rows_by_ticker.values() for row in ticker_rows.values()]
    payload = {
        "meta": {
            "schema": "shared-market-v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "asOf": max(dates) if dates else None,
            "source": args.source,
            "timezone": "Asia/Ho_Chi_Minh",
            "isDemo": bool(args.is_demo),
            "symbolCount": len(symbols),
            "rowCount": sum(len(rows) for rows in rows_by_ticker.values()),
        },
        "symbols": symbols,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if output_path.suffix.lower() == ".gz":
        with gzip.open(output_path, "wt", encoding="utf-8") as handle:
            handle.write(serialized)
    else:
        output_path.write_text(serialized, encoding="utf-8")
    # Keep CLI output ASCII-safe on Windows runners with a legacy code page.
    print(json.dumps(payload["meta"], ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
