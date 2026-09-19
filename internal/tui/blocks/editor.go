package blocks

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/google/uuid"
	"hydra-go/internal/theme"
)

type EditorMode int
const (ModeNormal EditorMode = iota; ModePalette; ModeBlockSettings)

type Editor struct {
	Width, Height int
	YOffset       int
	Blocks        []Block
	Connections   []Connection
	Mode          EditorMode
	Dragging      bool
	DragBlock     *Block
	DragOffX, DragOffY int
	Connecting    bool
	ConnFromBlock, ConnFromPort string
	ConnFromX, ConnFromY, ConnToX, ConnToY int
	PaletteCursor  int
	SettingsBlock  *Block
	SettingsCursor int
	ScrollX, ScrollY int
	Notification string
	NotifTimer   int
}

func NewEditor() Editor {
	return Editor{
		Blocks: []Block{NewBlockFromTemplate(DefaultTemplates[0], uuid.New().String(), 5, 5)},
		Connections: []Connection{}, Mode: ModeNormal, YOffset: 1,
	}
}

func (e Editor) Init() tea.Cmd { return nil }
func (e *Editor) SetSize(w, h int) { e.Width = w; e.Height = h }

func (e Editor) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg: return e.handleKey(msg)
	case tea.MouseMsg: return e.handleMouse(msg)
	case tea.WindowSizeMsg: e.Width = msg.Width; e.Height = msg.Height
	}
	return e, nil
}

func (e Editor) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch e.Mode {
	case ModePalette: return e.handlePaletteKey(msg)
	case ModeBlockSettings: return e.handleSettingsKey(msg)
	}
	switch {
	case key.Matches(msg, key.NewBinding(key.WithKeys("q"))): return e, tea.Quit
	case key.Matches(msg, key.NewBinding(key.WithKeys("p"))): e.Mode = ModePalette; e.PaletteCursor = 0; e.Notification = "Palette: j/k move, Enter add, q close"; e.NotifTimer = 5
	case key.Matches(msg, key.NewBinding(key.WithKeys("h", "left"))): if !e.Dragging { for i := range e.Blocks { if e.Blocks[i].Selected { e.Blocks[i].X-- } } }
	case key.Matches(msg, key.NewBinding(key.WithKeys("l", "right"))): if !e.Dragging { for i := range e.Blocks { if e.Blocks[i].Selected { e.Blocks[i].X++ } } }
	case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))): if !e.Dragging { for i := range e.Blocks { if e.Blocks[i].Selected { e.Blocks[i].Y-- } } }
	case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))): if !e.Dragging { for i := range e.Blocks { if e.Blocks[i].Selected { e.Blocks[i].Y++ } } }
	case key.Matches(msg, key.NewBinding(key.WithKeys("d"))):
		var nb []Block; var delID string
		for i := range e.Blocks { if !e.Blocks[i].Selected { nb = append(nb, e.Blocks[i]) } else { delID = e.Blocks[i].ID } }
		var nc []Connection
		for _, c := range e.Connections { if c.FromBlock != delID && c.ToBlock != delID { nc = append(nc, c) } }
		e.Blocks, e.Connections = nb, nc; e.Notification = "Deleted"; e.NotifTimer = 3
	case key.Matches(msg, key.NewBinding(key.WithKeys("c"))): e.Connections = nil; e.Notification = "Cleared connections"; e.NotifTimer = 3
	case key.Matches(msg, key.NewBinding(key.WithKeys("s"))):
		for i := range e.Blocks { if e.Blocks[i].Selected { e.SettingsBlock = &e.Blocks[i]; e.Mode = ModeBlockSettings; e.SettingsCursor = 0; break } }
	case key.Matches(msg, key.NewBinding(key.WithKeys("tab"))):
		if len(e.Blocks) > 0 { found := false; for i := range e.Blocks { if e.Blocks[i].Selected { e.Blocks[i].Selected = false; e.Blocks[(i+1)%len(e.Blocks)].Selected = true; found = true; break } }; if !found { e.Blocks[0].Selected = true } }
	}
	return e, nil
}

