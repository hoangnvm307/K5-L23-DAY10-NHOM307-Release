# Validator của nhóm

Viết `validate.py` ở đây. Giao diện cố định:

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

## Đầu ra và công cụ

- Validator ghi chín loại lỗi luật vào `--out`. `--candidates` chỉ ghi ứng viên, kèm box detection và vùng segment tính từ pixel mask. Nếu lớp bất đồng, trường `types` chứa cả `class_swap` và `category_swap` để người xem chọn.
- `trace_query.py <delivery> --out <trace.json>` dùng ticket, changelog và guideline trong `jobs.csv` để ghi hai tầng ảnh và người nhận.
- `review.py <delivery> --candidates <candidates.json> --out <review.html>` tạo trang mở offline. Với lô luyện tập, thêm `--rules <rules.json> --face-options` để có mục kiểm ảnh sai hash và ảnh ví dụ khuôn mặt.
- `finalize.py --hidden --review <review.json>` hoặc `finalize.py --run runs/r307007 --review <review.json>` nhận JSON tải xuống từ trang review. Lệnh cho lô luyện tập ghi hàng đợi sửa, tạo v2, cập nhật lineage, chạy kiểm tra của lab và xuất bài làm.
