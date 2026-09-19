package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/accounts"
	"hydra-go/internal/logger"
	"hydra-go/internal/modules"
	"hydra-go/internal/theme"
	"hydra-go/internal/tui/blocks"
	"hydra-go/internal/tui/tabs"
)

type App struct {
	Width     int
	Height    int
	ActiveTab int
	Tabs      []string

	AccMgr        *accounts.Manager
	ModScanner    *modules.Scanner
	Log           *logger.Logger

	Editor          tea.Model
	AccountsState   tabs.AccountsState
	AddAccountState tabs.AddAccountState
	ThemesState     tabs.ThemesState
	BackupLogsState tabs.BackupLogsState
	ModulesState    tabs.ModulesState

	Notification string
}

func NewApp() App {
	return App{
		Tabs:            []string{"Dashboard", "Blocks", "Accounts", "Add Acc", "Themes", "Backup", "Modules", "About"},
		ActiveTab:       0,
		AccMgr:          accounts.NewManager(),
		ModScanner:      modules.NewScanner(),
		Log:             logger.New(),
		Editor:          blocks.NewEditor(),
		AccountsState:   tabs.AccountsState{},
		AddAccountState: tabs.NewAddAccountState(),
		ThemesState:     tabs.ThemesState{},
		BackupLogsState: tabs.BackupLogsState{},
		ModulesState:    tabs.ModulesState{ViewMode: "list"},
	}
}

func (a App) Init() tea.Cmd { return nil }

func (a App) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		return a.handleKey(msg)
	case tea.WindowSizeMsg:
		a.Width = msg.Width
		a.Height = msg.Height
		if ed, ok := a.Editor.(interface{ SetSize(int, int) }); ok {
			ed.SetSize(msg.Width, msg.Height-6)
		}
	}

	// Pass to editor if on Blocks tab
	if a.ActiveTab == 1 {
		var cmd tea.Cmd
		a.Editor, cmd = a.Editor.Update(msg)
		return a, cmd
	}

	return a, nil
}

func (a App) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	// Global keys
	switch {
	case key.Matches(msg, key.NewBinding(key.WithKeys("ctrl+c", "ctrl+q"))):
		return a, tea.Quit
	case key.Matches(msg, key.NewBinding(key.WithKeys("1"))): a.ActiveTab = 0
	case key.Matches(msg, key.NewBinding(key.WithKeys("2"))): a.ActiveTab = 1
	case key.Matches(msg, key.NewBinding(key.WithKeys("3"))): a.ActiveTab = 2
	case key.Matches(msg, key.NewBinding(key.WithKeys("4"))): a.ActiveTab = 3
	case key.Matches(msg, key.NewBinding(key.WithKeys("5"))): a.ActiveTab = 4
	case key.Matches(msg, key.NewBinding(key.WithKeys("6"))): a.ActiveTab = 5
	case key.Matches(msg, key.NewBinding(key.WithKeys("7"))): a.ActiveTab = 6
	case key.Matches(msg, key.NewBinding(key.WithKeys("8"))): a.ActiveTab = 7
	case key.Matches(msg, key.NewBinding(key.WithKeys("tab", "l", "right"))):
		if a.ActiveTab < len(a.Tabs)-1 { a.ActiveTab++ }
	case key.Matches(msg, key.NewBinding(key.WithKeys("shift+tab", "h", "left"))):
		if a.ActiveTab > 0 { a.ActiveTab-- }
	default:
		// Tab-specific keys
		return a.handleTabKey(msg)
	}
	return a, nil
}

