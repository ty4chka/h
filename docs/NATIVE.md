# Нативная часть: Go-ядро и Cython

## Go-ядро (`gocore/`)

- `gocore/main.go` → бинарь `hydracore`: читает построчный JSON с stdin,
  отвечает `{"id", "ok", "result", "error"}` в stdout.
- Операции: `ping`, `ansi_strip`, `sha256`, `read_file`, `write_file`,
  `modules` (список `gocore/bin`), `run_module {module, args}`.
- Python-мост: `hydra_kernel.kernel.gobridge.GoBridge` (asyncio-subprocess,
  5 c таймаут ответа). Если бинарника нет — мост молча не стартует, ядро
  работает чисто на Python.

## Go-модули (полный паритет с Python)

Go-модуль — бинарник на SDK **`gocore/hydra`**: ядро держит с ним процесс
и общается JSON-строками по stdio (`op = meta / command / callback`).
Модуль умеет всё то же, что Python-модуль: команды, инлайн-формы,
callable-кнопки (через `.cb`-мост), `edit/delete/answer`, lang.

```go
// gocore/modules/echomod/main.go
type echomod struct{ hydra.Base }

func (m *echomod) Meta() hydra.Meta {
    return hydra.Meta{Name: "echomod", Version: "2.0.0",
        Commands: []hydra.Command{{Name: "echo", Desc: "эхо-форма"}}}
}
func main() { hydra.Run(&echomod{}) }

// echo.go — второй файл того же модуля
func (m *echomod) Command(cmd string, ev hydra.Event) (hydra.Response, error) {
    return hydra.Response{
        Text: "🔊 Эхо: " + ev.Args,
        Buttons: [][]hydra.Button{{
            {Text: "🔁 Повторить", Callback: "repeat"},
            {Text: "❌ Закрыть", Callback: "close"},
        }},
    }, nil
}
func (m *echomod) Callback(name string, ev hydra.Event) (hydra.Response, error) {
    if name == "repeat" { return hydra.Response{Edit: "..."}, nil }
    return hydra.Response{Delete: true}, nil
}
```

Python-сторона — `hydra_kernel.pkg.go_loader.GoLoader`: спавнит бинарник,
забирает мету, регистрирует команды и кнопки в ядре. `main.py` сам грузит
`gocore/bin/*` при старте.

## hrul — сборка модулей из нескольких файлов

`hrul` — декларативный сборщик: модуль = папка с манифестом `module.hrul`,
несколько исходников собираются в один артефакт:

```ini
name = echomod
lang = go            # go | python
version = 2.0.0
entry = main.go
sources = main.go echo.go
output = ../../bin/echomod
```

```bash
python3 tools/hrul.py build gocore/modules/echomod   # -> gocore/bin/echomod
python3 tools/hrul.py list                           # все модули с манифестами
sh tools/build_go.sh                                 # hydracore + все hrul-модули
```

В отличие от MCUB (скачивание готовых .py по modules.ini из репозитория),
hrul собирает модуль **локально из исходников** — Go-модуль из нескольких
файлов компилируется в один бинарник, python-модуль собирается в пакет.

## Cython-компиляция ядра

`python3 tools/build_native.py` собирает in-place `.so` для горячих модулей:

| цель | зачем |
| --- | --- |
| `hydra_kernel/pkg/scanner.py` | AST-обход на каждой загрузке модуля |
| `hydra_kernel/pkg/resolver.py` | топосорт зависимостей |
| `hydra_kernel/api/lang.py` | резолв строк на каждое сообщение |

Расширение имеет приоритет у импортёра — после сборки `from
hydra_kernel.pkg import scanner` берёт `.so`, проверка:

```bash
python3 -c "from hydra_kernel.pkg import scanner; print(scanner.__file__)"
```

Нет Cython — шаг печатает SKIP, ядро остаётся чистым Python. Оба шага
встроены в `python3 -m hydra_kernel.tools.build`.
