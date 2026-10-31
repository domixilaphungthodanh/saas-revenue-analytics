# Cách tạo dữ liệu

Dự án này **không tải dữ liệu từ đâu cả**. Toàn bộ dữ liệu được sinh ra bởi `src/etl/generate_data.py` với seed cố định.

Lý do đã trình bày ở [idea.md](idea.md): không có bộ dữ liệu SaaS công khai nào chứa đủ chuỗi sự kiện gốc để tính MRR/NRR từ đầu.

---

## Chạy

```bash
python -m src.etl.generate_data
```

Kết quả: 6 file CSV trong `data/raw/`.

```
accounts.csv                1.397 dòng
plans.csv                       4 dòng
subscription_events.csv     2.255 dòng
invoices.csv               15.897 dòng
monthly_usage.csv          15.897 dòng
support_tickets.csv         8.476 dòng
```

**Seed cố định = 42.** Chạy lại bao giờ cũng ra đúng bộ số đó. Nếu muốn bộ khác, đổi `RANDOM_SEED` trong `src/etl/config.py` — nhưng khi đó mọi con số trong `findings.md` sẽ không còn khớp.

---

## Mô hình mô phỏng

Vòng lặp chạy 36 tháng (01/2023 → 12/2025). Mỗi tháng thực hiện 4 bước.

### Bước 1 — Khách mới

Số khách mới tăng dần theo thời gian, có mùa vụ:

```
base = 14 + 1,5 × (số thứ tự tháng)          # 14 → 66,5
n_new = round( Normal(base × seasonal, base × 0,12) )
```

Hệ số mùa vụ phản ánh hành vi mua B2B — mạnh đầu quý, yếu cuối năm:

| Tháng | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Hệ số | 1,08 | 1,02 | 1,12 | 1,00 | 0,98 | 0,92 | **0,85** | 0,90 | 1,05 | 1,06 | 1,10 | **0,80** |

Mỗi khách mới được gán:
- **Ngành**: technology 28%, retail 18%, finance 14%, healthcare 12%, manufacturing 11%, education 9%, other 8%
- **Quốc gia**: US 45%, UK 12%, DE 9%, CA 8%, IN 6%, AU 6%, FR 5%, BR 4%, other 5%
- **Kênh**: organic 30%, paid_search 22%, outbound 18%, partner 15%, referral 15%
- **Số nhân viên**: lognormal(4,2; 1,1), kẹp 5–20.000
- **Gói ban đầu**: phụ thuộc số nhân viên

| Nhân viên | Starter | Growth | Business | Enterprise |
|---|---:|---:|---:|---:|
| < 20 | 60% | 33% | 7% | — |
| 20–99 | 22% | 50% | 28% | — |
| 100–499 | — | 25% | 50% | 25% |
| 500+ | — | — | 35% | 65% |

- **Số ghế ban đầu**: `nhân viên × hệ số áp dụng × U(0,6; 1,4)`, tối thiểu bằng số ghế kèm theo gói

| Gói | Hệ số áp dụng |
|---|---:|
| Starter | 0,30 |
| Growth | 0,22 |
| Business | 0,16 |
| Enterprise | 0,12 |

- **Thiên hướng sử dụng** `health ~ Beta(2,2; 1,8)` — đặc điểm cố định của tài khoản, quyết định họ dùng nhiều hay ít suốt vòng đời

### Bước 2 — Xử lý từng tài khoản đang hoạt động

#### 2a. Mức sử dụng

```
ratio       = clip( health × plan_usage + Normal(0; 0,10), 0,02; 1,0 )
active_days = round(30 × ratio)
seat_util   = clip( 0,35 + 0,55 × ratio + Normal(0; 0,06), 0,10; 1,0 )
```

`plan_usage`: Starter 0,55 · Growth 0,70 · Business 0,80 · Enterprise 0,85

Tỷ lệ lấp ghế **phải** tương quan với mức sử dụng — nếu không, "ghế trống" chẳng nói lên điều gì về sức khoẻ tài khoản. Đây là lỗi đã mắc và sửa trong quá trình xây dựng.

#### 2b. Ticket hỗ trợ

```
rate = plan_ticket_rate × (1,8 nếu thâm niên ≤ 2 tháng)
n    = Poisson(rate)
```

