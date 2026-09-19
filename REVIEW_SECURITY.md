# ty4chka/h — находки (критичные)

Репозиторий **публичный** (`https://github.com/ty4chka/h` → HTTP 200 без авторизации).
Всё ниже лежит в git-истории и доступно любому, кто откроет ссылку.

## 1. Утёкшие секреты

| Файл | Что | Значение |
|---|---|---|
| `ai_keys.json` | Google API key | `AIza…` (39 символов, полный ключ) |
| `config.py:6` | Telegram `api_hash` | `7d3ea0c0d4725498789bd51a9ee02421` |
| `config.py:34` | `'secret'` | `4126d43aa6bb16a0556cbbff1dfd33f5` |
| `hydra2.zip` | внутри архива тоже `AIza…` | ключ продублирован |

Проверено: `git grep -l "AIza"` → `ai_keys.json`, `hydra2.zip`.

## 2. Личные данные в репозитории

- `openagent_sessions/sessions.json` — переписка с ИИ, включая `chat_id: -1002202293795` (приватный супер-групповой чат) и текст сообщений.
- `crash.log`, `out.log`, `data/hydra.log` — рантайм-логи.
- `ai_history.json`, `ai_stats.json` — пустышки (`[]`, `{}`), но трекаются.

## 3. .gitignore не покрывает то, что уже закоммичено

В `.gitignore` есть `*.session`, `data/accounts.json`, `data/fheta_token.json` — но
**нет** `ai_keys.json`, `*.log`, `openagent_sessions/`, `*.zip`.
Даже если добавить их сейчас, файлы останутся в истории.

## 4. Что делать (порядок важен)

1. **Отозвать ключ Google** — console.cloud.google.com → Credentials → Revoke. Без этого
   всё остальное бессмысленно: ключ уже могли подобрать сканеры (GitHub сканируют боты
   за минуты после пуша).
2. Telegram `api_hash`/`secret` — перегенерировать приложение на my.telegram.org,
   если это не публичный общедоступный набор.
3. Вычистить историю: `git filter-repo --path ai_keys.json --path hydra2.zip
   --path openagent_sessions --path '*.log' --invert-paths`, затем `push --force`.
   Либо проще — создать новый репозиторий и залить чистое дерево одним коммитом.
4. Добавить в `.gitignore`: `ai_keys.json`, `*.log`, `openagent_sessions/`, `*.zip`, `data/`.
5. Проверить, не осталось ли секретов: `git log -p | grep -iE "aiza|api_key|secret|token"`.
