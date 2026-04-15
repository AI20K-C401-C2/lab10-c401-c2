# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** C401-C2
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| MinhPhan | Ingestion / Raw Owner | 26ai.minhpt@vinuni.edu.vn |
| Viet Anh | Cleaning & Quality Owner | 26ai.anhpv@vinuni.edu.vn |
| Linh | Cleaning & Quality Owner | 26ai.linhnt2@vinuni.edu.vn |
| Thanh | Embed & Idempotency Owner | 26ai.thanhld@vinuni.edu.vn |
| Trường | Embed & Idempotency Owner | 26ai.truongpd@vinuni.edu.vn |
| Hoàng | Embed & Idempotency Owner | 26ai.hoangpv@vinuni.edu.vn |
| Ngọc | Monitoring / Docs Owner | 26ai.ngocbm@vinuni.edu.vn |

**Ngày nộp:** 15/04/2026
**Repo:** https://github.com/AI20K-C401-C2/lab10-c401-c2
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

**Tóm tắt luồng:**

Nguồn raw là `data/raw/policy_export_dirty.csv` — ban đầu 10 dòng (Sprint 1–2), mở rộng thêm 3 dòng (rows 11–13) cho Sprint 3, tổng 13 dòng. File chứa 6 loại lỗi có chủ đích: duplicate chunk, refund window sai (14 ngày làm việc), ghi chú nội bộ/migration lẫn trong text, effective_date rỗng hoặc sai format (DD/MM/YYYY), HR policy phiên bản cũ (2025, 10 ngày phép), unknown doc_id, chunk quá ngắn ("Xem thêm.", 9 ký tự), BOM prefix, và exported_at tương lai (2099-12-31).

Pipeline chạy theo chuỗi 5 bước:
1. **Ingest** — `load_raw_csv()` đọc file, ghi `raw_records` vào log, sinh `run_id` (UTC timestamp hoặc truyền tường minh qua `--run-id`).
2. **Transform** — `clean_rows()` áp 10 rule, ghi `artifacts/cleaned/cleaned_<run_id>.csv` và `artifacts/quarantine/quarantine_<run_id>.csv`.
3. **Validate** — `run_expectations()` chạy 12 expectations (10 halt, 2 warn); bất kỳ halt nào fail → exit code 2 (`PIPELINE_HALT`), không embed.
4. **Embed** — `cmd_embed_internal()` upsert theo `chunk_id` vào ChromaDB collection `day10_kb`; prune chunk_id cũ không còn trong cleaned.
5. **Manifest + Freshness** — ghi `artifacts/manifests/manifest_<run_id>.json` rồi chạy `check_manifest_freshness()` so SLA 24h.

`run_id` đọc từ dòng đầu log, ví dụ: `run_id=restore-clean` trong `artifacts/logs/run_restore-clean.log`.

**Lệnh chạy một dòng:**

```
python etl_pipeline.py run --run-id restore-clean
```

---

## 2. Cleaning & expectation (150–200 từ)

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

**Cleaning Rules mới:**

