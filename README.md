# Stock System Cloud v0.1 — Tracker + Alpha Stock

Bộ này chuyển cơ chế dữ liệu sang **EOD tự động trên GitHub Actions**.

## Bạn cần làm thủ công một lần

1. Tạo **Public repository** trên GitHub (ví dụ `stock-system-cloud`).
2. Upload toàn bộ nội dung của ZIP này vào repo, giữ nguyên thư mục `.github/workflows/`.
3. Vào **Settings → Pages → Build and deployment → Source → GitHub Actions**.
4. Vào tab **Actions → Stock EOD Update + Deploy → Run workflow**.
5. Lần chạy thử đầu tiên nên giữ `allow_stale = true` để test bất kể giờ/ngày nghỉ.
6. Khi workflow xanh, mở URL GitHub Pages được hiển thị ở job `deploy`.

Sau đó không cần bấm gì mỗi ngày. Lịch tự chạy theo `Asia/Ho_Chi_Minh`:
- 16:20 T2–T6
- 16:45 T2–T6
- 17:10 T2–T6

Các lịch sau là retry. Nếu API chưa có EOD hôm nay, workflow dừng trước deploy nên Pages cũ không bị ghi đè.

## File quan trọng

- `src/cloud_eod.py`: Data Engine cloud.
- `config/cloud_config.json`: cấu hình số phiên, validator, timezone.
- `.github/workflows/eod-update.yml`: lịch GitHub Actions + deploy Pages.
- `public/tracker/`: Tracker đã gắn auto cloud loader.
- `public/alpha-stock/`: Alpha Stock đã gắn auto cloud loader.
- `public/data/status.json`: trạng thái phiên dữ liệu.
- `local/RUN_UPDATE_NOW.bat`: fallback chạy local khi cần.

## Nguồn dữ liệu

Bản v0.1 ưu tiên VNDIRECT public endpoint theo bulk query, vì Alpha Stock v1.20 vốn đã dùng endpoint này. Thiết kế không phụ thuộc request từng mã nên phù hợp hơn với GitHub Actions.

Nguồn public có thể thay đổi API/CORS/schema trong tương lai. Validator và cơ chế “không deploy khi lỗi” được đặt trước bước publish để giảm rủi ro dữ liệu hỏng.

## Kiểm thử

Xem `TEST_REPORT.md`. Bản build hiện tại đạt toàn bộ unit/static/loader tests có thể chạy offline. Lần `Run workflow` đầu tiên trên GitHub là live acceptance test bắt buộc cho kết nối/schema của data provider.

## Quyền riêng tư / repository

Với cấu hình GitHub Free + Pages đơn giản nhất, repo là **Public**, do đó code và các file dữ liệu được publish sẽ có thể được xem công khai. Không đặt API key, mật khẩu hoặc thông tin cá nhân vào repository. Bản v0.1 hiện không yêu cầu secret/API key.
