# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

Họ và tên: Nguyễn Thùy Linh  
Vai trò: Cleaning / Quality Owner (CQ)  
Ngày nộp: 15/04/2026

## 1. Phần tôi phụ trách

Tôi phụ trách mảng chất lượng dữ liệu cùng bạn Phạm Việt Anh, tập trung vào file quality/expectations.py và kiểm thử tác động của các rule mới từ transform/cleaning_rules.py. Công việc chính của tôi là bổ sung expectation để chặn dữ liệu không an toàn trước bước embed, sau đó đối chiếu lại log và quarantine để xác nhận rule có tác động thực, không làm cho đủ số lượng.

Các expectation tôi trực tiếp bổ sung và chỉnh sửa gồm:
- E7 no_empty_exported_at (warn)
- E8 chunk_id_unique (halt)
- E9 no_invisible_chars_in_chunk_text (halt)
- E10 no_internal_note_leak (halt)
- E11 chunk_min_length_20 (halt)
- E12 exported_at_not_future_24h (halt)

Tôi phối hợp với Ingestion Owner để chạy lại pipeline ở các run_id sprint2, sprint2-rerun, inject-bad, restore-clean nhằm đọc được số liệu trước/sau phục vụ báo cáo nhóm.

## 2. Một quyết định kỹ thuật tôi đưa ra

Quyết định quan trọng của tôi là tách rõ mức độ warn và halt theo mức rủi ro nghiệp vụ.

- no_empty_exported_at đặt warn vì thiếu timestamp là vấn đề quan sát, chưa chắc làm sai ngay câu trả lời retrieval.
- chunk_id_unique, no_internal_note_leak và exported_at_not_future_24h đặt halt vì các lỗi này có thể làm hỏng index hoặc đưa ngữ cảnh sai vào top-k.

Kết quả trong log run_sprint2.log cho thấy thiết kế này hoạt động đúng: mọi expectation đều OK, pipeline vẫn chạy đến embed_upsert count=5 và PIPELINE_OK. Điều này giúp nhóm tránh tình trạng pipeline dừng vì các lỗi “mềm”, nhưng vẫn chặn được lỗi “cứng” trước khi publish vector.

## 3. Một lỗi/anomaly tôi xử lý

Trong quá trình kiểm thử expectation mới, tôi gặp lỗi runtime ở E12 khi parse thời gian exported_at:

TypeError: can't compare offset-naive and offset-aware datetimes

Nguyên nhân là một số exported_at parse ra datetime không có timezone, trong khi mốc now dùng timezone UTC. Tôi sửa ở quality/expectations.py bằng cách chuẩn hóa exp_dt về UTC khi tzinfo bị thiếu, rồi mới so sánh với now + 24 giờ.

Sau khi sửa, pipeline chạy qua được bước expectation và cho kết quả đúng logic dữ liệu. Ở lần chạy có inject timestamp tương lai (run_id=sprint2 với raw_records=13), log ghi expectation[exported_at_not_future_24h] FAIL (halt) :: future_rows=1 và PIPELINE_HALT. Đây là hành vi mong muốn vì rule phải chặn dữ liệu bất thường trước embed.

## 4. Bằng chứng before/after

Vì công việc chính của tôi là bổ sung expectation, tôi dùng bằng chứng before/after theo đúng luồng validate trước khi embed:

Before (run_id=sprint2, dữ liệu chuẩn):
- Trong run_sprint2.log, toàn bộ expectation mới đều pass:
	expectation[no_empty_exported_at] OK,
	expectation[chunk_id_unique] OK,
	expectation[no_invisible_chars_in_chunk_text] OK,
	expectation[no_internal_note_leak] OK,
	expectation[chunk_min_length_20] OK,
	expectation[exported_at_not_future_24h] OK.
- Kết quả pipeline: PIPELINE_OK và embed_upsert count=5.

After (lần inject để kiểm thử expectation):
- Ở run_sprint2.log (lần raw_records=13), expectation[exported_at_not_future_24h] FAIL (halt) :: future_rows=1.
- Pipeline dừng tại bước validate: PIPELINE_HALT: expectation suite failed (halt), tức dữ liệu không được đi tiếp vào embed.
- Bằng chứng nguyên nhân nằm trong quarantine_inject-bad.csv: reason=future_exported_at, exported_at_raw=2099-12-31T23:59:59.

Tác động đến chất lượng retrieval sau khi khôi phục clean run:
- before_inject_bad.csv: q_refund_window có hits_forbidden=yes.
- after_restore.csv: q_refund_window chuyển về hits_forbidden=no.

Điểm tôi muốn chứng minh là expectation không chỉ để “đếm lỗi”, mà thật sự tạo chốt chặn quality gate: phát hiện dữ liệu bất thường đúng lúc, ngăn embed sai, và góp phần phục hồi tín hiệu retrieval sau khi chạy lại dữ liệu sạch.

## 5. Cải tiến nếu có thêm 2 giờ

Tôi sẽ bổ sung test tự động cho run_expectations bằng pytest theo các case biên: datetime có/không timezone, chunk chứa invisible chars, nội dung nội bộ, và duplicate chunk_id. Khi có test, nhóm sẽ phát hiện sớm lỗi logic như naive/aware datetime ngay trong CI thay vì đợi tới lúc chạy pipeline thủ công.