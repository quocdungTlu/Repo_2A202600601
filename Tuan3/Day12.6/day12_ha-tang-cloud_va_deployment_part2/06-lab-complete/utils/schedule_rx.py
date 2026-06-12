"""
Schedule builder — port từ prototype/js/schedule.js
"""
from __future__ import annotations
from datetime import date, timedelta

SLOTS: dict[int, list[str]] = {
    1: ["08:00"],
    2: ["08:00", "20:00"],
    3: ["08:00", "14:00", "21:00"],
    4: ["07:00", "12:00", "17:00", "22:00"],
}

_DRUG_MAP = {
    "amox": "amoxicillin-500",
    "para": "paracetamol-500",
    "panadol": "paracetamol-500",
    "omep": "omeprazole-20",
    "vitamin": "vitamin-c-500",
    "vit c": "vitamin-c-500",
    "ceti": "cetirizine-10",
}


def _match_drug_id(name: str) -> str:
    n = (name or "").lower()
    for key, drug_id in _DRUG_MAP.items():
        if key in n:
            return drug_id
    return "unknown"


def build_schedule(rx_lines: list[dict], start_date: date | None = None) -> list[dict]:
    if start_date is None:
        start_date = date.today()

    events: list[dict] = []
    for line in rx_lines:
        freq = min(4, max(1, int(float(line.get("frequency_per_day") or 1))))
        times = SLOTS.get(freq, SLOTS[3])
        days = int(line.get("duration_days") or 7)
        drug_name = line.get("drug_name", "")

        for d in range(days):
            day = start_date + timedelta(days=d)
            date_str = day.isoformat()
            for time_str in times:
                events.append({
                    "date": date_str,
                    "time": time_str,
                    "drug_name": drug_name,
                    "drug_id": _match_drug_id(drug_name),
                    "dose": line.get("dose_per_time", ""),
                    "meal": line.get("meal_relation", ""),
                    "label": f"{drug_name} — {line.get('dose_per_time', '')}",
                })

    events.sort(key=lambda e: e["date"] + e["time"])
    return events


def group_by_date(events: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for e in events:
        result.setdefault(e["date"], []).append(e)
    return result
