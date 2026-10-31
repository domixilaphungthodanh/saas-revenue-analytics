-- =============================================================================
-- MÔ-ĐUN 4 — CHURN THEO PHÂN KHÚC
-- Trả lời: ai rời bỏ, rời vì lý do gì, và rời ở tháng thứ mấy?
-- =============================================================================

DROP TABLE IF EXISTS mart_churn_by_segment;
CREATE TABLE mart_churn_by_segment AS
WITH base AS (
    SELECT a.account_id,
           a.initial_tier,
           a.industry,
           a.acquisition_channel,
           a.company_size,
           a.country,
           dm.year_month_no AS signup_no,
           (SELECT MIN(d2.year_month_no)
              FROM fact_subscription_events e
              JOIN dim_month d2 ON d2.month = e.event_month
             WHERE e.account_id = a.account_id AND e.is_churn = 1) AS churn_no,
           (SELECT SUM(e.mrr_delta)
              FROM fact_subscription_events e
             WHERE e.account_id = a.account_id
               AND e.event_month = a.signup_month) AS mrr_0
    FROM dim_account a
    JOIN dim_month dm ON dm.month = a.signup_month
),
flagged AS (
    SELECT *,
           CASE WHEN churn_no IS NULL THEN 0 ELSE 1 END AS churned,
           CASE WHEN churn_no IS NULL THEN NULL ELSE churn_no - signup_no END AS tenure_at_churn
    FROM base
)
-- Cột * ở trên bị trùng tên nên phải liệt kê lại tường minh
SELECT dimension,
       segment,
       COUNT(*) AS accounts,
       SUM(churned) AS churned_accounts,
       ROUND(100.0 * SUM(churned) / COUNT(*), 2) AS churn_rate_pct,
       ROUND(AVG(mrr_0), 2) AS avg_starting_mrr,
       ROUND(AVG(tenure_at_churn), 1) AS avg_tenure_at_churn_months
FROM (
    SELECT 'plan'   AS dimension, initial_tier      AS segment, account_id, churned, mrr_0, tenure_at_churn FROM flagged
    UNION ALL
    SELECT 'channel',      acquisition_channel, account_id, churned, mrr_0, tenure_at_churn FROM flagged
    UNION ALL
    SELECT 'industry',     industry,            account_id, churned, mrr_0, tenure_at_churn FROM flagged
    UNION ALL
    SELECT 'company_size', company_size,        account_id, churned, mrr_0, tenure_at_churn FROM flagged
    UNION ALL
    SELECT 'country',      country,             account_id, churned, mrr_0, tenure_at_churn FROM flagged
)
GROUP BY dimension, segment
ORDER BY dimension, churn_rate_pct DESC;

-- -----------------------------------------------------------------------------
-- Xác suất huỷ theo thâm niên: có "vực thẳm onboarding" không?
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_churn_by_tenure;
CREATE TABLE mart_churn_by_tenure AS
WITH base AS (
    SELECT a.account_id,
           dm.year_month_no AS signup_no,
           (SELECT MIN(e.event_month)
              FROM fact_subscription_events e
             WHERE e.account_id = a.account_id AND e.is_churn = 1) AS churn_month
    FROM dim_account a
    JOIN dim_month dm ON dm.month = a.signup_month
),
grid AS (
    SELECT b.account_id,
           d.year_month_no - b.signup_no AS tenure_month,
           CASE WHEN b.churn_month = d.month THEN 1 ELSE 0 END AS churned
    FROM base b
    JOIN dim_month d ON d.year_month_no >= b.signup_no
)
SELECT CASE WHEN tenure_month <= 2  THEN '1_0_2m'
            WHEN tenure_month <= 5  THEN '2_3_5m'
            WHEN tenure_month <= 11 THEN '3_6_11m'
            WHEN tenure_month <= 23 THEN '4_12_23m'
            ELSE                         '5_24m_plus' END AS tenure_band,
       COUNT(*) AS account_months,
       SUM(churned) AS churned_accounts,
       ROUND(100.0 * SUM(churned) / COUNT(*), 2) AS monthly_churn_pct
FROM grid
GROUP BY 1
ORDER BY 1;

-- -----------------------------------------------------------------------------
-- Lý do huỷ
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_churn_reasons;
CREATE TABLE mart_churn_reasons AS
WITH total AS (
    SELECT COUNT(*) AS n FROM fact_subscription_events WHERE is_churn = 1
)
SELECT e.reason,
       COUNT(*) AS churned_accounts,
       ROUND(100.0 * COUNT(*) / (SELECT n FROM total), 2) AS pct_of_churn,
       ROUND(SUM(-e.mrr_delta), 2) AS mrr_lost,
       ROUND(AVG(-e.mrr_delta), 2) AS avg_mrr_lost
FROM fact_subscription_events e
WHERE e.is_churn = 1
GROUP BY e.reason
ORDER BY churned_accounts DESC;
