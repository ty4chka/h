# Hydra v5.0 - Go Edition

Telegram UserBot with visual block editor in terminal.

## Features

- Block Editor (node-based) - drag blocks with mouse, connect ports
- Drag & Drop - full mouse support in terminal
- Connections - orthogonal routing between ports
- Block Palette - add blocks from templates (p)
- Block Settings - edit data fields (s)
- Themes - 15 built-in themes (Tokyo Night, Gruvbox, Dracula, etc)
- Tabs: Dashboard, Blocks, Accounts, Add Account, Themes, Backup, Modules, About
- Vim navigation: hjkl, g/G, Tab
- Account Manager - JSON storage, backups, favorites
- Module Scanner - scans modules/ and modules/mcub_mods/
- Logger - file logging with viewer

## Quick Start

```bash
cd hydra-go
go mod tidy
go run main.go
```

## Controls

| Key | Action |
|-----|--------|
| 1-8 | Switch tabs |
| j/k | Navigate / move block |
| h/l | Switch tabs / move block |
| Tab | Select next block |
| p | Open block palette |
| s | Block settings |
| d | Delete selected block / account |
| c | Clear connections / logs |
| f | Toggle favorite |
| b | Create backup |
| L | View logs |
| r | Rescan modules |
| Mouse | Click=select, Drag=move, Port+Port=connect |
| q | Quit / close |
| Ctrl+C | Exit app |

## Adding Custom Blocks

Edit `internal/tui/blocks/types.go` and add a BlockTemplate to DefaultTemplates.

## Telegram Integration

Edit `internal/config/config.go` with your api_id and api_hash from my.telegram.org.
The `internal/telegram/client.go` is a mock - implement gotd connection for real use.

## Project Structure

```
hydra-go/
├── main.go
├── go.mod
├── internal/
│   ├── config/
│   ├── theme/
│   ├── accounts/
│   ├── modules/
│   ├── logger/
│   ├── telegram/
│   └── tui/
│       ├── app.go
│       ├── blocks/
│       └── tabs/
├── modules/
└── data/
```

## License

MIT
