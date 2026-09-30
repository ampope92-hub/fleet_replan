# Driver pay run

`payroll` reads `/app/data/runs.csv`, `/app/data/drivers.csv` and `/app/data/tariff.json` and
writes `/app/out/payroll.json`. Every money figure in the output is a whole number of pence and
every hours figure is a whole number of quarter hours. There are no decimals anywhere in it.

## Input

`runs.csv` has a header line and one row per run: `run_id`, `driver_id`, `start_date` as
`YYYY-MM-DD`, `distance_km` with two decimal places, `drops` as a whole number, `transit_hours`
with three decimal places, and `status`, which is `completed`, `cancelled_before` or
`cancelled_after`.

`drivers.csv` has a header line and one `driver_id` per row: the drivers on the book this month.

`tariff.json` is one object. `quarter_hour_pence` is the driving rate per quarter hour.
`drop_pence` is the rate per paid drop. `band_a_max_km` is the longest run that is charged at
`band_a_km_pence` per kilometre; anything longer is charged at `band_b_km_pence`. `long_run_hours`
is the paid length from which a run earns `long_run_pence`. `fuel_percent` has at most one decimal
place. `weekly_cap_hours` is the cap on full-rate driving in a week. `cancel_after_pence` is what a
late cancellation pays. Every `_pence` value is a whole number of pence. `band_a_max_km` has two
decimal places, the same as a run's distance. `long_run_hours` and `weekly_cap_hours` are whole
quarter hours, so a multiple of `0.25`.

## Output

One JSON object with three keys. `drivers` is an array with one object per driver in
`drivers.csv`, sorted by `driver_id` ascending as text, whether or not the driver had any runs.
`unmatched_runs` is a count. `total_pence` is the sum of every driver's `total_pence`.

Each driver object has the keys `driver_id`, `runs`, `cancellations`, `paid_quarters`,
`driving_pence`, `drop_pence`, `distance_pence`, `fuel_pence`, `long_run_pence`,
`cancellation_pence` and `total_pence`. All but `driver_id` are whole numbers, and `total_pence`
is the sum of the six `_pence` components above it.

## The rules

Each rule is written out because more than one reasonable reading exists. The pay run is graded
on these and on nothing else.

**Which rows count.** A row whose `driver_id` is not in `drivers.csv` is left out of the pay run
entirely, whatever its status, and counted once in `unmatched_runs`. A `cancelled_before` row is
ignored: it pays nothing and is not counted anywhere. A `cancelled_after` row pays
`cancel_after_pence` into `cancellation_pence`, counts once in `cancellations`, and contributes
nothing else, no hours, no drops, no distance. A `completed` row counts once in `runs` and is
paid as below.

**Paid hours.** A completed run's `transit_hours` is rounded up to the next quarter hour. A run
that already sits exactly on a quarter stays there. `7.100` pays 29 quarters, `7.250` pays 29,
`7.251` pays 30. `paid_quarters` is the sum over the driver's completed runs.

**Driving pay and the weekly cap.** Weeks run Monday to Sunday and a run belongs to the week of
its `start_date`. Within a driver's week the runs are settled in `start_date` order, ties broken
by `run_id` ascending as text. The first `weekly_cap_hours` times four quarters in a week pay
`quarter_hour_pence` each. Every quarter after that pays half the rate. A run that crosses the
cap is split: the quarters up to the cap at the full rate, the rest at half. The half-rate part
of a run is rounded to the nearest penny, halves up, on its own. `driving_pence` is the sum.

**Drops.** The first drop of a run is part of the run. Each drop beyond the first pays
`drop_pence`. A run with one drop pays nothing here.

**Distance.** A run of `band_a_max_km` or less, at or under, is charged for its whole distance at
`band_a_km_pence`; a longer run is charged for its whole distance at `band_b_km_pence`. The band
covers the whole run, it is not a marginal rate. Multiply the kilometres by the rate and round to
the nearest penny, halves up, per run.

**Fuel.** `fuel_percent` of the run's distance pence, and of nothing else, rounded to the nearest
penny, halves up, per run.

**Long runs.** A completed run whose paid quarters come to `long_run_hours` times four or more,
at or over, pays `long_run_pence` once.

**Rounding.** Every rounding above happens per run on the component being rounded, and the
driver's totals are sums of those rounded figures. Nothing is rounded twice.
