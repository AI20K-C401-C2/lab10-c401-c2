# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Bùi Minh Ngọc
**Vai trò:** Monitoring / Docs Owner
**Ngày nộp:** 15/04/2026
**Độ dài yêu cầu:** 400–650 từ

---

> Viết **"tôi"**, đính kèm **run_id**, **tên file**, **đoạn log** hoặc **dòng CSV** thật.

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**

- `contracts/data_contract.yaml` — điền `owner_team: "C401-C2"`, `alert_channel: "email:dbrr231104@gmail.com"`, 4 `canonical_sources`, `allowed_doc_ids`, `policy_versioning.hr_leave_min_effective_date: "2026-01-01"`.
- `docs/data_contract.md` — Section 1: source map 3 nguồn (policy_refund_v4, hr_leave_policy, it_helpdesk_faq) với failure mode và metric thực từ các run.
- `docs/quality_report_template.md` — điền đầy đủ 5 mục: bảng số liệu sprint1 vs sprint2-rerun, before/after eval, freshness, corruption inject, hạn chế.
- `docs/pipeline_architecture.md` — viết toàn bộ 5 mục (sơ đồ ASCII, ranh giới trách nhiệm, idempotency, liên hệ Day 09, rủi ro).
- `reports/group_report.md` — tổng hợp báo cáo nhóm.

**Kết nối với thành viên khác:**

Nhận log từ MinhPhan (`run_sprint1.log`, `run_sprint2.log`) và eval CSV từ Trường (`before_inject_bad.csv`, `after_clean.csv`, `after_restore.csv`) để điền quality report và group report. Sau khi Việt Anh & Linh thêm rule/expectation mới, tôi chạy xác nhận bằng `--run-id ngoc-run`.

**Bằng chứng:**

`artifacts/logs/run_ngoc-run.log`, `artifacts/manifests/manifest_ngoc-run.json`, `docs/quality_report_template.md`.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Khi điền `contracts/data_contract.yaml`, tôi phải chọn `measured_at` cho freshness trong 3 lựa chọn: `ingest`, `cleaned`, `publish`. Tôi chọn `publish` — là boundary sau khi dữ liệu vào ChromaDB, sát nhất với thời điểm agent trả lời user.

Tuy nhiên, khi đọc `monitoring/freshness_check.py`, tôi nhận ra hàm `check_manifest_freshness()` thực ra đọc `latest_exported_at` từ manifest (ghi sau embed), không đo tại một boundary publish tách biệt. Điều này có nghĩa `measured_at: "publish"` trong contract là đúng về ý nghĩa kinh doanh nhưng chưa được implement riêng trong code. Tôi quyết định ghi rõ điểm này vào `quality_report_template.md` Section 5: "Chỉ đo 1 freshness boundary (ingest) — không có log đo tại boundary publish (lúc embed vào ChromaDB)." Đây là rủi ro đã biết, không sửa code nhưng phải document để team sau xử lý.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Khi viết `docs/pipeline_architecture.md`, tôi đặt `cleaned_csv` và `manifest` vào sơ đồ theo logic "viết sau validate", nhưng khi đọc lại `etl_pipeline.py` hàm `cmd_run()`, phát hiện thứ tự thực tế khác:

- `write_cleaned_csv()` và `write_quarantine_csv()` được gọi **sau `clean_rows()`**, trước `run_expectations()` — tức cleaned_csv ghi sau TRANSFORM, không phải sau VALIDATE.
- Manifest được ghi **sau `cmd_embed_internal()`** — tức sau EMBED, không phải trước.

Ngoài ra, tên quarantine reason và tên expectation trong sơ đồ ban đầu không khớp code: `"invalid_date"` thay vì `"invalid_effective_date_format"`, `"stale_hr_policy"` thay vì `"stale_hr_policy_effective_date"`, `"effective_date_iso"` thay vì `"effective_date_iso_yyyy_mm_dd"`. Tôi đối chiếu từng tên với `cleaning_rules.py` và `expectations.py`, sửa toàn bộ cho khớp chính xác. Thứ tự thực thi rule trong sơ đồ (R5/R6 trước R7–R10) cũng được sửa lại đúng theo flow trong code.

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Trước (sprint1, baseline 6 rules, `run_id=sprint1`):**
```
raw_records=10, cleaned_records=6, quarantine_records=4
freshness_check=FAIL {"age_hours": 117.226, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

**Sau (ngoc-run, 10 rules + 12 expectations, `run_id=ngoc-run`):**
```
raw_records=13, cleaned_records=6, quarantine_records=7
expectation[no_invisible_chars_in_chunk_text] OK (halt) :: violations=0
expectation[no_internal_note_leak] OK (halt) :: violations=0
expectation[exported_at_not_future_24h] OK (halt) :: future_rows=0
freshness_check=FAIL {"age_hours": 121.3, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
PIPELINE_OK
```

Quarantine tăng từ 4 → 7: thêm `internal_note_leak` (row 3), `future_exported_at` (row 12, exported_at=2099-12-31T23:59:59), `chunk_text_too_short` (row 13, "Xem thêm." — 9 ký tự). Tất cả 12 expectations pass. Freshness FAIL do data mẫu tĩnh (age ~121h >> SLA 24h) — hành vi đúng thiết kế, đã document trong quality report.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ hoàn thiện `docs/runbook.md` — hiện vẫn còn template chưa điền. Cụ thể: điền **Symptom** (agent trả lời "14 ngày" thay vì "7 ngày"), **Detection** (`hits_forbidden=yes` trong eval CSV, expectation `refund_no_stale_14d_window` FAIL), **Diagnosis** (3 bước: manifest → quarantine → eval), **Mitigation** (rerun không có `--no-refund-fix`), **Prevention** (alert khi freshness FAIL, CI/CD chạy eval trước merge). Runbook hoàn chỉnh giúp on-call xử lý sự cố mà không cần đọc code.