func (e Editor) handlePaletteKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch {
	case key.Matches(msg, key.NewBinding(key.WithKeys("q", "esc"))): e.Mode = ModeNormal; e.Notification = ""
	case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))): if e.PaletteCursor > 0 { e.PaletteCursor-- }
	case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))): if e.PaletteCursor < len(DefaultTemplates)-1 { e.PaletteCursor++ }
	case key.Matches(msg, key.NewBinding(key.WithKeys("enter"))):
		tmpl := DefaultTemplates[e.PaletteCursor]; x, y := 10, 10
		for _, b := range e.Blocks { if b.Selected { x, y = b.X+b.W+3, b.Y } }
		b := NewBlockFromTemplate(tmpl, uuid.New().String(), x, y)
		for i := range e.Blocks { e.Blocks[i].Selected = false }
		b.Selected = true; e.Blocks = append(e.Blocks, b); e.Mode = ModeNormal
		e.Notification = fmt.Sprintf("Added %s", tmpl.Title); e.NotifTimer = 3
	}
	return e, nil
}

func (e Editor) handleSettingsKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if e.SettingsBlock == nil { e.Mode = ModeNormal; return e, nil }
	switch {
	case key.Matches(msg, key.NewBinding(key.WithKeys("q", "esc"))): e.Mode = ModeNormal; e.SettingsBlock = nil
	case key.Matches(msg, key.NewBinding(key.WithKeys("k", "up"))): if e.SettingsCursor > 0 { e.SettingsCursor-- }
	case key.Matches(msg, key.NewBinding(key.WithKeys("j", "down"))):
		keys := make([]string, 0, len(e.SettingsBlock.Data))
		for k := range e.SettingsBlock.Data { keys = append(keys, k) }
		if e.SettingsCursor < len(keys)-1 { e.SettingsCursor++ }
	}
	return e, nil
}

func (e Editor) handleMouse(msg tea.MouseMsg) (tea.Model, tea.Cmd) {
	if e.Mode != ModeNormal { return e, nil }
	mx := msg.X + e.ScrollX; my := msg.Y - e.YOffset + e.ScrollY; if my < 0 { my = 0 }
	switch msg.Type {
	case tea.MouseLeft:
		for i := range e.Blocks {
			if p := e.Blocks[i].PortHitTest(mx, my); p != nil {
				if p.Side == 1 { e.Connecting = true; e.ConnFromBlock = e.Blocks[i].ID; e.ConnFromPort = p.ID; e.ConnFromX = p.AbsX; e.ConnFromY = p.AbsY; e.ConnToX = mx; e.ConnToY = my; return e, nil }
				if p.Side == -1 && e.Connecting { e.Connections = append(e.Connections, Connection{FromBlock: e.ConnFromBlock, FromPort: e.ConnFromPort, ToBlock: e.Blocks[i].ID, ToPort: p.ID}); e.Connecting = false; e.Notification = "Connected"; e.NotifTimer = 2; return e, nil }
			}
		}
		for i := range e.Blocks {
			if e.Blocks[i].HitTest(mx, my) { for j := range e.Blocks { e.Blocks[j].Selected = false }; e.Blocks[i].Selected = true; e.Dragging = true; e.DragBlock = &e.Blocks[i]; e.DragOffX = mx - e.Blocks[i].X; e.DragOffY = my - e.Blocks[i].Y; return e, nil }
		}
		for i := range e.Blocks { e.Blocks[i].Selected = false }
	case tea.MouseRelease: if e.Connecting { e.Connecting = false }; e.Dragging = false; e.DragBlock = nil
	case tea.MouseMotion:
		if e.Dragging && e.DragBlock != nil { for i := range e.Blocks { if e.Blocks[i].ID == e.DragBlock.ID { e.Blocks[i].X = mx - e.DragOffX; e.Blocks[i].Y = my - e.DragOffY } } }
		if e.Connecting { e.ConnToX = mx; e.ConnToY = my }
	}
	return e, nil
}

