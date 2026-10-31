"""Giai đoạn 5 — Chạy 9 mảng phân tích, xuất CSV và vẽ chart.

Quy trình:
    1. Thực thi toàn bộ file .sql trong sql/03_analysis/ theo thứ tự tên file
    2. Tự phát hiện mọi bảng mart_* vừa sinh ra (trừ bảng chất lượng dữ liệu)
    3. Xuất từng bảng ra reports/<ten_bang>.csv
    4. Vẽ chart theo CHART_SPECS

Chạy:
    python -m src.analysis.run_marts
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..etl.config import DB_PATH, FIGURES, PROJECT_ROOT, SQL_DIR  # noqa: E402
from ..etl.util import force_utf8_stdout  # noqa: E402

REPORTS = PROJECT_ROOT / "reports"
ANALYSIS_DIR = SQL_DIR / "03_analysis"

EXCLUDED = {"mart_data_quality", "mart_data_quality_summary"}

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 130,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.autolayout": True,
})

BLUE = "#1f4e79"
LIGHT_BLUE = "#4a90c4"
ORANGE = "#c55a11"
GREEN = "#2e7d32"
RED = "#c00000"
GREY = "#7f7f7f"

TENURE_LABELS = {
    "1_0_2m": "0–2 tháng",
    "2_3_5m": "3–5 tháng",
    "3_6_11m": "6–11 tháng",
    "4_12_23m": "12–23 tháng",
    "5_24m_plus": "24+ tháng",
}

USAGE_LABELS = {
    "dormant": "Không dùng (<5 ngày)",
    "low": "Ít (5–14 ngày)",
    "steady": "Đều (15–24 ngày)",
    "power": "Tích cực (25+ ngày)",
}

TICKET_LABELS = {
    "1_duoi_4h": "< 4 giờ",
    "2_4_24h": "4–24 giờ",
    "3_1_3_ngay": "1–3 ngày",
    "4_tren_3_ngay": "> 3 ngày",
}

SAT_LABELS = {
    "1_1_2": "1–2 điểm",
    "2_3": "3 điểm",
    "3_4": "4 điểm",
    "4_5": "5 điểm",
}

UTIL_LABELS = {
    "1_duoi_40": "< 40%",
    "2_40_60": "40–60%",
    "3_60_75": "60–75%",
    "4_75_90": "75–90%",
    "5_tu_90": "≥ 90%",
}

REASON_LABELS = {
    "too_expensive": "Quá đắt",
    "missing_features": "Thiếu tính năng",
    "switched_competitor": "Chuyển sang đối thủ",
    "no_longer_needed": "Không còn nhu cầu",
    "poor_support": "Hỗ trợ kém",
    "budget_cut": "Cắt ngân sách",
    "product_quality": "Chất lượng sản phẩm",
    "payment_failed": "Thanh toán thất bại",
}

SEGMENT_LABELS = {"starter": "Starter", "growth": "Growth",
                  "business": "Business", "enterprise": "Enterprise",
                  "smb": "SMB", "mid_market": "Mid-market"}

RISK_LABELS = {"churned": "Đã huỷ", "at_risk": "Rủi ro cao",
               "watch": "Cần theo dõi", "healthy": "Khoẻ"}


def labels(series: pd.Series, mapping: dict[str, str]) -> list[str]:
    return [mapping.get(v, v) for v in series]


def _save(fig, name: str) -> None:
    fig.savefig(FIGURES / name)
    plt.close(fig)


def _bar(ax, x, y, color=BLUE, fmt="{:.2f}", rotation=0, horizontal=False):  # noqa: ANN001
    if horizontal:
        bars = ax.barh(x, y, color=color)
        for b, v in zip(bars, y):
            ax.annotate(fmt.format(v), (b.get_width(), b.get_y() + b.get_height() / 2),
                        ha="left", va="center", fontsize=8)
    else:
        bars = ax.bar(x, y, color=color)
        for b, v in zip(bars, y):
            ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=8)
        if rotation:
            ax.tick_params(axis="x", rotation=rotation)


# =============================================================================
# THỰC THI SQL
# =============================================================================
def run_sql_files(conn: sqlite3.Connection) -> list[str]:
    files = sorted(ANALYSIS_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file SQL nào trong {ANALYSIS_DIR}")

    pattern = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)", re.I)
    made: list[str] = []
    for path in files:
        sql = path.read_text(encoding="utf-8")
        tables = [t for t in pattern.findall(sql) if t.startswith("mart_")]
        conn.executescript(sql)
        conn.commit()
        made.extend(tables)
        print(f"  {path.name:<34} -> {', '.join(tables) if tables else '(không tạo bảng)'}")
    return made


# =============================================================================
# CHART
# =============================================================================
def chart_mrr_bridge(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(df))
    ax.bar(x, df["new_mrr"], color=GREEN, label="MRR mới")
    ax.bar(x, df["expansion_mrr"], bottom=df["new_mrr"], color=LIGHT_BLUE, label="Mở rộng")
    ax.bar(x, df["churn_mrr"], color=RED, label="Mất do huỷ")
    ax.bar(x, df["contraction_mrr"], bottom=df["churn_mrr"], color=ORANGE, label="Thu hẹp")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["month_label"], rotation=90, fontsize=7)
    ax.set_ylabel("Thay đổi MRR (USD)")
    ax.set_title("Cầu nối MRR: doanh thu mới áp đảo, churn là lỗ hổng lớn nhất")
    ax.legend(ncol=4, fontsize=8, loc="upper left")

    ax2 = ax.twinx()
    ax2.plot(x, df["mrr_end"], color=BLUE, lw=2.2, marker="o", ms=2.5, label="MRR cuối kỳ")
    ax2.set_ylabel("MRR cuối kỳ (USD)", color=BLUE)
    ax2.tick_params(axis="y", colors=BLUE)
    ax2.grid(False)
    _save(fig, "01_mrr_bridge.png")


def chart_mrr_trend(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = np.arange(len(df))
    ax.fill_between(x, df["mrr_end"], color=BLUE, alpha=0.15)
    ax.plot(x, df["mrr_end"], color=BLUE, lw=2.4)
    ax.set_xticks(x[::3])
    ax.set_xticklabels(df["month_label"][::3], rotation=45)
    ax.set_ylabel("MRR (USD)")
    ax.set_title(f"MRR tăng từ ${df['mrr_end'].iloc[0]:,.0f} lên ${df['mrr_end'].iloc[-1]:,.0f} sau 36 tháng")
    _save(fig, "02_mrr_trend.png")


def chart_growth_decomposition(df: pd.DataFrame) -> None:
    d = df.sort_values("mrr")
    colors = [GREEN if v > 0 else RED for v in d["mrr"]]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.barh(d["component"], d["mrr"] / 1000, color=colors)
    for i, v in enumerate(d["mrr"] / 1000):
        ax.annotate(f"{v:,.0f}k", (v, i), ha="left" if v > 0 else "right",
                    va="center", fontsize=9, fontweight="bold")
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Tổng MRR (nghìn USD)")
    ax.set_title("Cơ cấu thay đổi MRR toàn kỳ")
    _save(fig, "03_growth_decomposition.png")


def chart_cohort_heatmap(df: pd.DataFrame, value: str, title: str,
                         name: str, cmap: str = "YlGnBu", vmin: float = 0,
                         vmax: float = 100) -> None:
    p = df.pivot(index="cohort_month", columns="month_index", values=value)
    p = p.loc[:, :12]
    fig, ax = plt.subplots(figsize=(11, 8))
    im = ax.imshow(p.values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(p.shape[1]))
    ax.set_xticklabels(p.columns)
    ax.set_yticks(range(p.shape[0]))
    ax.set_yticklabels(p.index, fontsize=7)
    ax.set_xlabel("Số tháng kể từ khi đăng ký")
    ax.set_ylabel("Cohort đăng ký")
    ax.set_title(title)
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="%")
    _save(fig, name)


def chart_cohort_logo(df: pd.DataFrame) -> None:
    chart_cohort_heatmap(
        df, "retention_pct",
        "Tỷ lệ giữ chân khách hàng theo cohort (%)",
        "04_cohort_retention.png", vmin=40,
    )


def chart_cohort_rev(df: pd.DataFrame) -> None:
    chart_cohort_heatmap(
        df, "revenue_retention_pct",
        "Tỷ lệ giữ chân doanh thu theo cohort (%)  — trên 100% là mở rộng",
        "05_cohort_revenue.png", cmap="RdYlGn", vmin=40, vmax=150,
    )


def chart_nrr_cohort(df: pd.DataFrame) -> None:
    d = df[df["is_mature"] == 1]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    _bar(axes[0], d["cohort_month"], d["nrr_12m_pct"], BLUE, "{:.0f}", 90)
    axes[0].axhline(100, color=RED, ls="--", lw=1.2)
    axes[0].set_ylabel("NRR 12 tháng (%)")
    axes[0].set_title("NRR theo cohort (đường đỏ = 100%)")

    axes[1].scatter(d["grr_12m_pct"], d["nrr_12m_pct"], s=d["accounts"] * 3,
                    color=BLUE, alpha=0.6, edgecolors="white")
    axes[1].axhline(100, color=RED, ls="--", lw=1)
    axes[1].axvline(100, color=RED, ls="--", lw=1)
    axes[1].set_xlabel("GRR 12 tháng (%)")
    axes[1].set_ylabel("NRR 12 tháng (%)")
    axes[1].set_title("Khoảng cách NRR – GRR = phần mở rộng\n(kích thước điểm = số tài khoản)")
    _save(fig, "06_nrr_cohort.png")


def chart_churn_segment(df: pd.DataFrame) -> None:
    d = df[df["dimension"] == "plan"].sort_values("churn_rate_pct")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    _bar(ax, labels(d["segment"], SEGMENT_LABELS), d["churn_rate_pct"], RED, "{:.1f}%", horizontal=True)
    ax.set_xlabel("Tỷ lệ huỷ (%)")
    ax.set_title("Gói càng nhỏ, khách càng dễ rời bỏ")
    _save(fig, "07_churn_by_plan.png")


def chart_churn_channel(df: pd.DataFrame) -> None:
    d = df[df["dimension"] == "channel"].sort_values("churn_rate_pct")
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    _bar(ax, d["segment"], d["churn_rate_pct"], ORANGE, "{:.1f}%", 20, horizontal=True)
    ax.set_xlabel("Tỷ lệ huỷ (%)")
    ax.set_title("Chất lượng khách theo kênh thu hút")
    _save(fig, "08_churn_by_channel.png")


def chart_churn_tenure(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.4))
    _bar(ax, labels(df["tenure_band"], TENURE_LABELS), df["monthly_churn_pct"], RED, "{:.2f}%")
    ax.set_ylabel("Xác suất huỷ mỗi tháng (%)")
    ax.set_xlabel("Thâm niên")
    ax.set_title("Thâm niên càng ngắn, xác suất huỷ càng cao")
    _save(fig, "09_churn_by_tenure.png")


def chart_churn_reasons(df: pd.DataFrame) -> None:
    d = df.sort_values("churned_accounts")
    fig, ax = plt.subplots(figsize=(9, 4.6))
    _bar(ax, labels(d["reason"], REASON_LABELS), d["churned_accounts"], ORANGE, "{:.0f}", horizontal=True)
    ax.set_xlabel("Số tài khoản")
    ax.set_title("Lý do huỷ dịch vụ")
    _save(fig, "10_churn_reasons.png")


def chart_plan_mix(df: pd.DataFrame) -> None:
    p = df.pivot_table(index="month", columns="tier", values="mrr", aggfunc="sum").fillna(0)
    order = [t for t in ["starter", "growth", "business", "enterprise"] if t in p.columns]
    p = p[order]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.stackplot(range(len(p)), [p[c] / 1000 for c in p.columns],
                 labels=[SEGMENT_LABELS.get(c, c) for c in p.columns],
                 colors=[GREY, LIGHT_BLUE, BLUE, GREEN], alpha=0.9)
    ax.set_xticks(range(0, len(p), 3))
    ax.set_xticklabels([str(i)[:7] for i in p.index[::3]], rotation=45)
    ax.set_ylabel("MRR (nghìn USD)")
    ax.set_title("Cơ cấu MRR theo gói: Business và Enterprise chi phối")
    ax.legend(loc="upper left", fontsize=8)
    _save(fig, "11_plan_mix.png")


def chart_plan_performance(df: pd.DataFrame) -> None:
    d = df.sort_values("churn_rate_pct")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    _bar(axes[0], labels(d["tier"], SEGMENT_LABELS), d["churn_rate_pct"], RED, "{:.1f}%", 15)
    axes[0].set_ylabel("Tỷ lệ huỷ (%)")
    axes[0].set_title("Tỷ lệ huỷ theo gói")

    _bar(axes[1], labels(d["tier"], SEGMENT_LABELS), d["current_mrr"] / 1000, BLUE, "{:,.0f}k", 15)
    axes[1].set_ylabel("MRR hiện tại (nghìn USD)")
    axes[1].set_title("MRR hiện tại theo gói")
    _save(fig, "12_plan_performance.png")


def chart_usage_churn(df: pd.DataFrame) -> None:
    order = ["dormant", "low", "steady", "power"]
    d = df.set_index("usage_band").reindex(order).reset_index().dropna(subset=["churn_rate_pct"])
    fig, ax = plt.subplots(figsize=(9, 4.4))
    _bar(ax, labels(d["usage_band"], USAGE_LABELS), d["churn_rate_pct"], RED, "{:.2f}%", 10)
    ax.set_ylabel("Xác suất huỷ tháng sau (%)")
    ax.set_title("Mức sử dụng là chỉ báo sớm mạnh nhất của churn")
    _save(fig, "13_usage_vs_churn.png")


def chart_risk(df: pd.DataFrame) -> None:
    d = df.copy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    _bar(axes[0], labels(d["risk_flag"], RISK_LABELS), d["accounts"], BLUE, "{:.0f}", 12)
    axes[0].set_ylabel("Số tài khoản")
    axes[0].set_title("Số lượng tài khoản theo mức rủi ro")
    _bar(axes[1], labels(d["risk_flag"], RISK_LABELS), d["pct_active_mrr"], GREEN, "{:.1f}%", 12)
    axes[1].set_ylabel("% MRR đang hoạt động")
    axes[1].set_title("Tỷ trọng MRR theo mức rủi ro")
    fig.suptitle("BẢNG RỦI RO TÀI KHOẢN", fontsize=13, fontweight="bold")
    _save(fig, "14_risk_summary.png")


def chart_support(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.4))
    _bar(ax, labels(df["resolution_band"], TICKET_LABELS), df["churn_rate_pct"], ORANGE, "{:.1f}%")
    ax.set_ylabel("Tỷ lệ huỷ trong 3 tháng sau ticket (%)")
    ax.set_xlabel("Thời gian xử lý ticket")
    ax.set_title("Thời gian xử lý ticket không dự báo churn — điểm hài lòng mới có")
    _save(fig, "15_support_impact.png")


def chart_satisfaction(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.4))
    _bar(ax, labels(df["satisfaction_band"], SAT_LABELS), df["churn_rate_pct"], RED, "{:.1f}%")
    ax.set_ylabel("Tỷ lệ huỷ (%)")
    ax.set_xlabel("Điểm hài lòng trung bình")
    ax.set_title("Khách không hài lòng rời bỏ nhiều hơn rõ rệt")
    _save(fig, "16_satisfaction_band.png")


def chart_billing_trend(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.plot(df["month_label"], df["failed_rate_pct"], color=RED, lw=2, marker="o", ms=3)
    ax.set_ylabel("Tỷ lệ hoá đơn thất bại (%)")
    ax.set_title("Tỷ lệ thanh toán thất bại theo tháng")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    _save(fig, "17_billing_trend.png")


def chart_expansion_tier(df: pd.DataFrame) -> None:
    d = df.sort_values("net_mrr_impact", ascending=False)
    x = np.arange(len(d))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(x - w / 2, d["seat_add_mrr"] / 1000, w, color=GREEN, label="Mua thêm ghế")
    ax.bar(x + w / 2, d["upgrade_mrr"] / 1000, w, color=BLUE, label="Nâng gói")
    ax.bar(x - w / 2, d["churn_mrr"] / 1000, w, color=RED, alpha=0.75, label="Mất do huỷ")
    ax.set_xticks(x)
    ax.set_xticklabels(labels(d["tier"], SEGMENT_LABELS))
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("MRR (nghìn USD)")
    ax.set_title("Động cơ mở rộng so với tổn thất do huỷ, theo gói")
    ax.legend(fontsize=8)
    _save(fig, "18_expansion_by_tier.png")


def chart_seat_growth(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.plot(df["month_label"], df["seats_billed"], color=BLUE, lw=2.2)
    ax.set_ylabel("Tổng số ghế đang bán")
    ax.set_title("Tổng số ghế tăng đều — mở rộng đến từ khách cũ, không chỉ khách mới")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    _save(fig, "19_seat_growth.png")


def chart_utilization(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    _bar(axes[0], labels(df["utilization_band"], UTIL_LABELS), df["expansion_rate_pct"],
         GREEN, "{:.1f}%", 15)
    axes[0].set_ylabel("Tỷ lệ mở rộng tháng sau (%)")
    axes[0].set_title("Lấp ghế cao → mua thêm ghế")
    _bar(axes[1], labels(df["utilization_band"], UTIL_LABELS), df["churn_rate_pct"],
         RED, "{:.2f}%", 15)
    axes[1].set_ylabel("Tỷ lệ huỷ tháng sau (%)")
    axes[1].set_title("Lấp ghế thấp → rời bỏ")
    fig.suptitle("TỶ LỆ LẤP GHẾ LÀ TÍN HIỆU HAI CHIỀU", fontsize=13, fontweight="bold")
    _save(fig, "20_seat_utilization.png")


CHART_SPECS: list[tuple[str, object]] = [
    ("mart_mrr_monthly", chart_mrr_bridge),
    ("mart_mrr_monthly", chart_mrr_trend),
    ("mart_growth_decomposition", chart_growth_decomposition),
    ("mart_cohort_retention", chart_cohort_logo),
    ("mart_cohort_revenue", chart_cohort_rev),
    ("mart_nrr_by_cohort", chart_nrr_cohort),
    ("mart_churn_by_segment", chart_churn_segment),
    ("mart_churn_by_segment", chart_churn_channel),
    ("mart_churn_by_tenure", chart_churn_tenure),
    ("mart_churn_reasons", chart_churn_reasons),
    ("mart_plan_mix_monthly", chart_plan_mix),
    ("mart_plan_performance", chart_plan_performance),
    ("mart_usage_vs_churn", chart_usage_churn),
    ("mart_risk_summary", chart_risk),
    ("mart_support_impact", chart_support),
    ("mart_satisfaction_band", chart_satisfaction),
    ("mart_billing_trend", chart_billing_trend),
    ("mart_expansion_by_tier", chart_expansion_tier),
    ("mart_seat_growth", chart_seat_growth),
    ("mart_seat_utilization_bands", chart_utilization),
]


def main() -> None:
    force_utf8_stdout()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Chưa có database: {DB_PATH}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    line = "=" * 74
    print(line)
    print("CHẠY 9 MẢNG PHÂN TÍCH + XUẤT CSV + VẼ CHART (GIAI ĐOẠN 5)")
    print(line)

    conn = sqlite3.connect(DB_PATH)
    try:
        print("\n[A] Thực thi SQL")
        tables = run_sql_files(conn)

        tables = [t for t in tables if t not in EXCLUDED]
        print(f"\n[B] Xuất CSV ({len(tables)} bảng)")
        data: dict[str, pd.DataFrame] = {}
        for t in tables:
            df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
            data[t] = df
            df.to_csv(REPORTS / f"{t}.csv", index=False, encoding="utf-8-sig")
            print(f"  {t:<32} {len(df):>6,} dòng -> reports/{t}.csv")

        print("\n[C] Vẽ chart")
        n_chart = 0
        for table, fn in CHART_SPECS:
            if table in data:
                try:
                    fn(data[table])  # type: ignore[operator]
                    n_chart += 1
                    print(f"  {table:<32} -> {fn.__name__}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  {table:<32} -> LỖI: {exc}")
        print(f"  Tổng: {n_chart} chart trong {FIGURES}")

        print("\n[D] Xem nhanh kết quả")
        for t in ["mart_retention_summary", "mart_growth_decomposition",
                  "mart_churn_by_tenure", "mart_risk_summary", "mart_dunning"]:
            if t in data:
                print(f"\n--- {t} ---")
                with pd.option_context("display.width", 170, "display.max_columns", 30):
                    print(data[t].to_string(index=False))
    finally:
        conn.close()

    print(f"\n{line}")
    print("Xong. Xem chart trong:", FIGURES)
    print(line)


if __name__ == "__main__":
    main()
