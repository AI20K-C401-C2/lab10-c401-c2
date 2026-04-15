# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** ___________  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| ___ | Ingestion / Raw Owner | ___ |
| ___ | Cleaning & Quality Owner | ___ |
| ___ | Embed & Idempotency Owner | ___ |
| ___ | Monitoring / Docs Owner | ___ |

**Ngày nộp:** ___________  
**Repo:** ___________  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

_________________

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

_________________

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

**Cleaning Rules mới:**

| Rule mới | Hành động | Trước (run 10 records) | Sau inject (run 13 records) | Chứng cứ |
|----------|-----------|------------------------|-----------------------------|-----------| 
| R7: `strip_bom_unicode` | Strip BOM `\ufeff` / NBSP / zero-width khỏi chunk_text; quarantine nếu text chỉ toàn invisible | cleaned=5, quarantine=5 | quarantine +1 khi inject dòng có BOM prefix | quarantine_sprint2.csv reason=`invisible_only_chunk_text` |
| R8: `future_exported_at` | Quarantine nếu `exported_at` > now + 24h (lỗi clock / data fabrication) | cleaned=5, quarantine=5 | quarantine +1 khi inject dòng `exported_at=2099-01-01` | quarantine_sprint2.csv reason=`future_exported_at` |
| R9: `internal_note_leak` | Strip marker nội bộ `(ghi chú:...lỗi migration)` khỏi chunk_text | Row 4 sau fix 14→7 vẫn chứa annotation nội bộ | Chunk cleaned không còn `(ghi chú:...)` | Diff cleaned CSV trước/sau |
| R10: `chunk_text_too_short` | Quarantine nếu chunk_text < 20 ký tự | cleaned=5 | quarantine +1 khi inject dòng `chunk_text="OK"` | quarantine_sprint2.csv reason=`chunk_text_too_short` |

**Expectation mới:**

| Expectation mới | Severity | Trước (run 10 records) | Sau inject (run 13 records) | Chứng cứ |
|-----------------|----------|------------------------|-----------------------------|-----------| 
| E7: `no_empty_exported_at` | warn | OK, empty=0 | OK, empty=0 | Log: `empty_exported_at_count=0` |
| E8: `chunk_id_unique` | halt | OK, dup=0 | OK, dup=0 | Log: `duplicate_chunk_ids=0` |
| E9: `no_invisible_chars_in_chunk_text` | halt | OK, violations=0 | OK, violations=0 | Rule R7 strip BOM trước → expectation pass |
| E10: `no_internal_note_leak` | halt | OK, violations=0 | OK, violations=0 | Rule R9 strip ghi chú trước → expectation pass |
| E11: `chunk_min_length_20` | halt | OK, short=0 | OK, short=0 | Rule R10 quarantine chunk ngắn trước → expectation pass |
| E12: `exported_at_not_future_24h` | halt | OK, future=0 | **FAIL, future=1 → PIPELINE_HALT** | Dòng inject `exported_at` tương lai bị bắt |

**Rule chính (baseline + mở rộng):**

- Baseline (6 rule): allowlist doc_id, chuẩn hoá ngày ISO, quarantine HR cũ <2026, quarantine text rỗng, dedupe, fix refund 14→7 ngày
- Rule mới R7: Strip BOM / Unicode control characters — tránh nhiễu embedding + dedupe fail
- Rule mới R8: Quarantine `exported_at` tương lai — ngăn data fabrication / lỗi clock
- Rule mới R9: Strip marker nội bộ `(ghi chú:...lỗi migration)` — tránh context misleading cho retrieval
- Rule mới R10: Quarantine chunk_text quá ngắn (<20 ký tự) — tránh embedding noise

**Ví dụ 1 lần expectation fail và cách xử lý:**

Khi inject 3 dòng mới vào CSV (raw 10→13), expectation E12 `exported_at_not_future_24h` phát hiện 1 dòng có `exported_at` ở tương lai và halt pipeline (`future_rows=1`). Pipeline dừng đúng thiết kế — không embed data bất thường vào ChromaDB. Xử lý: xóa dòng inject hoặc sửa `exported_at` về quá khứ → chạy lại → E12 OK, PIPELINE_OK.

---
## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

_________________

**Kết quả định lượng (từ CSV / bảng):**

_________________

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

_________________

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

_________________

---

## 6. Rủi ro còn lại & việc chưa làm

- …
