// Package hydra — SDK для Go-модулей юзербота Hydra.
//
// Go-модуль — отдельный бинарник, который общается с Python-ядром по
// JSON-строкам через stdio. Ядро спрашивает мету (имя, команды), отдаёт
// команды и нажатия кнопок, модуль отвечает текстом/формами/правками —
// тот же набор возможностей, что у Python-модулей:
// команды, инлайн-формы, callable-кнопки (.cb мост), edit/delete, lang.
//
//	minimal:
//	type mod struct{ hydra.Base }
//	func (m *mod) Meta() hydra.Meta { ... }
//	func (m *mod) Command(cmd string, ev hydra.Event) (hydra.Response, error) { ... }
//	func main() { hydra.Run(&mod{}) }
package hydra

import (
	"bufio"
	"encoding/json"
	"os"
)

// Button — кнопка формы. Callback — имя обработчика внутри модуля.
type Button struct {
	Text     string   `json:"text"`
	Callback string   `json:"callback,omitempty"`
	Args     []string `json:"args,omitempty"`
	URL      string   `json:"url,omitempty"`
	Input    bool     `json:"input,omitempty"` // кнопка ввода (.it N текст)
}

// Command — описание команды для ядра.
type Command struct {
	Name string `json:"name"`
	Desc string `json:"desc,omitempty"`
}

// Meta — метаданные модуля (ответ на op=meta).
type Meta struct {
	Name     string    `json:"name"`
	Version  string    `json:"version"`
	Commands []Command `json:"commands"`
}

// Event — контекст вызова (команда или нажатие кнопки).
type Event struct {
	ChatID    int64    `json:"chat_id"`
	MessageID int64    `json:"message_id"`
	SenderID  int64    `json:"sender_id"`
	Args      string   `json:"args"`      // хвост команды: ".echo hi" -> "hi"
	Lang      string   `json:"lang"`      // текущий язык ядра ("ru"/"en"/…)
	CbArgs    []string `json:"cb_args"`   // args кнопки при нажатии
}

// Response — ответ модуля. Text — новое сообщение; Edit — правка формы;
// Delete — удалить форму; Answer — уведомление; Buttons — ряды кнопок.
type Response struct {
	Text    string     `json:"text,omitempty"`
	Edit    string     `json:"edit,omitempty"`
	Delete  bool       `json:"delete,omitempty"`
	Answer  string     `json:"answer,omitempty"`
	Buttons [][]Button `json:"buttons,omitempty"`
}

// Module — интерфейс Go-модуля.
type Module interface {
	Meta() Meta
	Command(cmd string, ev Event) (Response, error)
	Callback(name string, ev Event) (Response, error)
}

// Base — заглушка для необязательных методов: встраивай в свою структуру.
type Base struct{}

func (Base) Callback(string, Event) (Response, error) { return Response{}, nil }

// ---- протокол (JSON-строки через stdio) ----

type request struct {
	ID   int    `json:"id"`
	Op   string `json:"op"`
	Cmd  string `json:"cmd,omitempty"`
	Name string `json:"name,omitempty"`
	Event
}

type response struct {
	ID     int         `json:"id"`
	Ok     bool        `json:"ok"`
	Result interface{} `json:"result,omitempty"`
	Error  string      `json:"error,omitempty"`
}

// Run — главный цикл модуля: читает запросы ядра со stdin, пишет ответы.
func Run(m Module) {
	in := bufio.NewScanner(os.Stdin)
	in.Buffer(make([]byte, 1024*1024), 1024*1024)
	out := bufio.NewWriter(os.Stdout)
	defer out.Flush()

	for in.Scan() {
		var req request
		if err := json.Unmarshal(in.Bytes(), &req); err != nil {
			continue
		}
		resp := response{ID: req.ID, Ok: true}
		switch req.Op {
		case "meta":
			resp.Result = m.Meta()
		case "command":
			r, err := m.Command(req.Cmd, req.Event)
			if err != nil {
				resp.Ok, resp.Error = false, err.Error()
			} else {
				resp.Result = r
			}
		case "callback":
			r, err := m.Callback(req.Name, req.Event)
			if err != nil {
				resp.Ok, resp.Error = false, err.Error()
			} else {
				resp.Result = r
			}
		default:
			resp.Ok, resp.Error = false, "unknown op: "+req.Op
		}
		line, _ := json.Marshal(resp)
		out.Write(line)
		out.WriteByte('\n')
		out.Flush()
	}
}
