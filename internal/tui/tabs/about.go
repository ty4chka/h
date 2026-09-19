package tabs

import (
	"fmt"
	"runtime"
	"time"

	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/theme"
)

var aboutStartTime = time.Now()

func AboutView() string {
	t := theme.Get()
	uptime := time.Since(aboutStartTime)
	uptimeStr := fmt.Sprintf("%02d:%02d:%02d", int(uptime.Hours())%24, int(uptime.Minutes())%60, int(uptime.Seconds())%60)

	info := []string{
		lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Hydra UserBot v5.0"),
		"",
		"Edition:    " + lipgloss.NewStyle().Foreground(lipgloss.Color(t.Cyan)).Render("Go + Blocks + TUI"),
		"Go Version: " + runtime.Version(),
		"Platform:   " + runtime.GOOS + "/" + runtime.GOARCH,
		"Uptime:     " + lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Green)).Render(uptimeStr),
		"",
		"Keyboard shortcuts:",
		"  1-6      Switch tabs",
		"  j/k      Navigate",
		"  l/ENTER  Select / Launch",
		"  h        Back",
		"  d        Delete account",
		"  f        Toggle favorite",
		"  b        Create backup",
		"  L        View logs",
		"  c        Clear logs",
		"  r        Refresh / Rescan",
		"  q        Quit",
	}

	return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
		lipgloss.JoinVertical(lipgloss.Left, info...),
	)
}
