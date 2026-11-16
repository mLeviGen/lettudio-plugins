"""Таймер сна: кнопка в плеере (15 → 30 → 60 мин → выкл) и секция на главной.
Пример плагина Lettudio: кнопки, секции, уведомления, команды плееру.
"""
import threading
import time

from lettudio import Plugin

p = Plugin()
CHOICES = [15, 30, 60, 0]
state = {"minutes": 0, "timer": None, "ends": 0}


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
        p.toast(f"Таймер сна: пауза через {minutes} мин")
    else:
        p.toast("Таймер сна выключен")
    refresh()


def fire():
    p.send("pause")
    p.toast("Спокойной ночи — музыка на паузе")
    state["minutes"] = 0
    state["timer"] = None
    refresh()


def refresh():
    m = state["minutes"]
    p.add_action("cycle", f"Сон: {m} мин" if m else "Таймер сна", icon="bedtime", where="player")
    p.home_section("sleep", "Таймер сна", [
        {"title": f"{c} мин" if c else "Выключить", "action": f"set:{c}",
         **({"subtitle": "сейчас"} if c == m and m else {})}
        for c in CHOICES
    ])


@p.on("hello")
def hello(_):
    refresh()


@p.on_action("cycle")
def cycle(_):
    i = CHOICES.index(state["minutes"]) if state["minutes"] in CHOICES else len(CHOICES) - 1
    set_timer(CHOICES[(i + 1) % len(CHOICES)])


for c in CHOICES:
    p.on_action(f"set:{c}")(lambda _, c=c: set_timer(c))

p.run()
