# Phân tích & Đề xuất Cleaning Rules mới cho `policy_export_dirty.csv`

## Phân tích dữ liệu dirty hiện tại

Đây là 11 dòng dữ liệu (không tính header) trong `data/raw/policy_export_dirty.csv`:

| Row | doc_id | Vấn đề | Baseline rule đã xử lý? |
|-----|--------|--------|--------------------------|
| 2 | `policy_refund_v4` | Clean, 7 ngày | ✅ giữ lại |
| 3 | `policy_refund_v4` | **Duplicate** nội dung y hệt row 2 | ✅ Rule 5 (dedupe) |
| 4 | `policy_refund_v4` | Chứa `"14 ngày làm việc"` (stale) | ✅ Rule 6 (fix 14→7) |
| 5 | `sla_p1_2026` | Clean | ✅ giữ lại |
| 6 | `policy_refund_v4` | `chunk_text` rỗng, `effective_date` rỗng | ✅ Rule 2+4 |
| 7 | `it_helpdesk_faq` | Clean | ✅ giữ lại |
| 8 | `hr_leave_policy` | `effective_date=2025-01-01` (stale HR) | ✅ Rule 3 |
| 9 | `hr_leave_policy` | Clean, 12 ngày phép 2026 | ✅ giữ lại |
| 10 | `legacy_catalog_xyz_zzz` | `doc_id` lạ | ✅ Rule 1 (allowlist) |
| 11 | `it_helpdesk_faq` | `effective_date=01/02/2026` (DD/MM/YYYY) | ✅ Rule 2 (chuẩn hoá) |

> [!NOTE]
> Baseline đã xử lý hết các lỗi hiện diện trong CSV! Vì vậy, cần thêm rules có **tác động thực sự khi inject corruption ở Sprint 3** hoặc xử lý các failure mode chưa được cover.

---

## 6 Baseline Rules hiện tại

| # | Rule | Hành động | Lý do quarantine |
|---|------|-----------|-----------------|
| **1** | `doc_id` không thuộc `ALLOWED_DOC_IDS` | Quarantine | `unknown_doc_id` |
| **2** | `effective_date` rỗng hoặc không parse được | Quarantine | `missing_effective_date` / `invalid_effective_date_format` |
| **3** | `hr_leave_policy` có `effective_date < 2026-01-01` | Quarantine | `stale_hr_policy_effective_date` |
| **4** | `chunk_text` rỗng | Quarantine | `missing_chunk_text` |
| **5** | Chunk trùng nội dung (duplicate) | Quarantine | `duplicate_chunk_text` |
| **6** | `policy_refund_v4` có chứa `"14 ngày làm việc"` | **Fix in-place** → đổi thành `"7 ngày làm việc"` + append `[cleaned: stale_refund_window]` | *(không quarantine, sửa trực tiếp)* |

---

## Đề xuất 3+ Rule mới (không trivial, có `metric_impact`)

### Rule 7: Strip BOM & Unicode control characters

```
metric_impact: quarantine_records tăng khi inject BOM/zero-width chars
```

- **Vấn đề:** File CSV xuất từ Excel/ERP có thể chứa BOM (`\ufeff`) hoặc zero-width characters (`\u200b`, `\u00a0`) → embedding bị nhiễu, dedupe fail vì 2 chunk nhìn giống nhưng bytes khác.
- **Hành động:** Strip BOM/NBSP/zero-width khỏi `chunk_text`. Nếu text sau strip trở thành rỗng → quarantine `"invisible_only_chunk_text"`.
- **Chứng minh:** Inject 1 dòng có BOM prefix vào CSV → trước rule: cleaned (không phát hiện), sau rule: hoặc text được chuẩn hoá hoặc quarantine.

---

### Rule 8: Quarantine `exported_at` future/bất thường

```
metric_impact: quarantine_records tăng khi inject exported_at trong tương lai
```

- **Vấn đề:** Nếu `exported_at` là timestamp tương lai (>24h so với `now`) → data bị lỗi clock hoặc giả mạo (data fabrication). Pipeline không nên embed dữ liệu chưa tồn tại.
- **Hành động:** Parse `exported_at`, nếu > `now + 24h` → quarantine `"future_exported_at"`.
- **Chứng minh:** Inject 1 dòng `exported_at=2099-01-01T00:00:00` → quarantine_records tăng 1.

---

### Rule 9: Quarantine chunk chứa marker ghi chú nội bộ / migration lỗi

```
metric_impact: quarantine_records tăng; hits_forbidden cải thiện khi eval
```

- **Vấn đề:** Row 4 trong CSV có ghi chú `"(ghi chú: bản sync cũ policy-v3 — lỗi migration)"`. Đây là **metadata nội bộ** lẫn vào nội dung chunk → gây confuse cho embedding + retrieval. Sau khi baseline fix 14→7, text vẫn còn ghi chú lỗi migration.
- **Hành động:** Detect pattern `(ghi chú:` hoặc `lỗi migration` → quarantine `"internal_note_leak"` **hoặc** strip ghi chú ra.
- **Chứng minh:** Trước rule: chunk chứa annotation nội bộ bị embed → retrieval trả context misleading. Sau rule: quarantine hoặc cleaned text.

---

### Rule 10 (bonus): Quarantine chunk_text quá ngắn (<20 ký tự)

```
metric_impact: cleaned_records giảm; retrieval precision tăng
```

- **Vấn đề:** Chunk quá ngắn (vd chỉ 1-2 từ) không mang đủ ngữ nghĩa → embedding "noise", gây false positive trong retrieval.
- **Hành động:** Nếu `len(chunk_text.strip()) < 20` → quarantine `"chunk_text_too_short"`.
- **Chứng minh:** Inject 1 dòng `chunk_text="OK"` → quarantine_records tăng.

---

## Tóm tắt đề xuất

| Rule | Tên | Hành động | metric_impact |
|------|-----|-----------|---------------|
| **7** | `strip_bom_unicode` | Strip BOM/NBSP/zero-width | `quarantine_records↑` nếu text chỉ toàn invisible chars |
| **8** | `future_exported_at` | Quarantine nếu `exported_at` > now+24h | `quarantine_records↑` khi inject timestamp tương lai |
| **9** | `internal_note_leak` | Quarantine/strip ghi chú `(ghi chú:…lỗi migration)` | `quarantine_records↑`, `hits_forbidden` cải thiện |
| **10** | `chunk_text_too_short` | Quarantine nếu <20 chars | `cleaned_records↓`, precision↑ |

> [!TIP]
> Mỗi rule cần có ít nhất 1 inject scenario ở Sprint 3 để chứng minh `metric_impact` trong `reports/group_report.md`. Rules 7, 8, 9 là đủ 3 rules bắt buộc và đều **non-trivial** vì chúng thay đổi `quarantine_records` khi test trên dữ liệu inject.
