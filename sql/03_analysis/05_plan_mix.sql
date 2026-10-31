-- =============================================================================
-- MÔ-ĐUN 5 — CƠ CẤU GÓI DỊCH VỤ
-- Trả lời: doanh thu đến từ gói nào, và gói nào giữ khách tốt nhất?
-- =============================================================================

DROP TABLE IF EXISTS mart_plan_mix_monthly;
CREATE TABLE mart_plan_mix_monthly AS
SELECT i.invoice_month AS month,
       d.month_label,
       p.tier,
       p.plan_name,
       COUNT(DISTINCT i.account_id) AS accounts,
       ROUND(SUM(i.amount), 2) AS mrr,
       ROUND(AVG(i.amount), 2) AS avg_mrr_per_account,
       ROUND(AVG(i.seats_billed), 1) AS avg_seats,
       ROUND(100.0 * SUM(i.amount)
             / SUM(SUM(i.amount)) OVER (PARTITION BY i.invoice_month), 2) AS pct_of_month_mrr
FROM fact_invoices i
JOIN dim_plan p ON p.plan_id = i.plan_id
JOIN dim_month d ON d.month = i.invoice_month
GROUP BY i.invoice_month, d.month_label, p.tier, p.plan_name
ORDER BY i.invoice_month, p.tier;

-- -----------------------------------------------------------------------------
-- Hiệu quả từng gói: quy mô, tốc độ huỷ, mức mở rộng
-- "Gói hiện tại" = gói trên hoá đơn gần nhất của mỗi tài khoản
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_plan_performance;
CREATE TABLE mart_plan_performance AS
WITH last_invoice AS (
    SELECT i.account_id,
           i.plan_id,
           i.amount,
           ROW_NUMBER() OVER (PARTITION BY i.account_id ORDER BY i.invoice_month DESC) AS rn
    FROM fact_invoices i
),
churned_accounts AS (
    SELECT DISTINCT account_id FROM fact_subscription_events WHERE is_churn = 1
),
-- Gói hiện tại = gói trên hoá đơn cuối cùng của tài khoản.
-- Tài khoản đã huỷ cũng được xếp vào gói mà họ rời đi.
acct AS (
    SELECT li.account_id,
           p.tier,
           li.amount,
           CASE WHEN c.account_id IS NULL THEN 0 ELSE 1 END AS churned
    FROM last_invoice li
    JOIN dim_plan p ON p.plan_id = li.plan_id
    LEFT JOIN churned_accounts c ON c.account_id = li.account_id
    WHERE li.rn = 1
),
movement AS (
    SELECT p.tier,
           SUM(CASE WHEN e.event_type = 'seat_add'    THEN e.mrr_delta ELSE 0 END) AS seat_add_mrr,
           SUM(CASE WHEN e.event_type = 'upgrade'     THEN e.mrr_delta ELSE 0 END) AS upgrade_mrr,
           SUM(CASE WHEN e.event_type = 'seat_remove' THEN e.mrr_delta ELSE 0 END) AS seat_remove_mrr,
           SUM(CASE WHEN e.event_type = 'downgrade'   THEN e.mrr_delta ELSE 0 END) AS downgrade_mrr,
           SUM(CASE WHEN e.is_churn = 1               THEN e.mrr_delta ELSE 0 END) AS churn_mrr
    FROM fact_subscription_events e
    JOIN dim_plan p ON p.plan_id = CASE WHEN e.is_churn = 1 THEN e.from_plan_id
                                        ELSE e.to_plan_id END
    GROUP BY p.tier
)
SELECT a.tier,
       dp.plan_name,
       ROUND(SUM(CASE WHEN a.churned = 0 THEN a.amount ELSE 0 END), 2) AS current_mrr,
       SUM(CASE WHEN a.churned = 0 THEN 1 ELSE 0 END) AS active_accounts,
       ROUND(AVG(CASE WHEN a.churned = 0 THEN a.amount END), 2) AS avg_mrr_per_account,
       SUM(a.churned) AS churned_accounts,
       ROUND(100.0 * SUM(a.churned) / COUNT(*), 2) AS churn_rate_pct,
       ROUND(COALESCE(m.seat_add_mrr, 0) + COALESCE(m.upgrade_mrr, 0), 2) AS expansion_mrr,
       ROUND(COALESCE(m.seat_remove_mrr, 0) + COALESCE(m.downgrade_mrr, 0), 2) AS contraction_mrr,
       ROUND(COALESCE(m.churn_mrr, 0), 2) AS churn_mrr,
       ROUND(COALESCE(m.seat_add_mrr, 0) + COALESCE(m.upgrade_mrr, 0)
             + COALESCE(m.seat_remove_mrr, 0) + COALESCE(m.downgrade_mrr, 0)
             + COALESCE(m.churn_mrr, 0), 2) AS net_expansion_mrr
FROM acct a
JOIN dim_plan dp ON dp.tier = a.tier
LEFT JOIN movement m ON m.tier = a.tier
GROUP BY a.tier, dp.plan_name, m.seat_add_mrr, m.upgrade_mrr,
         m.seat_remove_mrr, m.downgrade_mrr, m.churn_mrr
ORDER BY current_mrr DESC;
