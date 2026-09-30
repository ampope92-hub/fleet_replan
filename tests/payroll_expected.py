"""Independent pay run, in plain Python integers, for the verifier to compare against.

Written from SPEC.md without reference to the Go solution, so the two agree only where the rules
are followed. Every figure is an integer: kilometres are held in hundredths, hours in
thousandths, money in pence.
"""
import csv
import datetime as dt
import json
import os
import pathlib


def _open(path):
    return os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW))


def _hundredths(text):
    whole, _, frac = text.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def _thousandths(text):
    whole, _, frac = text.partition(".")
    return int(whole) * 1000 + int((frac + "000")[:3])


def _tenths(value):
    return round(float(value) * 10)


def _half_up(numerator, denominator):
    return (numerator + denominator // 2) // denominator


def expected(data_dir):
    data_dir = pathlib.Path(data_dir)
    with _open(data_dir / "tariff.json") as fh:
        t = json.load(fh)
    with _open(data_dir / "drivers.csv") as fh:
        drivers = sorted({row["driver_id"] for row in csv.DictReader(fh)})
    with _open(data_dir / "runs.csv") as fh:
        rows = list(csv.DictReader(fh))
    on_book = set(drivers)
    q_rate = int(t["quarter_hour_pence"])
    cap_quarters = round(float(t["weekly_cap_hours"]) * 4)
    long_quarters = round(float(t["long_run_hours"]) * 4)
    band_a_max = _hundredths(f"{float(t['band_a_max_km']):.2f}")
    fuel_tenths = _tenths(t["fuel_percent"])

    acc = {d: {"runs": 0, "cancellations": 0, "paid_quarters": 0, "driving_pence": 0, "drop_pence": 0,
               "distance_pence": 0, "fuel_pence": 0, "long_run_pence": 0, "cancellation_pence": 0}
           for d in drivers}
    unmatched = 0
    completed = []
    for r in rows:
        if r["driver_id"] not in on_book:
            unmatched += 1
            continue
        a = acc[r["driver_id"]]
        if r["status"] == "cancelled_before":
            continue
        if r["status"] == "cancelled_after":
            a["cancellations"] += 1
            a["cancellation_pence"] += int(t["cancel_after_pence"])
            continue
        completed.append(r)

    # settle order: driver, week (Monday-Sunday), start_date, run_id
    def week_of(day):
        return day - dt.timedelta(days=day.weekday())
    used = {}
    for r in sorted(completed, key=lambda r: (r["driver_id"], r["start_date"], r["run_id"])):
        a = acc[r["driver_id"]]
        day = dt.date.fromisoformat(r["start_date"])
        key = (r["driver_id"], week_of(day))
        quarters = -(-_thousandths(r["transit_hours"]) // 250)
        full = min(quarters, max(cap_quarters - used.get(key, 0), 0))
        over = quarters - full
        used[key] = used.get(key, 0) + full
        a["runs"] += 1
        a["paid_quarters"] += quarters
        a["driving_pence"] += full * q_rate + _half_up(over * q_rate, 2)
        a["drop_pence"] += max(int(r["drops"]) - 1, 0) * int(t["drop_pence"])
        km = _hundredths(r["distance_km"])
        rate = int(t["band_a_km_pence"]) if km <= band_a_max else int(t["band_b_km_pence"])
        dist = _half_up(km * rate, 100)
        a["distance_pence"] += dist
        a["fuel_pence"] += _half_up(dist * fuel_tenths, 1000)
        if quarters >= long_quarters:
            a["long_run_pence"] += int(t["long_run_pence"])

    out = []
    for d in drivers:
        a = acc[d]
        a["total_pence"] = (a["driving_pence"] + a["drop_pence"] + a["distance_pence"] + a["fuel_pence"]
                            + a["long_run_pence"] + a["cancellation_pence"])
        out.append({"driver_id": d, **a})
    return {"drivers": out, "unmatched_runs": unmatched, "total_pence": sum(x["total_pence"] for x in out)}


if __name__ == "__main__":
    import sys
    print(json.dumps(expected(sys.argv[1] if len(sys.argv) > 1 else "environment/data"), indent=1))
