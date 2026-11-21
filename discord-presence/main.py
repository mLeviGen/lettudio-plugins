"""Lettudio → Discord Rich Presence.

Без внешних зависимостей: подключается к локальному Discord через IPC (named pipe на Windows,
unix-сокет на Linux/macOS). События от Lettudio читает построчно из stdin.

Настраивать ничего не нужно: ID приложения «Lettudio» в Discord встроен (свой можно
задать в config.json → client_id). Discord запущен позже Lettudio или перезапущен —
плагин сам найдёт его в течение 15 секунд и вернёт статус.
"""
import json
import os
import socket
import struct
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
ACTIVITY_LISTENING = 2
RETRY_SECONDS = 15

# Приложение «Lettudio» в Discord Developer Portal: его имя видно в статусе.
DEFAULT_CLIENT_ID = "1573689547903074504"

# Язык интерфейса приложения (ru | en | de): LETTUDIO_LANG, затем события hello / lang.
LANG = (os.environ.get("LETTUDIO_LANG") or "ru").lower()
MSG_FILL_CLIENT_ID = {
    "ru": "Discord Presence: заполни client_id в config.json",
    "en": "Discord Presence: fill in client_id in config.json",
    "de": "Discord Presence: client_id in config.json eintragen",
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if not str(cfg.get("client_id") or "").strip():
        cfg["client_id"] = DEFAULT_CLIENT_ID
    return cfg


class DiscordIPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.conn = None
        self.lock = threading.Lock()
        self.activity = None  # что показать сейчас (None — статус убран)

    # --- транспорт ---
    def _open(self):
        for i in range(10):
            try:
                if os.name == "nt":
                    return open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                base = (os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR")
                        or os.environ.get("TMP") or "/tmp")
                s = socket.socket(socket.AF_UNIX)
                s.connect(os.path.join(base, f"discord-ipc-{i}"))
                return s.makefile("rwb", buffering=0)
            except OSError:
                continue
        return None

    def _send(self, op, payload):
        data = json.dumps(payload).encode("utf-8")
        self.conn.write(struct.pack("<II", op, len(data)) + data)
        self.conn.flush()

    def _recv(self):
        header = self.conn.read(8)
        if len(header) < 8:
            raise OSError("discord closed the pipe")
        op, length = struct.unpack("<II", header)
        return op, json.loads(self.conn.read(length).decode("utf-8"))

    def _connect(self):
        if self.conn:
            return True
        self.conn = self._open()
        if not self.conn:
            return False
        try:
            self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
            op, data = self._recv()
            if op == OP_CLOSE:
                raise OSError(data)
            log(f"подключено к Discord как {data.get('data', {}).get('user', {}).get('username', '?')}")
            return True
        except (OSError, ValueError) as e:
            log(f"handshake не удался: {e}")
            self._close()
            return False

    def _close(self):
        try:
            if self.conn:
                self.conn.close()
        except OSError:
            pass
        self.conn = None

    def _push(self):
        for _ in range(2):  # одна попытка переподключения
            if not self._connect():
                return False
            try:
                self._send(OP_FRAME, {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": os.getpid(), "activity": self.activity},
                    "nonce": str(uuid.uuid4()),
                })
                self._recv()
                return True
            except (OSError, ValueError):
                self._close()
        return False

    # --- снаружи ---
    def set_activity(self, activity):
        with self.lock:
            self.activity = activity
            self._push()

    def retry_if_disconnected(self):
        """Discord закрыт → ничего; запустили или перезапустили → вернуть статус."""
        with self.lock:
            if self.conn is None and self.activity is not None:
                self._push()

    def shutdown(self):
        with self.lock:
            self.activity = None
            if self.conn:
                self._push()
            self._close()


def build_activity(msg, cfg):
    t = msg.get("track")
    if not t or not msg.get("playing"):
        return None  # пауза или стоп — статус убираем
    now = time.time()
    pos = (msg.get("positionMs") or 0) / 1000
    dur = (msg.get("durationMs") or t.get("durationMs") or 0) / 1000
    act = {
        "type": ACTIVITY_LISTENING,
        "details": (t.get("title") or "—")[:128],
        "state": (t.get("artist") or "—")[:128],
        "timestamps": {"start": int(now - pos)},
    }
    if dur > 0:
        act["timestamps"]["end"] = int(now - pos + dur)
    # Обложка по ссылке (Discord показывает внешние картинки), иначе иконка приложения.
    cover = str(t.get("coverArt") or "")
    image = cover if cover.startswith("https://") and len(cover) <= 256 else cfg.get("large_image")
    if image:
        act["assets"] = {"large_image": image}
        if cfg.get("show_album", True) and t.get("album"):
            act["assets"]["large_text"] = t["album"][:128]
    return act


def toast_missing_client_id():
    text = MSG_FILL_CLIENT_ID.get(LANG, MSG_FILL_CLIENT_ID["ru"])
    print(json.dumps({"cmd": "toast", "text": text}, ensure_ascii=False), flush=True)


def main():
    global LANG
    cfg = load_config()
    has_id = bool(cfg.get("client_id"))
    if not has_id:
        log("Нет client_id: задай его в config.json (Discord Developer Portal → New Application).")
        toast_missing_client_id()
    ipc = DiscordIPC(cfg.get("client_id", ""))

    def retry_loop():
        while True:
            time.sleep(RETRY_SECONDS)
            ipc.retry_if_disconnected()

    if has_id:
        threading.Thread(target=retry_loop, daemon=True).start()

    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get("type")
        if kind in ("hello", "lang") and isinstance(msg.get("lang"), str) and msg["lang"]:
            new_lang = msg["lang"].lower()
            if kind == "hello" and not has_id and new_lang != LANG:
                LANG = new_lang
                toast_missing_client_id()  # hello приходит после старта: повторим подсказку на нужном языке
            LANG = new_lang
        if kind == "bye":
            ipc.shutdown()
            return
        if kind in ("track", "state", "stopped") and has_id:
            ipc.set_activity(build_activity(msg, cfg))


if __name__ == "__main__":
    main()
