# Quality report — Lab Day 10 (nhóm)

**run_id:** sprint2-rerun  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (sprint1) | Sau (sprint2-rerun) | Ghi chú |
|--------|-----------------|---------------------|---------|
| raw_records | 10 | 13 | thêm 3 row khi bổ sung data |
| cleaned_records | 6 | 6 | giữ nguyên sau khi fix expectation |
| quarantine_records | 4 | 7 | tăng vì thêm row lỗi + 1 future date |
| Expectation halt? | Không | Có → Không | lần 1 HALT (`exported_at_not_future_24h`, future_rows=1); lần 2 PASS |

---

## 2. Before / after retrieval (bắt buộc)

> Nguồn: `artifacts/eval/before_inject_bad.csv` (Trước) và `artifacts/eval/after_clean.csv` (Sau).

**Câu hỏi then chốt:** refund window (`q_refund_window`)

| Cột | Trước (`before_inject_bad`) | Sau (`after_clean`) |
|-----|-----------------------------|---------------------|
| top1_doc_id | policy_refund_v4 | policy_refund_v4 |
| top1_preview | Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng. | Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng. |
| contains_expected | yes | yes |
| **hits_forbidden** | **yes** | **no** |
| top1_doc_expected | — | — |

→ Sau khi clean, pipeline không còn trả về doc bị cấm (`hits_forbidden: yes → no`).

---

**Merit (khuyến nghị):** versioning HR — `q_leave_version`

| Cột | Trước (`before_inject_bad`) | Sau (`after_clean`) |
|-----|-----------------------------|---------------------|
| top1_doc_id | hr_leave_policy | hr_leave_policy |
| top1_preview | Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026. | Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026. |
| contains_expected | yes | yes |
| hits_forbidden | no | no |
| top1_doc_expected | yes | yes |

→ Retrieval HR versioning ổn định cả trước và sau — `top1_doc_expected=yes` giữ nguyên.

---

## 3. Freshness & monitor

**Kết quả:** `FAIL` — `freshness_sla_exceeded`

| Trường | Giá trị (từ log `run_sprint2-rerun.log`) |
|--------|------------------------------------------|
| `latest_exported_at` | `2026-04-10T08:00:00` |
| `age_hours` | `119.935` |
| `sla_hours` | `24.0` |
| Kết quả | **FAIL** — `freshness_sla_exceeded` |

**SLA chọn:** 24 giờ — lấy từ giá trị mặc định `FRESHNESS_SLA_HOURS=24` trong `etl_pipeline.py:125`.

**Logic phát hiện** (`monitoring/freshness_check.py`): đọc `latest_exported_at` từ manifest, tính `age_hours = (now - latest_exported_at) / 3600`, so với `sla_hours`. Nếu `age_hours > sla_hours` → FAIL.

> Freshness FAIL chỉ được log, không dừng pipeline (`PIPELINE_OK` vẫn xuất hiện sau).

---

## 4. Corruption inject (Sprint 3)

**Row bị inject** (`chunk_id=3`, `doc_id=policy_refund_v4`, trong `data/raw/policy_export_dirty.csv`):

```
"Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn
(ghi chú: bản sync cũ policy-v3 — lỗi migration)."
```

Row này vi phạm **2 expectation cùng lúc** (nguồn: `run_inject-bad.log`):

| Expectation (halt) | Điều kiện vi phạm | Kết quả |
|--------------------|-------------------|---------|
| `refund_no_stale_14d_window` | `doc_id=policy_refund_v4` và `chunk_text` chứa `"14 ngày làm việc"` | `violations=1` |
| `no_internal_note_leak` | `chunk_text` chứa `"(ghi chú:...)"` hoặc `"lỗi migration"` | `violations=1` |

**Cách phát hiện bình thường:** cả 2 expectation ở mức `halt` → pipeline dừng (`PIPELINE_HALT`).

**Cách inject qua guard:** chạy với `--skip-validate` (log ghi rõ: `"WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3)"`) → `cleaned_records` tăng 6→7, chunk xấu vào ChromaDB → retrieval trả `hits_forbidden=yes`.

**Restore (`run_id=restore-clean`):** chạy lại không có `--skip-validate` → `embed_prune_removed=1`, tất cả expectations PASS, `cleaned=6`, `quarantine=7`.

---

## 5. Hạn chế & việc chưa làm

- **`artifacts/eval/grading_run.jsonl` chưa có** — file không tồn tại trong repo; 3 câu grading (`gq_d10_01`–`gq_d10_03`) chưa được chạy qua `grading_run.py`.
- **`reports/group_report.md` chưa điền** — toàn bộ template còn trống (tên nhóm, thành viên, bảng `metric_impact`, lệnh chạy end-to-end).
- **Freshness luôn FAIL** — `latest_exported_at=2026-04-10T08:00:00`, age ~120h >> SLA 24h; không có cơ chế update timestamp hoặc điều chỉnh `FRESHNESS_SLA_HOURS` để phản ánh thực tế data mẫu.
- **Chỉ đo 1 freshness boundary (ingest)** — không có log đo tại boundary publish (lúc embed vào ChromaDB); thiếu điều kiện Bonus +1 / Distinction (b).
- **Eval chỉ 4 câu, không có LLM-judge** — `before_inject_bad.csv` / `after_clean.csv` có 4 câu hỏi; Distinction yêu cầu ≥5 slice + mô tả phương pháp fail/pass.
- **Rule 6 hard-code cutoff ngày** — `cleaning_rules.py` kiểm tra `hr_leave_policy < "2026-01-01"` cố định trong code, không đọc từ contract/env; không đạt Distinction (d).
