-- =============================================================================
-- MÔ-ĐUN 2 — COHORT RETENTION
-- Trả lời: khách đăng ký cùng một tháng còn trụ được bao lâu?
-- =============================================================================

DROP TABLE IF EXISTS mart_cohort_retention;
CREATE TABLE mart_cohort_retention AS
WITH base AS (
    SELECT a.account_id,
           a.signup_month AS cohort_month,
           dm.year_month_no AS signup_no
    FROM dim_account a
    JOIN dim_month dm ON dm.month = a.signup_month
),
churn AS (
    SELECT account_id, MIN(event_month) AS churn_month
    FROM fact_subscription_events
    WHERE is_churn = 1
    GROUP BY account_id
)
SELECT b.cohort_month,
       d.year_month_no - b.signup_no AS month_index,
       COUNT(*) AS accounts_start,
       SUM(CASE WHEN c.churn_month IS NULL OR c.churn_month >= d.month THEN 1 ELSE 0 END) AS accounts_retained,
       ROUND(100.0 * SUM(CASE WHEN c.churn_month IS NULL OR c.churn_month >= d.month THEN 1 ELSE 0 END)
             / COUNT(*), 2) AS retention_pct
FROM base b
JOIN dim_month d ON d.year_month_no >= b.signup_no
LEFT JOIN churn c ON c.account_id = b.account_id
GROUP BY b.cohort_month, d.year_month_no - b.signup_no
ORDER BY b.cohort_month, month_index;

-- -----------------------------------------------------------------------------
-- Retention theo doanh thu: cùng một cohort, MRR còn lại bao nhiêu %
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_cohort_revenue;
CREATE TABLE mart_cohort_revenue AS
WITH base AS (
    SELECT a.account_id,
           a.signup_month AS cohort_month,
           dm.year_month_no AS signup_no
    FROM dim_account a
    JOIN dim_month dm ON dm.month = a.signup_month
),
ev AS (
    SELECT e.account_id, dm.year_month_no AS ev_no, e.mrr_delta
    FROM fact_subscription_events e
    JOIN dim_month dm ON dm.month = e.event_month
),
grid AS (
    SELECT b.account_id, b.cohort_month, b.signup_no,
           d.year_month_no - b.signup_no AS month_index,
           d.year_month_no
    FROM base b
    JOIN dim_month d ON d.year_month_no >= b.signup_no
),
agg AS (
    SELECT g.cohort_month,
           g.month_index,
           SUM(CASE WHEN ev.ev_no <= g.year_month_no THEN ev.mrr_delta ELSE 0 END) AS mrr
    FROM grid g
    LEFT JOIN ev ON ev.account_id = g.account_id
    GROUP BY g.cohort_month, g.month_index
),
first AS (
    SELECT cohort_month, mrr AS mrr_0
    FROM agg
    WHERE month_index = 0
)
SELECT a.cohort_month,
       a.month_index,
       ROUND(a.mrr, 2) AS mrr,
       ROUND(f.mrr_0, 2) AS mrr_0,
       ROUND(100.0 * a.mrr / NULLIF(f.mrr_0, 0), 2) AS revenue_retention_pct
FROM agg a
JOIN first f ON f.cohort_month = a.cohort_month
ORDER BY a.cohort_month, a.month_index;
