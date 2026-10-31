# Ý tưởng dự án

## Vấn đề

Mọi công ty SaaS đều nhìn vào một biểu đồ MRR tăng dần và kết luận "mọi thứ đang tốt". Biểu đồ đó không nói được điều gì quan trọng:

- Doanh thu tăng vì **có thêm khách mới**, hay vì **khách cũ chi nhiều hơn**?
- Nếu ngừng chi tiền marketing ngay hôm nay, doanh thu sẽ đi về đâu?
- Nhóm khách nào đang rời bỏ, và họ rời ở tháng thứ mấy?
- Có dấu hiệu nào **xuất hiện trước** khi khách huỷ để can thiệp kịp không?

Báo cáo tài chính trả lời được "tháng này doanh thu bao nhiêu" nhưng không trả lời được "doanh thu này có bền không". Đó là khoảng trống dự án này lấp vào.

## Câu hỏi nghiên cứu

Sắp theo thứ tự sẽ trả lời trong `findings.md`:

| # | Câu hỏi | Mô-đun |
|---|---|---|
| Q1 | MRR tăng/giảm do đâu, từng tháng? | 01 |
| Q2 | Một lứa khách đăng ký cùng tháng sống được bao lâu? | 02 |
| Q3 | Sau 12 tháng, tệp khách cũ còn bao nhiêu % doanh thu? | 03 |
| Q4 | Phân khúc nào rời bỏ nhiều nhất? Rời ở tháng thứ mấy? | 04 |
| Q5 | Gói nào thực sự sinh lời, gói nào đang rút ròng? | 05 |
| Q6 | Mức sử dụng có dự báo được churn không? | 06 |
| Q7 | Hỗ trợ kém có làm khách rời đi không? | 07 |
| Q8 | Bao nhiêu doanh thu mất vì thẻ hỏng? | 08 |
| Q9 | Mở rộng đến từ đâu, và tín hiệu nào báo trước? | 09 |

## Phạm vi

**Trong phạm vi:**
- Doanh thu định kỳ (MRR), NRR, GRR
- Giữ chân khách và doanh thu theo cohort
- Phân tích churn theo 5 chiều: gói, kênh, ngành, quốc gia, quy mô
- Mức sử dụng, hỗ trợ, thanh toán
- Mở rộng (thêm ghế, nâng gói) và thu hẹp

**Ngoài phạm vi (cố ý):**
- **Không dự báo bằng ML.** Không có `sklearn`, không có mô hình churn prediction. Bài toán ở đây là *mô tả và giải thích*, không phải dự đoán từng cá nhân. Một bảng rủi ro dựa trên luật rõ ràng dễ giải thích với đội CS hơn một xác suất 0,73.
- **Không dashboard.** Không Streamlit, không Power BI. Kết quả là CSV + PNG, ai cũng mở được, không cần cài gì.
- **Không dữ liệu chi phí.** Không có CAC, LTV, gross margin. Nếu có, phân tích sẽ mạnh hơn nhiều — xem phần Hạn chế trong `findings.md`.

## Vì sao dùng dữ liệu mô phỏng?

Đây là quyết định lớn nhất của dự án, cần giải thích rõ.

**Không tồn tại bộ dữ liệu SaaS công khai phù hợp.** Đã cân nhắc và loại:

| Nguồn | Vấn đề |
|---|---|
| Kaggle "Telco Customer Churn" | 7.043 dòng, không có MRR, không có chuỗi sự kiện. Chỉ là bài toán phân loại. |
| Kaggle "SaaS Subscription Churn" | Bản thân cũng là dữ liệu tổng hợp, không có sự kiện nâng cấp/cắt ghế |
| KKBox (WSDM) | Có churn nhưng không có doanh thu định kỳ theo ghế |
| Dữ liệu công khai của Stripe/Chargebee | Không có, và cũng không được phép công bố |

Để tính được MRR bridge, NRR, cohort retention từ đầu, cần **chuỗi sự kiện gốc**: mỗi lần đăng ký, nâng gói, cắt ghế, huỷ đều là một dòng có ngày và số tiền. Không bộ dữ liệu công khai nào có cấu trúc đó.

**Cách xử lý:** viết một bộ sinh dữ liệu (`generate_data.py`) tạo ra chuỗi sự kiện thô giống hệt export từ hệ thống billing. Sau đó toàn bộ tầng phân tích là **SQL thật** — không có chỗ nào "biết trước đáp án".

Hệ quả cần nêu rõ: các quan hệ nhân quả trong dữ liệu là do người viết **đặt vào**, không phải **phát hiện ra**. Giá trị của dự án nằm ở **phương pháp phân tích**, không ở kết luận về một công ty cụ thể.

Đổi lại, pipeline dùng được nguyên vẹn với dữ liệu thật: chỉ cần thay bước 1 bằng bước nạp export từ Stripe/Chargebee/NetSuite. Tầng SQL không cần sửa một dòng nào.

## Vì sao chọn SQLite

- Chạy được ở mọi máy, không cần cài server
- File `.db` duy nhất, dễ backup
- SQL đầy đủ: window function, CTE, `LAG`, `ROW_NUMBER` — đủ cho mọi phép phân tích ở đây
- Không che giấu gì: mọi phép tính đều đọc được trong file `.sql`

## Nguyên tắc thiết kế

1. **Một nguồn sự thật.** MRR không được lưu sẵn theo tháng. Nó luôn được tính lại từ chuỗi sự kiện. Nếu lưu sẵn, sớm muộn hai nguồn sẽ lệch nhau.
2. **Tầng staging là bản sao nguyên trạng.** Mọi cột đọc dưới dạng chuỗi, không ép kiểu. `validate.py` chứng minh bằng hash từng dòng.
3. **Phép biến đổi chỉ ở một chỗ.** `transform.py` là nơi duy nhất đổi kiểu, tính cờ, join bảng. SQL phân tích không phải lặp lại các điều kiện đó.
4. **Kiểm tra cả phép tính, không chỉ dữ liệu.** Ngoài kiểm tra khoá ngoại và trùng lặp, `validate.py` còn kiểm tra **đẳng thức nghiệp vụ**: MRR cuối kỳ = tổng mrr_delta, MRR đầu tháng = MRR cuối tháng trước, cohort tháng 0 = 100%.
5. **Nêu rõ hạn chế.** Mọi báo cáo đều có phần Hạn chế, không giấu điểm yếu của dữ liệu.

## Kết quả kỳ vọng

- 9 mô-đun SQL, 23 bảng kết quả, 20 biểu đồ
- Báo cáo `findings.md` với 9 phát hiện và 5 khuyến nghị xếp theo tỷ lệ tác động/công sức
- Bảng rủi ro từng tài khoản dùng được ngay trong vận hành
- 45 quy tắc kiểm tra chất lượng, tất cả PASS
