package tabs

import (
	"fmt"
	"time"

	"github.com/charmbracelet/lipgloss"
	"hydra-go/internal/theme"
)

var startTime = time.Now()

func DashboardView() string {
	t := theme.Get()
	dragon := `
        @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
      @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
     @@@@@@@@%%*#*%%@@@@@@@@@@@@@@@@@@@@
    @@@@@@@%##**+*##%%@@@@@@@@@@@@@@@@@@
   @@@@@@%#*+*+***+++*#%@@@@@@@@@@@@@@@@
  @@@@@@%*++++**+++++++*#%@@@@@@@@@@@@@@
  @@@@@%##++++##*++*+*###%@@@@@@@@@@@@@@
  @@@@@%*++++#%%%%%%**%@@@@@@@@@@@@@@@@@
  @@@@@%##+++++*#%%@@@@@@@@@@@@@@@@@@@@@
   @@@@@@%%*++++++*#%%@@@@@@@@@@@@@@@@@@
    @@@@@@@@%%#*++++++#%@@@@@@@@@@@@@@@@
   @@@@@@%%%%%%%%%#++++*%@@@@@@@@@@@@@@@
  @@@@@@%*+++++##%%%#*+++*%@@@@@@@@@@@@@
 @@@@@@%*+++++++++*#*++++#%@@@@@@@@@@@@@
@@@@@@%*++*#%%#*++++++++#%@@@@@@@@@@@@@@
 @@@@@@#++#%@@@@%###*##%@@@@@@@@@@@@@@@@@@
  @@@@@%#++*%%%%%%%##*%@@@@@@@@@@@@@@@@@
   @@@@@@%#*++++++*#%%@@@@@@@@@@@@@@@@@@@
    @@@@@@@@@%%%%%@@@@@@@@@@@@@@@@@@@@@@@
     @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
`
	uptime := time.Since(startTime)
	uptimeStr := fmt.Sprintf("%02d:%02d:%02d", int(uptime.Hours())%24, int(uptime.Minutes())%60, int(uptime.Seconds())%60)

	dragonStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Blue))
	infoStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG))
	titleStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow)).Bold(true)
	accentStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Green)).Bold(true)

	info := titleStyle.Render("Welcome to Hydra v5.0") + "\n\n" +
		infoStyle.Render("Go Edition with Block Editor") + "\n" +
		infoStyle.Render("Drag blocks with mouse, connect ports") + "\n" +
		infoStyle.Render("Press [2] for Block Editor") + "\n" +
		infoStyle.Render("Press [3] for Accounts") + "\n" +
		infoStyle.Render("Press [4] for Themes") + "\n\n" +
		accentStyle.Render("Uptime: "+uptimeStr)

	return lipgloss.JoinHorizontal(lipgloss.Top, dragonStyle.Render(dragon), info)
}
