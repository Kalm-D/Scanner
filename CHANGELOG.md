# Changelog

## v0.1 — 2026-08-10

- Tách Stock Data Engine dùng chung cho Tracker + Alpha Stock.
- Chuyển cloud primary pipeline sang bulk EOD request thay vì request từng ticker.
- Hỗ trợ HOSE + HNX + UPCOM và VNINDEX benchmark.
- Rolling cache 320 phiên/mã, bootstrap khi cache trống, overlap incremental 10 ngày.
- Validator trước publish; không deploy dataset hỏng/chưa có EOD hôm nay.
- GitHub Actions schedule 16:20 / 16:45 / 17:10 Asia/Ho_Chi_Minh.
- Retry fast path: nếu phiên hôm nay đã SUCCESS, lượt retry không download lại và không lưu cache trùng.
- GitHub Pages landing page + status.
- Tracker v2.0.1 và Alpha Stock v1.20 PRO tự nạp cloud dataset khi mở.
- Giữ manual CSV/demo path làm fallback.
- Thêm Windows local fallback `local/RUN_UPDATE_NOW.bat`.
