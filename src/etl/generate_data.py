"""Giai đoạn 1 — Sinh bộ dữ liệu SaaS mô phỏng (6 file CSV).

VÌ SAO DÙNG DỮ LIỆU MÔ PHỎNG?
    Không tồn tại bộ dữ liệu SaaS công khai nào có đủ chuỗi sự kiện gốc
    (đăng ký → nâng cấp → cắt ghế → huỷ) để tính MRR, NRR và cohort.
    Các bộ trên Kaggle hoặc quá nhỏ (vài nghìn dòng), hoặc đã tổng hợp sẵn
    nên không thể tái tạo phép tính từ đầu.

    Bộ sinh này tạo ra chuỗi sự kiện **ở dạng thô**, giống hệt export từ một
    hệ thống billing thật. Toàn bộ phép tính MRR/NRR/cohort phía sau vẫn là
    SQL thật, nên pipeline dùng được nguyên vẹn với dữ liệu thật.

CƠ CHẾ MÔ PHỎNG (được thiết kế để có hành vi giống SaaS thật):
    - Tăng trưởng khách mới theo thời gian + mùa vụ (Q1 cao, tháng 7 và 12 thấp)
    - Xác suất huỷ phụ thuộc 5 yếu tố: gói, kênh, thâm niên, mức sử dụng,
      và điểm hài lòng hỗ trợ
    - Khách dùng gần hết ghế → có khả năng mua thêm (expansion)
    - Khách dùng ít ghế → có khả năng cắt bớt (contraction)
    - Thanh toán thất bại → thử lại 1 lần → huỷ ngoài ý muốn (involuntary churn)

Chạy:
    python -m src.etl.generate_data
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .config import (
    DATA_RAW,
    EVT_CHURN,
    EVT_DOWNGRADE,
    EVT_NEW,
    EVT_SEAT_ADD,
    EVT_SEAT_REMOVE,
    EVT_UPGRADE,
    RANDOM_SEED,
    SEAT_UTIL_EXPAND,
    SEAT_UTIL_SHRINK,
    SIM_END,
    SIM_START,
)
from .util import force_utf8_stdout

# =============================================================================
# THAM SỐ MÔ PHỎNG
# =============================================================================
@dataclass(frozen=True)
class Plan:
    plan_id: str
    plan_name: str
    tier: str
    base_price: float
    included_seats: int
    price_per_seat: float

    def monthly_price(self, seats: int) -> float:
        extra = max(0, seats - self.included_seats)
        return round(self.base_price + extra * self.price_per_seat, 2)


PLANS: list[Plan] = [
    Plan("PLAN-STARTER", "Starter", "starter", 49.0, 3, 12.0),
    Plan("PLAN-GROWTH", "Growth", "growth", 149.0, 10, 15.0),
    Plan("PLAN-BUSINESS", "Business", "business", 399.0, 25, 18.0),
    Plan("PLAN-ENTERPRISE", "Enterprise", "enterprise", 1200.0, 50, 22.0),
]
PLAN_BY_ID = {p.plan_id: p for p in PLANS}
NEXT_TIER = {"starter": "growth", "growth": "business", "business": "enterprise"}
PREV_TIER = {"growth": "starter", "business": "growth", "enterprise": "business"}

INDUSTRIES = (
    ("technology", 28), ("retail", 18), ("finance", 14), ("healthcare", 12),
    ("manufacturing", 11), ("education", 9), ("other", 8),
)
COUNTRIES = (
    ("US", 45), ("UK", 12), ("DE", 9), ("CA", 8), ("IN", 6),
    ("AU", 6), ("FR", 5), ("BR", 4), ("other", 5),
)
CHANNELS = (
    ("organic", 30), ("paid_search", 22), ("outbound", 18),
    ("partner", 15), ("referral", 15),
)
PAYMENT_METHODS = (("credit_card", 62), ("bank_transfer", 24), ("paypal", 14))
TICKET_CATEGORIES = (
    ("billing", 22), ("bug", 24), ("how_to", 28),
    ("integration", 14), ("feature_request", 12),
)
PRIORITIES = (("low", 40), ("medium", 38), ("high", 17), ("urgent", 5))

CHURN_REASONS = (
    ("too_expensive", 26), ("missing_features", 20), ("switched_competitor", 16),
    ("no_longer_needed", 15), ("poor_support", 9), ("budget_cut", 8),
    ("product_quality", 6),
)

# Mùa vụ đăng ký: B2B mua nhiều đầu quý, chậm vào tháng 7 và tháng 12
SEASONAL = {1: 1.08, 2: 1.02, 3: 1.12, 4: 1.00, 5: 0.98, 6: 0.92,
            7: 0.85, 8: 0.90, 9: 1.05, 10: 1.06, 11: 1.10, 12: 0.80}

BASE_CHURN = 0.015
PLAN_CHURN = {"starter": 1.9, "growth": 1.2, "business": 0.75, "enterprise": 0.25}
CHANNEL_CHURN = {"organic": 0.85, "paid_search": 1.25, "outbound": 1.15,
                 "partner": 0.80, "referral": 0.70}
PLAN_USAGE = {"starter": 0.55, "growth": 0.70, "business": 0.80, "enterprise": 0.85}
PLAN_TICKET_RATE = {"starter": 0.15, "growth": 0.30, "business": 0.55, "enterprise": 0.90}
PLAN_ADOPTION = {"starter": 0.30, "growth": 0.22, "business": 0.16, "enterprise": 0.12}

FAIL_RATE = 0.025          # tỷ lệ hoá đơn thất bại lần đầu
RETRY_SUCCESS = 0.80       # tỷ lệ thu được tiền ở lần thử lại

NAME_A = ["North", "Blue", "Vertex", "Lumen", "Atlas", "Cobalt", "Orbit", "Sable",
          "Harbor", "Quanta", "Pine", "Cedar", "Iron", "Nova", "Basalt", "Meridian",
          "Helix", "Crown", "Delta", "Ash", "Solstice", "Ridge", "Falcon", "Ember"]
NAME_B = ["Labs", "Systems", "Works", "Group", "Digital", "Analytics", "Cloud",
          "Industries", "Studio", "Solutions", "Partners", "Networks"]


@dataclass
class Account:
    account_id: str
    name: str
    industry: str
    country: str
    employees: int
    channel: str
    signup: date
    plan_id: str
    seats: int
    health: float
    mrr: float
    tenure: int = 0
    failed_streak: int = 0


# =============================================================================
# HÀM PHỤ
# =============================================================================
def _weighted(rng: random.Random, pairs) -> str:
    items, weights = zip(*pairs)
    return rng.choices(items, weights=weights, k=1)[0]


def _months(start: str, end: str) -> list[tuple[int, int]]:
    y, m = int(start[:4]), int(start[5:7])
    y_end, m_end = int(end[:4]), int(end[5:7])
    out: list[tuple[int, int]] = []
    while (y, m) <= (y_end, m_end):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _initial_plan(employees: int, rng: random.Random) -> Plan:
    if employees < 20:
        tier = rng.choices(["starter", "growth", "business"], [60, 33, 7])[0]
    elif employees < 100:
        tier = rng.choices(["starter", "growth", "business"], [22, 50, 28])[0]
    elif employees < 500:
        tier = rng.choices(["growth", "business", "enterprise"], [25, 50, 25])[0]
    else:
        tier = rng.choices(["business", "enterprise"], [35, 65])[0]
    return PLAN_BY_ID[f"PLAN-{tier.upper()}"]


def _initial_seats(plan: Plan, employees: int, npr: np.random.Generator) -> int:
    adoption = PLAN_ADOPTION[plan.tier]
    seats = int(round(employees * adoption * float(npr.uniform(0.6, 1.4))))
    return max(plan.included_seats, min(500, seats))


def _tenure_factor(tenure: int) -> float:
    if tenure <= 2:
        return 2.0          # vực thẳm onboarding
    if tenure <= 6:
        return 1.35
    if tenure <= 12:
        return 0.95
    return 0.55


def _churn_reason(rng: random.Random, active_days: int, satisfaction: list[int]) -> str:
    weights = dict(CHURN_REASONS)
    if active_days < 8:
        weights["no_longer_needed"] += 18
    if satisfaction and sum(satisfaction) / len(satisfaction) <= 3.0:
        weights["poor_support"] += 15
    items = list(weights)
    return rng.choices(items, weights=[weights[i] for i in items], k=1)[0]


# =============================================================================
# MÔ PHỎNG
# =============================================================================
def main() -> None:
    force_utf8_stdout()
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    rng = random.Random(RANDOM_SEED)
    npr = np.random.default_rng(RANDOM_SEED)

    months = _months(SIM_START, SIM_END)

    accounts: list[Account] = []
    events: list[dict] = []
    invoices: list[dict] = []
    usage_rows: list[dict] = []
    tickets: list[dict] = []

    active: dict[str, Account] = {}
    acct_seq = evt_seq = inv_seq = tck_seq = 0

    print("=" * 74)
    print("SINH DỮ LIỆU SAAS MÔ PHỎNG (GIAI ĐOẠN 1)")
    print("=" * 74)
    print(f"Khung thời gian: {SIM_START} → {SIM_END}  ({len(months)} tháng)")
    print(f"Seed: {RANDOM_SEED}\n")

    for m_idx, (year, month) in enumerate(months):
        month_start = date(year, month, 1)
        month_end = _last_day(year, month)

        # ---------------- 1. Khách mới ----------------
        base_new = 14 + 1.5 * m_idx
        n_new = max(3, int(round(npr.normal(base_new * SEASONAL[month], base_new * 0.12))))

        for _ in range(n_new):
            acct_seq += 1
            employees = int(max(5, min(20000, npr.lognormal(4.2, 1.1))))
            plan = _initial_plan(employees, rng)
            seats = _initial_seats(plan, employees, npr)
            acc = Account(
                account_id=f"ACC-{acct_seq:05d}",
                name=f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}",
                industry=_weighted(rng, INDUSTRIES),
                country=_weighted(rng, COUNTRIES),
                employees=employees,
                channel=_weighted(rng, CHANNELS),
                signup=month_start,
                plan_id=plan.plan_id,
                seats=seats,
                health=float(npr.beta(2.2, 1.8)),
                mrr=plan.monthly_price(seats),
            )
            accounts.append(acc)
            active[acc.account_id] = acc

            evt_seq += 1
            events.append({
                "event_id": f"EVT-{evt_seq:06d}",
                "account_id": acc.account_id,
                "event_date": month_start.isoformat(),
                "event_type": EVT_NEW,
                "from_plan_id": "",
                "to_plan_id": acc.plan_id,
                "seats_delta": acc.seats,
                "mrr_delta": acc.mrr,
                "reason": "",
            })

        # ---------------- 2. Xử lý từng tài khoản đang hoạt động ----------------
        to_churn: list[tuple[Account, str]] = []

        for acc in list(active.values()):
            acc.tenure += 1
            plan = PLAN_BY_ID[acc.plan_id]

            # --- Mức sử dụng
            ratio = float(np.clip(acc.health * PLAN_USAGE[plan.tier] + npr.normal(0, 0.10), 0.02, 1.0))
            active_days = int(round(30 * ratio))
            # Tỷ lệ lấp ghế phải tương quan với cường độ sử dụng, nếu không thì
            # "ghế trống" chẳng nói lên điều gì về sức khoẻ tài khoản.
            util = float(np.clip(0.35 + 0.55 * ratio + npr.normal(0, 0.06), 0.10, 1.0))
            seats_active = min(acc.seats, max(1, int(round(acc.seats * util))))
            seat_util = seats_active / acc.seats
            features_used = int(min(12, max(1, round(ratio * 12 + npr.normal(0, 1)))))
            api_calls = int(max(0, npr.lognormal(5 + 2 * ratio, 0.6)))

            usage_rows.append({
                "account_id": acc.account_id,
                "month": month_start.isoformat(),
                "active_days": active_days,
                "seats_active": seats_active,
                "features_used": features_used,
                "api_calls": api_calls,
            })

            # --- Ticket hỗ trợ
            rate = PLAN_TICKET_RATE[plan.tier] * (1.8 if acc.tenure <= 2 else 1.0)
            satisfaction: list[int] = []
            for _ in range(int(npr.poisson(rate))):
                tck_seq += 1
                prio = _weighted(rng, PRIORITIES)
                base_h = {"low": 9.0, "medium": 5.0, "high": 3.0, "urgent": 1.2}[prio]
                if rng.random() < 0.06:
                    # 6% ticket bị leo thang: xử lý kéo dài 2–7 ngày
                    resolution = round(float(npr.uniform(48, 168)), 1)
                else:
                    resolution = round(float(max(0.2, npr.lognormal(np.log(base_h), 0.7))), 1)
                # Điểm hài lòng giảm dần theo thời gian chờ
                mean_sat = 4.5 - 0.9 * float(np.log1p(resolution / 8.0))
                sat = int(min(5, max(1, round(float(npr.normal(mean_sat, 0.6))))))
                satisfaction.append(sat)
                tickets.append({
                    "ticket_id": f"TCK-{tck_seq:06d}",
                    "account_id": acc.account_id,
                    "opened_at": month_start.isoformat(),
                    "priority": prio,
                    "category": _weighted(rng, TICKET_CATEGORIES),
                    "resolution_hours": resolution,
                    "satisfaction": sat,
                })

            # --- Nâng cấp gói
            upgraded = False
            if acc.tenure >= 2 and plan.tier in NEXT_TIER and seat_util >= SEAT_UTIL_EXPAND \
                    and ratio >= 0.55 and npr.random() < 0.18:
                new_plan = PLAN_BY_ID[f"PLAN-{NEXT_TIER[plan.tier].upper()}"]
                old_mrr, old_plan_id = acc.mrr, acc.plan_id
                acc.plan_id = new_plan.plan_id
                acc.seats = max(acc.seats, new_plan.included_seats)
                acc.mrr = new_plan.monthly_price(acc.seats)
                evt_seq += 1
                events.append({
                    "event_id": f"EVT-{evt_seq:06d}",
                    "account_id": acc.account_id,
                    "event_date": month_start.isoformat(),
                    "event_type": EVT_UPGRADE,
                    "from_plan_id": old_plan_id,
                    "to_plan_id": new_plan.plan_id,
                    "seats_delta": 0,
                    "mrr_delta": round(acc.mrr - old_mrr, 2),
                    "reason": "",
                })
                upgraded = True
                plan = new_plan

            # --- Mua thêm ghế
            if not upgraded and seat_util >= SEAT_UTIL_EXPAND and acc.tenure >= 2 \
                    and npr.random() < 0.42:
                add = max(1, int(round(acc.seats * float(npr.uniform(0.08, 0.24)))))
                old_mrr = acc.mrr
                acc.seats = min(600, acc.seats + add)
                acc.mrr = plan.monthly_price(acc.seats)
                evt_seq += 1
                events.append({
                    "event_id": f"EVT-{evt_seq:06d}",
                    "account_id": acc.account_id,
                    "event_date": month_start.isoformat(),
                    "event_type": EVT_SEAT_ADD,
                    "from_plan_id": acc.plan_id,
                    "to_plan_id": acc.plan_id,
                    "seats_delta": add,
                    "mrr_delta": round(acc.mrr - old_mrr, 2),
                    "reason": "",
                })

            # --- Cắt bớt ghế
            elif seat_util <= SEAT_UTIL_SHRINK and acc.tenure >= 3 and acc.seats > plan.included_seats \
                    and npr.random() < 0.035:
                remove = min(max(1, int(round(acc.seats * float(npr.uniform(0.05, 0.15))))),
                             acc.seats - plan.included_seats)
                if remove > 0:
                    old_mrr = acc.mrr
                    acc.seats -= remove
                    acc.mrr = plan.monthly_price(acc.seats)
                    evt_seq += 1
                    events.append({
                        "event_id": f"EVT-{evt_seq:06d}",
                        "account_id": acc.account_id,
                        "event_date": month_start.isoformat(),
                        "event_type": EVT_SEAT_REMOVE,
                        "from_plan_id": acc.plan_id,
                        "to_plan_id": acc.plan_id,
                        "seats_delta": -remove,
                        "mrr_delta": round(acc.mrr - old_mrr, 2),
                        "reason": "",
                    })

            # --- Hạ gói
            elif acc.tenure >= 6 and plan.tier in PREV_TIER and ratio < 0.35 and npr.random() < 0.010:
                new_plan = PLAN_BY_ID[f"PLAN-{PREV_TIER[plan.tier].upper()}"]
                old_mrr, old_plan_id = acc.mrr, acc.plan_id
                acc.plan_id = new_plan.plan_id
                acc.seats = max(new_plan.included_seats, acc.seats)
                acc.mrr = new_plan.monthly_price(acc.seats)
                evt_seq += 1
                events.append({
                    "event_id": f"EVT-{evt_seq:06d}",
                    "account_id": acc.account_id,
                    "event_date": month_start.isoformat(),
                    "event_type": EVT_DOWNGRADE,
                    "from_plan_id": old_plan_id,
                    "to_plan_id": new_plan.plan_id,
                    "seats_delta": 0,
                    "mrr_delta": round(acc.mrr - old_mrr, 2),
                    "reason": "",
                })
                plan = new_plan

            # --- Hoá đơn
            inv_seq += 1
            if acc.failed_streak > 0:
                if npr.random() < RETRY_SUCCESS:
                    status = "paid"
                    acc.failed_streak = 0
                else:
                    status = "failed"
                    acc.failed_streak += 1
            elif npr.random() < FAIL_RATE:
                status = "failed"
                acc.failed_streak = 1
            else:
                status = "paid"

            invoices.append({
                "invoice_id": f"INV-{inv_seq:06d}",
                "account_id": acc.account_id,
                "invoice_date": month_start.isoformat(),
                "period_start": month_start.isoformat(),
                "period_end": month_end.isoformat(),
                "plan_id": acc.plan_id,
                "seats_billed": acc.seats,
                "amount": acc.mrr,
                "status": status,
                "payment_method": _weighted(rng, PAYMENT_METHODS),
            })

            # --- Huỷ do thanh toán thất bại 2 tháng liên tiếp
            if acc.failed_streak >= 2:
                to_churn.append((acc, "payment_failed"))
                continue

            # --- Huỷ tự nguyện
            hazard = BASE_CHURN * PLAN_CHURN[plan.tier] * CHANNEL_CHURN[acc.channel]
            hazard *= _tenure_factor(acc.tenure)
            if active_days < 5:
                hazard *= 2.0
            elif active_days < 10:
                hazard *= 1.4
            if satisfaction and min(satisfaction) <= 2:
                hazard *= 1.9      # trải nghiệm hỗ trợ tệ làm tăng rủi ro rời bỏ
            if satisfaction and sum(satisfaction) / len(satisfaction) <= 3.0:
                hazard *= 1.4
            hazard = min(0.30, max(0.002, hazard))

            if npr.random() < hazard:
                to_churn.append((acc, _churn_reason(rng, active_days, satisfaction)))

        # ---------------- 3. Ghi nhận huỷ ----------------
        for acc, reason in to_churn:
            evt_seq += 1
            events.append({
                "event_id": f"EVT-{evt_seq:06d}",
                "account_id": acc.account_id,
                "event_date": month_start.isoformat(),
                "event_type": EVT_CHURN,
                "from_plan_id": acc.plan_id,
                "to_plan_id": "",
                "seats_delta": -acc.seats,
                "mrr_delta": -acc.mrr,
                "reason": reason,
            })
            active.pop(acc.account_id, None)

    # ---------------- 4. Ghi CSV ----------------
    accounts_df = pd.DataFrame([{
        "account_id": a.account_id,
        "account_name": a.name,
        "industry": a.industry,
        "country": a.country,
        "employees": a.employees,
        "acquisition_channel": a.channel,
        "signup_date": a.signup.isoformat(),
        "initial_plan_id": a.plan_id if a.signup else "",
    } for a in accounts])

    # plan ban đầu phải lấy từ sự kiện "new", không phải plan hiện tại
    first_plan = {e["account_id"]: e["to_plan_id"] for e in events if e["event_type"] == EVT_NEW}
    accounts_df["initial_plan_id"] = accounts_df["account_id"].map(first_plan)

    plans_df = pd.DataFrame([{
        "plan_id": p.plan_id,
        "plan_name": p.plan_name,
        "tier": p.tier,
        "base_price": p.base_price,
        "included_seats": p.included_seats,
        "price_per_seat": p.price_per_seat,
    } for p in PLANS])

    files = {
        "accounts.csv": accounts_df,
        "plans.csv": plans_df,
        "subscription_events.csv": pd.DataFrame(events),
        "invoices.csv": pd.DataFrame(invoices),
        "monthly_usage.csv": pd.DataFrame(usage_rows),
        "support_tickets.csv": pd.DataFrame(tickets),
    }

    print(f"{'File':<26}{'Dòng':>10}{'Cột':>6}")
    print("-" * 42)
    for fname, df in files.items():
        df.to_csv(DATA_RAW / fname, index=False, encoding="utf-8")
        print(f"{fname:<26}{len(df):>10,}{df.shape[1]:>6}")

    print("-" * 42)
    print(f"Tổng: {sum(len(d) for d in files.values()):,} dòng\n")
    print(f"Tài khoản cuối kỳ: {len(active):,} / {len(accounts):,} đã đăng ký")
    print(f"MRR cuối kỳ      : ${sum(a.mrr for a in active.values()):,.0f}")
    print(f"\nBước tiếp theo: python -m src.etl.build_db")


if __name__ == "__main__":
    main()
