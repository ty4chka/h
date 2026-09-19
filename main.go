package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"hydra-go/internal/tui"
)

func main() {
	fmt.Fprintln(os.Stderr, "Starting Hydra v5.0 Go Edition...")

	p := tea.NewProgram(
		tui.NewApp(),
		tea.WithAltScreen(),
		tea.WithMouseCellMotion(),
	)

	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
