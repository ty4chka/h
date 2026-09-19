package tabs

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/modules"
	"hydra-go/internal/theme"
)

type ModulesState struct {
	Selected int
	ViewMode string // "list" or "bat"
	Scroll   int
}

func ModulesView(scanner *modules.Scanner, state *ModulesState, width int) string {
	t := theme.Get()
	mods := scanner.Modules
	if len(mods) == 0 {
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			"No modules found\n\nCheck folders: modules/ and modules/mcub_mods/",
		)
	}

	if state.ViewMode == "bat" && state.Selected < len(mods) {
		mod := mods[state.Selected]
		var lines []string
		lines = append(lines, lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render(mod.Name)+"  v"+mod.Version+"  |  "+mod.Author)
		lines = append(lines, "")
		lines = append(lines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render("File: "+mod.File))
		lines = append(lines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render(fmt.Sprintf("Lines: %d | Size: %d B", mod.Lines, mod.Size)))
		lines = append(lines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow)).Render("Commands: "+fmt.Sprintf("%v", mod.Commands)))
		lines = append(lines, "")
		lines = append(lines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(mod.Description))
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			lipgloss.JoinVertical(lipgloss.Left, lines...) + "\n\nh: back | j/k: scroll",
		)
	}

	var lines []string
	for i, mod := range mods {
		marker := "  "
		if i == state.Selected { marker = "▶ " }
		color := t.Green
		if mod.Type == "MCUB" { color = t.Cyan }
		cmdCount := len(mod.Commands)
		sizeStr := fmt.Sprintf("%d B", mod.Size)
		if mod.Size > 1024 { sizeStr = fmt.Sprintf("%.1f KB", float64(mod.Size)/1024) }
		line := fmt.Sprintf("%s%s  %s  v%s  %s  cmds:%d  %s",
			marker,
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.FG)).Render(mod.Name),
			lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Render(mod.Type),
			mod.Version, mod.Author, cmdCount, sizeStr,
		)
		lines = append(lines, line)
	}

	selected := ""
	if state.Selected < len(mods) { selected = mods[state.Selected].Name }

	return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
		lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Module Scanner") + "\n\n" +
			lipgloss.JoinVertical(lipgloss.Left, lines...) + "\n\n" +
			"Selected: " + lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render(selected) + "\n" +
			"l/ENTER: bat view | r: rescan | h: back",
	)
}
