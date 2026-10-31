# Từ điển dữ liệu

Tất cả tên bảng và tên cột bằng tiếng Anh. Mô tả bằng tiếng Việt.

Kiến trúc ba tầng:

```
data/raw/*.csv  →  stg_*  (staging, toàn bộ TEXT)  →  dim_* / fact_*  →  mart_*
```

---

## Tầng 1 — Nguồn (6 file CSV)

Sinh ra bởi `src/etl/generate_data.py`. Mỗi file mô phỏng một export từ hệ thống billing.

### `plans.csv`

Danh mục gói dịch vụ. Bảng tham chiếu, 4 dòng, không đổi theo thời gian.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `plan_id` | TEXT | Khoá chính. `PLAN-STARTER` … `PLAN-ENTERPRISE` |
| `plan_name` | TEXT | Tên hiển thị |
| `tier` | TEXT | `starter` / `growth` / `business` / `enterprise` |
| `base_price` | REAL | Giá cơ bản/tháng (USD), đã gồm `included_seats` ghế |
| `included_seats` | INTEGER | Số ghế nằm trong giá cơ bản |
| `price_per_seat` | REAL | Giá mỗi ghế vượt mức (USD/tháng) |

Giá tháng = `base_price + max(0, seats − included_seats) × price_per_seat`

| Gói | Giá cơ bản | Ghế kèm | Giá/ghế thêm |
|---|---:|---:|---:|
| Starter | $49 | 3 | $12 |
| Growth | $149 | 10 | $15 |
| Business | $399 | 25 | $18 |
| Enterprise | $1.200 | 50 | $22 |

### `accounts.csv`

1.397 tài khoản khách hàng doanh nghiệp.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `account_id` | TEXT | Khoá chính. `ACC-00001` … |
| `account_name` | TEXT | Tên công ty (sinh ngẫu nhiên) |
| `industry` | TEXT | `technology`, `retail`, `finance`, `healthcare`, `manufacturing`, `education`, `other` |
| `country` | TEXT | Mã quốc gia 2 ký tự. `US` chiếm 45% |
| `employees` | INTEGER | Số nhân viên (phân phối lognormal, 5–20.000) |
| `acquisition_channel` | TEXT | `organic`, `paid_search`, `outbound`, `partner`, `referral` |
| `signup_date` | TEXT | `YYYY-MM-DD`, luôn là ngày 1 của tháng |
| `initial_plan_id` | TEXT | Gói lúc đăng ký. Tham chiếu `plans.plan_id` |

### `subscription_events.csv`

**Bảng quan trọng nhất.** 2.255 dòng — chuỗi sự kiện vòng đời. Đây là nguồn sự thật duy nhất cho MRR.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `event_id` | TEXT | Khoá chính. `EVT-000001` … |
| `account_id` | TEXT | Tham chiếu `accounts.account_id` |
| `event_date` | TEXT | `YYYY-MM-DD`, ngày 1 của tháng xảy ra sự kiện |
| `event_type` | TEXT | `new` / `upgrade` / `downgrade` / `seat_add` / `seat_remove` / `churn` |
| `from_plan_id` | TEXT | Gói trước. Rỗng với sự kiện `new` |
| `to_plan_id` | TEXT | Gói sau. Rỗng với sự kiện `churn` |
| `seats_delta` | INTEGER | Thay đổi số ghế. Âm khi cắt ghế hoặc huỷ |
| `mrr_delta` | REAL | Thay đổi MRR (USD). Âm khi giảm |
| `reason` | TEXT | Lý do huỷ. Chỉ có giá trị với `churn` |

Quy ước quan trọng:

- Mỗi tài khoản có **đúng một** sự kiện `new`, tại tháng đăng ký.
- Mỗi tài khoản có **tối đa một** sự kiện `churn`.
- MRR tại một thời điểm = tổng `mrr_delta` của mọi sự kiện có `event_date` ≤ thời điểm đó.
- `churn` được ghi ở **tháng cuối còn hoạt động** — khách vẫn dùng và vẫn trả tiền trong tháng đó.

Giá trị `reason`: `too_expensive`, `missing_features`, `switched_competitor`, `no_longer_needed`, `poor_support`, `budget_cut`, `product_quality`, `payment_failed`.

### `invoices.csv`

15.897 hoá đơn — một dòng mỗi tài khoản mỗi tháng còn hoạt động.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `invoice_id` | TEXT | Khoá chính. `INV-000001` … |
| `account_id` | TEXT | Tham chiếu `accounts.account_id` |
| `invoice_date` | TEXT | Ngày phát hành = ngày 1 của kỳ |
| `period_start` | TEXT | Đầu kỳ dịch vụ |
| `period_end` | TEXT | Cuối kỳ dịch vụ |
| `plan_id` | TEXT | Gói áp dụng trong kỳ |
| `seats_billed` | INTEGER | Số ghế tính tiền |
| `amount` | REAL | Số tiền (USD) |
| `status` | TEXT | `paid` / `failed` |
| `payment_method` | TEXT | `credit_card` / `bank_transfer` / `paypal` |

