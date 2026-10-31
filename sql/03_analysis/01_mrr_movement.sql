-- =============================================================================
-- MÔ-ĐUN 1 — CẦU NỐI MRR (MRR BRIDGE)
-- Trả lời: doanh thu định kỳ tăng/giảm vì đâu, trong từng tháng?
-- =============================================================================

DROP TABLE IF EXISTS mart_mrr_monthly;
CREATE TABLE mart_mrr_monthly AS
WITH movement AS (
    SELECT event_month AS month,
           SUM(CASE WHEN event_type = 'new'          THEN mrr_delta ELSE 0 END) AS new_mrr,
           SUM(CASE WHEN is_expansion = 1            THEN mrr_delta ELSE 0 END) AS expansion_mrr,
           SUM(CASE WHEN is_contraction = 1          THEN mrr_delta ELSE 0 END) AS contraction_mrr,
           SUM(CASE WHEN is_churn = 1                THEN mrr_delta ELSE 0 END) AS churn_mrr,
           SUM(CASE WHEN event_type = 'new'          THEN 1 ELSE 0 END)         AS new_accounts,
           SUM(is_churn)                                                        AS churned_accounts
    FROM fact_subscription_events
    GROUP BY event_month
),
opening AS (
    SELECT m.month,
           COALESCE(SUM(e.mrr_delta), 0) AS mrr_start
    FROM dim_month m
    LEFT JOIN fact_subscription_events e ON e.event_month < m.month
    GROUP BY m.month
)
SELECT o.month,
       d.month_label,
       d.year,
       d.quarter,
       ROUND(o.mrr_start, 2)                                        AS mrr_start,
       ROUND(COALESCE(v.new_mrr, 0), 2)                             AS new_mrr,
       ROUND(COALESCE(v.expansion_mrr, 0), 2)                       AS expansion_mrr,
       ROUND(COALESCE(v.contraction_mrr, 0), 2)                     AS contraction_mrr,
       ROUND(COALESCE(v.churn_mrr, 0), 2)                           AS churn_mrr,
       ROUND(o.mrr_start + COALESCE(v.new_mrr, 0) + COALESCE(v.expansion_mrr, 0)
             + COALESCE(v.contraction_mrr, 0) + COALESCE(v.churn_mrr, 0), 2) AS mrr_end,
       ROUND(COALESCE(v.new_mrr, 0) + COALESCE(v.expansion_mrr, 0)
             + COALESCE(v.contraction_mrr, 0) + COALESCE(v.churn_mrr, 0), 2) AS net_new_mrr,
       COALESCE(v.new_accounts, 0)                                  AS new_accounts,
       COALESCE(v.churned_accounts, 0)                              AS churned_accounts,
       ROUND(100.0 * (o.mrr_start + COALESCE(v.expansion_mrr, 0) + COALESCE(v.contraction_mrr, 0)
             + COALESCE(v.churn_mrr, 0)) / NULLIF(o.mrr_start, 0), 2) AS nrr_pct,
       ROUND(100.0 * (o.mrr_start + COALESCE(v.contraction_mrr, 0) + COALESCE(v.churn_mrr, 0))
             / NULLIF(o.mrr_start, 0), 2)                            AS grr_pct,
       ROUND(100.0 * (COALESCE(v.new_mrr, 0) + COALESCE(v.expansion_mrr, 0)
             + COALESCE(v.contraction_mrr, 0) + COALESCE(v.churn_mrr, 0))
             / NULLIF(o.mrr_start, 0), 2)                            AS growth_pct
FROM opening o
JOIN dim_month d ON d.month = o.month
LEFT JOIN movement v ON v.month = o.month
ORDER BY o.month;

-- -----------------------------------------------------------------------------
-- Cơ cấu đóng góp của từng thành phần trên toàn kỳ
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS mart_growth_decomposition;
CREATE TABLE mart_growth_decomposition AS
WITH t AS (
    SELECT SUM(new_mrr)          AS new_mrr,
           SUM(expansion_mrr)    AS expansion_mrr,
           SUM(contraction_mrr)  AS contraction_mrr,
           SUM(churn_mrr)        AS churn_mrr
    FROM mart_mrr_monthly
),
gross AS (
    SELECT new_mrr + expansion_mrr + ABS(contraction_mrr) + ABS(churn_mrr) AS total
    FROM t
)
SELECT 'new'            AS component, ROUND(t.new_mrr, 2)         AS mrr,
       ROUND(100.0 * t.new_mrr / g.total, 2)                       AS pct_of_gross,
       'increase'       AS direction
FROM t, gross g
UNION ALL
SELECT 'expansion',     ROUND(t.expansion_mrr, 2),
       ROUND(100.0 * t.expansion_mrr / g.total, 2), 'increase'
FROM t, gross g
UNION ALL
SELECT 'contraction',   ROUND(t.contraction_mrr, 2),
       ROUND(100.0 * ABS(t.contraction_mrr) / g.total, 2), 'decrease'
FROM t, gross g
UNION ALL
SELECT 'churn',         ROUND(t.churn_mrr, 2),
       ROUND(100.0 * ABS(t.churn_mrr) / g.total, 2), 'decrease'
FROM t, gross g;
