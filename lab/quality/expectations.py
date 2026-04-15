"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []
    now_utc = datetime.now(timezone.utc)

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7: exported_at không được rỗng
    bad_exported_at = [r for r in cleaned_rows if not (r.get("exported_at") or "").strip()]
    ok7 = len(bad_exported_at) == 0
    results.append(
        ExpectationResult(
            "no_empty_exported_at",
            ok7,
            "warn",
            f"empty_exported_at_count={len(bad_exported_at)}",
        )
    )

    # E8: chunk_id phải duy nhất
    chunk_ids = [r.get("chunk_id") for r in cleaned_rows if (r.get("chunk_id") or "").strip()]
    duplicate_chunk_ids = sorted({chunk_id for chunk_id in chunk_ids if chunk_ids.count(chunk_id) > 1})
    ok8 = len(duplicate_chunk_ids) == 0
    results.append(
        ExpectationResult(
            "chunk_id_unique",
            ok8,
            "halt",
            f"duplicate_chunk_ids={len(duplicate_chunk_ids)}",
        )
    )

    # E9: chunk_text sau clean không còn ký tự invisible/BOM
    invisible_re = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060\u00a0\ufffe]")
    bad_invisible = [r for r in cleaned_rows if invisible_re.search(r.get("chunk_text") or "")]
    ok9 = len(bad_invisible) == 0
    results.append(
        ExpectationResult(
            "no_invisible_chars_in_chunk_text",
            ok9,
            "halt",
            f"violations={len(bad_invisible)}",
        )
    )

    # E10: chunk_text không chứa marker ghi chú nội bộ/migration lỗi
    internal_note_re = re.compile(r"\(ghi chú:.*?\)", re.IGNORECASE | re.DOTALL)
    migration_err_re = re.compile(r"lỗi migration", re.IGNORECASE)
    bad_internal_note = [
        r
        for r in cleaned_rows
        if internal_note_re.search(r.get("chunk_text") or "")
        or migration_err_re.search(r.get("chunk_text") or "")
    ]
    ok10 = len(bad_internal_note) == 0
    results.append(
        ExpectationResult(
            "no_internal_note_leak",
            ok10,
            "halt",
            f"violations={len(bad_internal_note)}",
        )
    )

    # E11: chunk_text đạt độ dài tối thiểu 20 ký tự theo rule clean mới
    too_short_20 = [r for r in cleaned_rows if len((r.get("chunk_text") or "").strip()) < 20]
    ok11 = len(too_short_20) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_20",
            ok11,
            "halt",
            f"short_chunks={len(too_short_20)}",
        )
    )

    # E12: exported_at (nếu có) không được ở tương lai quá 24h
    future_exported_at = []
    for r in cleaned_rows:
        exported_at = (r.get("exported_at") or "").strip()
        if not exported_at:
            continue
        try:
            exp_dt = datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)

            if exp_dt > now_utc + timedelta(hours=24):
                future_exported_at.append(r)
        except ValueError:
            # File clean cho phép giữ nguyên exported_at không parse được.
            continue

    ok12 = len(future_exported_at) == 0
    results.append(
        ExpectationResult(
            "exported_at_not_future_24h",
            ok12,
            "halt",
            f"future_rows={len(future_exported_at)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
