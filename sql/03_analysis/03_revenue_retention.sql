-- =============================================================================
-- MÔ-ĐUN 3 — NRR VÀ GRR THEO COHORT
-- Trả lời: sau 12 tháng, tập khách cũ còn giữ được bao nhiêu doanh thu?
--   NRR > 100%  -> khách cũ tự sinh thêm doanh thu (mua thêm ghế / nâng gói)
--   GRR < 100%  -> phần doanh thu bị mất do hạ gói và huỷ
-- =============================================================================

DROP TABLE IF EXISTS mart_nrr_by_cohort;
CREATE TABLE mart_nrr_by_cohort AS
WITH base AS (
    SELECT a.account_id,
           a.signup_month AS cohort_month,
           dm.year_month_no AS signup_no
    FROM dim_account a
    JOIN dim_month dm ON dm.month = a.signup_month
),
ev AS (
    SELECT e.account_id, dm.year_month_no AS ev_no, e.mrr_delta, e.is_expansion
    FROM fact_subscription_events e
    JOIN dim_month dm ON dm.month = e.event_month
),
last_no AS (
    SELECT MAX(year_month_no) AS max_no FROM dim_month
)
SELECT b.cohort_month,
       COUNT(DISTINCT b.account_id) AS accounts,
       ROUND(SUM(CASE WHEN ev.ev_no = b.signup_no THEN ev.mrr_delta ELSE 0 END), 2) AS mrr_0,
       ROUND(SUM(CASE WHEN ev.ev_no <= b.signup_no + 12 THEN ev.mrr_delta ELSE 0 END), 2) AS mrr_12m,
       ROUND(SUM(CASE WHEN ev.ev_no <= b.signup_no + 12 AND ev.is_expansion = 0
                      THEN ev.mrr_delta ELSE 0 END), 2) AS mrr_12m_no_expansion,
       ROUND(100.0 * SUM(CASE WHEN ev.ev_no <= b.signup_no + 12 THEN ev.mrr_delta ELSE 0 END)
             / NULLIF(SUM(CASE WHEN ev.ev_no = b.signup_no THEN ev.mrr_delta ELSE 0 END), 0), 2) AS nrr_12m_pct,
       ROUND(100.0 * SUM(CASE WHEN ev.ev_no <= b.signup_no + 12 AND ev.is_expansion = 0
                              THEN ev.mrr_delta ELSE 0 END)
             / NULLIF(SUM(CASE WHEN ev.ev_no = b.signup_no THEN ev.mrr_delta ELSE 0 END), 0), 2) AS grr_12m_pct,
       CASE WHEN b.signup_no + 12 <= (SELECT max_no FROM last_no) THEN 1 ELSE 0 END AS is_mature
FROM base b
LEFT JOIN ev ON ev.account_id = b.account_id
GROUP BY b.cohort_month, b.signup_no
ORDER BY b.cohort_month;

-- -----------------------------------------------------------------------------
-- Tổng hợp toàn bộ cohort đã đủ 12 tháng
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_retention_summary;
CREATE TABLE mart_retention_summary AS
WITH monthly AS (
    SELECT AVG(nrr_pct) AS avg_nrr_monthly,
           AVG(grr_pct) AS avg_grr_monthly
    FROM mart_mrr_monthly
    WHERE month >= '2024-01-01'
),
cohort AS (
    SELECT SUM(mrr_0) AS mrr_0,
           SUM(mrr_12m) AS mrr_12m,
           SUM(mrr_12m_no_expansion) AS mrr_12m_no_expansion,
           COUNT(*) AS cohorts
    FROM mart_nrr_by_cohort
    WHERE is_mature = 1
)
SELECT monthly.avg_nrr_monthly,
       monthly.avg_grr_monthly,
       ROUND(POWER(monthly.avg_nrr_monthly / 100.0, 12) * 100, 2) AS nrr_annualized_pct,
       ROUND(POWER(monthly.avg_grr_monthly / 100.0, 12) * 100, 2) AS grr_annualized_pct,
       cohort.cohorts,
       ROUND(100.0 * cohort.mrr_12m / NULLIF(cohort.mrr_0, 0), 2) AS nrr_cohort_12m_pct,
       ROUND(100.0 * cohort.mrr_12m_no_expansion / NULLIF(cohort.mrr_0, 0), 2) AS grr_cohort_12m_pct
FROM monthly, cohort;
