-- =============================================================================
-- MÔ-ĐUN 7 — TÁC ĐỘNG CỦA HỖ TRỢ KHÁCH HÀNG
--
-- LƯU Ý PHƯƠNG PHÁP:
--   Không được đếm "số ticket của tài khoản" rồi so tỷ lệ huỷ. Tài khoản rời
--   sớm có ít thời gian mở ticket, nên nhóm "0 ticket" sẽ trông như huỷ nhiều
--   nhất — đó là thiên lệch sống sót (survival bias), không phải quan hệ nhân quả.
--
--   Cách đúng: tính trên từng ticket, đo xem tài khoản có huỷ trong vòng 3
--   tháng SAU ticket hay không. Mọi ticket đều có cùng cửa sổ quan sát.
-- =============================================================================

DROP TABLE IF EXISTS mart_support_impact;
CREATE TABLE mart_support_impact AS
WITH ticket AS (
    SELECT tk.ticket_id,
           tk.account_id,
           tk.resolution_hours,
           dm.year_month_no AS ticket_no
    FROM fact_support_tickets tk
    JOIN dim_month dm ON dm.month = tk.opened_month
),
churn AS (
    SELECT e.account_id, dm.year_month_no AS churn_no
    FROM fact_subscription_events e
    JOIN dim_month dm ON dm.month = e.event_month
    WHERE e.is_churn = 1
)
SELECT CASE WHEN tk.resolution_hours < 4   THEN '1_duoi_4h'
            WHEN tk.resolution_hours < 24  THEN '2_4_24h'
            WHEN tk.resolution_hours < 72  THEN '3_1_3_ngay'
            ELSE                                '4_tren_3_ngay' END AS resolution_band,
       COUNT(*) AS tickets,
       SUM(CASE WHEN c.churn_no BETWEEN tk.ticket_no AND tk.ticket_no + 3 THEN 1 ELSE 0 END) AS churn_within_3m,
       ROUND(100.0 * SUM(CASE WHEN c.churn_no BETWEEN tk.ticket_no AND tk.ticket_no + 3 THEN 1 ELSE 0 END)
             / COUNT(*), 2) AS churn_rate_pct,
       ROUND(AVG(tk.resolution_hours), 1) AS avg_resolution_hours
FROM ticket tk
LEFT JOIN churn c ON c.account_id = tk.account_id
GROUP BY 1
ORDER BY 1;

-- -----------------------------------------------------------------------------
-- Chất lượng hỗ trợ theo thời gian
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_support_trend;
CREATE TABLE mart_support_trend AS
SELECT t.opened_month AS month,
       d.month_label,
       COUNT(*) AS tickets,
       COUNT(DISTINCT t.account_id) AS accounts_with_ticket,
       ROUND(AVG(t.resolution_hours), 1) AS avg_resolution_hours,
       ROUND(100.0 * SUM(t.is_low_satisfaction) / COUNT(*), 2) AS pct_low_satisfaction,
       ROUND(100.0 * SUM(CASE WHEN t.priority IN ('high', 'urgent') THEN 1 ELSE 0 END)
             / COUNT(*), 2) AS pct_high_priority
FROM fact_support_tickets t
JOIN dim_month d ON d.month = t.opened_month
GROUP BY t.opened_month, d.month_label
ORDER BY t.opened_month;

-- -----------------------------------------------------------------------------
-- Điểm hài lòng của ticket → có huỷ trong 3 tháng sau không?
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_satisfaction_band;
CREATE TABLE mart_satisfaction_band AS
WITH ticket AS (
    SELECT tk.ticket_id,
           tk.account_id,
           tk.satisfaction,
           dm.year_month_no AS ticket_no
    FROM fact_support_tickets tk
    JOIN dim_month dm ON dm.month = tk.opened_month
),
churn AS (
    SELECT e.account_id, dm.year_month_no AS churn_no
    FROM fact_subscription_events e
    JOIN dim_month dm ON dm.month = e.event_month
    WHERE e.is_churn = 1
)
SELECT CASE WHEN satisfaction <= 2 THEN '1_1_2'
            WHEN satisfaction = 3  THEN '2_3'
            WHEN satisfaction = 4  THEN '3_4'
            ELSE                        '4_5' END AS satisfaction_band,
       COUNT(*) AS tickets,
       SUM(CASE WHEN c.churn_no BETWEEN tk.ticket_no AND tk.ticket_no + 3 THEN 1 ELSE 0 END) AS churn_within_3m,
       ROUND(100.0 * SUM(CASE WHEN c.churn_no BETWEEN tk.ticket_no AND tk.ticket_no + 3 THEN 1 ELSE 0 END)
             / COUNT(*), 2) AS churn_rate_pct,
       ROUND(AVG(tk.satisfaction), 2) AS avg_satisfaction
FROM ticket tk
LEFT JOIN churn c ON c.account_id = tk.account_id
GROUP BY 1
ORDER BY 1;