Hoá đơn `failed` **không** làm giảm MRR hợp đồng — khách vẫn là khách cho tới khi bị huỷ. Đây là lý do tách `fact_invoices` khỏi `fact_subscription_events`.

### `monthly_usage.csv`

15.897 dòng — một dòng mỗi tài khoản mỗi tháng còn hoạt động (grain trùng với hoá đơn).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `account_id` | TEXT | Tham chiếu `accounts.account_id` |
| `month` | TEXT | `YYYY-MM-01` |
| `active_days` | INTEGER | Số ngày có hoạt động trong tháng (0–30) |
| `seats_active` | INTEGER | Số ghế thực sự được dùng |
| `features_used` | INTEGER | Số tính năng đã dùng (1–12) |
| `api_calls` | INTEGER | Số lệnh gọi API |

### `support_tickets.csv`

8.476 ticket hỗ trợ.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `ticket_id` | TEXT | Khoá chính. `TCK-000001` … |
| `account_id` | TEXT | Tham chiếu `accounts.account_id` |
| `opened_at` | TEXT | Ngày mở ticket |
| `priority` | TEXT | `low` / `medium` / `high` / `urgent` |
| `category` | TEXT | `billing` / `bug` / `how_to` / `integration` / `feature_request` |
| `resolution_hours` | REAL | Thời gian xử lý (giờ) |
| `satisfaction` | INTEGER | Điểm hài lòng 1–5 |

---

## Tầng 2a — Dimensions

### `dim_plan`

Sao chép `plans.csv` + một cột sắp xếp.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `plan_id` | TEXT | PK |
| `plan_name` | TEXT | |
| `tier` | TEXT | |
| `base_price` | REAL | |
| `included_seats` | INTEGER | |
| `price_per_seat` | REAL | |
| `tier_order` | INTEGER | 1 = Starter … 4 = Enterprise. Dùng để sắp xếp |

### `dim_account`

1.397 dòng, thêm các thuộc tính dẫn xuất.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `account_id` | TEXT | PK |
| `account_name` | TEXT | |
| `industry` | TEXT | |
| `country` | TEXT | |
| `employees` | INTEGER | |
| `employee_band` | TEXT | `1_1_49`, `2_50_199`, `3_200_499`, `4_500_1999`, `5_2000_plus` |
| `company_size` | TEXT | `smb` (<100), `mid_market` (100–999), `enterprise` (1000+) |
| `acquisition_channel` | TEXT | |
| `signup_date` | TEXT | |
| `signup_month` | TEXT | `YYYY-MM-01` |
| `initial_plan_id` | TEXT | FK → `dim_plan` |
| `initial_tier` | TEXT | Tiện cho GROUP BY, tránh phải join |

### `dim_month`

Bảng lịch, 36 dòng (01/2023 – 12/2025).

| Cột | Kiểu | Mô tả |
|---|---|---|
| `month` | TEXT | PK, `YYYY-MM-01` |
| `year` | INTEGER | |
| `quarter` | INTEGER | |
| `month_num` | INTEGER | 1–12 |
| `month_label` | TEXT | `YYYY-MM` để hiển thị |
| `year_month_no` | INTEGER | Số thứ tự tháng, 1–36. **Dùng để tính thâm niên** |

`year_month_no` là mẹo quan trọng: thâm niên = `tháng hiện tại − tháng đăng ký`, không cần xử lý ngày tháng.

---

## Tầng 2b — Facts

### `fact_subscription_events`

Grain: **1 dòng = 1 sự kiện vòng đời**. 2.255 dòng.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `event_id` | TEXT | PK |
| `account_id` | TEXT | FK → `dim_account` |
| `event_date` | TEXT | |
| `event_month` | TEXT | `YYYY-MM-01` |
| `event_type` | TEXT | |
| `from_plan_id` | TEXT | NULL nếu `new` |
| `to_plan_id` | TEXT | NULL nếu `churn` |
| `seats_delta` | INTEGER | |
| `mrr_delta` | REAL | |
| `reason` | TEXT | NULL nếu không phải `churn` |
| `mrr_increase` | REAL | `max(mrr_delta, 0)` |
| `mrr_decrease` | REAL | `min(mrr_delta, 0)` |
| `is_expansion` | INTEGER | 1 nếu `upgrade` hoặc `seat_add` |
| `is_contraction` | INTEGER | 1 nếu `downgrade` hoặc `seat_remove` |
| `is_churn` | INTEGER | 1 nếu `churn` |

Các cờ được tính sẵn để SQL phân tích không phải lặp lại điều kiện ở mọi nơi.

### `fact_invoices`

