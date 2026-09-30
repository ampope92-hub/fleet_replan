# Line-haul pay run export, 2026-07

Three files, one month. `runs.csv` is every run dispatched in the month as our tracker recorded
it, with the door to door hours it took. `drivers.csv` is the owner-drivers on the book for the
month. `tariff.json` is the rates the drivers are contracted at for the month; they change when
the contract is renewed, so the tool has to read them rather than know them.

## Columns of runs.csv

| column | source | description |
|---|---|---|
| `run_id` | dispatch | our reference for the run |
| `driver_id` | dispatch | the driver the run was dispatched to |
| `start_date` | dispatch | the date the run started, `YYYY-MM-DD` |
| `distance_km` | route plan | planned road distance, two decimal places |
| `drops` | route plan | number of delivery stops on the run |
| `transit_hours` | tracker | door to door hours the run took, three decimal places |
| `status` | dispatch | `completed`, `cancelled_before` or `cancelled_after` |

`cancelled_before` means the run was pulled before the driver was dispatched; `cancelled_after`
means the driver had already been sent.

Runs occasionally carry a `driver_id` that is not on the book: agency cover, or a driver who left
mid-month. Those are settled separately and are not part of this pay run.