`plan_ticket_rate`: Starter 0,15 · Growth 0,30 · Business 0,55 · Enterprise 0,90

Thời gian xử lý:
- 94% ticket: `lognormal(log(median_theo_priority); 0,7)` — median 1,2h (urgent) → 9h (low)
- **6% ticket bị leo thang**: `U(48; 168)` giờ (2–7 ngày)

Điểm hài lòng giảm theo thời gian chờ — đây là cơ chế tạo ra quan hệ nhân quả ở mô-đun 7:

```
mean_sat   = 4,5 − 0,9 × ln(1 + resolution_hours / 8)
satisfaction = clip( round(Normal(mean_sat; 0,6)), 1; 5 )
```

| Thời gian xử lý | Điểm hài lòng kỳ vọng |
|---|---:|
| 2 giờ | 4,3 |
| 8 giờ | 3,9 |
| 24 giờ | 3,4 |
| 72 giờ | 2,4 |
| 168 giờ | 1,7 |

#### 2c. Mở rộng và thu hẹp

| Hành động | Điều kiện | Xác suất | Quy mô |
|---|---|---:|---|
| Nâng gói | thâm niên ≥ 2, chưa phải Enterprise, lấp ghế ≥ 72%, dùng ≥ 55% | 18% | Nhảy sang gói kế tiếp |
| Mua thêm ghế | thâm niên ≥ 2, lấp ghế ≥ 72%, không vừa nâng gói | 42% | +8% đến +24% số ghế |
| Cắt ghế | thâm niên ≥ 3, lấp ghế ≤ 42%, còn ghế vượt mức kèm theo | 3,5% | −5% đến −15% |
| Hạ gói | thâm niên ≥ 6, không phải Starter, dùng < 35% | 1,0% | Xuống gói kế dưới |

Điều kiện "lấp ghế ≥ 72%" mới là thứ khiến mô-đun 9 có ý nghĩa: mở rộng xảy ra **vì** khách đã dùng gần hết chỗ, không phải ngẫu nhiên.

#### 2d. Xác suất huỷ

Đây là công thức trung tâm của mô hình:

```
hazard = 0,015                                    # nền
       × hệ_số_gói
       × hệ_số_kênh
       × hệ_số_thâm_niên
       × hệ_số_sử_dụng
       × hệ_số_hỗ_trợ
```

| Thành phần | Giá trị |
|---|---|
| **Hệ số gói** | Starter 1,9 · Growth 1,2 · Business 0,75 · Enterprise 0,25 |
| **Hệ số kênh** | Organic 0,85 · Paid search 1,25 · Outbound 1,15 · Partner 0,80 · Referral 0,70 |
| **Hệ số thâm niên** | ≤ 2 tháng: 2,0 · 3–6: 1,35 · 7–12: 0,95 · 13+: 0,55 |
| **Hệ số sử dụng** | < 5 ngày/tháng: ×2,0 · < 10 ngày: ×1,4 |
| **Hệ số hỗ trợ** | Có ticket ≤ 2 điểm: ×1,9 · Điểm TB ≤ 3,0: ×1,4 |

```
hazard = clip(hazard, 0,002; 0,30)
```

Hệ số thâm niên tạo ra "vực thẳm onboarding" — hiệu ứng mạnh nhất trong toàn bộ dữ liệu.

#### 2e. Hoá đơn và dunning

Mỗi tài khoản còn hoạt động nhận một hoá đơn/tháng:

```
amount = base_price + max(0, seats − included_seats) × price_per_seat
```

Trạng thái:

| Tình huống | Xử lý |
|---|---|
| Tháng trước thất bại, thử lại thành công | `paid` (xác suất 80%) |
| Tháng trước thất bại, thử lại thất bại | `failed`, tăng chuỗi thất bại |
| Bình thường, thẻ hỏng | `failed` (xác suất 2,5%) |
| **Chuỗi thất bại ≥ 2 tháng** | **Huỷ với lý do `payment_failed`** |

Đây là nguồn của "churn ngoài ý muốn" ở mô-đun 8.

### Bước 3 — Ghi nhận huỷ

Tài khoản bị huỷ được ghi một sự kiện `churn` với `mrr_delta = −MRR hiện tại` và một lý do. Lý do được chọn có trọng số, có điều chỉnh theo hoàn cảnh:

