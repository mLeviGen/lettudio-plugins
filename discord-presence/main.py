"""Lettudio → Discord Rich Presence.

Без внешних зависимостей: подключается к локальному Discord через IPC (named pipe на Windows,
unix-сокет на Linux/macOS). События от Lettudio читает построчно из stdin.
Discord закрыт или перезапущен — плагин тихо переподключится при следующем событии.
"""
import json
import os
import socket
import struct
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
ACTIVITY_LISTENING = 2


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
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


class DiscordIPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.conn = None

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

    def connect(self):
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
        except OSError as e:
            log(f"handshake не удался: {e}")
            self.close()
            return False

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except OSError:
            pass
        self.conn = None

    def set_activity(self, activity):
        for _ in range(2):  # одна попытка переподключения
            if not self.connect():
                return
            try:
                self._send(OP_FRAME, {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": os.getpid(), "activity": activity},
                    "nonce": str(uuid.uuid4()),
                })
                self._recv()
                return
            except OSError:
                self.close()


def build_activity(msg, cfg):
    t = msg.get("track")
    if not t or not msg.get("playing"):
        return None  # пауза или стоп — статус убираем
    now = time.time()
    pos = msg.get("positionMs", 0) / 1000
    dur = (msg.get("durationMs") or t.get("durationMs") or 0) / 1000
    act = {
        "type": ACTIVITY_LISTENING,
        "details": t["title"][:128],
        "state": t["artist"][:128],
        "timestamps": {"start": int(now - pos)},
    }
    if dur > 0:
        act["timestamps"]["end"] = int(now - pos + dur)
    if cfg.get("large_image"):
        act["assets"] = {"large_image": cfg["large_image"]}
        if cfg.get("show_album") and t.get("album"):
            act["assets"]["large_text"] = t["album"][:128]
    return act


def toast_missing_client_id():
    text = MSG_FILL_CLIENT_ID.get(LANG, MSG_FILL_CLIENT_ID["ru"])
    print(json.dumps({"cmd": "toast", "text": text}, ensure_ascii=False), flush=True)


def main():
    global LANG
    cfg = load_config()
    if not cfg.get("client_id"):
        log("Заполни client_id в config.json (Discord Developer Portal → New Application).")
        toast_missing_client_id()
    ipc = DiscordIPC(cfg.get("client_id", ""))

    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get("type")
        if kind in ("hello", "lang") and isinstance(msg.get("lang"), str) and msg["lang"]:
            new_lang = msg["lang"].lower()
            if kind == "hello" and not cfg.get("client_id") and new_lang != LANG:
                LANG = new_lang
                toast_missing_client_id()  # hello приходит после старта: повторим подсказку на нужном языке
            LANG = new_lang
        if kind == "bye":
            ipc.set_activity(None)
            ipc.close()
            return
        if kind in ("track", "state", "stopped") and cfg.get("client_id"):
            ipc.set_activity(build_activity(msg, cfg))


if __name__ == "__main__":
    main()
