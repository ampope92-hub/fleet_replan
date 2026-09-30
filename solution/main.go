// Pay run for the line-haul owner-drivers. Reads the month's runs, the drivers on the book and
// the tariff, applies the rules in SPEC.md, and writes /app/out/payroll.json.
//
// Everything is integer arithmetic: kilometres in hundredths, hours in thousandths, money in
// pence. Nothing goes through a float, so nothing is rounded twice.
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

type tariff struct {
	QuarterHourPence int     `json:"quarter_hour_pence"`
	DropPence        int     `json:"drop_pence"`
	BandAMaxKm       float64 `json:"band_a_max_km"`
	BandAKmPence     int     `json:"band_a_km_pence"`
	BandBKmPence     int     `json:"band_b_km_pence"`
	LongRunHours     float64 `json:"long_run_hours"`
	LongRunPence     int     `json:"long_run_pence"`
	FuelPercent      float64 `json:"fuel_percent"`
	WeeklyCapHours   float64 `json:"weekly_cap_hours"`
	CancelAfterPence int     `json:"cancel_after_pence"`
}

type run struct {
	id       string
	driver   string
	start    time.Time
	km       int64 // hundredths
	drops    int64
	hours    int64 // thousandths
	status   string
}

type pay struct {
	DriverID          string `json:"driver_id"`
	Runs              int64  `json:"runs"`
	Cancellations     int64  `json:"cancellations"`
	PaidQuarters      int64  `json:"paid_quarters"`
	DrivingPence      int64  `json:"driving_pence"`
	DropPence         int64  `json:"drop_pence"`
	DistancePence     int64  `json:"distance_pence"`
	FuelPence         int64  `json:"fuel_pence"`
	LongRunPence      int64  `json:"long_run_pence"`
	CancellationPence int64  `json:"cancellation_pence"`
	TotalPence        int64  `json:"total_pence"`
}

type report struct {
	Drivers       []*pay `json:"drivers"`
	UnmatchedRuns int64  `json:"unmatched_runs"`
	TotalPence    int64  `json:"total_pence"`
}

// fixed parses a decimal string with at most `places` decimals into an integer scaled by
// 10^places, without going through a float.
func fixed(s string, places int) (int64, error) {
	s = strings.TrimSpace(s)
	neg := strings.HasPrefix(s, "-")
	s = strings.TrimPrefix(s, "-")
	whole, frac, _ := strings.Cut(s, ".")
	if len(frac) > places {
		return 0, fmt.Errorf("%q has more than %d decimal places", s, places)
	}
	for len(frac) < places {
		frac += "0"
	}
	w, err := strconv.ParseInt(whole, 10, 64)
	if err != nil {
		return 0, err
	}
	f := int64(0)
	if places > 0 {
		f, err = strconv.ParseInt(frac, 10, 64)
		if err != nil {
			return 0, err
		}
	}
	v := w
	for i := 0; i < places; i++ {
		v *= 10
	}
	v += f
	if neg {
		v = -v
	}
	return v, nil
}

func halfUp(numerator, denominator int64) int64 {
	return (numerator + denominator/2) / denominator
}

func mondayOf(d time.Time) time.Time {
	back := (int(d.Weekday()) + 6) % 7 // Monday -> 0, Sunday -> 6
	return d.AddDate(0, 0, -back)
}

func readRuns(path string) ([]run, error) {
	fh, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer fh.Close()
	rows, err := csv.NewReader(fh).ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("%s is empty", path)
	}
	col := map[string]int{}
	for i, h := range rows[0] {
		col[strings.TrimSpace(h)] = i
	}
	var out []run
	for _, r := range rows[1:] {
		start, err := time.Parse("2006-01-02", strings.TrimSpace(r[col["start_date"]]))
		if err != nil {
			return nil, err
		}
		km, err := fixed(r[col["distance_km"]], 2)
		if err != nil {
			return nil, err
		}
		drops, err := strconv.ParseInt(strings.TrimSpace(r[col["drops"]]), 10, 64)
		if err != nil {
			return nil, err
		}
		hours, err := fixed(r[col["transit_hours"]], 3)
		if err != nil {
			return nil, err
		}
		out = append(out, run{
			id: strings.TrimSpace(r[col["run_id"]]), driver: strings.TrimSpace(r[col["driver_id"]]),
			start: start, km: km, drops: drops, hours: hours, status: strings.TrimSpace(r[col["status"]]),
		})
	}
	return out, nil
}