| Lý do | Trọng số gốc | Điều chỉnh |
|---|---:|---|
| `too_expensive` | 26 | |
| `missing_features` | 20 | |
| `switched_competitor` | 16 | |
| `no_longer_needed` | 15 | **+18 nếu dùng < 8 ngày/tháng** |
| `poor_support` | 9 | **+15 nếu điểm hài lòng TB ≤ 3,0** |
| `budget_cut` | 8 | |
| `product_quality` | 6 | |

Tài khoản bị huỷ bị loại khỏi tập hoạt động từ tháng sau.

---

## Kiểm chứng: dữ liệu có giống SaaS thật không?

| Chỉ số | Dữ liệu sinh ra | Chuẩn ngành B2B SaaS | Đánh giá |
|---|---:|---|---|
| Churn logo/tháng | ~2,4% | 2–3% (SMB nặng) | ✓ |
| Churn logo/năm | ~29% | 25–35% | ✓ |
| NRR/năm | 103% | 100–110% | ✓ |
| GRR/năm | 79% | 75–85% | ✓ |
| Tỷ lệ thu hồi dunning | 78% | 70–80% | ✓ |
| Churn ngoài ý muốn / tổng churn | 18% | 20–40% | hơi thấp |
| Tỷ lệ thất bại thanh toán | 3,0% | 2–5% | ✓ |
| MRR/tài khoản cuối kỳ | $746 | $200–2.000 | ✓ |

Điểm chưa khớp: tỷ lệ churn ngoài ý muốn hơi thấp so với thực tế (18% so với 20–40%). Muốn tăng, hạ `RETRY_SUCCESS` từ 0,80 xuống 0,70.

---

## Thay đổi hành vi dữ liệu

Mọi tham số nằm ở đầu `src/etl/generate_data.py`, gom thành một khối. Vài ví dụ:

| Muốn thay đổi | Sửa gì |
|---|---|
| Công ty tăng trưởng nhanh hơn | `base_new = 14 + 1.5 * m_idx` → tăng hệ số 1,5 |
| Churn cao hơn | `BASE_CHURN = 0.015` → 0,020 |
| NRR cao hơn | Tăng xác suất `seat_add` (0,42) hoặc `upgrade` (0,18) |
| Enterprise giữ khách tốt hơn nữa | `PLAN_CHURN["enterprise"] = 0.25` → 0,15 |
| Thanh toán thất bại nhiều hơn | `FAIL_RATE = 0.025` → 0,04 |
| Dunning kém hơn | `RETRY_SUCCESS = 0.80` → 0,65 |

Sau khi sửa, chạy lại `python run_all.py`. Số liệu trong `findings.md` sẽ lệch — cần cập nhật lại nếu muốn tài liệu khớp.

---

## Dùng với dữ liệu thật

Pipeline được thiết kế để thay thế bước 1 mà không sửa gì khác. Yêu cầu: 6 bảng nguồn có **đúng tên cột** như từ điển dữ liệu.

Xuất từ hệ thống billing thật:

| Bảng nguồn | Nguồn điển hình |
|---|---|
| `plans.csv` | Bảng giá trong Stripe/Chargebee |
| `accounts.csv` | CRM (HubSpot, Salesforce) + billing |
| `subscription_events.csv` | **Webhook** `customer.subscription.created/updated/deleted` |
| `invoices.csv` | API invoices của cổng thanh toán |
| `monthly_usage.csv` | Sự kiện sản phẩm (Amplitude, Mixpanel, Segment) |
| `support_tickets.csv` | Zendesk, Intercom |

Phần khó nhất là `subscription_events.csv`: phải **dựng lại chuỗi sự kiện** từ webhook hoặc từ lịch sử thay đổi subscription. Nhiều hệ thống không lưu lịch sử này — khi đó chỉ tính được MRR hiện tại, không tính được MRR bridge.

Ba quy tắc phải giữ khi map dữ liệu thật:

1. Mỗi tài khoản có **đúng một** sự kiện `new`.
2. `mrr_delta` phải là **thay đổi**, không phải MRR tuyệt đối.
3. Churn ghi ở **tháng cuối còn hoạt động**, không phải tháng đầu vắng mặt.
