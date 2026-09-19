(function (root) {
  "use strict";

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

  async function load(url = "./data/market.json") {
    const absolute = new URL(url, document.baseURI).href;
    const response = await fetch(absolute, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Shared market data HTTP ${response.status}`);
    const payload = await response.json();
    const result = inflate(payload);
    result.meta = { ...(result.meta || {}), url: absolute, loadedAt: new Date().toISOString() };
    return result;
  }

  root.SharedMarketData = { load, inflate, normalizeRow };
})(window);

