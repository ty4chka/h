package tabs

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/lipgloss/table"
	"hydra-go/internal/accounts"
	"hydra-go/internal/logger"
	"hydra-go/internal/theme"
)

type BackupLogsState struct {
	ShowLogs bool
}

func BackupLogsView(accMgr *accounts.Manager, log *logger.Logger, state *BackupLogsState, width int) string {
	t := theme.Get()
	var content string

	if state.ShowLogs {
		lines := log.ReadLast(20)
		content = lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Last Log Entries") + "\n\n" +
				lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render(lipgloss.JoinVertical(lipgloss.Left, lines...)) + "\n\n" +
				"Press q to go back",
		)
		return content
	}

	total := len(accMgr.Accounts)
	backupCount := accMgr.BackupCount()
	logSize := log.Size()
	logSizeStr := fmt.Sprintf("%d B", logSize)
	if logSize > 1024 { logSizeStr = fmt.Sprintf("%.1f KB", float64(logSize)/1024) }

	rows := [][]string{
		{"Total Accounts", fmt.Sprintf("%d", total)},
		{"Backups", fmt.Sprintf("%d", backupCount)},
		{"Log Size", logSizeStr},
		{"Log File", logger.LogFile},
	}

	tbl := table.New().
		Border(lipgloss.NormalBorder()).
		BorderStyle(lipgloss.NewStyle().Foreground(lipgloss.Color(t.Border))).
		StyleFunc(func(row, col int) lipgloss.Style {
			if col == 0 {
				return lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Bold(true).Width(20)
			}
			return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Width(30)
		}).
		Rows(rows...)

	backups := accMgr.Backups()
	var backupLines []string
	if len(backups) == 0 {
		backupLines = append(backupLines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render("  No backups yet"))
	} else {
		for i := len(backups)-1; i >= 0 && i >= len(backups)-5; i-- {
			info, _ := os.Stat(backups[i])
			sizeStr := fmt.Sprintf("%d B", info.Size())
			if info.Size() > 1024 { sizeStr = fmt.Sprintf("%.1f KB", float64(info.Size())/1024) }
			name := filepath.Base(backups[i])
			backupLines = append(backupLines, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Blue)).Render("  "+name)+"  "+lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Render(sizeStr))
		}
	}

	content = lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
		lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Backup & Logs") + "\n\n" +
			tbl.Render() + "\n\n" +
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Purple)).Render("Recent Backups") + "\n" +
			lipgloss.JoinVertical(lipgloss.Left, backupLines...) + "\n\n" +
			"b: create backup | L: view logs | c: clear logs",
	)
	return content
}
