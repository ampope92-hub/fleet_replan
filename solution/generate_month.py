"""Pay run export generator.

Writes one month of runs, the drivers on the book and the tariff for a seed. The shipped month is
seed 0; the held-back month the verifier bakes in is seed 2 with a different tariff, so figures
worked out once and written into the source come out wrong on it.

Every rule in SPEC.md has rows here that sit on its boundary, because a rule that never bites is
a rule that cannot be graded: runs exactly on a quarter hour and one thousandth past it, a run
exactly at the band limit, single-drop runs, a run exactly at the long-run threshold, drivers who
cross the weekly cap mid-run with two runs on the same date, Sunday and Monday starts either side
of a week boundary, both kinds of cancellation, drivers with no runs, and runs for drivers who are
not on the book.

    python3 generate_month.py [seed]     writes environment/data/  (seed 0)
    python3 generate_month.py 2 holdout  writes tests/holdout/
"""
import csv
import datetime as dt
import json
import pathlib
import random
import sys

TARIFFS = {
    0: {"quarter_hour_pence": 375, "drop_pence": 450, "band_a_max_km": 50.0, "band_a_km_pence": 42,
        "band_b_km_pence": 36, "long_run_hours": 12.0, "long_run_pence": 2600, "fuel_percent": 7.5,
        "weekly_cap_hours": 56.0, "cancel_after_pence": 1800},
    2: {"quarter_hour_pence": 410, "drop_pence": 300, "band_a_max_km": 60.0, "band_a_km_pence": 45,
        "band_b_km_pence": 38, "long_run_hours": 10.0, "long_run_pence": 3000, "fuel_percent": 6.2,
        "weekly_cap_hours": 48.0, "cancel_after_pence": 1500},
}
MONTHS = {0: (2026, 7), 2: (2026, 9)}


def month_days(year, month):
    first = dt.date(year, month, 1)
    nxt = dt.date(year + (month == 12), (month % 12) + 1, 1)
    return [first + dt.timedelta(days=i) for i in range((nxt - first).days)]


def build(seed):
    rng = random.Random(seed)
    year, month = MONTHS.get(seed, (2026, 7))
    days = month_days(year, month)
    tariff = TARIFFS.get(seed, TARIFFS[0])
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    drivers = sorted({f"D{rng.randint(100, 999):03d}{rng.choice(letters)}" for _ in range(rng.randint(38, 44))})
    idle = set(rng.sample(drivers, 3))          # on the book, no runs at all
    strangers = [f"X{rng.randint(10, 99)}Z" for _ in range(2)]   # not on the book

    rows = []
    def add(driver, day, km, drops, hours, status="completed"):
        rows.append({"driver_id": driver, "start_date": day, "distance_km": round(km, 2),
                     "drops": drops, "transit_hours": round(hours, 3), "status": status})

    working = [d for d in drivers if d not in idle]
    for d in working:
        n = rng.randint(6, 16)
        for _ in range(n):
            day = rng.choice(days)
            km = min(max(rng.gauss(55, 22), 5.0), 240.0)
            drops = rng.randint(1, 12)
            hours = min(max(rng.gauss(0.55 * km / 4 + 0.6 * drops + 5, 3.0), 1.0), 60.0)
            r = rng.random()
            status = "completed" if r < 0.9 else ("cancelled_after" if r < 0.95 else "cancelled_before")
            add(d, day, km, drops, hours, status)

    # boundary rows, on drivers who are on the book
    d1, d2, d3, d4 = rng.sample(working, 4)
    add(d1, days[3], 30.00, 4, 7.250)                       # exactly on a quarter
    add(d1, days[3], 30.00, 4, 7.251)                       # one thousandth over
    add(d1, days[4], 30.00, 4, 7.100)                       # rounds up to 7.25
    add(d2, days[5], tariff["band_a_max_km"], 2, 9.0)       # exactly at the band limit
    add(d2, days[5], tariff["band_a_max_km"] + 0.01, 2, 9.0)  # just over it
    add(d2, days[6], 44.00, 1, 8.0)                          # one drop: no drop pay
    add(d3, days[8], 120.00, 6, tariff["long_run_hours"])    # exactly at the long-run line
    add(d3, days[8], 120.00, 6, tariff["long_run_hours"] - 0.001)
    add(d3, days[9], 61.00, 3, 4.0, "cancelled_after")
    add(d3, days[9], 61.00, 3, 4.0, "cancelled_before")
    # a driver who crosses the weekly cap inside one run, with two runs on the same date
    monday = next(x for x in days if x.weekday() == 0 and x.day > 7)
    add(d4, monday, 150.00, 5, 20.0)
    add(d4, monday + dt.timedelta(days=1), 150.00, 5, 20.0)
    add(d4, monday + dt.timedelta(days=2), 150.00, 5, 15.0)   # crosses the cap
    add(d4, monday + dt.timedelta(days=2), 40.00, 2, 6.0)     # same date, settles by run_id
    add(d4, monday + dt.timedelta(days=6), 40.00, 2, 6.0)     # Sunday: still this week
    add(d4, monday + dt.timedelta(days=7), 40.00, 2, 6.0)     # Monday: next week, cap resets
    for s in strangers:
        add(s, rng.choice(days), 70.00, 3, 10.0)
        add(s, rng.choice(days), 70.00, 3, 10.0, "cancelled_after")

    rng.shuffle(rows)
    for i, r in enumerate(rows):
        r["run_id"] = f"R{i:05d}"
    rows.sort(key=lambda r: r["run_id"])
    return drivers, rows, tariff


def write(out, drivers, rows, tariff):
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "runs.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "driver_id", "start_date", "distance_km", "drops", "transit_hours", "status"])
        for r in rows:
            w.writerow([r["run_id"], r["driver_id"], r["start_date"].isoformat(), f"{r['distance_km']:.2f}",
                        r["drops"], f"{r['transit_hours']:.3f}", r["status"]])
    with open(out / "drivers.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["driver_id"])
        for d in drivers:
            w.writerow([d])
    with open(out / "tariff.json", "w") as fh:
        json.dump(tariff, fh, indent=2)
        fh.write("\n")


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    root = pathlib.Path(__file__).resolve().parent.parent
    out = root / ("tests/holdout" if len(sys.argv) > 2 and sys.argv[2] == "holdout" else "environment/data")
    drivers, rows, tariff = build(seed)
    write(out, drivers, rows, tariff)
    print(f"seed {seed}: {len(rows)} runs, {len(drivers)} drivers -> {out}")


if __name__ == "__main__":
    main()
