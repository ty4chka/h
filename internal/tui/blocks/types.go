package blocks

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
)

type Port struct {
	ID   string
	Label string
	Side int
	Y    int
	AbsX int
	AbsY int
	Type string
}

type Block struct {
	ID       string
	Type     string
	Category string
	X, Y     int
	W, H     int
	Title    string
	Color    string
	Inputs   []Port
	Outputs  []Port
	Data     map[string]string
	Selected bool
	Dragging bool
}

type Connection struct {
	FromBlock string
	FromPort  string
	ToBlock   string
	ToPort    string
}

type BlockTemplate struct {
	Type     string
	Category string
	Title    string
	Color    string
	Inputs   []Port
	Outputs  []Port
	DataKeys []string
}

var DefaultTemplates = []BlockTemplate{
	{Type: "start", Category: "core", Title: "Start", Color: "#7aa2f7",
		Inputs: []Port{}, Outputs: []Port{{ID: "out", Label: "run", Side: 1, Y: 2, Type: "exec"}}, DataKeys: []string{"account"}},
	{Type: "send_msg", Category: "telegram", Title: "Send Message", Color: "#9ece6a",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}, {ID: "chat", Label: "chat_id", Side: -1, Y: 3, Type: "string"}, {ID: "text", Label: "text", Side: -1, Y: 4, Type: "string"}},
		Outputs: []Port{{ID: "out", Label: "done", Side: 1, Y: 2, Type: "exec"}}, DataKeys: []string{"text"}},
	{Type: "delay", Category: "logic", Title: "Delay", Color: "#e0af68",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}},
		Outputs: []Port{{ID: "out", Label: "done", Side: 1, Y: 2, Type: "exec"}}, DataKeys: []string{"seconds"}},
	{Type: "if", Category: "logic", Title: "If Condition", Color: "#bb9af7",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}, {ID: "cond", Label: "bool", Side: -1, Y: 3, Type: "bool"}},
		Outputs: []Port{{ID: "true", Label: "true", Side: 1, Y: 2, Type: "exec"}, {ID: "false", Label: "false", Side: 1, Y: 3, Type: "exec"}}, DataKeys: []string{"expression"}},
	{Type: "read_var", Category: "data", Title: "Read Variable", Color: "#73daca",
		Inputs: []Port{}, Outputs: []Port{{ID: "val", Label: "value", Side: 1, Y: 2, Type: "any"}}, DataKeys: []string{"var_name"}},
	{Type: "set_var", Category: "data", Title: "Set Variable", Color: "#73daca",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}, {ID: "val", Label: "value", Side: -1, Y: 3, Type: "any"}},
		Outputs: []Port{{ID: "out", Label: "done", Side: 1, Y: 2, Type: "exec"}}, DataKeys: []string{"var_name"}},
	{Type: "loop", Category: "logic", Title: "Loop", Color: "#ff9e64",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}, {ID: "count", Label: "count", Side: -1, Y: 3, Type: "int"}},
		Outputs: []Port{{ID: "body", Label: "body", Side: 1, Y: 2, Type: "exec"}, {ID: "done", Label: "done", Side: 1, Y: 3, Type: "exec"}}, DataKeys: []string{"iterations"}},
	{Type: "http_req", Category: "network", Title: "HTTP Request", Color: "#f7768e",
		Inputs: []Port{{ID: "in", Label: "exec", Side: -1, Y: 2, Type: "exec"}, {ID: "url", Label: "url", Side: -1, Y: 3, Type: "string"}},
		Outputs: []Port{{ID: "out", Label: "resp", Side: 1, Y: 2, Type: "string"}, {ID: "err", Label: "error", Side: 1, Y: 3, Type: "string"}}, DataKeys: []string{"method", "url"}},
}

func (b *Block) UpdatePortPositions() {
	for i := range b.Inputs { b.Inputs[i].AbsX = b.X; b.Inputs[i].AbsY = b.Y + b.Inputs[i].Y }
	for i := range b.Outputs { b.Outputs[i].AbsX = b.X + b.W - 1; b.Outputs[i].AbsY = b.Y + b.Outputs[i].Y }
}

func (b *Block) HitTest(x, y int) bool {
	return x >= b.X && x < b.X+b.W && y >= b.Y && y < b.Y+b.H
}

func (b *Block) PortHitTest(x, y int) *Port {
	b.UpdatePortPositions()
	for i := range b.Inputs { if b.Inputs[i].AbsX == x && b.Inputs[i].AbsY == y { return &b.Inputs[i] } }
	for i := range b.Outputs { if b.Outputs[i].AbsX == x && b.Outputs[i].AbsY == y { return &b.Outputs[i] } }
	return nil
}

func NewBlockFromTemplate(t BlockTemplate, id string, x, y int) Block {
	b := Block{ID: id, Type: t.Type, Category: t.Category, X: x, Y: y, W: 22, H: 5 + max(len(t.Inputs), len(t.Outputs)), Title: t.Title, Color: t.Color, Data: make(map[string]string)}
	for _, p := range t.Inputs { b.Inputs = append(b.Inputs, p) }
	for _, p := range t.Outputs { b.Outputs = append(b.Outputs, p) }
	for _, k := range t.DataKeys { b.Data[k] = "" }
	b.UpdatePortPositions()
	return b
}

func max(a, b int) int { if a > b { return a }; return b }

type Cell struct { Char rune; Style lipgloss.Style }

type Canvas struct { Width, Height int; Cells [][]Cell }

func NewCanvas(w, h int) *Canvas {
	c := &Canvas{Width: w, Height: h}
	c.Cells = make([][]Cell, h)
	for i := range c.Cells {
		c.Cells[i] = make([]Cell, w)
		for j := range c.Cells[i] { c.Cells[i][j] = Cell{Char: ' ', Style: lipgloss.NewStyle().Foreground(lipgloss.Color("#333"))} }
	}
	return c
}

func (c *Canvas) Set(x, y int, char rune, style lipgloss.Style) {
	if x >= 0 && x < c.Width && y >= 0 && y < c.Height { c.Cells[y][x] = Cell{Char: char, Style: style} }
}

func (c *Canvas) SetString(x, y int, s string, style lipgloss.Style) {
	for i, ch := range s { c.Set(x+i, y, ch, style) }
}

func (c *Canvas) Render() string {
	var b strings.Builder
	for y := 0; y < c.Height; y++ {
		for x := 0; x < c.Width; x++ { cell := c.Cells[y][x]; b.WriteString(cell.Style.Render(string(cell.Char))) }
		if y < c.Height-1 { b.WriteString("\n") }
	}
	return b.String()
}
