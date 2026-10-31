-- =============================================================================
-- MÔ-ĐUN 8 — SỨC KHOẺ THANH TOÁN
-- Trả lời: bao nhiêu doanh thu bị mất vì thẻ hỏng, và có cứu được không?
-- =============================================================================

DROP TABLE IF EXISTS mart_payment_health;
CREATE TABLE mart_payment_health AS
WITH total AS (
    SELECT COUNT(*) AS n, SUM(amount) AS amt FROM fact_invoices
)
SELECT i.payment_method,
       COUNT(*) AS invoices,
       ROUND(100.0 * COUNT(*) / (SELECT n FROM total), 2) AS pct_invoices,
       SUM(i.is_failed) AS failed_invoices,
       ROUND(100.0 * SUM(i.is_failed) / COUNT(*), 2) AS failed_rate_pct,
       ROUND(SUM(i.amount), 2) AS billed_amount,
       ROUND(SUM(CASE WHEN i.is_failed = 1 THEN i.amount ELSE 0 END), 2) AS failed_amount,
       ROUND(100.0 * SUM(CASE WHEN i.is_failed = 1 THEN i.amount ELSE 0 END)
             / NULLIF(SUM(i.amount), 0), 2) AS pct_amount_at_risk
FROM fact_invoices i
GROUP BY i.payment_method
ORDER BY billed_amount DESC;

-- -----------------------------------------------------------------------------
-- Thu hồi sau thất bại: thử lại có cứu được khách không?
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_dunning;
CREATE TABLE mart_dunning AS
WITH failed AS (
    SELECT COUNT(*) AS failed_invoices,
           COUNT(DISTINCT account_id) AS accounts_affected,
           SUM(amount) AS amount_failed
    FROM fact_invoices
    WHERE is_failed = 1
),
involuntary AS (
    SELECT COUNT(*) AS involuntary_churn,
           SUM(-mrr_delta) AS mrr_lost
    FROM fact_subscription_events
    WHERE is_churn = 1 AND reason = 'payment_failed'
),
all_churn AS (
    SELECT COUNT(*) AS total_churn FROM fact_subscription_events WHERE is_churn = 1
)
SELECT f.failed_invoices,
       f.accounts_affected,
       ROUND(f.amount_failed, 2) AS amount_failed,
       i.involuntary_churn,
       ROUND(100.0 * i.involuntary_churn / NULLIF(a.total_churn, 0), 2) AS pct_of_all_churn,
       ROUND(i.mrr_lost, 2) AS mrr_lost_involuntary,
       ROUND(100.0 * (f.accounts_affected - i.involuntary_churn)
             / NULLIF(f.accounts_affected, 0), 2) AS recovery_rate_pct
FROM failed f, involuntary i, all_churn a;

-- -----------------------------------------------------------------------------
-- Diễn biến hoá đơn thất bại theo tháng
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_billing_trend;
CREATE TABLE mart_billing_trend AS
SELECT i.invoice_month AS month,
       d.month_label,
       COUNT(*) AS invoices,
       SUM(i.is_failed) AS failed_invoices,
       ROUND(100.0 * SUM(i.is_failed) / COUNT(*), 2) AS failed_rate_pct,
       ROUND(SUM(i.amount), 2) AS billed_mrr,
       ROUND(SUM(CASE WHEN i.is_failed = 1 THEN i.amount ELSE 0 END), 2) AS at_risk_mrr
FROM fact_invoices i
JOIN dim_month d ON d.month = i.invoice_month
GROUP BY i.invoice_month, d.month_label
ORDER BY i.invoice_month;
