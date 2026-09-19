package tabs

import (
	"fmt"
	"os"

	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/accounts"
	"hydra-go/internal/theme"
)

type AccountsState struct {
	Selected int
}

func AccountsView(m *accounts.Manager, state *AccountsState, width int) string {
	t := theme.Get()
	names := m.List()
	if len(names) == 0 {
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			"No accounts yet\n\nGo to tab [4] Add Account to add your first account",
		)
	}

	var lines []string
	for i, name := range names {
		acc := m.Accounts[name]
		marker := "  "
		if i == state.Selected { marker = "▶ " }

		sessionExists := false
		if _, err := os.Stat(acc.Session + ".session"); err == nil { sessionExists = true }

		status := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Red)).Render("MISSING")
		if sessionExists { status = lipgloss.NewStyle().Foreground(lipgloss.Color(t.Green)).Render("READY") }

		star := "☆"
		if acc.Favorite { star = "★" }

		methodColor := t.Comment
		if acc.LoginMethod == "qr" { methodColor = t.Cyan }

		line := fmt.Sprintf("%s %s %s | phone: %s | user: @%s | method: %s | %s",
			marker, star, name, acc.Phone, acc.Username,
			lipgloss.NewStyle().Foreground(lipgloss.Color(methodColor)).Render(acc.LoginMethod),
			status,
		)
		lines = append(lines, line)
	}

	selectedName := ""
	if state.Selected < len(names) { selectedName = names[state.Selected] }

	content := lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
		lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Accounts Dashboard") + "\n\n" +
			lipgloss.JoinVertical(lipgloss.Left, lines...) + "\n\n" +
			"Selected: " + lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render(selectedName) + "\n" +
			"l/ENTER: launch | d: delete | f: favorite | b: backup",
	)
	return content
}
