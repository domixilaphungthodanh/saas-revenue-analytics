"""Giai đoạn 4 — Kiểm tra chất lượng dữ liệu và tính đúng đắn của phép tính.

Ba nhóm kiểm tra:
    A. Trung thực của tầng staging  — staging phải trùng khít file CSV gốc
    B. Toàn vẹn cấu trúc            — khoá, tham chiếu, duy nhất
    C. Logic nghiệp vụ              — các đẳng thức MRR / churn / cohort phải khớp

Mọi kiểm tra đều ghi kết quả vào mart_data_quality để xem lại sau.

Chạy:
    python -m src.etl.validate
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

import pandas as pd

from .config import DATA_RAW, DB_PATH
from .util import force_utf8_stdout

STAGING_TABLES: list[tuple[str, str]] = [
    ("stg_plans", "plans.csv"),
    ("stg_accounts", "accounts.csv"),
    ("stg_subscription_events", "subscription_events.csv"),
    ("stg_invoices", "invoices.csv"),
    ("stg_monthly_usage", "monthly_usage.csv"),
    ("stg_support_tickets", "support_tickets.csv"),
]


@dataclass
class Check:
    code: str
    category: str
    description: str
    value: float
    expected: str
    passed: bool
    detail: str = ""

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def scalar(conn: sqlite3.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def check_zero(conn, code, category, description, sql, detail_sql=None) -> Check:
    """Quy tắc dạng 'phải bằng 0' — dùng cho đếm vi phạm."""
    n = scalar(conn, sql)
    detail = ""
    if n and detail_sql:
        rows = conn.execute(detail_sql).fetchmany(3)
        detail = "; ".join(str(r) for r in rows)
    return Check(code, category, description, float(n), "0", n == 0, detail)


def check_positive(conn, code, category, description, sql) -> Check:
    n = scalar(conn, sql)
    return Check(code, category, description, float(n), "> 0", (n or 0) > 0)


def check_equal(conn, code, category, description, sql_a, sql_b) -> Check:
    a, b = scalar(conn, sql_a), scalar(conn, sql_b)
    return Check(code, category, description, float(a or 0), f"= {b}",
                 a == b, f"trái={a}, phải={b}")


# =============================================================================
# A. TRUNG THỰC CỦA STAGING
# =============================================================================
def check_staging(conn: sqlite3.Connection) -> list[Check]:
    out: list[Check] = []
    for table, fname in STAGING_TABLES:
        path = DATA_RAW / fname
        if not path.exists():
            out.append(Check(f"A-{table}", "A. Staging", f"{fname} tồn tại", 0, "1", False))
            continue

        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""]).fillna("")
        csv_hash = sorted(
            hashlib.md5("\x1f".join(str(v) for v in row).encode("utf-8")).hexdigest()
            for row in df.itertuples(index=False)
        )
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        db_hash = sorted(
            hashlib.md5("\x1f".join("" if v is None else str(v) for v in row).encode("utf-8")).hexdigest()
            for row in rows
        )

        same_rows = len(csv_hash) == len(db_hash)
        same_content = csv_hash == db_hash
        out.append(Check(
            f"A-{table}-rows", "A. Staging",
            f"{fname}: số dòng CSV khớp staging",
            len(df), f"= {len(rows)}", same_rows,
        ))
        out.append(Check(
            f"A-{table}-hash", "A. Staging",
            f"{fname}: hash từng dòng khớp tuyệt đối",
            1.0 if same_content else 0.0, "= 1", same_content,
            "" if same_content else "có dòng bị biến đổi khi nạp",
        ))
    return out


# =============================================================================
# B + C. CẤU TRÚC VÀ LOGIC
# =============================================================================
def check_structure(conn: sqlite3.Connection) -> list[Check]:
    checks: list[Check] = []

    # --- B. Toàn vẹn tham chiếu
    for fact in ["fact_subscription_events", "fact_invoices",
                 "fact_monthly_usage", "fact_support_tickets"]:
        checks.append(check_zero(
            conn, f"B-{fact}-fk", "B. Cấu trúc",
            f"{fact}: account_id mồ côi",
            f"SELECT COUNT(*) FROM {fact} f WHERE NOT EXISTS "
            f"(SELECT 1 FROM dim_account a WHERE a.account_id = f.account_id)",
        ))

    checks.append(check_zero(
        conn, "B-invoice-plan-fk", "B. Cấu trúc",
        "fact_invoices: plan_id mồ côi",
        "SELECT COUNT(*) FROM fact_invoices i WHERE NOT EXISTS "
        "(SELECT 1 FROM dim_plan p WHERE p.plan_id = i.plan_id)",
    ))

    # --- B. Duy nhất
    for table, key in [("dim_account", "account_id"), ("dim_plan", "plan_id"),
                       ("fact_subscription_events", "event_id"),
                       ("fact_invoices", "invoice_id"),
                       ("fact_support_tickets", "ticket_id")]:
        checks.append(check_zero(
            conn, f"B-{table}-pk", "B. Cấu trúc",
            f"{table}: {key} bị trùng",
            f"SELECT COUNT(*) FROM (SELECT {key} FROM {table} "
            f"GROUP BY {key} HAVING COUNT(*) > 1)",
        ))

    checks.append(check_zero(
        conn, "B-usage-pk", "B. Cấu trúc",
        "fact_monthly_usage: (account_id, month) bị trùng",
        "SELECT COUNT(*) FROM (SELECT account_id, month FROM fact_monthly_usage "
        "GROUP BY account_id, month HAVING COUNT(*) > 1)",
    ))

    # --- B. Miền giá trị
    checks.append(check_zero(
        conn, "B-seat-util-range", "B. Cấu trúc",
        "seat_utilization nằm ngoài [0, 1]",
        "SELECT COUNT(*) FROM fact_monthly_usage "
        "WHERE seat_utilization < 0 OR seat_utilization > 1",
    ))
    checks.append(check_zero(
        conn, "B-satisfaction-range", "B. Cấu trúc",
        "satisfaction nằm ngoài [1, 5]",
        "SELECT COUNT(*) FROM fact_support_tickets "
        "WHERE satisfaction < 1 OR satisfaction > 5",
    ))
    checks.append(check_zero(
        conn, "B-amount-negative", "B. Cấu trúc",
        "hoá đơn có amount <= 0",
        "SELECT COUNT(*) FROM fact_invoices WHERE amount <= 0",
    ))
    checks.append(check_zero(
        conn, "B-seats-negative", "B. Cấu trúc",
        "hoá đơn có seats_billed <= 0",
        "SELECT COUNT(*) FROM fact_invoices WHERE seats_billed <= 0",
    ))
    checks.append(check_zero(
        conn, "B-active-days-range", "B. Cấu trúc",
        "active_days nằm ngoài [0, 31]",
        "SELECT COUNT(*) FROM fact_monthly_usage "
        "WHERE active_days < 0 OR active_days > 31",
    ))

    # --- C. Logic nghiệp vụ
    checks.append(check_zero(
        conn, "C-one-new-event", "C. Logic",
        "tài khoản không có đúng 1 sự kiện 'new'",
        "SELECT COUNT(*) FROM (SELECT account_id FROM fact_subscription_events "
        "WHERE event_type = 'new' GROUP BY account_id HAVING COUNT(*) <> 1 "
        "UNION ALL SELECT account_id FROM dim_account a WHERE NOT EXISTS "
        "(SELECT 1 FROM fact_subscription_events e WHERE e.account_id = a.account_id "
        "AND e.event_type = 'new'))",
    ))

    checks.append(check_equal(
        conn, "C-account-balance", "C. Logic",
        "số tài khoản = đã huỷ + còn hoạt động",
        "SELECT COUNT(*) FROM dim_account",
        "SELECT (SELECT COUNT(DISTINCT account_id) FROM fact_subscription_events WHERE is_churn = 1) "
        "+ (SELECT COUNT(*) FROM dim_account a WHERE NOT EXISTS "
        "(SELECT 1 FROM fact_subscription_events e WHERE e.account_id = a.account_id AND e.is_churn = 1))",
    ))

    checks.append(check_zero(
        conn, "C-event-before-signup", "C. Logic",
        "sự kiện xảy ra trước ngày đăng ký",
        "SELECT COUNT(*) FROM fact_subscription_events e JOIN dim_account a "
        "ON a.account_id = e.account_id WHERE e.event_date < a.signup_date",
    ))

    checks.append(check_zero(
        conn, "C-churn-reason-null", "C. Logic",
        "sự kiện huỷ thiếu lý do",
        "SELECT COUNT(*) FROM fact_subscription_events "
        "WHERE is_churn = 1 AND (reason IS NULL OR reason = '')",
    ))

    checks.append(check_zero(
        conn, "C-two-churns", "C. Logic",
        "một tài khoản bị huỷ nhiều hơn 1 lần",
        "SELECT COUNT(*) FROM (SELECT account_id FROM fact_subscription_events "
        "WHERE is_churn = 1 GROUP BY account_id HAVING COUNT(*) > 1)",
    ))

    checks.append(check_zero(
        conn, "C-usage-after-churn", "C. Logic",
        "có dữ liệu sử dụng sau tháng huỷ",
        "SELECT COUNT(*) FROM fact_monthly_usage u JOIN "
        "(SELECT account_id, MIN(event_month) cm FROM fact_subscription_events "
        " WHERE is_churn = 1 GROUP BY account_id) c ON c.account_id = u.account_id "
        "WHERE u.month > c.cm",
    ))

    checks.append(check_zero(
        conn, "C-invoice-without-usage", "C. Logic",
        "hoá đơn không có dòng sử dụng cùng tháng",
        "SELECT COUNT(*) FROM fact_invoices i WHERE NOT EXISTS "
        "(SELECT 1 FROM fact_monthly_usage u WHERE u.account_id = i.account_id "
        "AND u.month = i.invoice_month)",
    ))

    checks.append(check_zero(
        conn, "C-invoice-period-mismatch", "C. Logic",
        "invoice_month khác tháng của period_start",
        "SELECT COUNT(*) FROM fact_invoices "
        "WHERE SUBSTR(period_start, 1, 7) <> SUBSTR(invoice_month, 1, 7)",
    ))

    checks.append(check_zero(
        conn, "C-negative-mrr-except-churn", "C. Logic",
        "sự kiện làm giảm MRR nhưng không phải huỷ/thu hẹp",
        "SELECT COUNT(*) FROM fact_subscription_events "
        "WHERE mrr_delta < 0 AND is_churn = 0 AND is_contraction = 0",
    ))

    checks.append(check_zero(
        conn, "C-new-event-negative", "C. Logic",
        "sự kiện 'new' có MRR <= 0",
        "SELECT COUNT(*) FROM fact_subscription_events "
        "WHERE event_type = 'new' AND mrr_delta <= 0",
    ))

    # --- C. Đẳng thức MRR
    checks.append(check_equal(
        conn, "C-mrr-reconcile", "C. Logic",
        "MRR cuối kỳ = tổng mrr_delta của mọi sự kiện",
        "SELECT ROUND(COALESCE(SUM(mrr_delta), 0), 2) FROM fact_subscription_events",
        "SELECT ROUND(COALESCE(SUM(mrr_end), 0), 2) FROM mart_mrr_monthly "
        "WHERE month = (SELECT MAX(month) FROM mart_mrr_monthly)",
    ))

    checks.append(check_zero(
        conn, "C-mrr-bridge", "C. Logic",
        "công thức cầu nối MRR không khớp",
        "SELECT COUNT(*) FROM mart_mrr_monthly "
        "WHERE ABS(mrr_end - (mrr_start + new_mrr + expansion_mrr "
        "                      + contraction_mrr + churn_mrr)) > 0.01",
    ))

    checks.append(check_zero(
        conn, "C-mrr-chain", "C. Logic",
        "MRR đầu tháng không nối tiếp MRR cuối tháng trước",
        "WITH x AS (SELECT month, mrr_start, mrr_end, "
        "  LAG(mrr_end) OVER (ORDER BY month) prev FROM mart_mrr_monthly) "
        "SELECT COUNT(*) FROM x WHERE prev IS NOT NULL AND ABS(mrr_start - prev) > 0.01",
    ))

    # --- C. Sanity của mart
    checks.append(check_zero(
        conn, "C-cohort-baseline", "C. Logic",
        "cohort retention tháng 0 khác 100%",
        "SELECT COUNT(*) FROM mart_cohort_retention "
        "WHERE month_index = 0 AND ABS(retention_pct - 100) > 0.01",
    ))

    checks.append(check_zero(
        conn, "C-churn-rate-bound", "C. Logic",
        "tỷ lệ huỷ nằm ngoài [0, 100]",
        "SELECT COUNT(*) FROM mart_churn_by_segment "
        "WHERE churn_rate_pct < 0 OR churn_rate_pct > 100",
    ))

    checks.append(check_equal(
        conn, "C-risk-sum", "C. Logic",
        "tổng tài khoản trong bảng rủi ro khác dim_account",
        "SELECT SUM(accounts) FROM mart_risk_summary",
        "SELECT COUNT(*) FROM dim_account",
    ))

    checks.append(check_zero(
        conn, "C-nrr-range", "C. Logic",
        "NRR tháng nằm ngoài khoảng hợp lý [0, 300]",
        "SELECT COUNT(*) FROM mart_mrr_monthly "
        "WHERE nrr_pct IS NOT NULL AND (nrr_pct < 0 OR nrr_pct > 300)",
    ))

    return checks


# =============================================================================
# GHI KẾT QUẢ
# =============================================================================
def write_results(conn: sqlite3.Connection, checks: list[Check]) -> None:
    conn.execute("DROP TABLE IF EXISTS mart_data_quality")
    conn.execute("""
        CREATE TABLE mart_data_quality (
            code        TEXT PRIMARY KEY,
            category    TEXT,
            description TEXT,
            value       REAL,
            expected    TEXT,
            status      TEXT,
            detail      TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO mart_data_quality VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(c.code, c.category, c.description, c.value, c.expected, c.status, c.detail)
         for c in checks],
    )

    conn.execute("DROP TABLE IF EXISTS mart_data_quality_summary")
    conn.execute("""
        CREATE TABLE mart_data_quality_summary AS
        SELECT category,
               COUNT(*) AS checks,
               SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed,
               SUM(CASE WHEN status = 'FAIL' THEN 1 ELSE 0 END) AS failed
        FROM mart_data_quality
        GROUP BY category
    """)
    conn.commit()


def main() -> None:
    force_utf8_stdout()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Chưa có database: {DB_PATH}")

    line = "=" * 74
    print(line)
    print("KIỂM TRA CHẤT LƯỢNG DỮ LIỆU (GIAI ĐOẠN 4)")
    print(line)

    conn = sqlite3.connect(DB_PATH)
    try:
        print("\n[A] Kiểm tra trung thực tầng staging (hash từng dòng)")
        checks = check_staging(conn)

        print("[B/C] Kiểm tra cấu trúc và logic nghiệp vụ")
        checks += check_structure(conn)

        write_results(conn, checks)
    finally:
        conn.close()

    passed = sum(c.passed for c in checks)
    failed = len(checks) - passed

    print()
    for c in checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.code:<28} {c.description}")
        if not c.passed and c.detail:
            print(f"         -> {c.detail}")

    print()
    print(line)
    print(f"KẾT QUẢ: {passed} PASS / {failed} FAIL  (tổng {len(checks)} quy tắc)")
    print(f"Bảng kết quả: mart_data_quality, mart_data_quality_summary")
    print(line)

    if failed:
        raise SystemExit(1)
    print("\nBước tiếp theo: python -m src.analysis.run_marts")


if __name__ == "__main__":
    main()