func (e Editor) View() string {
	t := theme.Get(); if e.Width == 0 || e.Height == 0 { return "Loading..." }
	canvasW := e.Width - 24; canvasH := e.Height - 2; if canvasW < 20 { canvasW = e.Width }; if canvasH < 5 { canvasH = e.Height }
	c := NewCanvas(canvasW, canvasH)
	for _, conn := range e.Connections { e.renderConnection(c, conn) }
	if e.Connecting { e.renderLine(c, e.ConnFromX-e.ScrollX, e.ConnFromY-e.ScrollY, e.ConnToX-e.ScrollX, e.ConnToY-e.ScrollY, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow))) }
	for i := range e.Blocks { e.renderBlock(c, &e.Blocks[i]) }
	mainView := c.Render(); sidebar := e.renderSidebar()
	headerStyle := lipgloss.NewStyle().Background(lipgloss.Color(t.BG)).Foreground(lipgloss.Color(t.Blue)).Bold(true).Padding(0, 1)
	header := headerStyle.Render("HYDRA BLOCK EDITOR  |  p: palette  s: settings  d: delete  c: clear  mouse: drag & connect")
	notif := ""; if e.Notification != "" && e.NotifTimer > 0 { notif = lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow)).Render("i " + e.Notification) }
	return lipgloss.JoinVertical(lipgloss.Left, header, lipgloss.JoinHorizontal(lipgloss.Top, mainView, sidebar), notif)
}

func (e *Editor) renderBlock(c *Canvas, b *Block) {
	t := theme.Get(); color := b.Color; if b.Selected { color = t.Yellow }
	style := lipgloss.NewStyle().Foreground(lipgloss.Color(color))
	bgStyle := lipgloss.NewStyle().Background(lipgloss.Color(t.Surface)).Foreground(lipgloss.Color(color))
	bx := b.X - e.ScrollX; by := b.Y - e.ScrollY; if bx+b.W < 0 || by+b.H < 0 || bx >= c.Width || by >= c.Height { return }
	for x := 0; x < b.W; x++ { if bx+x >= 0 && bx+x < c.Width && by >= 0 && by < c.Height { ch := '─'; if x == 0 { ch = '┌' } else if x == b.W-1 { ch = '┐' }; c.Set(bx+x, by, ch, style) } }
	titleY := by + 1; if titleY >= 0 && titleY < c.Height { if bx >= 0 && bx < c.Width { c.Set(bx, titleY, '│', style) }; title := b.Title; if len(title) > b.W-4 { title = title[:b.W-4] }; if bx+1 >= 0 && bx+1 < c.Width { c.SetString(bx+1, titleY, " "+title+strings.Repeat(" ", b.W-3-len(title)), bgStyle) }; if bx+b.W-1 >= 0 && bx+b.W-1 < c.Width { c.Set(bx+b.W-1, titleY, '│', style) } }
	divY := by + 2; if divY >= 0 && divY < c.Height { for x := 0; x < b.W; x++ { if bx+x >= 0 && bx+x < c.Width { ch := '─'; if x == 0 { ch = '├' } else if x == b.W-1 { ch = '┤' }; c.Set(bx+x, divY, ch, style) } } }
	for y := 3; y < b.H-1; y++ {
		py := by + y; if py < 0 || py >= c.Height { continue }
		if bx >= 0 && bx < c.Width { c.Set(bx, py, '│', style) }
		if bx+b.W-1 >= 0 && bx+b.W-1 < c.Width { c.Set(bx+b.W-1, py, '│', style) }
		for _, p := range b.Inputs { if p.Y == y { if bx >= 0 && bx < c.Width { c.Set(bx, py, '●', lipgloss.NewStyle().Foreground(lipgloss.Color(t.Cyan))) }; label := p.Label; if len(label) > b.W-4 { label = label[:b.W-4] }; if bx+2 >= 0 && bx+2 < c.Width { c.SetString(bx+2, py, label, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment))) } } }
		for _, p := range b.Outputs { if p.Y == y { if bx+b.W-1 >= 0 && bx+b.W-1 < c.Width { c.Set(bx+b.W-1, py, '●', lipgloss.NewStyle().Foreground(lipgloss.Color(t.Green))) }; label := p.Label; if len(label) > b.W-4 { label = label[:b.W-4] }; startX := bx + b.W - 2 - len(label); if startX >= 0 && startX < c.Width { c.SetString(startX, py, label, lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment))) } } }
	}
	botY := by + b.H - 1; if botY >= 0 && botY < c.Height { for x := 0; x < b.W; x++ { if bx+x >= 0 && bx+x < c.Width { ch := '─'; if x == 0 { ch = '└' } else if x == b.W-1 { ch = '┘' }; c.Set(bx+x, botY, ch, style) } } }
}

