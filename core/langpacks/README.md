# core/langpacks — языковые паки модулей

Поверхность `core.langpacks` из [MCUB-fork](https://github.com/hairpin01/MCUB-fork)
(порт 1:1, MIT). Пак — это `{locale: {module: {key: value}}}`.

## Порядок сборки (позже — приоритетнее)

1. встроенные паки ядра Hydra (`hydra_kernel.api.lang`: `GLOBAL_PACK` + `MODULE_PACKS`) —
   работают всегда, без файлов и без PyYAML;
2. `core/langpacks/icons/*.{json,yaml,yml}` — глобальные иконочные группы
   (значения вида `[id](alt)` разворачиваются в `<tg-emoji emoji-id="id">alt</tg-emoji>`,
   если в блоке стоит маркер `__premium_emoji__`);
3. `core/langpacks/*.{json,yaml,yml}` — паки репозитория;
4. `data/langpacks/*` и `core/langpacks/custom/*` — пользовательские паки
   (аналог `CUSTOM_LANGPACKS_DIR` в MCUB-fork).

Блок модуля с маркером `__global__: 1` попадает в общий набор строк всех модулей
(кнопки, ошибки, иконочки), ключ `lang: xx` задаёт базовый язык локали.
Глобальная строка, которая одновременно должна быть группой, хранится как
`{"__value__": "текст", "ключ": ...}` — это `StringsGroupValue` из `utils.strings`.

## Файлы репозитория

* `ru.json`, `en.json` — сгенерированы из паков MCUB-fork
  (`core/langpacks/ru.yaml`, `en.yaml`, © Шмэлькa | @hairpin01, MIT) плюс блок
  `system` для `modules/protect.py` (`# name: system`);
* JSON выбран как формат по умолчанию: он читается без PyYAML, а YAML-паки
  (в том числе скопированные из MCUB-fork) поддерживаются, когда PyYAML есть.

## API

`get_langpacks()`, `get_module_strings(module, locale)`, `get_kernel_strings(locale)`,
`get_all_module_strings(module)`, `get_available_locales()`,
`clear_langpacks_cache()`, `reload_packs()`, `CUSTOM_LANGPACKS_DIR`, `LANGPACKS`.

Добавить язык: положить `data/langpacks/<locale>.json` (или `.yaml`) в формате
`{module: {key: value}}` и выполнить `.reloadlang` — без перезапуска ядра.
