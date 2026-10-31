-- =============================================================================
-- SCHEMA — SAAS REVENUE ANALYTICS
-- Ba tầng: staging (dữ liệu thô) → dim/fact (star schema) → mart (phân tích)
-- Chạy tự động bởi src/etl/build_db.py
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
-- TẦNG 1: STAGING
-- Mọi cột đều là TEXT để bảo toàn nguyên trạng giá trị gốc. Không ép kiểu,
-- không làm tròn, không đổi định dạng ngày. Phép biến đổi chỉ xảy ra ở tầng 2.
-- =============================================================================

CREATE TABLE IF NOT EXISTS stg_plans (
    plan_id        TEXT,
    plan_name      TEXT,
    tier           TEXT,
    base_price     TEXT,
    included_seats TEXT,
    price_per_seat TEXT
);

CREATE TABLE IF NOT EXISTS stg_accounts (
    account_id          TEXT,
    account_name        TEXT,
    industry            TEXT,
    country             TEXT,
    employees           TEXT,
    acquisition_channel TEXT,
    signup_date         TEXT,
    initial_plan_id     TEXT
);

CREATE TABLE IF NOT EXISTS stg_subscription_events (
    event_id     TEXT,
    account_id   TEXT,
    event_date   TEXT,
    event_type   TEXT,
    from_plan_id TEXT,
    to_plan_id   TEXT,
    seats_delta  TEXT,
    mrr_delta    TEXT,
    reason       TEXT
);

CREATE TABLE IF NOT EXISTS stg_invoices (
    invoice_id     TEXT,
    account_id     TEXT,
    invoice_date   TEXT,
    period_start   TEXT,
    period_end     TEXT,
    plan_id        TEXT,
    seats_billed   TEXT,
    amount         TEXT,
    status         TEXT,
    payment_method TEXT
);

CREATE TABLE IF NOT EXISTS stg_monthly_usage (
    account_id   TEXT,
    month        TEXT,
    active_days  TEXT,
    seats_active TEXT,
    features_used TEXT,
    api_calls    TEXT
);

CREATE TABLE IF NOT EXISTS stg_support_tickets (
    ticket_id        TEXT,
    account_id       TEXT,
    opened_at        TEXT,
    priority         TEXT,
    category         TEXT,
    resolution_hours TEXT,
    satisfaction     TEXT
);

-- =============================================================================
-- TẦNG 2: DIMENSIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS dim_plan (
    plan_id        TEXT PRIMARY KEY,
    plan_name      TEXT NOT NULL,
    tier           TEXT NOT NULL,
    base_price     REAL NOT NULL,
    included_seats INTEGER NOT NULL,
    price_per_seat REAL NOT NULL,
    tier_order     INTEGER NOT NULL      -- 1=thấp nhất … 4=cao nhất, để sắp xếp
);

CREATE TABLE IF NOT EXISTS dim_account (
    account_id          TEXT PRIMARY KEY,
    account_name        TEXT NOT NULL,
    industry            TEXT NOT NULL,
    country             TEXT NOT NULL,
    employees           INTEGER NOT NULL,
    employee_band       TEXT NOT NULL,
    company_size        TEXT NOT NULL,      -- SMB / Mid-market / Enterprise
    acquisition_channel TEXT NOT NULL,
    signup_date         TEXT NOT NULL,      -- YYYY-MM-DD
    signup_month        TEXT NOT NULL,      -- YYYY-MM-01
    initial_plan_id     TEXT NOT NULL,
    initial_tier        TEXT NOT NULL,
    FOREIGN KEY (initial_plan_id) REFERENCES dim_plan (plan_id)
);

CREATE TABLE IF NOT EXISTS dim_month (
    month       TEXT PRIMARY KEY,           -- YYYY-MM-01
    year        INTEGER NOT NULL,
    quarter     INTEGER NOT NULL,
    month_num   INTEGER NOT NULL,
    month_label TEXT NOT NULL,              -- 2023-01
    year_month_no INTEGER NOT NULL          -- số thứ tự tháng, dùng tính tenure
);

-- =============================================================================
-- TẦNG 2: FACTS
-- =============================================================================