func (e *Editor) renderConnection(c *Canvas, conn Connection) {
	t := theme.Get(); style := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Comment))
	var fromX, fromY, toX, toY int; found := false
	for i := range e.Blocks { if e.Blocks[i].ID == conn.FromBlock { for _, p := range e.Blocks[i].Outputs { if p.ID == conn.FromPort { fromX = p.AbsX - e.ScrollX; fromY = p.AbsY - e.ScrollY; found = true; break } } }; if e.Blocks[i].ID == conn.ToBlock { for _, p := range e.Blocks[i].Inputs { if p.ID == conn.ToPort { toX = p.AbsX - e.ScrollX; toY = p.AbsY - e.ScrollY; break } } } }
	if !found { return }; e.renderLine(c, fromX, fromY, toX, toY, style)
}

func (e *Editor) renderLine(c *Canvas, x1, y1, x2, y2 int, style lipgloss.Style) {
	midX := (x1 + x2) / 2
	step := 1; if x1 > midX { step = -1 }; for x := x1; x != midX; x += step { if x >= 0 && x < c.Width && y1 >= 0 && y1 < c.Height { c.Set(x, y1, '─', style) } }
	step = 1; if y1 > y2 { step = -1 }; for y := y1; y != y2; y += step { if midX >= 0 && midX < c.Width && y >= 0 && y < c.Height { c.Set(midX, y, '│', style) } }
	step = 1; if midX > x2 { step = -1 }; for x := midX; x != x2; x += step { if x >= 0 && x < c.Width && y2 >= 0 && y2 < c.Height { c.Set(x, y2, '─', style) } }
	if midX >= 0 && midX < c.Width && y1 >= 0 && y1 < c.Height { if y2 > y1 { c.Set(midX, y1, '┐', style) } else if y2 < y1 { c.Set(midX, y1, '┘', style) } }
	if midX >= 0 && midX < c.Width && y2 >= 0 && y2 < c.Height { if y2 > y1 { c.Set(midX, y2, '└', style) } else if y2 < y1 { c.Set(midX, y2, '┌', style) } }
}

func (e Editor) renderSidebar() string {
	t := theme.Get(); w := 24
	var b strings.Builder
	style := lipgloss.NewStyle().Foreground(lipgloss.Color(t.FG))
	borderStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Border))
	titleStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Blue)).Bold(true)
	selectedStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(t.Yellow)).Bold(true)
	b.WriteString(titleStyle.Render("Blocks")); b.WriteString("\n")
	if e.Mode == ModePalette { for i, tmpl := range DefaultTemplates { cursor := "  "; if i == e.PaletteCursor { cursor = "▶ "; b.WriteString(selectedStyle.Render(cursor + tmpl.Title)) } else { b.WriteString(style.Render(cursor + tmpl.Title)) }; b.WriteString("\n") } }
	else { for _, block := range e.Blocks { marker := "  "; if block.Selected { marker = "▶ " }; b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color(block.Color)).Render(marker + "█ " + block.Title)); b.WriteString("\n") } }
	b.WriteString(borderStyle.Render(strings.Repeat("─", w))); b.WriteString("\n")
	if e.Mode == ModeBlockSettings && e.SettingsBlock != nil { b.WriteString(titleStyle.Render("Settings")); b.WriteString("\n"); keys := make([]string, 0, len(e.SettingsBlock.Data)); for k := range e.SettingsBlock.Data { keys = append(keys, k) }; for i, k := range keys { cursor := "  "; if i == e.SettingsCursor { cursor = "▶ " }; val := e.SettingsBlock.Data[k]; if len(val) > 12 { val = val[:12] + "..." }; b.WriteString(style.Render(fmt.Sprintf("%s%s: %s", cursor, k, val))); b.WriteString("\n") } }
	else { b.WriteString(style.Render("Selected: ")); found := false; for _, block := range e.Blocks { if block.Selected { b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color(block.Color)).Render(block.Title)); found = true; break } }; if !found { b.WriteString(style.Render("none")) }; b.WriteString("\n"); b.WriteString(style.Render(fmt.Sprintf("Blocks: %d", len(e.Blocks)))); b.WriteString("\n"); b.WriteString(style.Render(fmt.Sprintf("Conns: %d", len(e.Connections)))); b.WriteString("\n") }
	return lipgloss.NewStyle().Width(w).Height(e.Height).Border(lipgloss.NormalBorder(), false, false, false, true).BorderForeground(lipgloss.Color(t.Border)).Padding(0, 1).Render(b.String())
}
