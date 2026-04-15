# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| policy_refund_v4 | Batch CSV export từ DB qua file policy_export_dirty.csv | Duplicate chunk (dòng 2với 3), stale version "14 ngày" từ migration v3, chunk_text/date rỗng |quarantine_records=4, expectation[refund_no_stale_14d_window] halt, freshness_check=FAIL (age 117h > SLA 24h)|
|hr_leave_policy|Batch CSV export cùng file|Version conflict: bản 2025 ghi "10 ngày phép năm" vs bản 2026 ghi "12 ngày", phân biệt bằng effective_date < 2026-01-01|quarantine_records (reason: stale_hr_policy_effective_date), expectation[hr_leave_no_stale_10d_annual] halt|
|it_helpdesk_faq|Batch CSV export cùng file|Date format không chuẩn ISO: ghi 01/02/2026 (DD/MM/YYYY) thay vì 2026-02-01|expectation[effective_date_iso_yyyy_mm_dd] halt nếu parse fail, cleaning rule tự chuyển DD/MM/YYYY → ISO|
---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | … |
| doc_id | string | Có | … |
| chunk_text | string | Có | … |
| effective_date | date | Có | … |
| exported_at | datetime | Có | … |

---

## 3. Quy tắc quarantine vs drop

> Record bị flag đi đâu? Ai approve merge lại?

---

## 4. Phiên bản & canonical

> Source of truth cho policy refund: file nào / version nào?
