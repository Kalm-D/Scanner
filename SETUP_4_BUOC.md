# CÀI ĐẶT GITHUB — 4 BƯỚC

> Mục tiêu: sau khi cài một lần, laptop có thể tắt. GitHub tự cập nhật dữ liệu EOD cho Tracker + Alpha Stock.

## Bước 1 — Tạo repository

1. Đăng nhập GitHub.
2. Chọn **New repository**.
3. Tên gợi ý: `stock-system-cloud`.
4. Chọn **Public** nếu dùng GitHub Free + GitHub Pages miễn phí.
5. Không cần tạo README/.gitignore/license vì bộ này đã có sẵn.
6. Bấm **Create repository**.

## Bước 2 — Upload bộ file

1. Giải nén ZIP này.
2. Trong repository mới, chọn **Add file → Upload files**.
3. Upload **nội dung bên trong thư mục `Stock_System_Cloud_v0.1`**, không upload thêm một lớp thư mục ngoài.
4. Kiểm tra repo có đường dẫn chính xác:
   - `.github/workflows/eod-update.yml`
   - `src/cloud_eod.py`
   - `public/index.html`
   - `public/tracker/index.html`
   - `public/alpha-stock/index.html`
5. Commit upload.

> Nếu giao diện web không cho upload thư mục ẩn `.github` thuận tiện, dùng GitHub Desktop hoặc tạo `.github/workflows/eod-update.yml` bằng **Add file → Create new file**, rồi copy đúng nội dung file trong ZIP.

## Bước 3 — Bật GitHub Pages

1. Vào **Settings** của repository.
2. Chọn **Pages**.
3. Ở **Build and deployment → Source**, chọn **GitHub Actions**.

## Bước 4 — Chạy thử lần đầu

1. Vào tab **Actions**.
2. Chọn workflow **Stock EOD Update + Deploy**.
3. Chọn **Run workflow**.
4. Giữ `allow_stale = true` cho lần test đầu tiên.
5. Bấm **Run workflow**.
6. Nếu tất cả job màu xanh, mở URL được hiển thị trong job `deploy`.

Trang chính sẽ có hai nút:
- **Tracker**
- **Alpha Stock**

và ô trạng thái dữ liệu EOD.

## Sau lần đầu

Không cần bấm gì hằng ngày. Workflow tự chạy theo giờ Việt Nam:
- 16:20 — lượt chính
- 16:45 — retry
- 17:10 — retry

Nếu lượt 16:20 đã có dữ liệu phiên hôm nay, state được cache; các lượt retry sau nhận biết phiên đã SUCCESS, bỏ qua download lại và không tạo cache trùng.

## Khi workflow màu đỏ

Không sửa code vội. Mở job đỏ → mở step lỗi → copy khoảng 30–80 dòng log cuối hoặc chụp màn hình và gửi lại. Dataset public cũ không bị deploy đè khi build/validator thất bại.
