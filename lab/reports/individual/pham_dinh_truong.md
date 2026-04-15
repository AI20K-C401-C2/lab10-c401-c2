# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Phạm Đình Trường  
**Vai trò:** Embed Owner / Evaluation Owner  
**MSV:** 2A202600255
**Ngày nộp:** 2026-04-15  

---

## 1. Tôi phụ trách phần nào? (120 từ)

Trong buổi Lab Day 10, tôi đảm nhận vai trò **Embed Owner** và **Evaluation Owner**. Nhiệm vụ chính của tôi là quản lý luồng dữ liệu sau khi đã được làm sạch, thực hiện việc nhúng (embedding) vào Vector Store (ChromaDB) và đánh giá chất lượng truy xuất (retrieval) thông qua các kịch bản so sánh "Before" và "After". 

Cụ thể, tôi phụ trách file `eval_retrieval.py` để chạy đánh giá trên bộ câu hỏi test. Tôi đã phối hợp chặt chẽ với thành viên phụ trách Ingestion và Cleaning để đảm bảo dữ liệu qua cổng kiểm soát (Expectation Suite) đạt chuẩn trước khi cập nhật vào hệ thống. Ngoài ra, tôi cũng trực tiếp xử lý các vấn đề liên quan đến logic xử lý ngày tháng trong `cleaning_rules.py` khi phát hiện sự cố trong quá trình chạy thực tế.

**Bằng chứng:** 
- Thực hiện các lệnh: `python etl_pipeline.py run --run-id sprint2-rerun` và các lệnh eval.
- Fix lỗi Rule 8 trong `transform/cleaning_rules.py` liên quan đến so sánh timezone-aware datetime.

---

## 2. Một quyết định kỹ thuật (150 từ)

Một quyết định kỹ thuật quan trọng mà tôi thực hiện là áp dụng chiến lược **Idempotency** kết hợp với **Pruning** (cắt tỉa) trong quá trình nhúng dữ liệu. 

Vấn đề đặt ra là khi chạy pipeline nhiều lần hoặc khi dữ liệu nguồn thay đổi, nếu chỉ đơn thuần thêm mới, Vector Store sẽ bị phình to hoặc chứa các bản ghi cũ lỗi thời (stale vectors). Tôi đã kiểm tra cơ chế sử dụng `chunk_id` ổn định (stable IDs) được băm từ nội dung để dùng lệnh `upsert`. Quyết định này giúp đảm bảo nếu nội dung không đổi, vector sẽ không bị tạo trùng. 

Đặc biệt, tôi đã xác nhận tính đúng đắn của bước **Prune**: xóa các ID cũ không còn xuất hiện trong lần chạy `cleaned` hiện tại. Trong lần chạy `sprint2-rerun`, tôi đã ghi nhận log `embed_prune_removed=5`. Điều này cực kỳ quan trọng vì nếu không xóa các vector "ma" này, kết quả retrieval sẽ bị nhiễu bởi dữ liệu cũ (ví dụ: vẫn trả về bản 14 ngày dù data mới chỉ có 7 ngày), làm mất đi tính minh bạch của dữ liệu (Data Observability).

---

## 3. Một lỗi hoặc anomaly đã xử lý (150 từ)

Trong quá trình chạy Sprint 2, tôi phát hiện một **anomaly** nghiêm trọng: Pipeline đáng lẽ phải chặn dòng dữ liệu có ngày tương lai (`exported_at=2099`), nhưng nó lại cho qua và kết quả eval báo FAIL ở bước Validate. 

**Triệu chứng:** Log hiển thị `future_rows=1` ở bước Expectation, nhưng trước đó bước Cleaning lại không đưa dòng này vào `Quarantine`. 
**Nguyên nhân:** Khi debug `cleaning_rules.py`, tôi nhận ra hàm `datetime.fromisoformat()` trả về một *naive datetime* (không có múi giờ) nếu chuỗi input không có ký tự "Z" hoặc "+00:00". Trong khi đó, biến `now_utc` lại là một *aware datetime*. Việc so sánh giữa hai kiểu này đã ném ra lỗi `TypeError`, dẫn đến khối `try...except` bỏ qua lỗi một cách âm thầm (silent failure) và dòng dữ liệu xấu được lọt vào tập `cleaned`.

**Cách xử lý:** Tôi đã sửa lại Rule 8 bằng cách thêm bước kiểm tra: nếu `exp_dt.tzinfo` là `None`, tôi sẽ thực hiện `.replace(tzinfo=timezone.utc)`. Sau khi fix, pipeline đã hoạt động chính xác, `quarantine_records` tăng lên 7 và `PIPELINE_OK` được xác lập.

---

## 4. Bằng chứng trước / sau (100 từ)

Dưới đây là bằng chứng thực tế trích xuất từ các file eval mà tôi đã thực hiện trên câu hỏi then chốt `q_refund_window`:

**Run ID Clean:** `sprint2-rerun` (Sau khi sạch) | **Run ID Bad:** `inject-bad` (Khi nạp lỗi)

| Scenario | File | hits_forbidden | contains_expected |
|----------|------|----------------|-------------------|
| **Trước (Bẩn)** | `before_inject_bad.csv` | **yes** (vì dính chunk "14 ngày") | yes |
| **Sau (Sạch)** | `after_clean.csv` | **no** (đã fix/quarantine) | yes |

Ngoài ra, tôi cũng đã đạt chứng cứ **Merit** cho câu `q_leave_version` với kết quả: `contains_expected=yes`, `hits_forbidden=no`, và `top1_doc_expected=yes`, chứng minh hệ thống phân tách phiên bản chính sách HR hoàn hảo.

---

## 5. Cải tiến tiếp theo (50 từ)

Nếu có thêm 2 giờ, tôi sẽ triển khai **LLM-as-a-judge** tích hợp trực tiếp vào `eval_retrieval.py`. Thay vì chỉ kiểm tra keyword thủ công (`contains_expected`), tôi sẽ dùng một model nhỏ (như GPT-4o-mini hoặc Gemini Flash) để đánh giá độ tương quan ngữ nghĩa của Top-k preview, giúp phát hiện các lỗi sai tinh vi hơn mà chuỗi ký tự đơn thuần không thấy được.
