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
import os
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
        # Язык интерфейса приложения: ru | en | de. Берётся из LETTUDIO_LANG, затем из
        # событий hello / lang (при смене языка приходит событие lang).
        self.lang = (os.environ.get("LETTUDIO_LANG") or "ru").lower()
        self._threads = []

    # ---------- приём событий ----------

    def on(self, event_type):
        """Декоратор: событие hello | lang | track | state | stopped | bye."""
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

    def translator(self, table):
        """Возвращает функцию t(text, **fmt): text — русская строка (она же ключ),
        table — {"en": {"русская строка": "English"}, "de": {...}}. Нет перевода — русская строка.
        Подстановки {name} делаются через str.format. Язык берётся из self.lang на каждом вызове."""
        def t(text, **fmt):
            s = (table.get(self.lang) or {}).get(text)
            if not s and self.lang == "de":  # нет немецкого — английский
                s = (table.get("en") or {}).get(text)
            s = s or text
            return s.format(**fmt) if fmt else s
        return t

    # ---------- команды ----------

    def send(self, cmd, **fields):
        with _out_lock:
            sys.stdout.write(json.dumps({"cmd": cmd, **fields}, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def log(self, text):
        self.send("log", text=str(text))

    def toast(self, text):
        self.send("toast", text=str(text))

    def add_action(self, action_id, title, icon="extension", where="player"):
        """where: player | track | both."""
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
        """tracks: [{"artist": ..., "title": ...} | {"path": ...} | {"serverId": ...}]."""
        self.send("play_tracks", tracks=tracks, start=start, **({"title": title} if title else {}))

    def request(self, what, timeout=10):
        """Синхронный запрос: current | queue | library | liked | playlists | history."""
        req_id = next(self._ids)
        box = queue.Queue(maxsize=1)
        self._waiting[req_id] = box
        self.send("request", reqId=req_id, what=what)
        try:
            resp = box.get(timeout=timeout)
        finally:
            self._waiting.pop(req_id, None)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error"))
        return resp.get("data")

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
            if t in ("hello", "lang") and isinstance(ev.get("lang"), str) and ev["lang"]:
                self.lang = ev["lang"].lower()
            if t in ("track", "state", "stopped"):
                self.state = ev
            if t == "action":
                fn = self._actions.get(ev.get("id"))
                if fn:
                    self._spawn(fn, ev)
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
