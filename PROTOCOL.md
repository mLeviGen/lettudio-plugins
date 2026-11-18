# Плагины Lettudio (протокол 4)

Плагин — это папка с `plugin.json` в каталоге плагинов. Установить плагин можно прямо в приложении через **Настройки → Плагины** (из `.zip`-архива, папки или по URL — копировать вручную в скрытые папки AppData / Android не нужно); там же находятся включение и выключение, удаление, «Открыть папку» и лог. На Windows каталог лежит в `%APPDATA%\app.lettudio\lettudio\plugins`.

Если не включён ни один плагин, приложение не запускает процессов и не подписывается на события.

**На чём писать:** на чём угодно. Плагин-процесс — обычная программа, которая читает строки JSON из stdin и пишет строки JSON в stdout. Проще всего на Python: в `sdk/python/lettudio.py` лежит мини-SDK без зависимостей. Пример — `sleep-timer/`.

---

## Тип `theme` — внешний вид (ПК и телефон)

```json
{
  "id": "my-theme", "name": "Моя тема", "version": "1.0.0", "type": "theme",
  "theme": {
    "bg": "#0F1216", "surface": "#181D23", "surfaceHi": "#232A33", "fill": "#2B5A55",
    "text": "#E6EDF3", "muted": "#7D8A99", "accent": "#7FD1B9",
    "coverA": "#7FD1B9", "coverB": "#2B4C5E",
    "radius": 14,
    "coverShape": "rounded",
    "density": "compact",
    "navLabels": "all",
    "font": "Inter.ttf",
    "background": "bg.jpg",
    "backgroundOpacity": 0.25
  }
}
```

| Поле | Значения |
|---|---|
| Цвета | `#RRGGBB` или `#AARRGGBB`: фон, плашки, дорожка и заливка прогресса, текст, подписи, акцент, градиент заглушки обложки |
| `brightness` | `dark` · `light` (по умолчанию `dark`) |
| `radius` | скругление плашек |
| `panelShape` | форма углов панелей: `rounded` · `squircle` (непрерывный суперэллипс One UI; по умолчанию `rounded`) |
| `blur` | размытие (`BackdropFilter` sigma `0`–`36`) для панелей, карточек и индикатора прогресса |
| `menuBlur` | размытие (`0`–`36`) выпадающих и всплывающих меню |
| `borderColor`, `borderWidth` | тонкая стеклянная рамка панелей (`#AARRGGBB`, толщина `0`–`3`) |
| `highlightColor` | верхний стеклянный блик внутри панелей (`#AARRGGBB`) |
| `shadowOpacity` | прозрачность мягкой тени карточек (`0`–`1`) |
| `ambientGlow`, `glowA`, `glowB`, `glowOpacity` | фоновое свечение за стеклом: `true`/`false`, цвета орбов `#RRGGBB`/`#AARRGGBB`, прозрачность `0`–`1` |
| `navIndicator` | подсветка активной вкладки навигации: `none` · `pill` |
| `coverShape` | `circle` · `rounded` · `square` |
| `density` | `compact` · `normal` · `comfortable` или число 0.7–1.4 |
| `navLabels` | подписи в навигации: `active` · `all` · `none` |
| `font` | файл .ttf/.otf в папке плагина |
| `background`, `backgroundOpacity` | картинка в папке плагина, прозрачность 0–1 |
| `presets` | массив готовых вариантов `{ "id", "name", "description"?, "theme": { ... } }`, переключаемых в Настройках |
| `customizable` | `true` / `false` — включает кнопку «Настроить цвета» с живым редактором палитры и параметров интерфейса |

Любое поле можно не указывать. Включённые темы накладываются слоями по алфавиту. Если у темы заданы `presets`, применяется выбранный пользователем пресет (по умолчанию первый), а при активном пресете `custom` (или при отсутствии пресетов) поверх накладываются пользовательские переопределения.

### Переводы названий: `i18n`

