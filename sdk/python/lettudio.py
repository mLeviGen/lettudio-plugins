"""Мини-SDK для плагинов Lettudio на Python (без зависимостей).

Скопируй этот файл в папку своего плагина и пиши так:

    from lettudio import Plugin

    p = Plugin()

    @p.on("track")
    def on_track(ev):
        p.toast(f"Сейчас: {ev['track']['artist']} — {ev['track']['title']}")

    @p.on_action("hello")
    def hello(ev):
        p.toast("Привет!")

    p.add_action("hello", "Привет", icon="star", where="player")
    p.run()

Протокол целиком — в plugins/PROTOCOL.md.
"""
import itertools
import json
import queue
import sys
import threading

# Вывод только через этот поток: stdout — канал команд, его нельзя смешивать с print().
_out_lock = threading.Lock()


class Plugin:
    def __init__(self):
        self._handlers = {}
        self._actions = {}
        self._waiting = {}
        self._ids = itertools.count(1)
        self.state = {}  # последний снимок: track, playing, positionMs, ...
        self._threads = []

    # ---------- приём событий ----------

    def on(self, event_type):
        """Декоратор: событие hello | track | state | stopped | search | bye."""
        def deco(fn):
            self._handlers.setdefault(event_type, []).append(fn)
            return fn
        return deco

    def on_action(self, action_id):
        """Декоратор: нажата кнопка плагина с этим id."""
        def deco(fn):
            self._actions[action_id] = fn
            return fn
        return deco

    def on_search(self, fn=None):
        """Декоратор: запрос поиска из приложения (@p.on_search или @p.on('search'))."""
        def deco(f):
            self._handlers.setdefault("search", []).append(f)
            return f
        return deco(fn) if fn is not None else deco

    # ---------- команды ----------

    def send(self, cmd, **fields):
        with _out_lock:
            sys.stdout.write(json.dumps({"cmd": cmd, **fields}, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def log(self, text):
        self.send("log", text=str(text))

    def toast(self, text):
        self.send("toast", text=str(text))

    def status(self, text):
        """Показать (строка) или скрыть (None) индикатор загрузки."""
        self.send("status", text=text)

    def register_search(self, title):
        """Зарегистрировать плагин во вкладке «Поиск»."""
        self.send("register_search", title=title)

    def reply(self, req_id, ok=True, data=None, error=None):
        """Ответить на входящий запрос от приложения (например, search)."""
        fields = {"reqId": req_id, "ok": bool(ok)}
        if data is not None or ok:
            fields["data"] = data
        if error is not None:
            fields["error"] = str(error)
        self.send("reply", **fields)

    def add_action(self, action_id, title, icon="extension", where="player"):
        """where: player | track | search | both."""
        self.send("add_action", id=action_id, title=title, icon=icon, where=where)

    def remove_action(self, action_id):
        self.send("remove_action", id=action_id)

    def home_section(self, section_id, title, items):
        """items: [{"title": ..., "subtitle": ..., "action": "id"} или {"title": ..., "tracks": [...]}]; None — убрать."""
        self.send("home_section", id=section_id, title=title, items=items)

    def set_theme(self, theme):
        """Живая тема поверх остальных (None — снять)."""
        self.send("set_theme", theme=theme)

    def play_tracks(self, tracks, start=0, title=None):
        """tracks: [{"artist": ..., "title": ...} | {"path": ...} | {"serverId": ...} | {"streamUrl": ...}]."""
        self.send("play_tracks", tracks=tracks, start=start, **({"title": title} if title else {}))

    def queue_add(self, tracks, next=False):
        """Добавить треки в очередь (в конец или сразу после текущего при next=True)."""
        self.send("queue_add", tracks=tracks, next=bool(next))

    def _ask(self, cmd, timeout=10, **fields):
        req_id = next(self._ids)
        box = queue.Queue(maxsize=1)
        self._waiting[req_id] = box
        self.send(cmd, reqId=req_id, **fields)
        try:
            resp = box.get(timeout=timeout)
        finally:
            self._waiting.pop(req_id, None)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error"))
        return resp.get("data")

    def request(self, what, timeout=10):
        """Синхронный запрос: current | queue | library | liked | playlists | history | library_folder."""
        return self._ask("request", timeout=timeout, what=what)

    def library_folder(self, timeout=10):
        """Путь к папке локальной медиатеки."""
        return self.request("library_folder", timeout=timeout)

    def add_file(self, path, timeout=10):
        """Проиндексировать скачанный файл в медиатеке и вернуть объект трека."""
        return self._ask("add_file", timeout=timeout, path=path)

    def rescan(self, timeout=30):
        """Пересканировать папку медиатеки."""
        return self._ask("rescan", timeout=timeout)

    def prompt(self, title, hint=None, initial=None, timeout=120):
        """Показать диалог ввода текста. Возвращает строку или None при отмене."""
        fields = {"title": title}
        if hint is not None:
            fields["hint"] = hint
        if initial is not None:
            fields["initial"] = initial
        data = self._ask("prompt", timeout=timeout, **fields)
        if not data or data.get("cancelled"):
            return None
        return data.get("text")

    # ---------- цикл ----------

    def run(self):
        """Читает события из stdin. Обработчики выполняются в отдельных потоках,
        поэтому внутри них можно делать request() и ждать ответа.
        Перед выходом (bye или конец ввода) ждёт работающие обработчики до 2 секунд."""
        try:
            self._loop()
        finally:
            for t in list(self._threads):
                t.join(timeout=2)

    def _spawn(self, fn, ev):
        t = threading.Thread(target=self._safe, args=(fn, ev), daemon=True)
        self._threads = [x for x in self._threads if x.is_alive()] + [t]
        t.start()

    def _loop(self):
        for line in sys.stdin:
            try:
                ev = json.loads(line.lstrip('\ufeff'))  # BOM от некоторых оболочек
            except ValueError:
                continue
            t = ev.get("type")
            if t == "response":
                box = self._waiting.get(ev.get("reqId"))
                if box:
                    box.put(ev)
                continue
            if t in ("track", "state", "stopped"):
                self.state = ev
            if t == "action":
                fn = self._actions.get(ev.get("id"))
                if fn:
                    self._spawn(fn, ev)
                continue
            if t == "search":
                handlers = self._handlers.get("search", [])
                if handlers:
                    for fn in handlers:
                        self._spawn(fn, ev)
                elif ev.get("reqId") is not None:
                    self.reply(ev.get("reqId"), ok=False, error="search handler not registered")
                continue
            for fn in self._handlers.get(t, []):
                self._spawn(fn, ev)
            if t == "bye":
                return

    def _safe(self, fn, ev):
        try:
            fn(ev)
        except Exception as e:  # ошибка плагина не должна его ронять
            print(f"{fn.__name__}: {e}", file=sys.stderr, flush=True)
