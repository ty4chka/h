// echomod — полноценный Go-модуль Hydra на SDK gocore/hydra.
// Команда .echo, инлайн-форма с кнопками (repeat/close), lang, edit/delete.
package main

import (
	"hydra-go/gocore/hydra"
)

type echomod struct{ hydra.Base }

func (m *echomod) Meta() hydra.Meta {
	return hydra.Meta{
		Name:    "echomod",
		Version: "2.0.0",
		Commands: []hydra.Command{
			{Name: "echo", Desc: "эхо-форма с кнопками (Go)"},
		},
	}
}

func main() { hydra.Run(&echomod{}) }
