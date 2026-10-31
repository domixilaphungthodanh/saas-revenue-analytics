"""Chạy toàn bộ pipeline bằng một lệnh.

    python run_all.py

Thứ tự bắt buộc:
    generate_data -> build_db -> transform -> run_marts -> validate

Ghi chú: validate chạy CUỐI vì nó kiểm tra cả các bảng mart_* do run_marts sinh ra
(đẳng thức cầu nối MRR, mốc cohort 0 = 100%, tổng bảng rủi ro...).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS: list[tuple[str, list[str]]] = [
    ("Giai đoạn 1 — Sinh dữ liệu mô phỏng (6 CSV)", ["-m", "src.etl.generate_data"]),
    ("Giai đoạn 2 — Nạp staging vào SQLite", ["-m", "src.etl.build_db"]),
    ("Giai đoạn 3 — Transform sang star schema", ["-m", "src.etl.transform"]),
    ("Giai đoạn 4 — Phân tích, CSV, chart", ["-m", "src.analysis.run_marts"]),
    ("Giai đoạn 5 — Kiểm tra chất lượng", ["-m", "src.etl.validate"]),
]


def main() -> int:
    os.chdir(ROOT)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    line = "=" * 74
    print(line)
    print("SAAS REVENUE ANALYTICS — CHẠY TOÀN BỘ PIPELINE")
    print(line)
    print(f"Thư mục: {ROOT}\n")

    for i, (title, args) in enumerate(STEPS, start=1):
        print(f"\n{'#' * 74}")
        print(f"# BƯỚC {i}/{len(STEPS)}: {title}")
        print(f"{'#' * 74}\n")
        result = subprocess.run([sys.executable, *args], env=env, check=False)
        if result.returncode != 0:
            print(f"\nDỪNG: bước {i} thất bại (exit code {result.returncode}).")
            return result.returncode

    print(f"\n{line}")
    print("HOÀN TẤT PIPELINE")
    print(f"  Database : {ROOT / 'data' / 'processed' / 'saas.db'}")
    print(f"  CSV      : {ROOT / 'reports'}")
    print(f"  Chart    : {ROOT / 'reports' / 'figures'}")
    print(f"  Báo cáo  : {ROOT / 'docs' / 'findings.md'}")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