func readDrivers(path string) ([]string, error) {
	fh, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer fh.Close()
	rows, err := csv.NewReader(fh).ReadAll()
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	var out []string
	for _, r := range rows[1:] {
		id := strings.TrimSpace(r[0])
		if id != "" && !seen[id] {
			seen[id] = true
			out = append(out, id)
		}
	}
	sort.Strings(out)
	return out, nil
}

func main() {
	var t tariff
	raw, err := os.ReadFile("/app/data/tariff.json")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.Unmarshal(raw, &t); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	drivers, err := readDrivers("/app/data/drivers.csv")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	runs, err := readRuns("/app/data/runs.csv")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	// Tariff figures as integers: the cap and the long-run line in quarters, the band limit in
	// hundredths of a kilometre, the fuel rate in tenths of a percent.
	capQuarters := int64(t.WeeklyCapHours*4 + 0.5)
	longQuarters := int64(t.LongRunHours*4 + 0.5)
	bandAMax := int64(t.BandAMaxKm*100 + 0.5)
	fuelTenths := int64(t.FuelPercent*10 + 0.5)
	q := int64(t.QuarterHourPence)

	acc := map[string]*pay{}
	for _, d := range drivers {
		acc[d] = &pay{DriverID: d}
	}
	var unmatched int64
	var completed []run
	for _, r := range runs {
		p, ok := acc[r.driver]
		if !ok {
			unmatched++
			continue
		}
		switch r.status {
		case "cancelled_before":
		case "cancelled_after":
			p.Cancellations++
			p.CancellationPence += int64(t.CancelAfterPence)
		default:
			completed = append(completed, r)
		}
	}

	// Settle each driver's week in start date order, ties by run_id, so the run that crosses
	// the cap is the right one.
	sort.Slice(completed, func(i, j int) bool {
		a, b := completed[i], completed[j]
		if a.driver != b.driver {
			return a.driver < b.driver
		}
		if !a.start.Equal(b.start) {
			return a.start.Before(b.start)
		}
		return a.id < b.id
	})
	type weekKey struct {
		driver string
		monday string
	}
	used := map[weekKey]int64{}
	for _, r := range completed {
		p := acc[r.driver]
		key := weekKey{r.driver, mondayOf(r.start).Format("2006-01-02")}
		quarters := (r.hours + 249) / 250 // up to the next quarter hour
		room := capQuarters - used[key]
		if room < 0 {
			room = 0
		}
		full := quarters
		if full > room {
			full = room
		}
		over := quarters - full
		used[key] += full
		p.Runs++
		p.PaidQuarters += quarters
		p.DrivingPence += full*q + halfUp(over*q, 2)
		if r.drops > 1 {
			p.DropPence += (r.drops - 1) * int64(t.DropPence)
		}
		rate := int64(t.BandBKmPence)
		if r.km <= bandAMax {
			rate = int64(t.BandAKmPence)
		}
		dist := halfUp(r.km*rate, 100)
		p.DistancePence += dist
		p.FuelPence += halfUp(dist*fuelTenths, 1000)
		if quarters >= longQuarters {
			p.LongRunPence += int64(t.LongRunPence)
		}
	}

	rep := report{UnmatchedRuns: unmatched}
	for _, d := range drivers {
		p := acc[d]
		p.TotalPence = p.DrivingPence + p.DropPence + p.DistancePence + p.FuelPence + p.LongRunPence + p.CancellationPence
		rep.TotalPence += p.TotalPence
		rep.Drivers = append(rep.Drivers, p)
	}
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out, err := json.Marshal(rep)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := os.WriteFile("/app/out/payroll.json", append(out, '\n'), 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("settled %d drivers, %d runs left unmatched\n", len(drivers), unmatched)
}
