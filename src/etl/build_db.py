"""Giai đoạn 3a — Dựng database và nạp 6 file CSV vào tầng staging.

Nguyên tắc: tầng staging là **bản sao nguyên trạng**. Mọi cột được đọc dưới
dạng chuỗi (dtype=str) để không có bất kỳ phép ép kiểu nào làm thay đổi giá
trị gốc. Kiểm tra này được xác nhận lại bằng hash từng dòng ở validate.py.

Chạy:
    python -m src.etl.build_db
"""

from __future__ import annotations

import sqlite3
import time

import pandas as pd

from .config import DATA_RAW, DB_PATH, SQL_DIR
from .util import force_utf8_stdout

# (tên bảng staging, tên file CSV)
STAGING_LOAD_ORDER: list[tuple[str, str]] = [
    ("stg_plans", "plans.csv"),
    ("stg_accounts", "accounts.csv"),
    ("stg_subscription_events", "subscription_events.csv"),
    ("stg_invoices", "invoices.csv"),
    ("stg_monthly_usage", "monthly_usage.csv"),
    ("stg_support_tickets", "support_tickets.csv"),
]


def main() -> None:
    force_utf8_stdout()

    missing = [f for _, f in STAGING_LOAD_ORDER if not (DATA_RAW / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Thiếu {len(missing)} file CSV trong {DATA_RAW}. "
            "Chạy trước: python -m src.etl.generate_data"
        )

    if DB_PATH.exists():
        DB_PATH.unlink()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    line = "=" * 74
    print(line)
    print("DỰNG DATABASE + NẠP STAGING (GIAI ĐOẠN 3a)")
    print(line)
    print(f"Database: {DB_PATH}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")

        schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.commit()
        print("Đã tạo schema.\n")

        total_rows = 0
        for i, (table, filename) in enumerate(STAGING_LOAD_ORDER, start=1):
            t0 = time.perf_counter()
            df = pd.read_csv(DATA_RAW / filename, dtype=str,
                             keep_default_na=False, na_values=[""])
            df.to_sql(table, conn, if_exists="append", index=False, chunksize=10_000)

            n_rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            total_rows += n_rows
            print(f"[{i}/{len(STAGING_LOAD_ORDER)}] {table:<26} "
                  f"{n_rows:>8,} dòng x {df.shape[1]:>2} cột   "
                  f"({time.perf_counter() - t0:5.1f}s)")

        conn.commit()
        print()
        print(line)
        print(f"TỔNG: {total_rows:,} dòng trong {len(STAGING_LOAD_ORDER)} bảng staging")
        print(f"Dung lượng database: {DB_PATH.stat().st_size / 1e6:.1f} MB")
        print(line)
    finally:
        conn.close()

    print("\nBước tiếp theo: python -m src.etl.transform")


if __name__ == "__main__":
    main()