func (a App) handleTabKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch a.ActiveTab {
	case 2: // Accounts
		names := a.AccMgr.List()
		switch {
		case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))):
			if a.AccountsState.Selected < len(names)-1 { a.AccountsState.Selected++ }
		case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))):
			if a.AccountsState.Selected > 0 { a.AccountsState.Selected-- }
		case key.Matches(msg, key.NewBinding(key.WithKeys("d"))):
			if len(names) > 0 && a.AccountsState.Selected < len(names) {
				a.AccMgr.Remove(names[a.AccountsState.Selected])
				a.Notification = "Account deleted"
				if a.AccountsState.Selected >= len(a.AccMgr.List()) { a.AccountsState.Selected = len(a.AccMgr.List()) - 1 }
				if a.AccountsState.Selected < 0 { a.AccountsState.Selected = 0 }
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("f"))):
			if len(names) > 0 && a.AccountsState.Selected < len(names) {
				isFav := a.AccMgr.ToggleFavorite(names[a.AccountsState.Selected])
				if isFav { a.Notification = "Starred" } else { a.Notification = "Unstarred" }
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("b"))):
			a.AccMgr.Save()
			a.Notification = fmt.Sprintf("Backup created! (%d total)", a.AccMgr.BackupCount())
		case key.Matches(msg, key.NewBinding(key.WithKeys("enter", "l"))):
			if len(names) > 0 && a.AccountsState.Selected < len(names) {
				a.AccMgr.UpdateLastUsed(names[a.AccountsState.Selected])
				a.Notification = "Launching " + names[a.AccountsState.Selected]
			}
		}
	case 3: // Add Account
		switch a.AddAccountState.Step {
		case 0: // Method select
			switch {
			case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))):
				if a.AddAccountState.Method < 1 { a.AddAccountState.Method++ }
			case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))):
				if a.AddAccountState.Method > 0 { a.AddAccountState.Method-- }
			case key.Matches(msg, key.NewBinding(key.WithKeys("enter", "l"))):
				a.AddAccountState.Step = 1
			}
		case 1: // Name input
			// In real app would use textinput bubble
			a.AddAccountState.Step = 2
		case 2: // Phone input
			a.AddAccountState.Step = 3
		case 3: // Code input
			// Mock add
			method := "classic"
			if a.AddAccountState.Method == 1 { method = "qr" }
			a.AccMgr.Add(a.AddAccountState.Name, a.AddAccountState.Phone, "hydra_"+a.AddAccountState.Name, "", "", method)
			a.Notification = "Account added!"
			a.AddAccountState = tabs.NewAddAccountState()
			a.ActiveTab = 2
		}
	case 4: // Themes
		list := theme.List()
		switch {
		case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))):
			if a.ThemesState.Cursor < len(list)-1 { a.ThemesState.Cursor++ }
		case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))):
			if a.ThemesState.Cursor > 0 { a.ThemesState.Cursor-- }
		case key.Matches(msg, key.NewBinding(key.WithKeys("enter", "l"))):
			if a.ThemesState.Cursor < len(list) {
				theme.Set(list[a.ThemesState.Cursor])
				a.Notification = "Theme: " + theme.Get().Name
			}
		}
	case 5: // Backup & Logs
		switch {
		case key.Matches(msg, key.NewBinding(key.WithKeys("b"))):
			a.AccMgr.Save()
			a.Notification = fmt.Sprintf("Backup created! (%d total)", a.AccMgr.BackupCount())
		case key.Matches(msg, key.NewBinding(key.WithKeys("L"))):
			a.BackupLogsState.ShowLogs = true
		case key.Matches(msg, key.NewBinding(key.WithKeys("c"))):
			a.Log.Clear()
			a.Notification = "Logs cleared"
		case key.Matches(msg, key.NewBinding(key.WithKeys("q", "esc", "h"))):
			a.BackupLogsState.ShowLogs = false
		}
	case 6: // Modules
		mods := a.ModScanner.Modules
		switch {
		case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))):
			if a.ModulesState.ViewMode == "list" {
				if a.ModulesState.Selected < len(mods)-1 { a.ModulesState.Selected++ }
			} else {
				a.ModulesState.Scroll += 3
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))):
			if a.ModulesState.ViewMode == "list" {
				if a.ModulesState.Selected > 0 { a.ModulesState.Selected-- }
			} else {
				if a.ModulesState.Scroll > 0 { a.ModulesState.Scroll -= 3 }
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("enter", "l"))):
			if a.ModulesState.ViewMode == "list" && len(mods) > 0 {
				a.ModulesState.ViewMode = "bat"
			}
		case key.Matches(msg, key.NewBinding(key.WithKeys("h", "q", "esc"))):
			if a.ModulesState.ViewMode == "bat" { a.ModulesState.ViewMode = "list" }
		case key.Matches(msg, key.NewBinding(key.WithKeys("r"))):
			a.ModScanner.Scan()
			a.ModulesState.Selected = 0
			a.Notification = fmt.Sprintf("Scanned %d modules", len(a.ModScanner.Modules))
		}
	}
	return a, nil
}

