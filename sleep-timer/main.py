"""Таймер сна: кнопка в плеере (15 → 30 → 60 мин → выкл) и секция на главной.
Пример плагина Lettudio: кнопки, секции, уведомления, команды плееру.
Тексты на языке интерфейса: p.lang приходит в hello/lang, строки — в таблице STRINGS.
"""
import threading
import time

from lettudio import Plugin

p = Plugin()
CHOICES = [15, 30, 60, 0]
state = {"minutes": 0, "timer": None, "ends": 0}

# Ключ — русская строка (язык по умолчанию), значения — переводы.
STRINGS = {
    "en": {
        "Таймер сна: пауза через {n} мин": "Sleep timer: pause in {n} min",
        "Таймер сна выключен": "Sleep timer is off",
        "Спокойной ночи — музыка на паузе": "Good night — music paused",
        "Сон: {n} мин": "Sleep: {n} min",
        "Таймер сна": "Sleep timer",
        "{n} мин": "{n} min",
        "Выключить": "Turn off",
        "сейчас": "now",
    },
    "de": {
        "Таймер сна: пауза через {n} мин": "Schlaftimer: Pause in {n} Min.",
        "Таймер сна выключен": "Schlaftimer ist aus",
        "Спокойной ночи — музыка на паузе": "Gute Nacht — Musik pausiert",
        "Сон: {n} мин": "Schlaf: {n} Min.",
        "Таймер сна": "Schlaftimer",
        "{n} мин": "{n} Min.",
        "Выключить": "Ausschalten",
        "сейчас": "jetzt",
    },
}
T = p.translator(STRINGS)


def set_timer(minutes):
    if state["timer"]:
        state["timer"].cancel()
    state["minutes"] = minutes
    state["timer"] = None
    if minutes:
        state["ends"] = time.time() + minutes * 60
        state["timer"] = threading.Timer(minutes * 60, fire)
        state["timer"].daemon = True
        state["timer"].start()
        p.toast(T("Таймер сна: пауза через {n} мин", n=minutes))
    else:
        p.toast(T("Таймер сна выключен"))
    refresh()


def fire():
    p.send("pause")
    p.toast(T("Спокойной ночи — музыка на паузе"))
    state["minutes"] = 0
    state["timer"] = None
    refresh()


def refresh():
    m = state["minutes"]
    p.add_action("cycle", T("Сон: {n} мин", n=m) if m else T("Таймер сна"), icon="bedtime", where="player")
    p.home_section("sleep", T("Таймер сна"), [
        {"title": T("{n} мин", n=c) if c else T("Выключить"), "action": f"set:{c}",
         **({"subtitle": T("сейчас")} if c == m and m else {})}
        for c in CHOICES
    ])


@p.on("hello")
def hello(_):
    refresh()


@p.on("lang")
def lang_changed(_):
    refresh()  # перерегистрируем кнопку и секцию на новом языке


@p.on_action("cycle")
def cycle(_):
    i = CHOICES.index(state["minutes"]) if state["minutes"] in CHOICES else len(CHOICES) - 1
    set_timer(CHOICES[(i + 1) % len(CHOICES)])


for c in CHOICES:
    p.on_action(f"set:{c}")(lambda _, c=c: set_timer(c))

p.run()
