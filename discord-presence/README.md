# Discord Presence

Показывает в статусе Discord текущий трек: «Слушает Lettudio». В статусе видно название, исполнителя и полоску прогресса. На паузе статус пропадает.

## Настройка (один раз)
1. Открой https://discord.com/developers/applications → **New Application** и назови приложение «Lettudio». Это имя появится в статусе.
2. Скопируй **Application ID** в `config.json` → `client_id`.
3. (Необязательно) *Rich Presence → Art Assets*: загрузи картинку с ключом `lettudio`. Это большая иконка в статусе.
4. Lettudio → «Настройки → Плагины» → включи **Discord Presence**.

Нужен Python 3 в PATH, внешние библиотеки не требуются. Discord должен быть запущен на этом ПК.