-- Grain: 1 dòng = 1 sự kiện vòng đời thuê bao
CREATE TABLE IF NOT EXISTS fact_subscription_events (
    event_id       TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL,
    event_date     TEXT NOT NULL,
    event_month    TEXT NOT NULL,
    event_type     TEXT NOT NULL,           -- new/upgrade/downgrade/seat_add/seat_remove/churn
    from_plan_id   TEXT,
    to_plan_id     TEXT,
    seats_delta    INTEGER NOT NULL,
    mrr_delta      REAL NOT NULL,           -- âm = giảm MRR
    reason         TEXT,
    mrr_increase   REAL NOT NULL,           -- phần tăng (>=0)
    mrr_decrease   REAL NOT NULL,           -- phần giảm (<=0)
    is_expansion   INTEGER NOT NULL,        -- 1 nếu upgrade hoặc seat_add
    is_contraction INTEGER NOT NULL,        -- 1 nếu downgrade hoặc seat_remove
    is_churn       INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES dim_account (account_id)
);

-- Grain: 1 dòng = 1 hoá đơn
CREATE TABLE IF NOT EXISTS fact_invoices (
    invoice_id     TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL,
    invoice_date   TEXT NOT NULL,
    invoice_month  TEXT NOT NULL,
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    plan_id        TEXT NOT NULL,
    seats_billed   INTEGER NOT NULL,
    amount         REAL NOT NULL,
    status         TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    is_paid        INTEGER NOT NULL,
    is_failed      INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES dim_account (account_id),
    FOREIGN KEY (plan_id) REFERENCES dim_plan (plan_id)
);

-- Grain: 1 dòng = 1 tài khoản trong 1 tháng
CREATE TABLE IF NOT EXISTS fact_monthly_usage (
    account_id      TEXT NOT NULL,
    month           TEXT NOT NULL,
    active_days     INTEGER NOT NULL,
    seats_active    INTEGER NOT NULL,
    seats_billed    INTEGER NOT NULL,
    features_used   INTEGER NOT NULL,
    api_calls       INTEGER NOT NULL,
    seat_utilization REAL NOT NULL,          -- seats_active / seats_billed
    usage_band      TEXT NOT NULL,           -- dormant/low/steady/power
    PRIMARY KEY (account_id, month),
    FOREIGN KEY (account_id) REFERENCES dim_account (account_id)
);

-- Grain: 1 dòng = 1 ticket hỗ trợ
CREATE TABLE IF NOT EXISTS fact_support_tickets (
    ticket_id          TEXT PRIMARY KEY,
    account_id         TEXT NOT NULL,
    opened_at          TEXT NOT NULL,
    opened_month       TEXT NOT NULL,
    priority           TEXT NOT NULL,
    category           TEXT NOT NULL,
    resolution_hours   REAL NOT NULL,
    satisfaction       INTEGER NOT NULL,
    is_low_satisfaction INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES dim_account (account_id)
);

-- =============================================================================
-- INDEX
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_acc_signup      ON dim_account (signup_month);
CREATE INDEX IF NOT EXISTS idx_acc_channel     ON dim_account (acquisition_channel);
CREATE INDEX IF NOT EXISTS idx_acc_tier        ON dim_account (initial_tier);

CREATE INDEX IF NOT EXISTS idx_evt_account     ON fact_subscription_events (account_id);
CREATE INDEX IF NOT EXISTS idx_evt_month       ON fact_subscription_events (event_month);
CREATE INDEX IF NOT EXISTS idx_evt_type        ON fact_subscription_events (event_type);

CREATE INDEX IF NOT EXISTS idx_inv_account     ON fact_invoices (account_id);
CREATE INDEX IF NOT EXISTS idx_inv_month       ON fact_invoices (invoice_month);
CREATE INDEX IF NOT EXISTS idx_inv_status      ON fact_invoices (status);

CREATE INDEX IF NOT EXISTS idx_use_account     ON fact_monthly_usage (account_id);
CREATE INDEX IF NOT EXISTS idx_use_month       ON fact_monthly_usage (month);

CREATE INDEX IF NOT EXISTS idx_tck_account     ON fact_support_tickets (account_id);
CREATE INDEX IF NOT EXISTS idx_tck_month       ON fact_support_tickets (opened_month);