В `plugin.json` (и в записях `catalog.json`) можно добавить необязательный объект `i18n` с переводами `name` и `description`; для тем — и у каждого пресета:

```json
{
  "id": "my-theme", "name": "Моя тема", "description": "Описание",
  "i18n": { "en": { "name": "My theme", "description": "Description" },
            "de": { "name": "Mein Theme" } },
  "presets": [
    { "id": "system", "name": "Системные цвета", "description": "Как в системе",
      "i18n": { "en": { "name": "System colors" }, "de": { "name": "Systemfarben" } },
      "theme": { } }
  ]
}
```
Язык выбирается по языку интерфейса (`en`, `de`); нет перевода языка или поля — берутся основные (русские) `name` и `description`. Манифесты без `i18n` работают как раньше.

---

## Тип `process` — программа (пока только ПК)

```json
{
  "id": "sleep-timer", "name": "Таймер сна", "version": "1.0.0", "type": "process",
  "description": "…",
  "run": { "command": "python", "args": ["-u", "main.py"] }
}
```
Рабочая папка процесса — папка плагина. stderr и строки не в формате JSON попадают в лог плагина.

### Язык интерфейса

Приложение поддерживает русский (язык по умолчанию), английский и немецкий. Плагин узнаёт язык тремя способами:
- переменная окружения `LETTUDIO_LANG` (`ru` · `en` · `de`) при запуске процесса;
- поле `lang` в событии `hello`;
- событие `{"type":"lang","lang":"en"}` при смене языка во время работы — тексты, отданные приложению раньше (`add_action`, `home_section`, `register_search`), надо отправить заново на новом языке.

Плагин сам переводит свои строки (`toast`, `status`, заголовки кнопок и секций, `prompt`); неизвестный язык — русский. В Python SDK язык лежит в `p.lang`, а `t = p.translator({"en": {"Привет": "Hello"}, "de": {...}})` даёт функцию `t("Привет")` с подстановками `{name}` (`t("Играет: {x}", x=...)`); для `de` без перевода берётся английский, затем русская строка.

Название и описание самого плагина, а также пресетов тем переводятся через `i18n` (см. ниже).

### События: приложение → плагин (stdin)

| type | Когда | Поля |
|---|---|---|
| `hello` | при запуске | `app`, `protocol` (=4), `platform`, `lang` (`ru` · `en` · `de`) |
| `lang` | пользователь сменил язык интерфейса | `lang` — плагин должен заново зарегистрировать свои кнопки, секции, заголовок поиска |
| `track` | сменился трек | `track`, `playing`, `positionMs`, `durationMs`, `shuffle`, `repeat`, `volume`, `liked` |
| `state` | play/pause, перемотка | те же поля |
| `stopped` | ничего не играет | — |
| `action` | нажата кнопка плагина | `id`, `track` (если нажата в меню трека или в плеере), `arg` (необязательный аргумент, например из `search`) |
| `search` | поисковый запрос из вкладки «Поиск» | `reqId`, `query` |
| `resolve_track` | запрос свежей потоковой ссылки для трека | `reqId`, `track` |
| `response` | ответ на `request` | `reqId`, `ok`, `data` или `error` |
| `bye` | плагин выключают или приложение закрывается; через 1 с процесс будет убит | — |

`track`: `{title, artist, album, durationMs, genre?, coverArt?, path?, serverId?, streamUrl?, httpHeaders?, sourceUrl?, sourcePlugin?, key}`.

На `resolve_track` плагин отвечает командой `reply` (или `response`) с тем же `reqId`, `ok: true` и `data`: `{"streamUrl": "https://…", "httpHeaders"?: {...}, "sourceUrl"?: "…", "sourcePlugin"?: "…", "title"?: "…", "artist"?: "…", "album"?: "…", "durationMs"?: 180000, "coverArt"?: "…"}` (либо `ok: false, error: "..."`).

Позиция **не** присылается каждую секунду: считай её сам по `positionMs` и `playing`.

### Команды: плагин → приложение (stdout)

