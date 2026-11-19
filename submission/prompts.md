# Dùng AI

| # | Ai dùng | Công cụ | Prompt | Vấn đề và cách kiểm lại |
|---|---|---|---|---|
| 1 | Nguyễn Viết Minh Hoàng | Codex | “đọc các file hướng dẫn và làm giúp tôi sẵn sàng để nộp” | Codex hỗ trợ validator, truy vết, giao diện xem ảnh và công cụ đóng gói. Chạy validator trên lô sạch 50 ảnh, chạy công cụ tự đo làm tròn của lab trên lô luyện tập và kiểm tra kết quả truy vết theo ticket và job. Lần chạy ban đầu với `-X utf8` không truyền chế độ UTF-8 cho tiến trình con của lab trên Windows. Khắc phục bằng `PYTHONUTF8=1` và dùng lệnh lineage gốc cho lô đã tạo. |
| 2 | Nguyễn Viết Minh Hoàng | Codex | “bạn làm giúp tôi phần ấy luôn đi” | Codex mở các ảnh COCO trong lô luyện tập và đề ẩn, đối chiếu vùng ứng viên với box và lớp, rồi gợi ý ghi chú. CV tự động có thể nhầm lệch tự nhiên với lỗi. Ví dụ ở ảnh `000000003501`, hai box phủ hai phần bông cải nhưng mask gom cả hai, nên độ phủ một box thấp. Gợi ý hiển thị riêng trong trang review để người làm xem ảnh, đối chiếu và tự xác nhận hoặc sửa trước khi xuất kết luận. |
