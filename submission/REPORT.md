# Báo cáo nhóm 307

## 1. Số liệu luyện tập

Nhóm chọn seed `307007` theo ví dụ số nhóm × 1000 + 7 trong đề. Lô luyện tập có 250 ảnh, validator phát hiện 10 lỗi luật và tạo 7 ứng viên đối chiếu trên 7 ảnh. Lô sạch seed 5 có 50 ảnh riêng, chạy cùng cấu hình cho 0 lỗi luật và 0 ứng viên.

Kết quả tự đo tại bước kiểm luật trên seed 307007. F1 tổng xấp xỉ **0,7**, F1 lỗi luật xấp xỉ **1,0**. Tự đo được F1 xấp xỉ **1,0** cho cả `tier_a`, `tier_b` và `notify`.

Kiểm thêm seed `307008` ở chế độ kiểm luật. Validator phát hiện 9 lỗi, F1 lỗi luật xấp xỉ **1,0**, F1 tổng xấp xỉ **0,6** tại bước này.

Validator đổi YOLO sang pixel và ghép theo tên lớp. Cặp cùng lớp được ưu tiên khi box phủ ít nhất 90% pixel của segment, với IoU bbox từ 0,48 hoặc ít nhất 72% diện tích box nằm trong bbox segment. Với ứng viên bất đồng lớp, IoU từ 0,57 và độ phủ mask từ 84% giúp tập trung vào hai nhãn mô tả cùng vùng. Ứng viên lệch box cần cùng lớp, có giao nhau và độ phủ mask thấp hơn 90%. Segment thiếu box phải có ít nhất 650 pixel và chiếm tối thiểu 0,5% diện tích ảnh. Bỏ crowd khi đối chiếu. Các ngưỡng nhằm giảm cảnh báo do vật nhỏ, che khuất và khác biệt cách khoanh vật. Chạy trên lô sạch để đo số cảnh báo nền với cùng cấu hình.

## 2. Vì sao báo hết ứng viên làm F1 giảm?

Precision giảm khi thêm cặp báo thừa mà không thêm lỗi thật. F1 là trung bình điều hòa của precision và recall nên cũng giảm khi recall giữ nguyên. Ví dụ từ hàng đợi luyện tập, ảnh `000000003501` có box riêng cho hai phần bông cải. Box phía dưới chỉ phủ khoảng 70% segment do mask gom cả hai. Báo `bbox_drift` dựa trên độ phủ thấp ở ảnh này có thể thêm một báo thừa. Với bất đồng lớp, báo đồng thời `class_swap` và `category_swap` cũng có thể tạo một cặp báo thừa cho cùng ảnh.

## 3. Quyết định và lineage

QC từ lỗi luật đã đạt **10/250 = 4,0%**, vượt ngưỡng 2%. Đã ghi **HOLD** cho `lab250_66363156fdbb`. Truy vấn lineage trả về `R-021: affected=True action=review_or_retrain`. R-021 đã học từ v1, vì vậy cần rà soát kết quả và train lại khi cần bằng dữ liệu đã QC. Cập nhật dữ liệu không thay đổi trọng số của run đã train.

## 4. Hash và phiên bản

SHA-256 được tính từ bytes của từng file để đối chiếu tính toàn vẹn với manifest và để kiểm lại gói bàn giao. Hash khớp xác nhận bytes khớp bản đã kê. Nhãn sai vẫn có thể có hash khớp, nên chất lượng nhãn cần kiểm luật và xem ảnh. Giữ v1 để tái lập dữ liệu đầu vào của R-021, đối chiếu ticket và truy vết thay đổi giữa hai bản.

## 5. Truy vết

Changelog luyện tập đổi quy tắc gán box lớp `cup` từ v1.2 sang v1.3. Chỉ xét ảnh có box detection của lớp này và thuộc job theo v1.2. Tầng a gồm 3 ảnh trong `scene_794` và `scene_906` do team AI nêu. Tầng b gồm 4 ảnh ở các cảnh khác. Cần báo 2 mã người từ các job liên quan. Lấy phiên bản theo job vì metadata của từng ảnh có thể có lỗi `guideline_mismatch`.

## 6. Chạy trên Windows

`python -X utf8 scripts/run_lab.py` tạo xong lô nhưng tiến trình con của script gặp lỗi mã hóa CP1252 khi in tiếng Việt qua pipe. PowerShell có thể đặt `$env:PYTHONUTF8='1'` trước khi chạy để các tiến trình Python con nhận cùng chế độ. Với lô này, các event inject và train được ghi bằng lệnh lineage gốc cho release đã tạo, sau đó mới ghi quyết định HOLD.

Lô v1 của bài được tạo bằng Python trên Windows. Khi tái tạo để chấm, dùng Python trên Windows vì trình tạo lô tính release ID từ bytes JSON, bao gồm ký tự xuống dòng của hệ điều hành. Git được cấu hình theo đường dẫn để giữ nguyên bytes của thư mục bàn giao khi checkout.

## 7. Số liệu sau review

<!-- review-result:start -->
- Review luyện tập gồm 7 ứng viên. Xác nhận 6 và bác 1.
- F1 tổng ≈ 0.9 · lỗi luật ≈ 1.0 · lỗi gán nhãn ≈ 0.8
- Truy vết F1 ≈ tier_a 1.0 · tier_b 1.0 · notify 1.0
- QC v1 là 16/250 = 6,4%. Hold — 6,4% vượt ngưỡng 2%.
- V2 giữ 240 ảnh và 1656 nhãn detection, chuyển 10 ảnh sang rework. Lô cha là lab250_66363156fdbb.
- Kiểm định dạng bàn giao của lab đạt 17/17 mục.
<!-- review-result:end -->
