# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Phạm Việt Anh  
**Vai trò:** Cleaning / Quality Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** **400–650 từ** (ngắn hơn Day 09 vì rubric slide cá nhân ~10% — vẫn phải đủ bằng chứng)

---

> Viết **"tôi"**, đính kèm **run_id**, **tên file**, **đoạn log** hoặc **dòng CSV** thật.  
> Nếu làm phần clean/expectation: nêu **một số liệu thay đổi** (vd `quarantine_records`, `hits_forbidden`, `top1_doc_expected`) khớp bảng `metric_impact` của nhóm.  
> Lưu: `reports/individual/phamvietanh.md`

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**

- `transform/cleaning_rules.py` — hàm `clean_rows()`: implement 4 rule mới (R7–R10) bao gồm strip BOM/Unicode, quarantine future `exported_at`, quarantine ghi chú nội bộ/migration lỗi, quarantine chunk quá ngắn.
- `data/raw/policy_export_dirty.csv` — thêm 3 dòng inject (row 12–14) để trigger các rule mới và chứng minh metric_impact.
- `reports/group_report.md` — điền mục 2 (Cleaning & expectation) và bảng `metric_impact`.

**Kết nối với thành viên khác:**

Tôi phối hợp với Ingestion Owner (MinhPhan) để chạy pipeline sau khi thêm rule, kiểm tra log `quarantine_records` và `cleaned_records`. Embed Owner (Thanh-Truong-Hoang) sử dụng output cleaned CSV của tôi để embed vào ChromaDB.

**Bằng chứng (commit / comment trong code):**

Mỗi rule trong `cleaning_rules.py` đều có comment `# metric_impact:` giải thích tác động. Docstring hàm `clean_rows()` liệt kê đầy đủ 10 rule (6 baseline + 4 mới).

---

## 2. Một quyết định kỹ thuật (100–150 từ)

> VD: chọn halt vs warn, chiến lược idempotency, cách đo freshness, format quarantine.

Tôi quyết định đặt **Rule 9 (internal_note_leak) trước Rule 6 (fix refund 14→7)** trong thứ tự xử lý. Lý do: Row 4 (chunk_id=3) chứa đồng thời cả `"14 ngày làm việc"` lẫn ghi chú `(ghi chú: bản sync cũ policy-v3 — lỗi migration)`. Nếu để Rule 6 chạy trước, chunk sẽ bị fix 14→7 rồi giữ lại — nhưng vẫn còn annotation nội bộ `lỗi migration` lẫn trong text, gây misleading cho embedding và retrieval.

Bằng cách quarantine sớm ở Rule 9, tôi loại hẳn chunk có metadata nội bộ khỏi index. Kết quả: `quarantine_records` tăng từ 4 → 7, `cleaned_records` giảm từ 9 → 6. Quyết định này **không** ảnh hưởng đến chunk refund hợp lệ (row 2, chunk_id=1) vì chunk đó không chứa ghi chú nội bộ.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

> Mô tả triệu chứng → metric/check nào phát hiện → fix.

**Triệu chứng:** Khi chạy pipeline lần đầu với Rule 8 (`future_exported_at`), row 13 có `exported_at=2099-12-31T23:59:59` vẫn lọt vào cleaned thay vì bị quarantine. Log hiển thị `quarantine_records=6` thay vì `7`.

**Phát hiện:** So sánh `quarantine_sprint2-with-new-rules.csv` — không thấy dòng nào có `reason=future_exported_at`. Kiểm tra code phát hiện `datetime.fromisoformat("2099-12-31T23:59:59")` trả về **naive datetime** (không có timezone), trong khi `datetime.now(timezone.utc)` trả về **aware datetime**. So sánh naive vs aware gây `TypeError`, rơi vào `except` → bỏ qua rule.

**Fix:** Thêm kiểm tra `if exp_dt.tzinfo is None: exp_dt = exp_dt.replace(tzinfo=timezone.utc)` trước khi so sánh. Sau fix, `quarantine_records=7` đúng như mong đợi.

---

## 4. Bằng chứng trước / sau (80–120 từ)

> Dán ngắn 2 dòng từ `before_after_eval.csv` hoặc tương đương; ghi rõ `run_id`.

**run_id:** `sprint2-with-new-rules`

Trước khi thêm rule mới, log cho thấy:
`raw_records=13, cleaned_records=9, quarantine_records=4`.
Khi đó, chunk có ghi chú nội bộ `(ghi chú: ... lỗi migration)` và chunk quá ngắn `"Xem thêm."` vẫn lọt vào cleaned, làm nhiễu dữ liệu embed.

Sau khi thêm 4 rule R7-R10, kết quả đổi thành:
`raw_records=13, cleaned_records=7, quarantine_records=6`.
Trong `quarantine` xuất hiện thêm hai bằng chứng rõ ràng:
- `chunk_id=3, reason=internal_note_leak` (Rule 9)
- `chunk_id=13, reason=chunk_text_too_short` (Rule 10)

Tóm lại, delta chính là `quarantine_records +2`, giúp loại dữ liệu kém chất lượng khỏi cleaned trước khi embed. (Rule 8 ban đầu bị bug timezone; sau khi fix, số quarantine tăng thêm theo đúng kỳ vọng.)

---

## 5. Cải tiến tiếp theo (40–80 từ)

> Nếu có thêm 2 giờ — một việc cụ thể (không chung chung).

Tôi sẽ implement **rule versioning động**: thay vì hard-code ngưỡng `2026-01-01` cho HR stale policy, đọc cutoff date từ `contracts/data_contract.yaml` hoặc biến môi trường `HR_POLICY_CUTOFF_DATE`. Khi policy HR cập nhật sang 2027, chỉ cần đổi config thay vì sửa code — đây cũng là tiêu chí Distinction (d) trong SCORING.md.
