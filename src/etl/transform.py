"""Giai đoạn 3b — Chuyển staging sang star schema (dim + fact).

Mọi phép biến đổi nằm ở đây, không nằm ở staging. Ba điểm quan trọng:

    1. `fact_monthly_usage` cần `seats_billed` để tính tỷ lệ lấp ghế. Cột này
       chỉ có trong hoá đơn, nên phải join theo (account_id, month).
    2. Cờ expansion/contraction được tính sẵn để SQL phân tích không phải lặp
       lại điều kiện ở mọi nơi.
    3. Trước khi ghi, kiểm tra toàn vẹn tham chiếu: mọi account_id trong fact
       phải tồn tại trong dim_account.

Chạy:
    python -m src.etl.transform
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from .config import DB_PATH
from .util import force_utf8_stdout

TIER_ORDER = {"starter": 1, "growth": 2, "business": 3, "enterprise": 4}
EXPANSION_TYPES = ("upgrade", "seat_add")
CONTRACTION_TYPES = ("downgrade", "seat_remove")


# -----------------------------------------------------------------------------
# Hàm phụ
# -----------------------------------------------------------------------------
def _read(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def _employee_band(n: int) -> str:
    if n < 50:
        return "1_1_49"
    if n < 200:
        return "2_50_199"
    if n < 500:
        return "3_200_499"
    if n < 2000:
        return "4_500_1999"
    return "5_2000_plus"


def _company_size(n: int) -> str:
    if n < 100:
        return "smb"
    if n < 1000:
        return "mid_market"
    return "enterprise"


def _usage_band(days: int) -> str:
    if days < 5:
        return "dormant"
    if days < 15:
        return "low"
    if days < 25:
        return "steady"
    return "power"


def _month_series(start: str, end: str) -> list[str]:
    months = pd.period_range(start=start, end=end, freq="M")
    return [p.strftime("%Y-%m-01") for p in months]


def _clear(conn: sqlite3.Connection, tables: list[str]) -> None:
    for t in tables:
        conn.execute(f"DELETE FROM {t}")


def _load(conn: sqlite3.Connection, df: pd.DataFrame, table: str) -> None:
    df.to_sql(table, conn, if_exists="append", index=False, chunksize=10_000)


# -----------------------------------------------------------------------------
# DIMENSIONS
# -----------------------------------------------------------------------------
def build_dim_plan(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_plans")
    out = pd.DataFrame({
        "plan_id": df["plan_id"],
        "plan_name": df["plan_name"],
        "tier": df["tier"],
        "base_price": df["base_price"].astype(float),
        "included_seats": df["included_seats"].astype(int),
        "price_per_seat": df["price_per_seat"].astype(float),
    })
    out["tier_order"] = out["tier"].map(TIER_ORDER).astype(int)
    return out.sort_values("tier_order").reset_index(drop=True)


def build_dim_account(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_accounts")
    plan = _read(conn, "stg_plans")[["plan_id", "tier"]].rename(
        columns={"plan_id": "initial_plan_id", "tier": "initial_tier"}
    )
    out = pd.DataFrame({
        "account_id": df["account_id"],
        "account_name": df["account_name"],
        "industry": df["industry"],
        "country": df["country"],
        "employees": df["employees"].astype(int),
        "acquisition_channel": df["acquisition_channel"],
        "signup_date": df["signup_date"],
        "signup_month": df["signup_date"].str.slice(0, 7) + "-01",
        "initial_plan_id": df["initial_plan_id"],
    })
    out["employee_band"] = out["employees"].map(_employee_band)
    out["company_size"] = out["employees"].map(_company_size)
    out = out.merge(plan, on="initial_plan_id", how="left")
    if out["initial_tier"].isna().any():
        raise ValueError("Có tài khoản trỏ tới plan_id không tồn tại")
    return out[[
        "account_id", "account_name", "industry", "country", "employees",
        "employee_band", "company_size", "acquisition_channel",
        "signup_date", "signup_month", "initial_plan_id", "initial_tier",
    ]]


def build_dim_month(conn: sqlite3.Connection) -> pd.DataFrame:
    acc = _read(conn, "stg_accounts")
    months = _month_series(acc["signup_date"].min(), "2025-12-01")
    out = pd.DataFrame({"month": months})
    p = pd.PeriodIndex(pd.to_datetime(out["month"]), freq="M")
    out["year"] = p.year
    out["quarter"] = p.quarter
    out["month_num"] = p.month
    out["month_label"] = p.strftime("%Y-%m")
    out["year_month_no"] = np.arange(1, len(out) + 1)
    return out


# -----------------------------------------------------------------------------
# FACTS
# -----------------------------------------------------------------------------
def build_fact_events(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_subscription_events")
    out = pd.DataFrame({
        "event_id": df["event_id"],
        "account_id": df["account_id"],
        "event_date": df["event_date"],
        "event_month": df["event_date"].str.slice(0, 7) + "-01",
        "event_type": df["event_type"],
        "from_plan_id": df["from_plan_id"].replace("", None),
        "to_plan_id": df["to_plan_id"].replace("", None),
        "seats_delta": df["seats_delta"].astype(int),
        "mrr_delta": df["mrr_delta"].astype(float),
        "reason": df["reason"].replace("", None),
    })
    out["mrr_increase"] = out["mrr_delta"].clip(lower=0)
    out["mrr_decrease"] = out["mrr_delta"].clip(upper=0)
    out["is_expansion"] = out["event_type"].isin(EXPANSION_TYPES).astype(int)
    out["is_contraction"] = out["event_type"].isin(CONTRACTION_TYPES).astype(int)
    out["is_churn"] = (out["event_type"] == "churn").astype(int)
    return out


def build_fact_invoices(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_invoices")
    out = pd.DataFrame({
        "invoice_id": df["invoice_id"],
        "account_id": df["account_id"],
        "invoice_date": df["invoice_date"],
        "invoice_month": df["invoice_date"].str.slice(0, 7) + "-01",
        "period_start": df["period_start"],
        "period_end": df["period_end"],
        "plan_id": df["plan_id"],
        "seats_billed": df["seats_billed"].astype(int),
        "amount": df["amount"].astype(float),
        "status": df["status"],
        "payment_method": df["payment_method"],
    })
    out["is_paid"] = (out["status"] == "paid").astype(int)
    out["is_failed"] = (out["status"] == "failed").astype(int)
    return out


def build_fact_usage(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_monthly_usage")
    inv = _read(conn, "stg_invoices")

    out = pd.DataFrame({
        "account_id": df["account_id"],
        "month": df["month"],
        "active_days": df["active_days"].astype(int),
        "seats_active": df["seats_active"].astype(int),
        "features_used": df["features_used"].astype(int),
        "api_calls": df["api_calls"].astype(int),
    })

    billed = pd.DataFrame({
        "account_id": inv["account_id"],
        "month": inv["invoice_date"].str.slice(0, 7) + "-01",
        "seats_billed": inv["seats_billed"].astype(int),
    })
    billed = billed.drop_duplicates(subset=["account_id", "month"])
    out = out.merge(billed, on=["account_id", "month"], how="left")

    missing = int(out["seats_billed"].isna().sum())
    if missing:
        raise ValueError(f"{missing} dòng usage không tìm thấy hoá đơn tương ứng")

    out["seats_billed"] = out["seats_billed"].astype(int)
    out["seat_utilization"] = (out["seats_active"] / out["seats_billed"]).round(4)
    out["usage_band"] = out["active_days"].map(_usage_band)
    return out[[
        "account_id", "month", "active_days", "seats_active", "seats_billed",
        "features_used", "api_calls", "seat_utilization", "usage_band",
    ]]


def build_fact_tickets(conn: sqlite3.Connection) -> pd.DataFrame:
    df = _read(conn, "stg_support_tickets")
    out = pd.DataFrame({
        "ticket_id": df["ticket_id"],
        "account_id": df["account_id"],
        "opened_at": df["opened_at"],
        "opened_month": df["opened_at"].str.slice(0, 7) + "-01",
        "priority": df["priority"],
        "category": df["category"],
        "resolution_hours": df["resolution_hours"].astype(float),
        "satisfaction": df["satisfaction"].astype(int),
    })
    out["is_low_satisfaction"] = (out["satisfaction"] <= 3).astype(int)
    return out


# -----------------------------------------------------------------------------
# KIỂM TRA TOÀN VẸN
# -----------------------------------------------------------------------------
def _check_integrity(conn: sqlite3.Connection,
                     facts: dict[str, pd.DataFrame],
                     accounts: pd.DataFrame) -> None:
    valid = set(accounts["account_id"])
    problems: list[str] = []
    for name, df in facts.items():
        orphans = set(df["account_id"]) - valid
        if orphans:
            problems.append(f"{name}: {len(orphans)} account_id không có trong dim_account")
    if problems:
        raise ValueError("Vi phạm toàn vẹn tham chiếu:\n  " + "\n  ".join(problems))


def main() -> None:
    force_utf8_stdout()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Chưa có database: {DB_PATH}")

    line = "=" * 74
    print(line)
    print("TRANSFORM SANG STAR SCHEMA (GIAI ĐOẠN 3b)")
    print(line)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        print("\n[A] Dimensions")
        dim_plan = build_dim_plan(conn)
        dim_account = build_dim_account(conn)
        dim_month = build_dim_month(conn)

        _clear(conn, ["dim_plan", "dim_account", "dim_month"])
        _load(conn, dim_plan, "dim_plan")
        _load(conn, dim_account, "dim_account")
        _load(conn, dim_month, "dim_month")
        conn.commit()
        print(f"  dim_plan      {len(dim_plan):>8,} dòng")
        print(f"  dim_account   {len(dim_account):>8,} dòng")
        print(f"  dim_month     {len(dim_month):>8,} dòng")

        print("\n[B] Facts")
        fact_events = build_fact_events(conn)
        fact_invoices = build_fact_invoices(conn)
        fact_usage = build_fact_usage(conn)
        fact_tickets = build_fact_tickets(conn)

        facts = {
            "fact_subscription_events": fact_events,
            "fact_invoices": fact_invoices,
            "fact_monthly_usage": fact_usage,
            "fact_support_tickets": fact_tickets,
        }
        _check_integrity(conn, facts, dim_account)

        _clear(conn, list(facts))
        for name, df in facts.items():
            _load(conn, df, name)
        conn.commit()
        for name, df in facts.items():
            print(f"  {name:<26} {len(df):>8,} dòng")

        print("\n[C] Kiểm tra nhanh")
        n_acc = conn.execute("SELECT COUNT(*) FROM dim_account").fetchone()[0]
        n_churn = conn.execute(
            "SELECT COUNT(*) FROM fact_subscription_events WHERE is_churn = 1"
        ).fetchone()[0]
        mrr_last = conn.execute(
            "SELECT ROUND(SUM(mrr_delta), 2) FROM fact_subscription_events "
            "WHERE event_month <= (SELECT MAX(month) FROM dim_month)"
        ).fetchone()[0]
        print(f"  Tài khoản đăng ký : {n_acc:,}")
        print(f"  Tài khoản đã huỷ  : {n_churn:,}")
        print(f"  Còn hoạt động     : {n_acc - n_churn:,}")
        print(f"  MRR kỳ cuối       : ${mrr_last:,.0f}")
    finally:
        conn.close()

    print("\nBước tiếp theo: python -m src.etl.validate")


if __name__ == "__main__":
    main()
