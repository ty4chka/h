# 🧬 Hydra — Telegram UserBot with a universal kernel

> Русская версия: [README.md](README.md)

**Hydra** is a userbot with its own modular kernel (`hydra_kernel`) that builds
and runs modules from **five ecosystems at once: Hydra, MCUB, Hikka, Heroku and
Dragon**. One process — five module families.

```
L4  modules/ + mcub_mods/ your modules (Hydra and saved MCUB modules)
L3  pkg/                 loader · registry · resolver · manifest · scanner
L2  compat/              MCUB · Hikka · Heroku · Dragon · legacy Hydra
L1  api/                 ModuleBase · decorators · permissions · inline · lang
L0  kernel/              transport · db · runtime · logging · gobridge(Go)
```

Dependencies point strictly downward: the kernel knows nothing about the
frameworks — the frameworks know the kernel.

## ✨ Features

- **Five framework targets** from a single build: `hydra / mcub / hikka / heroku / dragon`
- **MCUB-grade inline**: forms, callable buttons, inline routing by handler
  name, callback routing by longest data prefix, message fallback for results
- **Buttons as text**: a userbot never receives CallbackQuery — the kernel
  renders form buttons as a `.cb N M` menu right in the message (MCUB-style
  bridge): multiple menus per chat, `.it N` input buttons, `.cbf` hides
  hints, `.iq`/`.iqs` inline search incl. hash-from-Saved-Messages (API keys
  never appear in the chat)
- **MCUB-grade i18n**: per-locale `strings`, nested groups, `.setlang` with
  buttons, **custom user strings** via `.langset`
- **Fixed terminal**: `.term` with timeout, ANSI stripping and
  “rerun / close” buttons
- **GUI editor at launch**: `python3 main.py` boots the userbot together with
  a TUI editor — module list, paginated viewing, editing with syntax/scanner
  validation and automatic backups
- **Go core**: `gocore/` — native `hydracore` (stdio JSON-RPC) for fast ops,
  with a Python `gobridge` and a pure-Python fallback
- **Go modules with full parity**: the `gocore/hydra` SDK gives them
  commands, forms, buttons and lang just like Python modules; **hrul**
  builds a module from multiple files (`module.hrul` → one binary)
- **Cython compilation**: hot kernel modules are compiled to `.so`
  (`tools/build_native.py`) and picked up by the importer automatically
- **Security**: AST scanner blocks `exec/eval/os.system/subprocess` before
  execution; `owner_only` permission level
- **Automatic personal MCUB module loading**: `modules/mcub_mods/*.py`,
  including OpenAgent, starts alongside normal modules; identical copies are
  not started twice
- **Offline builds**: the kernel compiles and passes smoke tests without
  telethon and without network; unsupported `psutil` on Termux/Android uses a
  safe fallback
- **Package system**: manifests, dependency topological sort, registry,
  lifecycle hooks

## 🚀 Quick start

```bash
# build + full run of every target and the module suite
python3 -m hydra_kernel.tools.build

# run the userbot with the GUI editor (headless: --no-tui)
python3 main.py

# native (Cython) build of the kernel and the Go core
python3 tools/build_native.py
sh tools/build_go.sh
```

Green output = kernel + all targets + module suite are working.

## 📦 A module in 30 seconds

```python
from hydra_kernel.api import ModuleBase, command

class Hello(ModuleBase):
    name = "hello"
    strings = {"ru": {"hi": "Привет, {name}!"}, "en": {"hi": "Hello, {name}!"}}

    @command("hello")
    async def cmd(self, event):
        await self.form(
            event.chat_id,
            self.t("hi", name="world"),
            buttons=[[{"text": self.strings("buttons")("close"), "callback": self.cb_close}]],
        )

    async def cb_close(self, call):
        await call.delete()
```

MCUB modules (`from core.lib.loader.module_base import ...`, `@command`,
`@owner_only`, `self.args/answer/Button`) and Heroku modules
(`from heroku import loader`, `@loader.command`, `self.inline.form`) load
**unmodified** through the compatibility adapters.

## 📚 Documentation

| Document | About |
|---|---|
| [docs/KERNEL.md](docs/KERNEL.md) | kernel architecture, layers, inline routing, lang, build |
| [docs/COMPAT.md](docs/COMPAT.md) | compatibility matrix + honest approximations |
| [docs/MODULES.md](docs/MODULES.md) | module dev guide: buttons, lang, terminal |
| [docs/MIGRATION.md](docs/MIGRATION.md) | old code → new, what migrates automatically |
| [docs/NATIVE.md](docs/NATIVE.md) | Go core, Go modules, Cython compilation |

## ⚠️ Security note

Secrets were present in repository history (`ai_keys.json`, `config.py`,
session logs). **Revoke the keys** before pushing anything; add `ai_keys.json`,
`*.log`, `openagent_sessions/`, `*.zip` to `.gitignore`. The new kernel stores
no secrets: config lives in local `data/kernel_config.json`.

## 📄 License

See [LICENSE](LICENSE).
