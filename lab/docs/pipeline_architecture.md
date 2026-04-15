# Kiến trúc pipeline — Lab Day 10

**Nhóm:** C401-C2  
**Cập nhật:** 2026-04-15

---

## 1. Sơ đồ luồng

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ETL PIPELINE — Day 10 KB                            │
└─────────────────────────────────────────────────────────────────────────────┘

  data/raw/
  policy_export_dirty.csv
          │
          │  etl_pipeline.py run --run-id <run_id>
          ▼
  ┌───────────────┐
  │    INGEST     │  ← đọc raw CSV, đếm raw_records
  │               │  ← ghi run_id = YYYY-MM-DDTHH-MMZ (UTC)
  └───────┬───────┘
          │  rows[]  (chunk_id, doc_id, chunk_text, effective_date, exported_at)
          ▼
  ┌───────────────┐
  │   TRANSFORM   │  ← clean_rows()  (transform/cleaning_rules.py)
  │  (10 rules)   │  R1 allowlist doc_id → quarantine: unknown_doc_id
  │               │  R2 normalize effective_date ISO → quarantine: missing_effective_date / invalid_effective_date_format
  │               │  R3 HR stale < 2026-01-01 → quarantine: stale_hr_policy_effective_date
  │               │  R4 empty chunk_text → quarantine: missing_chunk_text
  │               │  R7 strip BOM/NBSP/zero-width → quarantine: invisible_only_chunk_text
  │               │  R8 exported_at > now+24h → quarantine: future_exported_at
  │               │  R9 "(ghi chú:…)" / "lỗi migration" → quarantine: internal_note_leak
  │               │  R10 chunk_text < 20 ký tự → quarantine: chunk_text_too_short
  │               │  R5 dedupe chunk_text → quarantine: duplicate_chunk_text
  │               │  R6 fix "14 ngày làm việc" → "7 ngày làm việc" (policy_refund_v4)
  └───────┬───────┘
          │                        ┌─────────────────────────────────────────┐
          │  quarantine rows ──────►  artifacts/quarantine/quarantine_<run_id>.csv
          │                        │  (thêm cột "reason")                   │
          │                        └─────────────────────────────────────────┘
          │  cleaned rows
          │  ← cleaned_csv → artifacts/cleaned/cleaned_<run_id>.csv
          ▼
  ┌───────────────┐
  │   VALIDATE    │  ← run_expectations()  (quality/expectations.py)
  │ (12 expects)  │
  │               │  halt: E1 min_one_row, E2 no_empty_doc_id,
  │               │        E3 refund_no_stale_14d_window, E5 effective_date_iso_yyyy_mm_dd,
  │               │        E6 hr_leave_no_stale_10d_annual, E8 chunk_id_unique,
  │               │        E9 no_invisible_chars_in_chunk_text, E10 no_internal_note_leak,
  │               │        E11 chunk_min_length_20, E12 exported_at_not_future_24h
  │               │  warn:  E4 chunk_min_length_8, E7 no_empty_exported_at
  │               │
  │               │  FAIL (halt=True) ──► PIPELINE_HALT  (exit code 2)
  └───────┬───────┘
          │  cleaned rows (validated)
          ▼
  ┌───────────────┐
  │     EMBED     │  ← cmd_embed_internal()
  │  (ChromaDB)   │  model: all-MiniLM-L6-v2
  │               │  collection: day10_kb
  │               │  upsert by chunk_id (idempotent)
  │               │  prune: xóa chunk_id cũ không còn trong cleaned
  │               │  metadata: {doc_id, effective_date, run_id}
  └───────┬───────┘
          │  ← manifest → artifacts/manifests/manifest_<run_id>.json
          │               (raw_records, cleaned_records, quarantine_records,
          │                latest_exported_at, run_id, run_timestamp…)   ◄── ĐO FRESHNESS TẠI ĐÂY
          ▼
  ┌───────────────┐
  │    SERVING    │  ← eval_retrieval.py / retrieval worker Day 09
  │  (Retrieval)  │  ChromaDB query → top-k docs → agent trả lời
  └───────────────┘

  MONITOR (song song):
  etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run_id>.json
       └── check: latest_exported_at vs now, SLA=24h (FRESHNESS_SLA_HOURS)
       └── kết quả: PASS / FAIL (freshness_sla_exceeded)
       └── log → artifacts/logs/run_<run_id>.log
