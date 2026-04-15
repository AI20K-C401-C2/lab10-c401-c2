# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Phạm Việt Hoàng  
**Mã học viên:** 2A202600274  
**Vai trò:** Sprint 3 — Inject corruption & Grading run owner  
**Ngày nộp:** 15/04/2026

---

## 1. Tôi phụ trách phần nào?

Trong lab Day 10, tôi đảm nhận hai tác vụ thực thi chính:

1. **Sprint 3 — Inject corruption:** Tôi chạy lệnh `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` để cố ý embed dữ liệu bẩn vào ChromaDB. Đây là kịch bản demo việc bỏ qua cleaning rule sẽ khiến vector store chứa thông tin sai (cửa sổ hoàn tiền "14 ngày" thay vì "7 ngày").
2. **Grading run — 17h:** Tôi chạy `python grading_run.py --out artifacts/eval/grading_run.jsonl` để sinh file JSONL phục vụ chấm điểm 3 câu `gq_d10_01` đến `gq_d10_03`.

Tôi không trực tiếp chỉnh sửa code mà đảm bảo pipeline được thực thi đúng thứ tự và artifact được tạo ra đầy đủ cho nhóm.

---

## 2. Một quyết định kỹ thuật

Quyết định quan trọng nhất của tôi là **chọn cờ `--skip-validate` khi inject**. Nếu không có cờ này, expectation `refund_no_stale_14d_window` (severity halt) sẽ dừng pipeline ngay lập tức và vector "14 ngày làm việc" không bao giờ được embed. Bằng cách bỏ qua validate, tôi cho phép dữ liệu bẩn đi vào `day10_kb`, tạo ra một **snapshot lỗi** để nhóm có bằng chứng before/after rõ ràng.

Tuy nhiên, trước khi chạy grading run lúc 17h, tôi đảm bảo nhóm đã chạy lại pipeline chuẩn (run `sprint2-rerun`) để xóa vector cũ và embed lại dữ liệu đã được clean. Việc này cực kỳ quan trọng vì `grading_run.py` chỉ query từ collection hiện tại; nếu để sót vector inject, `gq_d10_01` và `gq_d10_03` sẽ bị `hits_forbidden=true`.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Sau khi chạy inject, log `run_inject-bad.log` ghi rõ expectation `refund_no_stale_14d_window` FAIL với `violations=1`, nhưng pipeline vẫn tiếp tục embed nhờ `--skip-validate`. Kết quả là collection chứa chunk `policy_refund_v4` với cửa sổ "14 ngày làm việc".

**Phát hiện:** Tôi kiểm tra log và thấy `embed_upsert count=7` trong khi run sạch chỉ có `count=6`. Điều này chứng tỏ vector cũ chưa bị prune hết hoặc dữ liệu inject đã chen vào.

**Xử lý:** Tôi thông báo nhóm cần chạy lại pipeline chuẩn để restore. Log `run_sprint2-rerun.log` cho thấy `embed_prune_removed=5` và `embed_upsert count=6`, chứng minh collection đã được dọn sạch. Sau đó grading run của tôi cho kết quả `gq_d10_03` đạt `top1_doc_matches=true`, `hits_forbidden=false`.

---

## 4. Bằng chứng trước / sau

**Inject run (`run_id=inject-bad`):**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
embed_upsert count=7 collection=day10_kb
```

**Grading run sạch (`artifacts/eval/grading_run.jsonl`):**
```json
{"id":"gq_d10_01","contains_expected":true,"hits_forbidden":false}
{"id":"gq_d10_02","contains_expected":true}
{"id":"gq_d10_03","contains_expected":true,"hits_forbidden":false,"top1_doc_matches":true}
```

Sự khác biệt rõ rệt: nếu grading chạy ngay sau inject mà không restore, `gq_d10_01` và `gq_d10_03` chắc chắn sẽ `hits_forbidden=true` do còn chunk "14 ngày làm việc" trong top-k. Chỉ khi pipeline chuẩn được chạy lại, cả 3 câu mới pass hoàn toàn.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ viết một script `run_grading.sh` tự động kiểm tra xem collection ChromaDB hiện tại có phải là bản sạch hay không trước khi gọi `grading_run.py`. Ví dụ, query thử "hoàn tiền bao nhiêu ngày" và kiểm tra top-k có chứa "14 ngày" không; nếu có thì abort và cảnh báo nhóm chạy lại pipeline chuẩn. Việc này sẽ tránh rủi ro quên restore dẫn đến grading fail.
