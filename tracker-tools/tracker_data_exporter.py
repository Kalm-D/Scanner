#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tracker Data Exporter
-------------------------
Tạo file CSV lịch sử giá OHLCV để import vào Tracker v2.x.

Bản v1.5 ưu tiên chạy an toàn với tài khoản Guest của Vnstock và hỗ trợ tách dữ liệu theo sàn:
- Mặc định nghỉ 3.6 giây/request để tránh vượt 20 requests/phút.
- Tự chờ và retry nếu gặp rate limit.
- Tự lưu từng phần để có thể resume khi chạy lại.
- Có tham số --exchange HOSE/HNX/UPCOM để chỉ tải một sàn.

Nguồn dữ liệu mặc định: Vnstock. Script cố gắng dùng giao diện Vnstock v4 trước,
sau đó fallback về Quote.history nếu cần.

Lệnh nhanh:
    python tools/alpha_data_exporter.py --sessions 320 --output data/tracker_prices_250_sessions.csv

CSV xuất ra có cột chuẩn:
    ticker,exchange,sector,date,open,high,low,close,volume,value
"""
from __future__ import annotations

import argparse
import sys
import time
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_SYMBOLS = [
    "FPT", "HPG", "MWG", "GMD", "ACV", "MBB", "VCB", "TCB", "ACB", "STB",
    "DGC", "REE", "VGI", "PVS", "IDC", "VHM", "VNM", "PNJ", "SSI", "HCM",
]
DEFAULT_INDEXES = ["VNINDEX"]
EXCHANGE_ALLOWLIST = {"HOSE", "HNX", "UPCOM", "UPCoM"}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export OHLCV CSV cho Tracker")
    parser.add_argument("--sessions", type=int, default=320, help="Số phiên gần nhất muốn giữ trong CSV. Nên >= 252; mặc định 320.")
    parser.add_argument("--calendar-days", type=int, default=0, help="Số ngày lịch sử theo lịch dương để tải. 0 = tự ước lượng theo sessions.")
    parser.add_argument("--output", default="data/tracker_prices_250_sessions.csv", help="Đường dẫn CSV đầu ra.")
    parser.add_argument("--errors-output", default="data/export_errors.csv", help="File ghi các mã lỗi/không tải được.")
    parser.add_argument("--quality-output", default="data/export_quality.csv", help="File báo cáo ngày dữ liệu từng mã.")
    parser.add_argument("--symbols", default="", help="Danh sách mã cách nhau bằng dấu phẩy. Bỏ trống = tự lấy universe từ Vnstock.")
    parser.add_argument("--symbols-file", default="", help="File .txt/.csv chứa danh sách mã, mỗi dòng một mã hoặc cột ticker/symbol/code.")
    parser.add_argument("--exchange", default="ALL", choices=["ALL", "HOSE", "HNX", "UPCOM"], help="Chỉ tải một sàn: HOSE, HNX hoặc UPCOM. Mặc định ALL = toàn bộ.")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số mã cổ phiếu để test. 0 = không giới hạn.")
    parser.add_argument("--sleep", type=float, default=3.6, help="Nghỉ giữa mỗi request. Guest nên dùng >=3.3s vì giới hạn khoảng 20 requests/phút.")
    parser.add_argument("--retries", type=int, default=20, help="Số lần thử lại khi gặp rate limit/lỗi tạm thời cho mỗi mã.")
    parser.add_argument("--retry-sleep", type=float, default=70.0, help="Số giây chờ khi gặp rate limit trước khi thử lại.")
    parser.add_argument("--save-every", type=int, default=5, help="Lưu file CSV tạm sau mỗi N mã tải thành công. 0 = chỉ lưu cuối cùng.")
    parser.add_argument("--resume", action="store_true", help="Nếu file output đã có dữ liệu, bỏ qua các mã đã tải để chạy tiếp.")
    parser.add_argument("--source", default="KBS", help="Nguồn ưu tiên cho Quote.history. Mặc định KBS; script sẽ fallback sang VCI nếu cần.")
    parser.add_argument("--no-index", action="store_true", help="Không tải VNINDEX.")
    parser.add_argument("--min-rows", type=int, default=210, help="Số dòng tối thiểu/mã để coi là đủ dùng cho Tracker.")
    return parser.parse_args()


def import_pandas():
    try:
        import pandas as pd  # type: ignore
        return pd
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Thiếu pandas. Hãy chạy: pip install pandas") from exc


def import_vnstock():
    try:
        import vnstock  # noqa: F401
        return True
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Thiếu vnstock. Hãy chạy: pip install -U vnstock") from exc


def normalize_ticker(value: object) -> str:
    return str(value or "").strip().upper()


def is_plain_stock_ticker(ticker: str) -> bool:
    """Chỉ giữ cổ phiếu cơ sở 3 ký tự chữ/số, loại chứng quyền/quỹ/phái sinh như CFPT2518, E1VFVN30."""
    return bool(re.fullmatch(r"[A-Z0-9]{3}", normalize_ticker(ticker)))


def normalize_exchange(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"UPCOM", "UPCOMINDEX", "UPCO", "UPC"}:
        return "UPCOM"
    if text in {"HNX", "HASTC"}:
        return "HNX"
    if text in {"HOSE", "HSX", "HOCHIMINH", "HOSTC"}:
        return "HOSE"
    return text


def read_symbols_file(path: str) -> List[Dict[str, str]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy symbols-file: {path}")
    text = p.read_text(encoding="utf-8-sig")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    if "," in lines[0] and any(h.lower() in lines[0].lower() for h in ["ticker", "symbol", "code"]):
        pd = import_pandas()
        df = pd.read_csv(p)
        return normalize_universe_df(df)
    return [{"ticker": normalize_ticker(line.split(",")[0]), "exchange": "", "sector": ""} for line in lines]


def normalize_universe_df(df) -> List[Dict[str, str]]:
    cols = {str(c).lower().strip(): c for c in df.columns}
    ticker_col = first_existing(cols, ["ticker", "symbol", "code", "organ_code", "organCode"])
    exchange_col = first_existing(cols, ["exchange", "floor", "comgroupcode", "comGroupCode", "stock_exchange", "board"])
    sector_col = first_existing(cols, ["sector", "industry", "industry_name", "industryName", "icb_name", "icbName"])
    if ticker_col is None:
        return []
    items: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        ticker = normalize_ticker(row.get(ticker_col, ""))
        if not ticker or not is_plain_stock_ticker(ticker):
            continue
        exchange = normalize_exchange(row.get(exchange_col, "") if exchange_col else "")
        sector = str(row.get(sector_col, "") if sector_col else "").strip()
        items.append({"ticker": ticker, "exchange": exchange, "sector": sector})
    seen = set()
    unique = []
    for item in items:
        if item["ticker"] not in seen:
            seen.add(item["ticker"])
            unique.append(item)
    return unique


def first_existing(cols: Dict[str, str], names: Iterable[str]) -> Optional[str]:
    lower_names = [n.lower() for n in names]
    for n in lower_names:
        if n in cols:
            return cols[n]
    # loose match
    for key, original in cols.items():
        if key in lower_names:
            return original
    return None


def get_universe(symbols_arg: str, symbols_file: str, limit: int, exchange_filter: str) -> List[Dict[str, str]]:
    if symbols_arg.strip():
        items = [{"ticker": normalize_ticker(x), "exchange": "", "sector": ""} for x in symbols_arg.split(",") if normalize_ticker(x)]
    elif symbols_file:
        items = read_symbols_file(symbols_file)
    else:
        items = fetch_universe_from_vnstock(exchange_filter)
    if not items:
        eprint("Không tự lấy được universe từ Vnstock. Dùng danh sách fallback để test.")
        items = [{"ticker": s, "exchange": "", "sector": ""} for s in DEFAULT_SYMBOLS]
    # Chỉ giữ cổ phiếu cơ sở có đúng 3 ký tự chữ/số; loại chứng quyền, ETF, quỹ, phái sinh.
    before_stock_only = len(items)
    items = [x for x in items if is_plain_stock_ticker(x.get("ticker", ""))]
    removed = before_stock_only - len(items)
    if removed:
        print(f"Stock-only filter: đã loại {removed} mã không phải cổ phiếu cơ sở 3 ký tự chữ/số.")
    # Loại index nếu lẫn trong danh sách cổ phiếu.
    items = [x for x in items if x["ticker"] not in {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}]
    exchange_filter = normalize_exchange(exchange_filter)
    if exchange_filter != "ALL":
        with_exchange = [x for x in items if normalize_exchange(x.get("exchange", "")) == exchange_filter]
        # Nếu lấy universe từ file/symbol thủ công và không có cột exchange, không tự loại hết; chỉ gắn nhãn theo sàn người dùng chọn.
        if with_exchange:
            items = with_exchange
        else:
            for x in items:
                if not normalize_exchange(x.get("exchange", "")):
                    x["exchange"] = exchange_filter
    if limit and limit > 0:
        items = items[:limit]
    return items


def fetch_universe_from_vnstock(exchange_filter: str = "ALL") -> List[Dict[str, str]]:
    """Lấy universe theo API vnstock hiện hành, có fallback cho các phiên bản cũ."""
    import_vnstock()
    candidates = []
    exchange_filter = normalize_exchange(exchange_filter)
    requested_exchanges = ["HOSE", "HNX", "UPCOM"] if exchange_filter == "ALL" else [exchange_filter]

    # Vnstock 4.x documented interface: Listing(source='KBS').all_symbols().
    try:
        from vnstock import Listing  # type: ignore
        for src in ["KBS", "VCI"]:
            try:
                listing = Listing(source=src)
            except TypeError:
                try:
                    listing = Listing()
                except Exception:
                    continue
            try:
                df = listing.all_symbols()
                if df is not None and len(df):
                    candidates.extend(normalize_universe_df(df))
                    if candidates:
                        break
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: Reference/equity interface nếu phiên bản cài đặt hỗ trợ.
    if not candidates:
        try:
            from vnstock import Reference  # type: ignore
            ref = Reference()
            methods = []
            if exchange_filter == "ALL":
                methods.append((None, lambda: ref.equity.list()))
            for ex in requested_exchanges:
                methods.append((ex, lambda ex=ex: ref.equity.list_by_exchange(ex)))
            for ex, fn in methods:
                try:
                    df = fn()
                    if df is not None and len(df):
                        rows = normalize_universe_df(df)
                        for item in rows:
                            if ex and not normalize_exchange(item.get("exchange", "")):
                                item["exchange"] = ex
                        candidates.extend(rows)
                except Exception:
                    continue
        except Exception:
            pass

    seen = set()
    result = []
    for item in candidates:
        ticker = item["ticker"]
        if not ticker:
            continue
        item["exchange"] = normalize_exchange(item.get("exchange", ""))
        if exchange_filter != "ALL" and item.get("exchange") and item.get("exchange") != exchange_filter:
            continue
        if ticker not in seen:
            seen.add(ticker)
            result.append(item)
    return result


def fetch_ohlcv(symbol: str, start: str, end: str, source: str, is_index: bool = False):
    import_vnstock()
    errors = []

    # Vnstock documented interface (4.x): Quote(symbol=..., source='KBS').history(..., interval='d').
    sources = []
    for src in [source, "KBS", "VCI"]:
        src = str(src or "").strip().upper()
        if src and src not in sources:
            sources.append(src)
    try:
        from vnstock import Quote  # type: ignore
        for src in sources:
            try:
                quote = Quote(symbol=symbol, source=src)
                for interval in ["d", "1D"]:
                    try:
                        df = quote.history(start=start, end=end, interval=interval)
                        if df is not None and len(df):
                            return df
                    except Exception as exc:
                        errors.append(f"Quote.history {src}/{interval}: {exc}")
            except Exception as exc:
                errors.append(f"Quote init {src}: {exc}")
    except Exception as exc:
        errors.append(f"Quote import: {exc}")

    # Optional unified Market interface on builds that expose it.
    try:
        from vnstock import Market  # type: ignore
        market = Market()
        if is_index and hasattr(market, "index"):
            try:
                return market.index.ohlcv(symbol=symbol, start=start, end=end)
            except Exception as exc:
                errors.append(f"Market.index.ohlcv: {exc}")
        if hasattr(market, "equity"):
            try:
                return market.equity.ohlcv(symbol=symbol, start=start, end=end)
            except Exception as exc:
                errors.append(f"Market.equity.ohlcv: {exc}")
    except Exception as exc:
        errors.append(f"Market import: {exc}")

    raise RuntimeError(" | ".join(errors) or f"Không lấy được dữ liệu {symbol}")


def normalize_ohlcv_df(df, symbol: str, exchange: str, sector: str, sessions: int):
    pd = import_pandas()
    if df is None or len(df) == 0:
        return pd.DataFrame()
    data = df.copy()
    cols = {str(c).lower().strip(): c for c in data.columns}
    date_col = first_existing(cols, ["date", "time", "tradingdate", "trading_date"])
    open_col = first_existing(cols, ["open", "open_price", "o"])
    high_col = first_existing(cols, ["high", "high_price", "h"])
    low_col = first_existing(cols, ["low", "low_price", "l"])
    close_col = first_existing(cols, ["close", "close_price", "c", "price"])
    volume_col = first_existing(cols, ["volume", "match_volume", "vol", "total_volume"])
    value_col = first_existing(cols, ["value", "match_value", "trading_value", "total_value"])
    required = [date_col, open_col, high_col, low_col, close_col, volume_col]
    if any(c is None for c in required):
        raise ValueError(f"Thiếu cột OHLCV. Columns={list(data.columns)}")
    out = pd.DataFrame({
        "ticker": symbol,
        "exchange": exchange or "UNKNOWN",
        "sector": sector or "Chưa phân loại",
        "date": pd.to_datetime(data[date_col]).dt.strftime("%Y-%m-%d"),
        "open": pd.to_numeric(data[open_col], errors="coerce"),
        "high": pd.to_numeric(data[high_col], errors="coerce"),
        "low": pd.to_numeric(data[low_col], errors="coerce"),
        "close": pd.to_numeric(data[close_col], errors="coerce"),
        "volume": pd.to_numeric(data[volume_col], errors="coerce"),
    })
    # Chuẩn hóa đơn vị giá về VND/cp.
    # Một số nguồn dữ liệu Việt Nam/vnstock/VCI trả giá theo nghìn đồng/cp,
    # ví dụ FPT = 118 thay vì 118000. Nếu không nhân 1000, GTGD TB20 sẽ
    # bị thấp hơn 1000 lần và bộ lọc thanh khoản có thể về 0.
    median_close = out["close"].dropna().median()
    price_scale = 1000 if pd.notna(median_close) and 0 < float(median_close) < 1000 else 1
    if price_scale != 1:
        for col in ["open", "high", "low", "close"]:
            out[col] = out[col] * price_scale

    # Tính lại value bằng OHLC đã chuẩn hóa để tránh lệch đơn vị giữa value và close.
    out["value"] = out["close"] * out["volume"]
    out = out.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    out = out.drop_duplicates(subset=["ticker", "date"]).sort_values("date")
    if sessions > 0 and len(out) > sessions:
        out = out.tail(sessions)
    return out



def is_rate_limit_message(text: str) -> bool:
    """Nhận diện lỗi rate limit từ Vnstock hoặc API bên dưới."""
    lowered = (text or "").lower()
    keywords = [
        "rate limit", "request limit", "too many requests", "maximum api request",
        "giới hạn", "gioi han", "đạt tối đa", "dat toi da", "wait to retry",
    ]
    return any(k in lowered for k in keywords)


def fetch_ohlcv_with_retry(symbol: str, start: str, end: str, source: str, is_index: bool, retries: int, retry_sleep: float):
    """Tải dữ liệu cho một mã, tự chờ nếu gặp rate limit.

    Một số phiên bản vnstock có thể dùng sys.exit khi bị rate limit. Vì vậy cần
    bắt SystemExit để script không chết giữa chừng.
    """
    last_error = None
    for attempt in range(1, max(1, retries + 1) + 1):
        try:
            return fetch_ohlcv(symbol, start, end, source, is_index=is_index)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # bắt cả SystemExit từ thư viện bên dưới
            last_error = exc
            text = f"{type(exc).__name__}: {exc}"
            rate_limited = is_rate_limit_message(text) or isinstance(exc, SystemExit)
            if rate_limited and attempt <= retries:
                print(f"    Rate limit/lỗi tạm thời ở {symbol}. Chờ {int(retry_sleep)} giây rồi thử lại ({attempt}/{retries})...")
                time.sleep(retry_sleep)
                continue
            raise RuntimeError(text) from None
    raise RuntimeError(f"Không tải được {symbol} sau {retries} lần thử. Lỗi cuối: {last_error}")


def save_export_files(pd, frames, errors, quality, output: Path, errors_output: Path, quality_output: Path) -> None:
    """Lưu dữ liệu hiện có ra đĩa để không mất tiến độ nếu script dừng giữa chừng."""
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        all_df = all_df.drop_duplicates(subset=["ticker", "date"], keep="last").sort_values(["ticker", "date"])
        all_df.to_csv(output, index=False, encoding="utf-8-sig")
    pd.DataFrame(errors).to_csv(errors_output, index=False, encoding="utf-8-sig")
    pd.DataFrame(quality).drop_duplicates(subset=["ticker"], keep="last").to_csv(quality_output, index=False, encoding="utf-8-sig")

def main() -> int:
    args = parse_args()
    pd = import_pandas()
    import_vnstock()

    today = date.today()
    calendar_days = args.calendar_days or int(args.sessions * 1.8 + 60)
    start = (today - timedelta(days=calendar_days)).isoformat()
    end = today.isoformat()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    errors_output = Path(args.errors_output)
    errors_output.parent.mkdir(parents=True, exist_ok=True)
    quality_output = Path(args.quality_output)
    quality_output.parent.mkdir(parents=True, exist_ok=True)

    universe = get_universe(args.symbols, args.symbols_file, args.limit, args.exchange)
    tasks: List[Tuple[str, str, str, bool]] = []
    if not args.no_index:
        tasks.extend((idx, "INDEX", "Chỉ số", True) for idx in DEFAULT_INDEXES)
    tasks.extend((item["ticker"], item.get("exchange", ""), item.get("sector", ""), False) for item in universe)

    print(f"Tracker Data Exporter v1.8")
    print(f"Sàn đang tải: {args.exchange}")
    print(f"Khoảng thời gian tải: {start} → {end}")
    print(f"Số phiên giữ lại/mã: {args.sessions}")
    print(f"Số mã/chỉ số cần tải: {len(tasks)}")
    print("Bắt đầu tải dữ liệu...\n")

    frames = []
    errors = []
    quality = []
    completed = set()
    if args.resume and output.exists():
        try:
            existing = pd.read_csv(output)
            if len(existing) and "ticker" in existing.columns:
                existing["ticker"] = existing["ticker"].astype(str).str.upper().str.strip()
                completed = set(existing["ticker"].dropna().unique())
                frames.append(existing)
                print(f"Resume: tìm thấy {len(completed)} mã/chỉ số đã có trong {output}. Sẽ bỏ qua các mã này.")
        except Exception as exc:
            print(f"Không đọc được file resume hiện có: {exc}. Sẽ tải lại từ đầu.")

    success_since_save = 0
    for i, (symbol, exchange, sector, is_index) in enumerate(tasks, start=1):
        if symbol in completed:
            print(f"[{i}/{len(tasks)}] SKIP {symbol:>8}  đã có trong file output")
            continue
        try:
            raw = fetch_ohlcv_with_retry(symbol, start, end, args.source, is_index=is_index, retries=args.retries, retry_sleep=args.retry_sleep)
            df = normalize_ohlcv_df(raw, symbol, exchange, sector, args.sessions)
            if len(df) < args.min_rows:
                errors.append({"ticker": symbol, "issue": "too_few_rows", "detail": f"{len(df)} rows"})
            if len(df):
                frames.append(df)
                quality.append({"ticker": symbol, "rows": len(df), "first_date": df["date"].iloc[0], "last_date": df["date"].iloc[-1], "status": "ok" if len(df) >= args.min_rows else "too_few_rows"})
                print(f"[{i}/{len(tasks)}] OK  {symbol:>8}  rows={len(df):>4}  last={df['date'].iloc[-1]}")
                success_since_save += 1
                if args.save_every > 0 and success_since_save >= args.save_every:
                    save_export_files(pd, frames, errors, quality, output, errors_output, quality_output)
                    print(f"    Đã lưu tạm tiến độ vào {output}")
                    success_since_save = 0
            else:
                errors.append({"ticker": symbol, "issue": "empty", "detail": "no rows"})
                quality.append({"ticker": symbol, "rows": 0, "first_date": "", "last_date": "", "status": "empty"})
                print(f"[{i}/{len(tasks)}] ERR {symbol:>8}  empty")
        except KeyboardInterrupt:
            print("\nNgười dùng đã dừng script. Đang lưu tiến độ hiện có...")
            save_export_files(pd, frames, errors, quality, output, errors_output, quality_output)
            raise
        except BaseException as exc:
            errors.append({"ticker": symbol, "issue": "fetch_error", "detail": str(exc)[:500]})
            quality.append({"ticker": symbol, "rows": 0, "first_date": "", "last_date": "", "status": "fetch_error"})
            print(f"[{i}/{len(tasks)}] ERR {symbol:>8}  {exc}")
        if args.sleep > 0 and i < len(tasks):
            time.sleep(args.sleep)

    if frames:
        save_export_files(pd, frames, errors, quality, output, errors_output, quality_output)
        all_df = pd.read_csv(output)
        print(f"\nĐã xuất CSV: {output.resolve()}")
        print(f"Tổng dòng: {len(all_df):,}")
        print(f"Tổng mã/chỉ số có dữ liệu: {all_df['ticker'].nunique():,}")
    else:
        print("\nKhông có dữ liệu nào được xuất.")
        save_export_files(pd, frames, errors, quality, output, errors_output, quality_output)

    print(f"Báo cáo lỗi: {errors_output.resolve()}")
    print(f"Báo cáo chất lượng export: {quality_output.resolve()}")
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())