```

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner nhóm |
|------------|-------|--------|------------|
| **Ingest** | `data/raw/policy_export_dirty.csv` (13 rows) | `rows[]` in-memory, `raw_records` count | MinhPhan |
| **Transform** | `rows[]` in-memory | `cleaned[]` + `quarantine[]`, ghi `artifacts/cleaned/cleaned_<run_id>.csv`, `artifacts/quarantine/quarantine_<run_id>.csv` | PhamVietAnh |
| **Quality** | `cleaned[]` in-memory (12 expectations) | `(results, halt_bool)` → `PIPELINE_OK` hoặc `PIPELINE_HALT` (exit 2) | PhamVietAnh |
| **Embed** | `artifacts/cleaned/cleaned_<run_id>.csv` | ChromaDB collection `day10_kb` (upsert + prune), `artifacts/manifests/manifest_<run_id>.json` | Trường-Hoàng |
| **Monitor** | `artifacts/manifests/manifest_<run_id>.json` | Freshness status (PASS/FAIL), log `artifacts/logs/run_<run_id>.log` | Ngọc |

---

## 3. Idempotency & rerun

Pipeline đảm bảo idempotency theo hai cơ chế:

**3a. Upsert theo `chunk_id` (không duplicate vector)**

Mỗi chunk có `chunk_id` ổn định được sinh bằng SHA256:
```
chunk_id = f"{doc_id}_{seq}_{sha256(doc_id|chunk_text|seq)[:16]}"
# Ví dụ: policy_refund_v4_1_a1b2c3d4e5f6g7h8
```
Cùng `doc_id` + `chunk_text` + `seq` → cùng `chunk_id`. Gọi `col.upsert()` hai lần với cùng `chunk_id` chỉ cập nhật record, không tạo bản mới.

**3b. Prune chunk_id cũ**

Trước khi upsert, pipeline lấy toàn bộ `chunk_id` hiện có trong ChromaDB, so sánh với `chunk_id` trong cleaned run hiện tại:
```python
drop = sorted(prev_ids - set(ids))  # chunk cũ không còn trong cleaned
if drop:
    col.delete(ids=drop)
```
→ Rerun 2 lần với cùng data: ChromaDB giữ nguyên trạng thái, không phình vector store.  
→ Rerun sau khi clean loại bỏ chunk xấu: chunk xấu bị prune khỏi ChromaDB (`embed_prune_removed=1`).

---

## 4. Liên hệ Day 09

Pipeline Day 10 cung cấp corpus cho retrieval worker của Day 09 theo cách:

- **Cùng thư mục `data/docs/`**: 4 tài liệu canonical (`policy_refund_v4.txt`, `sla_p1_2026.txt`, `it_helpdesk_faq.txt`, `hr_leave_policy.txt`) là nguồn chung giữa Day 09 và Day 10. Day 09 dùng trực tiếp text, Day 10 clean → embed vào ChromaDB `day10_kb`.
- **ChromaDB collection `day10_kb`** là serving layer cho retrieval agent: agent query `col.query(query_texts=[…], n_results=k)` → lấy top-k chunks đã được clean và validated.
- **Versioning**: Rule R3 (quarantine HR stale < 2026-01-01) và E6 (`hr_leave_no_stale_10d_annual`) đảm bảo chỉ chunk HR 2026 (12 ngày phép) vào ChromaDB — tránh agent Day 09 trả lời sai với policy cũ (10 ngày).
- **Tách collection**: Day 10 dùng collection `day10_kb` độc lập — không ghi đè collection của Day 09 nếu có, tránh xung đột khi chạy song song.

---

## 5. Rủi ro đã biết

| Rủi ro | Mô tả | Phát hiện | Trạng thái |
|--------|-------|-----------|------------|
| **Freshness luôn FAIL** | `latest_exported_at=2026-04-10T08:00:00`, age ~120h >> SLA 24h; data mẫu không được cập nhật | `etl_pipeline.py freshness` → `FAIL: freshness_sla_exceeded` | Chưa xử lý — SLA 24h không phù hợp data mẫu tĩnh |
| **`--skip-validate` bypass halt** | Cờ `--skip-validate` cho phép chunk vi phạm expectation halt vào ChromaDB (dùng cho Sprint 3 demo) | Log ghi `WARN: expectation failed but --skip-validate` | Chỉ dùng trong demo, không dùng trong production |
| **Chỉ đo freshness tại ingest** | `latest_exported_at` lấy từ manifest (sau clean), không đo tại boundary publish (sau embed) | Không có log riêng tại embed step | Thiếu điều kiện Distinction (b) |
| **Rule R3 hard-code ngưỡng 2026** | `cleaning_rules.py` kiểm tra `< "2026-01-01"` cố định — khi HR policy cập nhật sang 2027 phải sửa code | Không có test tự động cho cutoff date | Nên đọc từ `contracts/data_contract.yaml:policy_versioning.hr_leave_min_effective_date` |
| **Eval chỉ 4 câu hỏi** | `data/test_questions.json` có 4 câu — không đủ coverage để phát hiện regression trên toàn KB | `eval_retrieval.py` output chỉ 4 dòng CSV | Cần thêm câu hỏi và LLM-judge để đạt Distinction |