Grain: **1 dòng = 1 hoá đơn**. 15.897 dòng.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `invoice_id` | TEXT | PK |
| `account_id` | TEXT | FK → `dim_account` |
| `invoice_date` | TEXT | |
| `invoice_month` | TEXT | `YYYY-MM-01` |
| `period_start` | TEXT | |
| `period_end` | TEXT | |
| `plan_id` | TEXT | FK → `dim_plan` |
| `seats_billed` | INTEGER | |
| `amount` | REAL | |
| `status` | TEXT | `paid` / `failed` |
| `payment_method` | TEXT | |
| `is_paid` | INTEGER | |
| `is_failed` | INTEGER | |

### `fact_monthly_usage`

Grain: **1 dòng = 1 tài khoản trong 1 tháng**. 15.897 dòng.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `account_id` | TEXT | PK phần 1, FK → `dim_account` |
| `month` | TEXT | PK phần 2 |
| `active_days` | INTEGER | |
| `seats_active` | INTEGER | |
| `seats_billed` | INTEGER | **Join từ `fact_invoices`** — cần để tính tỷ lệ lấp ghế |
| `features_used` | INTEGER | |
| `api_calls` | INTEGER | |
| `seat_utilization` | REAL | `seats_active / seats_billed`, 0–1 |
| `usage_band` | TEXT | `dormant` (<5 ngày), `low` (5–14), `steady` (15–24), `power` (25+) |

`seats_billed` không có trong file nguồn — `transform.py` phải join theo `(account_id, month)`. Nếu thiếu, tỷ lệ lấp ghế không tính được.

### `fact_support_tickets`

Grain: **1 dòng = 1 ticket**. 8.476 dòng.

| Cột | Kiểu | Mô tả |
|---|---|---|
| `ticket_id` | TEXT | PK |
| `account_id` | TEXT | FK → `dim_account` |
| `opened_at` | TEXT | |
| `opened_month` | TEXT | `YYYY-MM-01` |
| `priority` | TEXT | |
| `category` | TEXT | |
| `resolution_hours` | REAL | |
| `satisfaction` | INTEGER | 1–5 |
| `is_low_satisfaction` | INTEGER | 1 nếu ≤ 3 |

---

## Tầng 3 — Mart (kết quả phân tích)

23 bảng, xem danh mục đầy đủ ở cuối `docs/findings.md`. Vài bảng quan trọng nhất:

| Bảng | Grain | Dùng cho |
|---|---|---|
| `mart_mrr_monthly` | tháng | Cầu nối MRR: mở đầu, mới, mở rộng, thu hẹp, huỷ, cuối kỳ, NRR, GRR |
| `mart_cohort_retention` | cohort × tháng thứ n | Ma trận giữ chân khách |
| `mart_nrr_by_cohort` | cohort | NRR/GRR sau 12 tháng, kèm cờ `is_mature` |
| `mart_churn_by_segment` | chiều × phân khúc | Churn theo gói/kênh/ngành/quốc gia/quy mô |
| `mart_plan_performance` | gói | MRR, churn, mở rộng, ròng theo gói hiện tại |
| `mart_account_risk` | tài khoản | **Bảng rủi ro vận hành**: cờ `churned` / `at_risk` / `watch` / `healthy` |

### Cờ rủi ro trong `mart_account_risk`

| Giá trị | Điều kiện |
|---|---|
| `churned` | Đã có sự kiện huỷ |
| `at_risk` | Không dùng (<5 ngày/tháng), **hoặc** dùng ít + có hoá đơn thất bại 3 tháng gần nhất + điểm hài lòng < 3,5 |
| `watch` | Dùng ít, **hoặc** có hoá đơn thất bại gần đây, **hoặc** điểm hài lòng < 3,5 |
| `healthy` | Còn lại |

---

## Từ điển nhanh các chỉ số

| Chỉ số | Công thức |
|---|---|
| **MRR** | `SUM(mrr_delta)` của mọi sự kiện tính đến thời điểm đo |
| **ARR** | `MRR × 12` |
| **NRR** | `(MRR đầu kỳ + mở rộng + thu hẹp + huỷ) / MRR đầu kỳ` |
| **GRR** | `(MRR đầu kỳ + thu hẹp + huỷ) / MRR đầu kỳ` — loại bỏ mở rộng |
| **Logo churn** | Số tài khoản huỷ / số tài khoản đầu kỳ |
| **Revenue churn** | `−churn_mrr / MRR đầu kỳ` |
| **Tỷ lệ lấp ghế** | `seats_active / seats_billed` |
| **Thâm niên** | `year_month_no(hiện tại) − year_month_no(đăng ký)` |
| **Churn ngoài ý muốn** | Huỷ có `reason = 'payment_failed'` |

NRR > 100% nghĩa là tệp khách cũ **tự sinh thêm** doanh thu. GRR luôn ≤ 100% và đo phần doanh thu **chắc chắn giữ được** nếu không bán thêm gì.
