package tabs

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/theme"
)

type ThemesState struct {
	Cursor int
}

func ThemesView(state *ThemesState) string {
	t := theme.Get()
	var b strings.Builder
	b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color(t.Blue)).Bold(true).Render("Theme Selector"))
	b.WriteString("\n\n")

	list := theme.List()
	for i, name := range list {
		th := theme.Themes[name]
		cursor := "  "
		if i == state.Cursor { cursor = "▶ " }
		preview := lipgloss.NewStyle().Foreground(lipgloss.Color(th.Blue)).Render("█") +
			lipgloss.NewStyle().Foreground(lipgloss.Color(th.Green)).Render("█") +
			lipgloss.NewStyle().Foreground(lipgloss.Color(th.Red)).Render("█") +
			lipgloss.NewStyle().Foreground(lipgloss.Color(th.Yellow)).Render("█") +
			lipgloss.NewStyle().Foreground(lipgloss.Color(th.Purple)).Render("█")
		marker := lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(cursor)
		if theme.Current == name {
			marker = lipgloss.NewStyle().Foreground(lipgloss.Color(t.Green)).Render(cursor)
		}
		b.WriteString(fmt.Sprintf("%s %-20s %s\n", marker, th.Name, preview))
	}

	b.WriteString("\n")
	b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render("j/k: navigate  ENTER: apply"))
	return b.String()
}