| Rule mới | Hành động | Trước (sprint1 — 10 records) | Sau (sprint2 / restore-clean — 10/13 records) | Chứng cứ |
|----------|-----------|------------------------------|------------------------------------------------|-----------|
| R7: `strip_bom_unicode` | Strip BOM `\ufeff` / NBSP / zero-width khỏi `chunk_text`; quarantine nếu text chỉ toàn invisible sau strip | sprint1: cleaned=6, quarantine=4; row 11 chưa tồn tại | restore-clean 13 rows: row 11 (BOM prefix) được strip → text valid → vào cleaned; E9 `no_invisible_chars_in_chunk_text` OK violations=0 | `run_restore-clean.log`: `expectation[no_invisible_chars_in_chunk_text] OK (halt) :: violations=0` |
| R8: `future_exported_at` | Quarantine nếu `exported_at` > now + 24h | sprint2 10 rows: không có future date → E12 OK `future_rows=0` | sprint2 second run 13 rows (R8 chưa quarantine): E12 FAIL `future_rows=1` → PIPELINE_HALT; restore-clean: R8 quarantine row 12 → E12 OK `future_rows=0` | `quarantine_restore-clean.csv` reason=`future_exported_at`, `exported_at_raw=2099-12-31T23:59:59`; `run_sprint2.log`: `exported_at_not_future_24h FAIL (halt) :: future_rows=1` |
| R9: `internal_note_leak` | Quarantine nếu `chunk_text` chứa `(ghi chú:…)` hoặc `lỗi migration` | sprint1 10 rows: row 3 đi qua R6 fix "14→7 ngày" và vào cleaned (cleaned=6) — annotation nội bộ vẫn lọt | sprint2 10 rows: row 3 bị quarantine reason=`internal_note_leak` → cleaned giảm từ 6 xuống 5 | `quarantine_sprint2.csv` row 3: reason=`internal_note_leak`; sprint1 `cleaned_records=6` vs sprint2 `cleaned_records=5` |
| R10: `chunk_text_too_short` | Quarantine nếu `chunk_text` < 20 ký tự sau strip | sprint2 10 rows: không có chunk ngắn → E11 OK `short_chunks=0` | sprint2 second run 13 rows: row 13 `"Xem thêm."` (9 ký tự) → quarantine reason=`chunk_text_too_short` | `quarantine_sprint2.csv` row 7: `chunk_id=13`, `chunk_text="Xem thêm."`, reason=`chunk_text_too_short`; `run_sprint2.log` (second run): `quarantine_records=6` |

**Expectation mới:**

| Expectation mới | Severity | Trước (sprint1 — 6 expectations) | Sau (sprint2 — 12 expectations) | Chứng cứ |
|-----------------|----------|------------------------------------|----------------------------------|-----------|
| E7: `no_empty_exported_at` | warn | Không tồn tại trong sprint1 | OK `empty_exported_at_count=0` | `run_sprint2.log`: `expectation[no_empty_exported_at] OK (warn) :: empty_exported_at_count=0` |
| E8: `chunk_id_unique` | halt | Không tồn tại trong sprint1 | OK `duplicate_chunk_ids=0` | `run_sprint2.log`: `expectation[chunk_id_unique] OK (halt) :: duplicate_chunk_ids=0` |
| E9: `no_invisible_chars_in_chunk_text` | halt | Không tồn tại trong sprint1 | OK `violations=0` (R7 strip trước → không còn BOM trong cleaned) | `run_restore-clean.log`: `expectation[no_invisible_chars_in_chunk_text] OK (halt) :: violations=0` |
| E10: `no_internal_note_leak` | halt | Không tồn tại trong sprint1 | OK `violations=0` (R9 quarantine trước) | `run_sprint2.log`: `expectation[no_internal_note_leak] OK (halt) :: violations=0` |
| E11: `chunk_min_length_20` | halt | Không tồn tại trong sprint1 | OK `short_chunks=0` (R10 quarantine trước) | `run_sprint2.log`: `expectation[chunk_min_length_20] OK (halt) :: short_chunks=0` |
| E12: `exported_at_not_future_24h` | halt | Không tồn tại trong sprint1 | **FAIL `future_rows=1` → PIPELINE_HALT** khi inject row 12 (`exported_at=2099-12-31T23:59:59`) và R8 chưa hoàn thiện | `run_sprint2.log` (second run): `expectation[exported_at_not_future_24h] FAIL (halt) :: future_rows=1` + `PIPELINE_HALT` |

**Rule chính (baseline + mở rộng):**

- Baseline (6 rule): (R1) allowlist doc_id, (R2) chuẩn hoá ngày ISO, (R3) quarantine HR cũ < 2026-01-01, (R4) quarantine chunk_text rỗng, (R5) dedupe chunk_text, (R6) fix refund 14→7 ngày làm việc.
- Rule mới R7: Strip BOM / Unicode control characters — tránh nhiễu embedding; bảo đảm E9 pass.
- Rule mới R8: Quarantine `exported_at` tương lai (> now + 24h) — ngăn data fabrication / lỗi clock.
- Rule mới R9: Quarantine marker nội bộ `(ghi chú:…lỗi migration)` — tránh context misleading cho retrieval.
- Rule mới R10: Quarantine chunk_text < 20 ký tự — tránh embedding noise từ fragment không đủ ngữ nghĩa.

