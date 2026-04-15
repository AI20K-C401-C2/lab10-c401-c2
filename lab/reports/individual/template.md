# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Phan Tuấn Minh 
**Vai trò:** Ingestion / Cleaning / Embed / Monitoring — Ingestion  
**Ngày nộp:** 15/04/2026 
**Độ dài yêu cầu:** **400–650 từ** (ngắn hơn Day 09 vì rubric slide cá nhân ~10% — vẫn phải đủ bằng chứng)

---

> Viết **"tôi"**, đính kèm **run_id**, **tên file**, **đoạn log** hoặc **dòng CSV** thật.  
> Nếu làm phần clean/expectation: nêu **một số liệu thay đổi** (vd `quarantine_records`, `hits_forbidden`, `top1_doc_expected`) khớp bảng `metric_impact` của nhóm.  
> Lưu: `reports/individual/[ten_ban].md`

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**

- `etl_pipeline.py` — chạy entrypoint pipeline, kiểm tra log output và tạo artifacts
- `data/raw/policy_export_dirty.csv` — phân tích dữ liệu bẩn, inject dòng test (thêm 3 dòng, raw 10→13)
- `docs/data_contract.md` mục 1 — điền bảng source map 3 nguồn (cùng Ngọc)
- `contracts/data_contract.yaml` — điền `owner_team: C401-C2`, `alert_channel: email:dbrr231104@gmail.com`

**Kết nối với thành viên khác:**

Tôi chạy pipeline (`--run-id sprint1`, `sprint2`) và gửi log cho Việt Anh & Linh (Cleaning/Quality Owner) kiểm tra rule/expectation mới. Khi họ thêm rule xong, tôi chạy lại xác nhận `PIPELINE_OK`.

**Bằng chứng:**

Log `artifacts/logs/run_sprint1.log`, manifest `artifacts/manifests/manifest_sprint1.json`, quarantine `artifacts/quarantine/quarantine_sprint1.csv`.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Tôi quyết định sử dụng `--run-id` rõ ràng cho mỗi lần chạy (ví dụ `sprint1`, `sprint2`, `inject-bad`) thay vì để mặc định UTC timestamp. Lý do: mở thư mục `artifacts/manifests/` thấy ngay `manifest_sprint1.json` vs `manifest_inject-bad.json` mà không cần đọc nội dung — tiện cho truy vết.

Khi phân tích manifest sprint1, tôi thấy `freshness_check=FAIL` với `age_hours=117.135` (> SLA 24h). Nguyên nhân: `latest_exported_at: "2026-04-10T08:00:00"` trong CSV mẫu cách thời điểm chạy `run_timestamp: "2026-04-15T05:13:33"` hơn 4 ngày. Đây là hành vi đúng — data mẫu cũ, không phải bug pipeline. Tôi ghi nhận để Ngọc (Docs Owner) giải thích trong runbook: SLA 24h áp cho data snapshot, không phải pipeline run.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Triệu chứng:** Khi chạy sprint2 lần 2 (sau inject 3 dòng test, raw 10→13), pipeline halt:

```
expectation[exported_at_not_future_24h] FAIL (halt) :: future_rows=1
PIPELINE_HALT: expectation suite failed (halt).
```

**Phát hiện bằng:** Expectation E12 (Việt Anh & Linh thêm) phát hiện 1 dòng inject có `exported_at` tương lai.

**Fix:** Kiểm tra CSV → xác nhận dòng inject sai timestamp. Sửa `exported_at` về `2026-04-10T08:00:00`. Chạy lại → E12 OK, `PIPELINE_OK`.

Ngoài ra, quarantine CSV cho thấy rule mới hoạt động đúng: dòng 3 bị quarantine lý do `internal_note_leak` (chứa `"ghi chú: bản sync cũ policy-v3 — lỗi migration"`), dòng 13 bị quarantine lý do `chunk_text_too_short` (text chỉ là `"Xem thêm."`).

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Manifest sprint1 (trước thêm rules, `run_id=sprint1`):**
```
raw_records=10, cleaned_records=6, quarantine_records=4
freshness_check=FAIL (age_hours=117.135, sla_hours=24.0)
```

**Sprint2 sau thêm rules + inject (`run_id=sprint2`):**
```
raw_records=13, cleaned_records=7, quarantine_records=6
expectation[exported_at_not_future_24h] FAIL → PIPELINE_HALT

```

Quarantine tăng từ 4→6 nhờ rule mới: `internal_note_leak` (dòng 3), `chunk_text_too_short` (dòng 13). Pipeline halt đúng thiết kế khi phát hiện data bất thường.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ viết script so sánh 2 manifest JSON (ví dụ `manifest_sprint1.json` vs `manifest_inject-bad.json`) để tự động highlight delta `cleaned_records`, `quarantine_records`, `no_refund_fix`. Hiện tại phải mở từng file đối chiếu thủ công — script diff manifest sẽ tiết kiệm thời gian debug khi có nhiều run.