**Воспроизведение**
```json
{"cmd":"play"}  {"cmd":"pause"}  {"cmd":"toggle"}  {"cmd":"next"}  {"cmd":"previous"}
{"cmd":"seek","positionMs":60000}
{"cmd":"volume","value":40}
{"cmd":"shuffle","on":true}
{"cmd":"play_tracks","title":"Моя подборка","start":0,
 "tracks":[{"artist":"Daft Punk","title":"One More Time"},{"path":"D:\\Music\\a.flac"},{"serverId":"…"},{"streamUrl":"https://…","title":"Поток","artist":"Радио","httpHeaders":{"User-Agent":"…"}}]}
{"cmd":"queue_add","tracks":[{"path":"D:\\Music\\b.flac"}],"next":true}
```
Трек ищется так: по `streamUrl` (`http://` или `https://`; при необходимости можно передать `httpHeaders` со строковыми ключами и значениями для HTTP-запросов плеера), по `path` в медиатеке (если файл есть на диске, но ещё не в индексе — индексируется автоматически), затем по «исполнитель + название» на диске и на сервере, затем по `serverId`.
`queue_add` добавляет треки в конец очереди (или сразу после текущего при `"next":true`).

**Библиотека**
```json
{"cmd":"like","on":true}
{"cmd":"like","track":{"artist":"…","title":"…"}}
{"cmd":"add_to_playlist","playlist":"Ночное","track":{"artist":"…","title":"…"}}
{"cmd":"add_file","reqId":1,"path":"D:\\Music\\new.mp3"}
{"cmd":"rescan","reqId":2}
```
`like` без `track` относится к текущему треку. Если плейлиста с таким именем нет, он будет создан.
`add_file` индексирует один файл и (если передан `reqId`) отвечает `response` с `track` в `data`.
`rescan` запускает пересканирование папки медиатеки (если передан `reqId` — отвечает `response`).

**Интерфейс**
```json
{"cmd":"add_action","id":"lyrics","title":"Текст","icon":"lyrics","where":"both"}
{"cmd":"remove_action","id":"lyrics"}
{"cmd":"home_section","id":"mix","title":"Подборка дня","items":[
   {"title":"Утро","subtitle":"12 треков","tracks":[{"artist":"…","title":"…"}]},
   {"title":"Обновить","action":"refresh"}
]}
{"cmd":"home_section","id":"mix","items":null}
{"cmd":"set_theme","theme":{"accent":"#FF8A65","fill":"#5D3A2E"}}
{"cmd":"set_theme","theme":null}
{"cmd":"toast","text":"Готово"}
{"cmd":"status","text":"Поиск потока..."}
{"cmd":"status","text":null}
{"cmd":"register_search","title":"YouTube / Поток (yt-dlp)"}
{"cmd":"reply","reqId":4,"ok":true,"data":[{"title":"Трек","artist":"Исполнитель","album":"","durationMs":180000,"action":"play_url","downloadAction":"download_url","arg":"https://…"}]}
{"cmd":"prompt","reqId":3,"title":"Введите ссылку","hint":"https://…","initial":""}
{"cmd":"log","text":"отладка"}
```
- **`add_action`** добавляет кнопку. `where`: `player` (на ПК — в нижней панели у таймлайна, при нехватке места уходит в «…»; на телефоне — в полноэкранном плеере), `track` (пункт в меню трека), `search` (кнопка во вкладке «Поиск») или `both` (`player` + `track`). Повторный `add_action` с тем же `id` обновляет название и иконку.
- **`icon`**:
  - имя из набора: `timer bedtime alarm star heart bolt music mic lyrics radio cloud download share info settings equalizer shuffle playlist search bookmark flag chat globe palette speed auto extension`;
  - **или своя картинка** из папки плагина: `"icon": "icon.png"` (PNG/JPG/WebP). Картинка перекрашивается в цвет текста темы, поэтому лучше рисовать её белым по прозрачному фону.
