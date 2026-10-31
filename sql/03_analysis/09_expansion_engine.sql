-- =============================================================================
-- MÔ-ĐUN 9 — ĐỘNG CƠ MỞ RỘNG
-- Trả lời: mua thêm ghế và nâng gói đóng góp bao nhiêu, tập trung ở đâu?
-- =============================================================================

DROP TABLE IF EXISTS mart_expansion_by_tier;
CREATE TABLE mart_expansion_by_tier AS
WITH movement AS (
    SELECT p.tier,
           SUM(CASE WHEN e.event_type = 'seat_add'     THEN e.mrr_delta ELSE 0 END) AS seat_add_mrr,
           SUM(CASE WHEN e.event_type = 'upgrade'      THEN e.mrr_delta ELSE 0 END) AS upgrade_mrr,
           SUM(CASE WHEN e.event_type = 'seat_remove'  THEN e.mrr_delta ELSE 0 END) AS seat_remove_mrr,
           SUM(CASE WHEN e.event_type = 'downgrade'    THEN e.mrr_delta ELSE 0 END) AS downgrade_mrr,
           SUM(CASE WHEN e.is_churn = 1                THEN e.mrr_delta ELSE 0 END) AS churn_mrr,
           SUM(CASE WHEN e.event_type = 'seat_add'     THEN 1 ELSE 0 END) AS seat_add_events,
           SUM(CASE WHEN e.event_type = 'upgrade'      THEN 1 ELSE 0 END) AS upgrade_events
    FROM fact_subscription_events e
    JOIN dim_account a ON a.account_id = e.account_id
    JOIN dim_plan p ON p.plan_id = a.initial_plan_id
    GROUP BY p.tier
),
sizes AS (
    SELECT p.tier, COUNT(*) AS accounts
    FROM dim_account a
    JOIN dim_plan p ON p.plan_id = a.initial_plan_id
    GROUP BY p.tier
)
SELECT m.tier,
       s.accounts,
       ROUND(m.seat_add_mrr, 2) AS seat_add_mrr,
       ROUND(m.upgrade_mrr, 2) AS upgrade_mrr,
       ROUND(m.seat_remove_mrr, 2) AS seat_remove_mrr,
       ROUND(m.downgrade_mrr, 2) AS downgrade_mrr,
       ROUND(m.churn_mrr, 2) AS churn_mrr,
       ROUND(m.seat_add_mrr + m.upgrade_mrr + m.seat_remove_mrr
             + m.downgrade_mrr + m.churn_mrr, 2) AS net_mrr_impact,
       m.seat_add_events,
       m.upgrade_events,
       ROUND(100.0 * (m.seat_add_events + m.upgrade_events) / NULLIF(s.accounts, 0), 2) AS expansion_events_per_100_accounts
FROM movement m
JOIN sizes s ON s.tier = m.tier
ORDER BY net_mrr_impact DESC;

-- -----------------------------------------------------------------------------
-- Quy mô ghế theo thời gian: khách đang dùng nhiều hay ít ghế hơn?
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_seat_growth;
CREATE TABLE mart_seat_growth AS
WITH monthly AS (
    SELECT i.invoice_month AS month,
           d.month_label,
           SUM(i.seats_billed) AS seats_billed,
           COUNT(DISTINCT i.account_id) AS accounts,
           ROUND(AVG(i.seats_billed), 1) AS avg_seats_per_account
    FROM fact_invoices i
    JOIN dim_month d ON d.month = i.invoice_month
    GROUP BY i.invoice_month, d.month_label
)
SELECT month,
       month_label,
       seats_billed,
       accounts,
       avg_seats_per_account,
       ROUND(100.0 * (seats_billed - LAG(seats_billed) OVER (ORDER BY month))
             / NULLIF(LAG(seats_billed) OVER (ORDER BY month), 0), 2) AS seat_growth_pct
FROM monthly
ORDER BY month;

-- -----------------------------------------------------------------------------
-- Tương quan giữa mức lấp ghế và hành vi mở rộng
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_seat_utilization_bands;
CREATE TABLE mart_seat_utilization_bands AS
WITH banded AS (
    SELECT f.account_id,
           f.month,
           CASE WHEN f.seat_utilization < 0.40 THEN '1_duoi_40'
                WHEN f.seat_utilization < 0.60 THEN '2_40_60'
                WHEN f.seat_utilization < 0.75 THEN '3_60_75'
                WHEN f.seat_utilization < 0.90 THEN '4_75_90'
                ELSE                               '5_tu_90' END AS utilization_band,
           d.year_month_no AS no
    FROM fact_monthly_usage f
    JOIN dim_month d ON d.month = f.month
),
expansion_next AS (
    SELECT e.account_id, d.year_month_no AS no
    FROM fact_subscription_events e
    JOIN dim_month d ON d.month = e.event_month
    WHERE e.is_expansion = 1
),
churn_next AS (
    SELECT e.account_id, d.year_month_no AS no
    FROM fact_subscription_events e
    JOIN dim_month d ON d.month = e.event_month
    WHERE e.is_churn = 1
)
SELECT b.utilization_band,
       COUNT(*) AS account_months,
       SUM(CASE WHEN x.account_id IS NOT NULL THEN 1 ELSE 0 END) AS expansion_next_month,
       ROUND(100.0 * SUM(CASE WHEN x.account_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS expansion_rate_pct,
       SUM(CASE WHEN c.account_id IS NOT NULL THEN 1 ELSE 0 END) AS churn_next_month,
       ROUND(100.0 * SUM(CASE WHEN c.account_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate_pct
FROM banded b
LEFT JOIN expansion_next x ON x.account_id = b.account_id AND x.no = b.no + 1
LEFT JOIN churn_next c ON c.account_id = b.account_id AND c.no = b.no + 1
GROUP BY b.utilization_band
ORDER BY b.utilization_band;