**Ví dụ 1 lần expectation fail và cách xử lý:**

Sprint 2, run thứ 2 với 13 rows (sau khi thêm row 12 `exported_at=2099-12-31T23:59:59`): E12 `exported_at_not_future_24h` phát hiện `future_rows=1` và halt pipeline (`exit code 2`). Lúc đó R8 chưa hoàn thiện trong `cleaning_rules.py` nên row 12 vẫn lọt vào cleaned (cleaned=7), nhưng E12 chặn đúng thiết kế. Xử lý: hoàn thiện R8 trong `clean_rows()` để quarantine row 12 trước bước validate → restore-clean chạy lại: E12 OK `future_rows=0`, `embed_prune_removed=1`, PIPELINE_OK.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

**Kịch bản inject:**

Run `inject-bad` cố ý nhúng chunk bẩn vào ChromaDB bằng cờ `--no-refund-fix --skip-validate`: chunk `policy_refund_v4` chứa `"14 ngày làm việc"` (sai — đúng phải là 7 ngày) kèm ghi chú nội bộ `(ghi chú: bản sync cũ policy-v3 — lỗi migration)`. Hai expectation halt bị vi phạm (`refund_no_stale_14d_window violations=1`, `no_internal_note_leak violations=1`) nhưng bị bypass bởi `--skip-validate` — log ghi `WARN: expectation failed but --skip-validate → tiếp tục embed`. Kết quả: `raw=13, cleaned=7, quarantine=6`, `embed_upsert count=7`, chunk xấu vào ChromaDB.

Sau đó chạy `restore-clean` không có flag bypass → `cleaned=6, quarantine=7`, `embed_prune_removed=1`, ChromaDB trở về trạng thái sạch.

**Kết quả định lượng (từ CSV):**

Nguồn: `artifacts/eval/before_inject_bad.csv` (sau inject-bad) và `artifacts/eval/after_clean.csv` (trước inject-bad / sau clean).

**Câu hỏi bị ảnh hưởng:** `q_refund_window`

| Cột | Trước — `after_clean.csv` (trạng thái sạch) | Sau inject — `before_inject_bad.csv` (trạng thái bẩn) |
|-----|---------------------------------------------|--------------------------------------------------------|
| top1_doc_id | policy_refund_v4 | policy_refund_v4 |
| top1_preview | Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng. | Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng. |
| contains_expected | yes | yes |
| **hits_forbidden** | **no** ← chunk "14 ngày" chưa vào ChromaDB | **yes** ← chunk "14 ngày làm việc" đã được embed |
| top1_doc_expected | — | — |

→ `hits_forbidden` chuyển từ `no → yes` sau inject-bad, rồi `yes → no` sau restore-clean (`after_restore.csv`). Dù top1 vẫn là chunk đúng (7 ngày), chunk sai (14 ngày) xuất hiện trong top-k — agent có nguy cơ trả lời sai nếu dùng context toàn bộ top-k.

---

**Bằng chứng thêm (Merit — Step 3.7): `q_leave_version`**

Kiểm tra trong cả 3 snapshot eval — `q_leave_version` nhất quán đúng xuyên suốt:

| Cột | `after_clean.csv` | `before_inject_bad.csv` | `after_restore.csv` |
|-----|-------------------|-------------------------|----------------------|
| top1_doc_id | hr_leave_policy | hr_leave_policy | hr_leave_policy |
| top1_preview | Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026. | Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026. | Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026. |
| **contains_expected** | **yes** | **yes** | **yes** |
| **hits_forbidden** | **no** | **no** | **no** |
| **top1_doc_expected** | **yes** | **yes** | **yes** |

→ `q_leave_version` đạt cả 3 điều kiện chất lượng trong mọi snapshot. Chunk `hr_leave_policy` (2026, 12 ngày) không bị ảnh hưởng bởi injection vào `policy_refund_v4` — xác nhận pipeline isolate đúng doc versioning. Chunk HR cũ (2025, 10 ngày phép năm) đã bị R3 quarantine từ bước clean với reason=`stale_hr_policy_effective_date` (`effective_date=2025-01-01 < 2026-01-01`).