- **`home_section`** добавляет свою секцию на главной. Тап по пункту включает его `tracks` или присылает плагину `action`.
- **`set_theme`** — «живая» тема поверх остальных. Например, можно перекрашивать интерфейс под обложку.
- **`status`** показывает индикатор загрузки с текстом `text` (или скрывает его при `text: null`).
- **`register_search`** регистрирует плагин во вкладке «Поиск» под заголовком `title`. При поиске приложение присылает событие `search` (`{"type":"search","reqId":...,"query":"..."}`), на которое нужно ответить командой `reply` с тем же `reqId` и массивом результатов в `data` (или `ok: false, error: "..."`). Каждый результат может задавать `action`, `downloadAction` и `arg`; при выборе элемента приложение отправит событие `action` с соответствующим `id` и полем `arg`.
- **`prompt`** открывает диалог ввода текста и возвращает `response` с `data`: `{"text": "...", "cancelled": false}` или `{"cancelled": true}`.

Всё, что добавил плагин (кнопки, секции, тема), исчезает, когда плагин выключают.

**Запросы с ответом**
```json
{"cmd":"request","reqId":1,"what":"current"}
```
`what`:
- `current` — что играет сейчас;
- `queue` — очередь;
- `library` — все локальные треки;
- `liked` — «Избранные»;
- `playlists` — список плейлистов;
- `history` — недавно прослушанное;
- `library_folder` — путь к папке медиатеки.

Ответ приходит событием `response` с тем же `reqId`.

---

## Версионирование и каталог плагинов (`catalog.json`)

В поле `"version"` в `plugin.json` используется SemVer (`major.minor.patch`, допускаются пререлиз-теги вроде `1.2.0-beta.1` и необязательный префикс `v`).

При установке и автообновлении из каталога приложение сравнивает версию в каталоге с уже установленной:
- если установлена та же или более новая версия (`<=`), скачивание пропускается без сетевого запроса;
- если в каталоге версия новее (`>`), плагин обновляется (с остановкой процесса для `process`-плагинов перед заменой);
- ручная переустановка (`force: true`) перезаписывает плагин независимо от версии.

Официальный каталог по умолчанию находится по адресу:
`https://raw.githubusercontent.com/mLeviGen/lettudio-plugins/main/catalog.json`

### Формат `catalog.json`

```json
{
  "version": 1,
  "plugins": [
    {
      "id": "lettudio-themes",
      "name": "Темы Lettudio",
      "version": "1.0.0",
      "type": "theme",
      "description": "Описание плагина",
      "platforms": ["windows", "android"],
      "url": "https://raw.githubusercontent.com/mLeviGen/lettudio-plugins/main/lettudio-themes/plugin.json",
      "zipUrl": "https://github.com/mLeviGen/lettudio-plugins/releases/latest/download/lettudio-themes.zip",
      "minAppVersion": "1.0.0"
    }
  ]
}
```

| Поле | Описание |
|---|---|
| `id` | уникальный идентификатор плагина (должен совпадать с `id` в `plugin.json`) |
| `name` | отображаемое название |
| `version` | актуальная SemVer-версия плагина |
| `type` | `theme` или `process` |
| `description` | краткое описание (необязательно) |
| `i18n` | необязательные переводы `name` и `description` (`{"en": {...}, "de": {...}}`), см. выше |
| `platforms` | список поддерживаемых ОС (`windows`, `android`, `linux`, `macos`); если пуст или не указан — определяется по `type` |
| `url` | ссылка на `plugin.json` (для `theme`) или `.zip`-архив |
| `zipUrl` | необязательная ссылка на `.zip`-архив (например, релиз на GitHub) |
| `minAppVersion` | необязательная минимальная версия приложения |

---

## Идеи
- Тексты песен (`.lrc` рядом с файлом) — кнопка «Текст» и уведомления по строкам.
- Скробблинг в Last.fm или ListenBrainz.
- Тема под цвет обложки (`set_theme` на каждый `track`).
- «Подборка дня» на главной из `history` и `library`.
- Глобальные горячие клавиши, вывод «сейчас играет» в OBS.
