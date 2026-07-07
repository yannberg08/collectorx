//go:build !windows

package main

import "os"

// openShared on non-Windows is a plain open; these OSes use advisory locks, so
// reading the Cookies DB while Doubao runs is fine.
func openShared(path string) (*os.File, error) { return os.Open(path) }