---

## 4. Freshness & monitoring (100–150 từ)

SLA được chọn: **24 giờ** — cấu hình qua biến môi trường `FRESHNESS_SLA_HOURS=24` (mặc định trong `.env.example`). Ý nghĩa: nếu `latest_exported_at` trong manifest cũ hơn 24h so với thời điểm chạy → `FAIL: freshness_sla_exceeded`; ngược lại → `PASS`.

Kết quả thực tế trên manifest `restore-clean`:
```
FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 120.705, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

Toàn bộ 4 run đều **FAIL** vì data mẫu có `latest_exported_at` tĩnh (`2026-04-10T08:00:00`), cách thời điểm chạy lab (2026-04-15) ~120 giờ >> SLA 24h:

| run_id | age_hours | Kết quả |
|--------|-----------|---------|
| sprint2 | 120.101 | FAIL |
| sprint2-rerun | 120.212 | FAIL |
| inject-bad | 120.498 | FAIL |
| restore-clean | 120.705 | FAIL |

Lệnh kiểm tra độc lập:
```
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_restore-clean.json
```

Rủi ro đã biết: SLA 24h không phù hợp với data mẫu tĩnh — cần dùng SLA lớn hơn (ví dụ 168h) hoặc cập nhật `exported_at` trong data mẫu khi chạy lab thực tế.

---

## 5. Liên hệ Day 09 (50–100 từ)

Pipeline Day 10 cung cấp corpus đã được clean và embed cho retrieval agent Day 09. Cả hai ngày dùng chung 4 tài liệu canonical trong `data/docs/` (`policy_refund_v4.txt`, `sla_p1_2026.txt`, `it_helpdesk_faq.txt`, `hr_leave_policy.txt`). Day 09 dùng trực tiếp text file; Day 10 clean → embed vào ChromaDB collection `day10_kb` với model `all-MiniLM-L6-v2`. Retrieval agent Day 09 query `col.query(query_texts=[…], n_results=k)` → nhận lại top-k chunks đã được validate. Collection `day10_kb` là độc lập — không ghi đè collection Day 09 nếu tồn tại, tránh xung đột khi chạy song song. Rule R3 và expectation E6 đảm bảo chỉ chunk HR 2026 (12 ngày phép) vào ChromaDB — agent không bao giờ trả lời sai với policy 2025 (10 ngày).

---

## 6. Rủi ro còn lại & việc chưa làm

| Rủi ro | Mô tả | Phát hiện | Trạng thái |
|--------|-------|-----------|------------|
| **Freshness luôn FAIL** | `latest_exported_at=2026-04-10T08:00:00`, age ~120h >> SLA 24h; data mẫu tĩnh không được cập nhật | `etl_pipeline.py freshness` → `FAIL: freshness_sla_exceeded` (tất cả 4 run) | Chưa xử lý — SLA 24h không phù hợp data mẫu tĩnh |
| **`--skip-validate` bypass halt** | Cờ cho phép chunk vi phạm expectation halt vào ChromaDB (dùng Sprint 3 demo) | Log ghi `WARN: expectation failed but --skip-validate` trong `run_inject-bad.log` | Chỉ dùng trong demo, không dùng production |
| **Chỉ đo freshness tại ingest** | `latest_exported_at` lấy từ manifest (ghi sau embed), không đo tại boundary publish riêng biệt | Không có log freshness riêng tại bước embed | Thiếu boundary đo sau publish |
| **Rule R3 hard-code ngưỡng 2026** | `cleaning_rules.py` kiểm tra `< "2026-01-01"` cố định — khi HR policy cập nhật sang 2027 phải sửa code | Không có test tự động cho cutoff date | Nên đọc từ `contracts/data_contract.yaml` |
| **Eval chỉ 4 câu hỏi** | `data/test_questions.json` có 4 câu — không đủ coverage để phát hiện regression toàn KB | `eval_retrieval.py` output chỉ 4 dòng CSV | Cần thêm câu hỏi để tăng coverage |
