"""Cấu hình đường dẫn và hằng số cho toàn dự án."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DOCS = PROJECT_ROOT / "docs"
SQL_DIR = PROJECT_ROOT / "sql"
FIGURES = PROJECT_ROOT / "reports" / "figures"
NOTEBOOKS = PROJECT_ROOT / "notebooks"

DB_PATH = DATA_PROCESSED / "saas.db"

# --- Cửa sổ mô phỏng: 36 tháng, đủ dài cho phân tích cohort ------------------
SIM_START = "2023-01-01"
SIM_END = "2025-12-31"

# --- Khoá sự kiện -----------------------------------------------------------
EVT_NEW = "new"
EVT_UPGRADE = "upgrade"
EVT_DOWNGRADE = "downgrade"
EVT_SEAT_ADD = "seat_add"
EVT_SEAT_REMOVE = "seat_remove"
EVT_CHURN = "churn"
EVT_REACTIVATE = "reactivate"

# Các loại sự kiện làm tăng MRR / giảm MRR
EXPANSION_EVENTS = (EVT_UPGRADE, EVT_SEAT_ADD)
CONTRACTION_EVENTS = (EVT_DOWNGRADE, EVT_SEAT_REMOVE)

# --- Ngưỡng phân tích -------------------------------------------------------
HEALTHY_ACTIVE_DAYS = 15      # >= 15 ngày hoạt động / tháng được coi là khoẻ
SEAT_UTIL_EXPAND = 0.72       # dùng >= 72% ghế -> có khả năng mua thêm
SEAT_UTIL_SHRINK = 0.42       # dùng < 42% ghế  -> có khả năng cắt bớt
TENURE_MONTHS_MATURE = 12     # sau 12 tháng coi là khách trưởng thành
SAMPLE_MIN_ACCOUNTS = 20      # nhóm ít hơn 20 tài khoản: không kết luận

RANDOM_SEED = 42
