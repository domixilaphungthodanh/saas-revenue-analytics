# Bắt đầu từ đâu

## Nếu bạn có 2 phút

Đọc **Tóm tắt điều hành** trong [findings.md](findings.md). Ba con số: NRR 103,7% / GRR 76,0% / MRR cuối kỳ $729.625. Kết luận: tăng trưởng đến từ khách mới, không phải từ giữ chân.

## Nếu bạn có 10 phút

1. [README.md](../README.md) — tổng quan và 6 phát hiện chính
2. Mở `reports/figures/` xem 20 biểu đồ
3. [findings.md](findings.md) mục 1 và mục 4

## Nếu bạn muốn chạy thử

```bash
pip install -r requirements.txt
python run_all.py
```

Khoảng 15 giây. Kết quả ở `reports/`.

## Nếu bạn muốn hiểu cách làm

| Muốn hiểu | Đọc |
|---|---|
| Vì sao dùng dữ liệu mô phỏng | [idea.md](idea.md) |
| Cơ chế sinh dữ liệu | [getting_data.md](getting_data.md) |
| Ý nghĩa từng cột | [data_dictionary.md](data_dictionary.md) |
| Cách tính từng chỉ số | `sql/03_analysis/*.sql` |
| Kiểm tra chất lượng | `src/etl/validate.py` |

## Bản đồ file

```
run_all.py                      ← chạy tất cả
│
├── src/etl/
│   ├── generate_data.py        ← 6 CSV, seed 42
│   ├── build_db.py             ← CSV → staging
│   ├── transform.py            ← staging → dim/fact
│   └── validate.py             ← 45 quy tắc
│
├── src/analysis/
│   └── run_marts.py            ← SQL → CSV + 20 chart
│
├── sql/03_analysis/            ← 9 mô-đun phân tích
│   ├── 01_mrr_movement.sql     ← cầu nối MRR
│   ├── 02_cohort_retention.sql ← ma trận giữ chân
│   ├── 03_revenue_retention.sql← NRR/GRR
│   ├── 04_churn_analysis.sql   ← churn theo phân khúc
│   ├── 05_plan_mix.sql         ← hiệu quả từng gói
│   ├── 06_usage_health.sql     ← sử dụng + bảng rủi ro
│   ├── 07_support_impact.sql   ← hỗ trợ (có bẫy phương pháp)
│   ├── 08_payment_health.sql   ← dunning
│   └── 09_expansion_engine.sql ← mở rộng
│
├── docs/                       ← tài liệu
├── notebooks/01_explore.ipynb  ← EDA
├── data/                       ← không commit
└── reports/                    ← kết quả
```

## Ba điều dễ hiểu nhầm

**1. "Doanh thu tăng 729 nghìn đô, vậy công ty khoẻ."**
Không hẳn. GRR 76% nghĩa là 24% doanh thu nền biến mất mỗi năm. Nếu ngừng bán hàng mới, doanh thu co lại ngay trong quý đầu.

**2. "Khách mở nhiều ticket thì sắp bỏ."**
Số liệu thô nói ngược lại — nhưng đó là **thiên lệch sống sót**. Xem mục 7 của [findings.md](findings.md). Đơn vị phân tích phải là ticket, không phải tài khoản.

**3. "NRR 103% là chỉ số tốt nhất để đánh giá giữ chân."**
NRR trộn hai thứ khác nhau: giữ chân và bán thêm. GRR mới là thước đo giữ chân thuần. Luôn đọc cặp NRR–GRR cùng nhau.

## Câu hỏi tự kiểm tra

Nếu đọc xong mà trả lời được những câu này thì đã nắm được dự án:

- Vì sao MRR tăng nhưng GRR chỉ 76%?
- Tại sao nhóm 0 ticket có tỷ lệ huỷ cao nhất?
- Vì sao chỉ tính NRR cho cohort đủ 12 tháng?
- Tỷ lệ lấp ghế cao báo hiệu điều gì, và cho ai?
- Nếu chỉ được làm một việc để giảm churn, nên làm gì?

Đáp án nằm trong [findings.md](findings.md) — lần lượt ở mục 1, 7, 3, 9, và phần Khuyến nghị.