func (a App) View() string {
	if a.Width == 0 { return "Loading..." }
	t := theme.Get()

	// Header
	var tabStrs []string
	for i, tab := range a.Tabs {
		if i == a.ActiveTab {
			style := lipgloss.NewStyle().Background(lipgloss.Color(t.Blue)).Foreground(lipgloss.Color(t.BG)).Bold(true).Padding(0, 1)
			tabStrs = append(tabStrs, style.Render(fmt.Sprintf("%d:%s", i+1, tab)))
		} else {
			style := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Padding(0, 1)
			tabStrs = append(tabStrs, style.Render(fmt.Sprintf("%d:%s", i+1, tab)))
		}
	}

	header := lipgloss.NewStyle().Background(lipgloss.Color(t.BG)).Foreground(lipgloss.Color(t.Blue)).Padding(0, 1).Render("HYDRA v5.0 Go Edition") + " " + strings.Join(tabStrs, " ")

	// Content
	var content string
	switch a.ActiveTab {
	case 0:
		content = tabs.DashboardView()
	case 1:
		content = a.Editor.View()
	case 2:
		content = tabs.AccountsView(a.AccMgr, &a.AccountsState, a.Width)
	case 3:
		content = a.addAccountView()
	case 4:
		content = tabs.ThemesView(&a.ThemesState)
	case 5:
		content = tabs.BackupLogsView(a.AccMgr, a.Log, &a.BackupLogsState, a.Width)
	case 6:
		content = tabs.ModulesView(a.ModScanner, &a.ModulesState, a.Width)
	case 7:
		content = tabs.AboutView()
	}

	// Footer
	footerStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment)).Background(lipgloss.Color(t.BG))
	footer := footerStyle.Render(fmt.Sprintf("TAB:1-8 | j/k:nav | q:quit | Theme:%s | Accounts:%d | Modules:%d", theme.Get().Name, len(a.AccMgr.Accounts), len(a.ModScanner.Modules)))

	// Notification
	notif := ""
	if a.Notification != "" {
		notif = lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow)).Render("i " + a.Notification)
	}

	return lipgloss.JoinVertical(lipgloss.Left, header, content, notif, footer)
}

func (a App) addAccountView() string {
	t := theme.Get()
	s := a.AddAccountState

	methods := []string{"Classic Login (Phone + SMS)", "QR Code Login"}

	switch s.Step {
	case 0:
		var lines []string
		lines = append(lines, lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Add New Account"))
		lines = append(lines, "")
		for i, m := range methods {
			marker := "  "
			if i == s.Method { marker = "▶ " }
			lines = append(lines, marker+m)
		}
		lines = append(lines, "")
		lines = append(lines, "j/k: choose, Enter: confirm")
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(lipgloss.JoinVertical(lipgloss.Left, lines...))
	case 1:
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Step 1/3 - Account Name") + "\n\n" +
			"Enter a name (e.g. Main, Work)\n" +
			"In real app this would use text input.\n\n" +
			"Press Enter to continue (mock: using 'test')",
		)
	case 2:
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Blue)).Render("Step 2/3 - Phone Number") + "\n\n" +
			"Format: +79XXXXXXXXX\n\n" +
			"Press Enter to continue (mock: using '+79990000000')",
		)
	case 3:
		return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG)).Render(
			lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(t.Yellow)).Render("Step 3/3 - SMS Code") + "\n\n" +
			"Enter code sent to your phone\n\n" +
			"Press Enter to finish (mock)",
		)
	}
	return ""
}
