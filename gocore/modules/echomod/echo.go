// echo.go — логика команды и кнопок echomod (второй файл модуля:
// собирается hrul'ом из нескольких источников в один бинарник).
package main

import (
	"fmt"
	"hydra-go/gocore/hydra"
)

// last — последний аргумент .echo по чатам: repeat повторяет именно его.
var last = map[int64]string{}

func (m *echomod) Command(cmd string, ev hydra.Event) (hydra.Response, error) {
	if cmd != "echo" {
		return hydra.Response{}, fmt.Errorf("unknown cmd: %s", cmd)
	}
	last[ev.ChatID] = ev.Args
	return hydra.Response{
		Text: echoText(ev.Args, ev.Lang),
		Buttons: [][]hydra.Button{
			{
				{Text: str(ev.Lang, "repeat"), Callback: "repeat"},
				{Text: str(ev.Lang, "close"), Callback: "close"},
			},
		},
	}, nil
}

func (m *echomod) Callback(name string, ev hydra.Event) (hydra.Response, error) {
	switch name {
	case "repeat":
		return hydra.Response{Edit: echoText(last[ev.ChatID], ev.Lang) + " " + str(ev.Lang, "again")}, nil
	case "close":
		return hydra.Response{Delete: true}, nil
	}
	return hydra.Response{Answer: "?"}, nil
}

func echoText(arg, lang string) string {
	if arg == "" {
		arg = "…"
	}
	return fmt.Sprintf(str(lang, "echo_fmt"), arg)
}

func str(lang, key string) string {
	table := map[string]map[string]string{
		"en": {
			"echo_fmt": "🔊 Echo: %s",
			"repeat":   "🔁 Repeat",
			"close":    "❌ Close",
			"again":    "(again)",
		},
	}
	if t, ok := table[lang]; ok {
		if v, ok := t[key]; ok {
			return v
		}
	}
	ru := map[string]string{
		"echo_fmt": "🔊 Эхо: %s",
		"repeat":   "🔁 Повторить",
		"close":    "❌ Закрыть",
		"again":    "(ещё раз)",
	}
	return ru[key]
}
