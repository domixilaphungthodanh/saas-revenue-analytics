-- =============================================================================
-- MÔ-ĐUN 6 — MỨC SỬ DỤNG VÀ SỨC KHOẺ TÀI KHOẢN
-- Trả lời: dùng ít có phải dấu hiệu sắp rời bỏ? Có cảnh báo sớm được không?
-- =============================================================================

DROP TABLE IF EXISTS mart_usage_vs_churn;
CREATE TABLE mart_usage_vs_churn AS
WITH usage AS (
    SELECT f.account_id,
           f.usage_band,
           f.active_days,
           f.seat_utilization,
           d.year_month_no AS no
    FROM fact_monthly_usage f
    JOIN dim_month d ON d.month = f.month
),
churn AS (
    SELECT e.account_id, d.year_month_no AS churn_no
    FROM fact_subscription_events e
    JOIN dim_month d ON d.month = e.event_month
    WHERE e.is_churn = 1
)
SELECT u.usage_band,
       COUNT(*) AS account_months,
       SUM(CASE WHEN c.churn_no = u.no + 1 THEN 1 ELSE 0 END) AS churn_next_month,
       ROUND(100.0 * SUM(CASE WHEN c.churn_no = u.no + 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate_pct,
       ROUND(AVG(u.active_days), 1) AS avg_active_days,
       ROUND(AVG(u.seat_utilization), 3) AS avg_seat_utilization
FROM usage u
LEFT JOIN churn c ON c.account_id = u.account_id
GROUP BY u.usage_band
ORDER BY churn_rate_pct DESC;

-- -----------------------------------------------------------------------------
-- Bảng rủi ro từng tài khoản — dùng cho đội CS chủ động gọi điện
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_account_risk;
CREATE TABLE mart_account_risk AS
WITH last_usage AS (
    SELECT account_id, month, active_days, seat_utilization, usage_band,
           ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY month DESC) AS rn
    FROM fact_monthly_usage
),
last_month_usage AS (
    SELECT * FROM last_usage WHERE rn = 1
),
last_invoice AS (
    SELECT i.account_id, i.amount, i.plan_id,
           ROW_NUMBER() OVER (PARTITION BY i.account_id ORDER BY i.invoice_month DESC) AS rn
    FROM fact_invoices i
),
tickets AS (
    SELECT account_id,
           COUNT(*) AS tickets,
           ROUND(AVG(satisfaction), 2) AS avg_satisfaction
    FROM fact_support_tickets
    GROUP BY account_id
),
payments AS (
    SELECT account_id, SUM(is_failed) AS failed_invoices
    FROM fact_invoices
    GROUP BY account_id
),
recent_payments AS (
    SELECT account_id, SUM(is_failed) AS recent_failed
    FROM fact_invoices
    WHERE invoice_month >= (SELECT month FROM dim_month ORDER BY month DESC LIMIT 1 OFFSET 2)
    GROUP BY account_id
),
churn AS (
    SELECT account_id, MIN(event_month) AS churn_month
    FROM fact_subscription_events
    WHERE is_churn = 1
    GROUP BY account_id
)
SELECT a.account_id,
       a.account_name,
       p.tier,
       a.company_size,
       a.acquisition_channel,
       a.signup_month,
       ROUND(li.amount, 2) AS mrr_last,
       lu.active_days AS last_active_days,
       lu.seat_utilization AS last_seat_utilization,
       lu.usage_band AS last_usage_band,
       COALESCE(t.tickets, 0) AS total_tickets,
       COALESCE(t.avg_satisfaction, 0) AS avg_satisfaction,
       COALESCE(pay.failed_invoices, 0) AS failed_invoices,
       COALESCE(rp.recent_failed, 0) AS recent_failed_invoices,
       CASE WHEN c.account_id IS NULL THEN 0 ELSE 1 END AS churned,
       CASE
           WHEN c.account_id IS NOT NULL THEN 'churned'
           WHEN lu.usage_band = 'dormant' THEN 'at_risk'
           WHEN lu.usage_band = 'low'
                AND (COALESCE(rp.recent_failed, 0) > 0 OR COALESCE(t.avg_satisfaction, 5) < 3.5) THEN 'at_risk'
           WHEN lu.usage_band = 'low' THEN 'watch'
           WHEN COALESCE(rp.recent_failed, 0) > 0 OR COALESCE(t.avg_satisfaction, 5) < 3.5 THEN 'watch'
           ELSE 'healthy'
       END AS risk_flag
FROM dim_account a
JOIN dim_plan p ON p.plan_id = a.initial_plan_id
LEFT JOIN last_month_usage lu ON lu.account_id = a.account_id
LEFT JOIN last_invoice li ON li.account_id = a.account_id AND li.rn = 1
LEFT JOIN tickets t ON t.account_id = a.account_id
LEFT JOIN payments pay ON pay.account_id = a.account_id
LEFT JOIN recent_payments rp ON rp.account_id = a.account_id
LEFT JOIN churn c ON c.account_id = a.account_id
ORDER BY CASE risk_flag
             WHEN 'churned' THEN 1
             WHEN 'at_risk' THEN 2
             WHEN 'watch' THEN 3
             ELSE 4
         END, mrr_last DESC;

-- -----------------------------------------------------------------------------
-- Tổng hợp theo cờ rủi ro
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_risk_summary;
CREATE TABLE mart_risk_summary AS
WITH total AS (
    SELECT SUM(CASE WHEN churned = 0 THEN mrr_last ELSE 0 END) AS active_mrr
    FROM mart_account_risk
)
SELECT risk_flag,
       COUNT(*) AS accounts,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM mart_account_risk), 2) AS pct_accounts,
       ROUND(SUM(CASE WHEN churned = 0 THEN mrr_last ELSE 0 END), 2) AS active_mrr,
       ROUND(100.0 * SUM(CASE WHEN churned = 0 THEN mrr_last ELSE 0 END)
             / NULLIF((SELECT active_mrr FROM total), 0), 2) AS pct_active_mrr
FROM mart_account_risk
GROUP BY risk_flag
ORDER BY accounts DESC;
