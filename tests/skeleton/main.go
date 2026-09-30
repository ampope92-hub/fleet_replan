// Pay run tool. See SPEC.md beside this file for the rules.
//
// Build and run with:  cd /app/payroll && go build -o payroll . && ./payroll
package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Fprintln(os.Stderr, "payroll: not implemented")
	os.Exit(1)
}
