package theme

import "github.com/charmbracelet/lipgloss"

type Theme struct {
	Name    string
	BG      string
	Surface string
	Border  string
	Comment string
	Blue    string
	Green   string
	Cyan    string
	FG      string
	Yellow  string
	Red     string
	Purple  string
	Orange  string
}

var Themes = map[string]Theme{
	"tokyo_night": {
		Name: "Tokyo Night", BG: "#1a1b26", Surface: "#24283b", Border: "#3b4261",
		Comment: "#565f89", Blue: "#7aa2f7", Green: "#9ece6a", Cyan: "#73daca",
		FG: "#c0caf5", Yellow: "#e0af68", Red: "#f7768e", Purple: "#bb9af7", Orange: "#ff9e64",
	},
	"catppuccin_mocha": {
		Name: "Catppuccin Mocha", BG: "#1e1e2e", Surface: "#313244", Border: "#45475a",
		Comment: "#6c7086", Blue: "#89b4fa", Green: "#a6e3a1", Cyan: "#94e2d5",
		FG: "#cdd6f4", Yellow: "#f9e2af", Red: "#f38ba8", Purple: "#cba6f7", Orange: "#fab387",
	},
	"gruvbox_dark": {
		Name: "Gruvbox Dark", BG: "#282828", Surface: "#3c3836", Border: "#504945",
		Comment: "#928374", Blue: "#83a598", Green: "#b8bb26", Cyan: "#8ec07c",
		FG: "#ebdbb2", Yellow: "#fabd2f", Red: "#fb4934", Purple: "#d3869b", Orange: "#fe8019",
	},
	"nord": {
		Name: "Nord", BG: "#2e3440", Surface: "#3b4252", Border: "#434c5e",
		Comment: "#4c566a", Blue: "#81a1c1", Green: "#a3be8c", Cyan: "#88c0d0",
		FG: "#eceff4", Yellow: "#ebcb8b", Red: "#bf616a", Purple: "#b48ead", Orange: "#d08770",
	},
	"dracula": {
		Name: "Dracula", BG: "#282a36", Surface: "#44475a", Border: "#6272a4",
		Comment: "#6272a4", Blue: "#8be9fd", Green: "#50fa7b", Cyan: "#8be9fd",
		FG: "#f8f8f2", Yellow: "#f1fa8c", Red: "#ff5555", Purple: "#bd93f9", Orange: "#ffb86c",
	},
	"one_dark": {
		Name: "One Dark", BG: "#282c34", Surface: "#353b45", Border: "#3e4451",
		Comment: "#5c6370", Blue: "#61afef", Green: "#98c379", Cyan: "#56b6c2",
		FG: "#abb2bf", Yellow: "#e5c07b", Red: "#e06c75", Purple: "#c678dd", Orange: "#d19a66",
	},
	"solarized_dark": {
		Name: "Solarized Dark", BG: "#002b36", Surface: "#073642", Border: "#586e75",
		Comment: "#657b83", Blue: "#268bd2", Green: "#859900", Cyan: "#2aa198",
		FG: "#eee8d5", Yellow: "#b58900", Red: "#dc322f", Purple: "#d33682", Orange: "#cb4b16",
	},
	"monokai": {
		Name: "Monokai", BG: "#272822", Surface: "#383830", Border: "#49483e",
		Comment: "#75715e", Blue: "#66d9ef", Green: "#a6e22e", Cyan: "#66d9ef",
		FG: "#f8f8f2", Yellow: "#e6db74", Red: "#f92672", Purple: "#ae81ff", Orange: "#fd971f",
	},
	"rose_pine": {
		Name: "Rose Pine", BG: "#191724", Surface: "#1f1d2e", Border: "#26233a",
		Comment: "#6e6a86", Blue: "#9ccfd8", Green: "#31748f", Cyan: "#9ccfd8",
		FG: "#e0def4", Yellow: "#f6c177", Red: "#eb6f92", Purple: "#c4a7e7", Orange: "#ebbcba",
	},
	"cyberpunk": {
		Name: "Cyberpunk", BG: "#0d0221", Surface: "#1a0b2e", Border: "#2d1b4e",
		Comment: "#5a4a6a", Blue: "#00f0ff", Green: "#00ff9f", Cyan: "#00f0ff",
		FG: "#f0e6ff", Yellow: "#ffee00", Red: "#ff006e", Purple: "#bc13fe", Orange: "#ff8500",
	},
	"material_ocean": {
		Name: "Material Ocean", BG: "#0f111a", Surface: "#1a1c25", Border: "#2a2d3a",
		Comment: "#464b5d", Blue: "#82aaff", Green: "#c3e88d", Cyan: "#89ddff",
		FG: "#a6accd", Yellow: "#ffcb6b", Red: "#f07178", Purple: "#c792ea", Orange: "#f78c6c",
	},
	"ayu_dark": {
		Name: "Ayu Dark", BG: "#0a0e14", Surface: "#131721", Border: "#242936",
		Comment: "#5c6773", Blue: "#39bae6", Green: "#7ee787", Cyan: "#73d0ff",
		FG: "#bfbdb6", Yellow: "#e6b450", Red: "#f07178", Purple: "#d2a6ff", Orange: "#ff8f40",
	},
	"github_dark": {
		Name: "GitHub Dark", BG: "#0d1117", Surface: "#161b22", Border: "#30363d",
		Comment: "#8b949e", Blue: "#58a6ff", Green: "#3fb950", Cyan: "#39c5cf",
		FG: "#c9d1d9", Yellow: "#d29922", Red: "#f85149", Purple: "#a371f7", Orange: "#f0883e",
	},
	"matrix": {
		Name: "Matrix", BG: "#000000", Surface: "#0d1117", Border: "#1a2e1a",
		Comment: "#2d5a27", Blue: "#00ff41", Green: "#00ff41", Cyan: "#00ff41",
		FG: "#00ff41", Yellow: "#55ff55", Red: "#ff0040", Purple: "#00cc33", Orange: "#33ff33",
	},
	"night_owl": {
		Name: "Night Owl", BG: "#011627", Surface: "#0b2942", Border: "#1d3b53",
		Comment: "#637777", Blue: "#82aaff", Green: "#c792ea", Cyan: "#7fdbca",
		FG: "#d6deeb", Yellow: "#ecc48d", Red: "#ef5350", Purple: "#c792ea", Orange: "#f78c6c",
	},
	"kanagawa": {
		Name: "Kanagawa", BG: "#1f1f28", Surface: "#2a2a37", Border: "#363646",
		Comment: "#727169", Blue: "#7e9cd8", Green: "#98bb6c", Cyan: "#6a9589",
		FG: "#dcd7ba", Yellow: "#e6c384", Red: "#ff5d62", Purple: "#957fb8", Orange: "#ffa066",
	},
	"catppuccin_latte": {
		Name: "Catppuccin Latte", BG: "#eff1f5", Surface: "#e6e9ef", Border: "#ccd0da",
		Comment: "#9ca0b0", Blue: "#1e66f5", Green: "#40a02b", Cyan: "#179299",
		FG: "#4c4f69", Yellow: "#df8e1d", Red: "#d20f39", Purple: "#8839ef", Orange: "#fe640b",
	},
}

var Current = "tokyo_night"

func Get() Theme {
	if t, ok := Themes[Current]; ok {
		return t
	}
	return Themes["tokyo_night"]
}

func Set(name string) bool {
	if _, ok := Themes[name]; ok {
		Current = name
		return true
	}
	return false
}

func List() []string {
	keys := make([]string, 0, len(Themes))
	for k := range Themes {
		keys = append(keys, k)
	}
	return keys
}

func (t Theme) StyleFG() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG))
}
