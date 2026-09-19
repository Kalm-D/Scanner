(function (root) {
  "use strict";
  const LIVE_CACHE_KEY = "tracker.shared.live.v1";

  function finite(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function normalizeRow(row, ticker, exchange, sector) {
    if (Array.isArray(row)) {
      const [date, open, high, low, close, volume] = row;
      return { ticker, exchange, sector, date: String(date), open: finite(open), high: finite(high), low: finite(low), close: finite(close), volume: finite(volume) };
    }
    const t = String(row?.ticker || ticker || "").trim().toUpperCase();
    const date = String(row?.date || "").slice(0, 10);
    if (!t || !date) return null;
    return {
      ticker: t,
      exchange: String(row?.exchange || exchange || "UNKNOWN").toUpperCase(),
      sector: String(row?.sector || sector || "Chưa phân loại"),
      date,
      open: finite(row?.open),
      high: finite(row?.high),
      low: finite(row?.low),
      close: finite(row?.close),
      volume: finite(row?.volume)
    };
  }

  function normalizeProviderRow(item) {
    const ticker = String(item?.code || item?.symbol || item?.ticker || item?.stockCode || "").trim().toUpperCase();
    const date = String(item?.date || item?.tradingDate || item?.time || item?.tradingdate || "").slice(0, 10);
    if (!ticker || !/^([A-Z0-9]{3}|VNINDEX)$/.test(ticker) || !date) return null;
    const number = (value) => {
      const n = Number(value);
      return Number.isFinite(n) ? n : null;
    };
    const open = number(item?.adOpen ?? item?.open ?? item?.o ?? item?.basicPrice);
    const high = number(item?.adHigh ?? item?.high ?? item?.h ?? item?.ceilingPrice);
    const low = number(item?.adLow ?? item?.low ?? item?.l ?? item?.floorPrice);
    const close = number(item?.adClose ?? item?.close ?? item?.c ?? item?.average ?? item?.basicPrice);
    const volume = number(item?.nmVolume ?? item?.volume ?? item?.matchVolume ?? item?.totalVolume ?? item?.vol) ?? 0;
    if (![open, high, low, close].every(Number.isFinite)) return null;
    const isIndex = ticker === "VNINDEX" || ticker.endsWith("INDEX");
    const scale = !isIndex && close > 0 && close < 1000 ? 1000 : 1;
    return {
      ticker,
      exchange: String(item?.floor || item?.exchange || (isIndex ? "INDEX" : "UNKNOWN")).trim().toUpperCase(),
      sector: isIndex ? "Chỉ số" : "Chưa phân loại",
      date,
      open: open * scale,
      high: high * scale,
      low: low * scale,
      close: close * scale,
      volume
    };
  }

  function dateDaysAgo(date, days) {
    const value = new Date(`${date}T12:00:00Z`);
    value.setUTCDate(value.getUTCDate() - days);
    return value.toISOString().slice(0, 10);
  }

  function expectedTradingDate() {
    const now = new Date();
    const weekday = now.getUTCDay();
    const daysBack = weekday === 0 ? 2 : weekday === 6 ? 1 : 0;
    now.setUTCDate(now.getUTCDate() - daysBack);
    return now.toISOString().slice(0, 10);
  }

  function mergeRows(baseRows, extraRows) {
    const merged = new Map(baseRows.map(row => [`${row.ticker}|${row.date}`, row]));
    for (const row of extraRows) merged.set(`${row.ticker}|${row.date}`, row);
    return [...merged.values()].sort((a, b) => `${a.ticker}|${a.date}`.localeCompare(`${b.ticker}|${b.date}`));
  }

  function readLiveCache() {
    try {
      const raw = root.localStorage?.getItem(LIVE_CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && Array.isArray(parsed.rows) ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function writeLiveCache(rows, meta, publishedDate) {
    try {
      const liveRows = rows.filter(row => String(row.date) > String(publishedDate || ""));
      if (!liveRows.length) return;
      root.localStorage?.setItem(LIVE_CACHE_KEY, JSON.stringify({
        meta: { asOf: meta?.asOf || "", source: meta?.liveSource || "VNDIRECT public API", cachedAt: new Date().toISOString() },
        rows: liveRows
      }));
    } catch (_) {}
  }

  async function refreshLatest(result) {
    const asOf = String(result.meta?.asOf || "").slice(0, 10);
    const expected = expectedTradingDate();
    if (asOf && asOf >= expected) {
      result.meta = { ...result.meta, expectedTradingDate: expected, refreshedOnOpen: Boolean(result.meta?.cachedOnOpen), freshness: "current" };
      return result;
    }

    const fromDate = dateDaysAgo(expected, 3);
    const urls = [
      `https://finfo-api.vndirect.com.vn/v4/stock_prices?sort=date&q=date:gte:${fromDate}&size=3000&page=1`,
      `https://api-finfo.vndirect.com.vn/v4/stock_prices?sort=date&q=date:gte:${fromDate}&size=3000&page=1`
    ];
    let payload = null;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    for (const url of urls) {
      try {
        const response = await fetch(url, { signal: controller.signal, cache: "no-store", headers: { Accept: "application/json" } });
        if (response.ok) { payload = await response.json(); break; }
      } catch (_) {}
    }
    clearTimeout(timeout);
    const items = Array.isArray(payload) ? payload : payload?.data || payload?.items || payload?.results || [];
    const liveRows = items.map(normalizeProviderRow).filter(Boolean);
    if (!liveRows.length) {
      result.meta = { ...result.meta, expectedTradingDate: expected, refreshedOnOpen: false, freshness: "stale" };
      return result;
    }

    const merged = new Map(result.rows.map(row => [`${row.ticker}|${row.date}`, row]));
    for (const row of liveRows) {
      const key = `${row.ticker}|${row.date}`;
      if (row.date >= asOf || !merged.has(key)) merged.set(key, row);
    }
    result.rows = [...merged.values()].sort((a, b) => `${a.ticker}|${a.date}`.localeCompare(`${b.ticker}|${b.date}`));
    const latest = result.rows.reduce((max, row) => row.date > max ? row.date : max, "");
    result.meta = { ...result.meta, asOf: latest || result.meta?.asOf, expectedTradingDate: expected, refreshedOnOpen: latest > asOf, freshness: latest >= expected ? "current" : "stale", liveSource: "VNDIRECT public API" };
    writeLiveCache(result.rows, result.meta, asOf);
    return result;
  }

  function inflate(payload) {
    if (Array.isArray(payload)) {
      return { meta: {}, rows: payload.map(row => normalizeRow(row)).filter(Boolean) };
    }
    if (Array.isArray(payload?.rows)) {
      return { meta: payload.meta || {}, rows: payload.rows.map(row => normalizeRow(row)).filter(Boolean) };
    }
    if (Array.isArray(payload?.symbols)) {
      const rows = [];
      for (const item of payload.symbols) {
        const ticker = String(item?.ticker || "").trim().toUpperCase();
        if (!ticker || !Array.isArray(item.rows)) continue;
        for (const row of item.rows) {
          const normalized = normalizeRow(row, ticker, item.exchange, item.sector);
          if (normalized) rows.push(normalized);
        }
      }
      return { meta: payload.meta || {}, rows };
    }
    return { meta: {}, rows: [] };
  }

  async function parsePayload(response, absolute) {
    if (!absolute.endsWith(".gz")) return response.json();
    if (!("DecompressionStream" in root)) throw new Error("Trình duyệt không hỗ trợ giải nén snapshot giá.");
    const stream = response.body.pipeThrough(new root.DecompressionStream("gzip"));
    return new root.Response(stream).json();
  }

  async function load(url = "./data/market.json.gz") {
    let absolute = new URL(url, document.baseURI).href;
    let response = await fetch(absolute, { cache: "no-store", headers: { Accept: "application/json, application/gzip" } });
    if (!response.ok && absolute.endsWith(".gz")) {
      absolute = absolute.slice(0, -3);
      response = await fetch(absolute, { cache: "no-store", headers: { Accept: "application/json" } });
    }
    if (!response.ok) throw new Error(`Shared market data HTTP ${response.status}`);
    const payload = await parsePayload(response, absolute);
    const result = inflate(payload);
    result.meta = { ...(result.meta || {}), url: absolute, loadedAt: new Date().toISOString() };
    const cached = readLiveCache();
    const publishedDate = String(result.meta?.asOf || "").slice(0, 10);
    if (cached?.rows?.length) {
      const cachedRows = cached.rows.filter(row => String(row.date) > publishedDate);
      if (cachedRows.length) {
        result.rows = mergeRows(result.rows, cachedRows);
        result.meta = { ...result.meta, asOf: cached.meta?.asOf || result.meta?.asOf, cachedOnOpen: true, liveSource: cached.meta?.source || "VNDIRECT public API" };
      }
    }
    return refreshLatest(result);
  }

  root.SharedMarketData = { load, inflate, normalizeRow, refreshLatest };
})(window);
