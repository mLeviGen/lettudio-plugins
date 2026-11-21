"""Плагин Lettudio: потоковое воспроизведение и скачивание аудио через yt-dlp
с поиском метаданных в каталогах (Deezer, iTunes, MusicBrainz) и источниках (YouTube, SoundCloud).

Возможности:
- Кнопка в плеере «Поток / URL» для запуска потока по ссылке или текстовому поиску.
- Секция на главной «Потоковое аудио»: воспроизведение, добавление в очередь,
  скачивание по запросу, скачивание текущего потока и до 5 недавних потоков.
- Вкладка «Поиск»: параллельный поиск в каталогах (Deezer, iTunes, MusicBrainz)
  и потоковых источниках (YouTube + SoundCloud) с очисткой названий,
  ранжированием и тегированием через mutagen при скачивании.
"""
import base64
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request

# На Windows при запуске через pipe stdout/stdin могут использовать локальную кодовую страницу,
# поэтому принудительно включаем UTF-8 до любых вызовов SDK.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from lettudio import Plugin

p = Plugin()

# Тексты для пользователя. Ключ — русская строка; язык приложения приходит в hello/lang.
STRINGS = {
    "en": {
        "Музыка и потоки (YT / SoundCloud)": "Music and streams (YT / SoundCloud)",
        "Поток / URL": "Stream / URL",
        "Потоковое аудио": "Streaming audio",
        "Воспроизвести URL или поиск": "Play URL or search",
        "Добавить в очередь": "Add to queue",
        "Скачать в медиатеку": "Download to library",
        "Скачать текущий поток": "Download current stream",
        "недавний": "recent",
        "{source}: превышено время ожидания ({sec} с)": "{source}: timed out ({sec} s)",
        "{source}: ошибка запуска yt-dlp ({e})": "{source}: failed to start yt-dlp ({e})",
        "{source}: некорректный JSON ({e})": "{source}: invalid JSON ({e})",
        "код возврата {code}": "exit code {code}",
        "yt-dlp не найден в PATH. Установите yt-dlp для поиска и потоков.": "yt-dlp not found in PATH. Install yt-dlp for search and streaming.",
        "yt-dlp не найден в PATH. Установите yt-dlp для поиска.": "yt-dlp not found in PATH. Install yt-dlp for search.",
        "yt-dlp не найден в PATH. Установите yt-dlp для скачивания.": "yt-dlp not found in PATH. Install yt-dlp for downloading.",
        "По запросу ничего не найдено": "Nothing found for this query",
        "Пустой запрос": "Empty query",
        "{source}: превышено время ожидания yt-dlp ({sec} с)": "{source}: yt-dlp timed out ({sec} s)",
        "Ошибка запуска yt-dlp: {e}": "Failed to start yt-dlp: {e}",
        "Некорректный JSON от yt-dlp: {e}": "Invalid JSON from yt-dlp: {e}",
        "Неожиданный ответ yt-dlp": "Unexpected yt-dlp response",
        "Найден длинный сборник или запись без длительности вместо трека. Уточните запрос или откройте нужную запись по ссылке.": "Found a long compilation or an entry without duration instead of a track. Refine the query or open the right entry by link.",
        "Не удалось получить прямой URL аудиопотока": "Could not get a direct audio stream URL",
        "Источник": "The source",
        "{source} не ответил вовремя. Повторите запуск позже или выберите другую запись.": "{source} did not respond in time. Try again later or pick another entry.",
        "SoundCloud не ответил. Ищу эту запись на YouTube...": "SoundCloud did not respond. Looking for this track on YouTube...",
        "Поиск в каталогах и потоках...": "Searching catalogs and streams...",
        "Получение потока...": "Getting the stream...",
        "Скачивание в медиатеку...": "Downloading to library...",
        "В очереди: {label}": "Queued: {label}",
        "Играет: {label}": "Playing: {label}",
        "Ошибка доступа к медиатеке: {e}": "Library access error: {e}",
        "Сначала выберите папку локальной медиатеки в настройках Lettudio": "First choose the local library folder in Lettudio settings",
        "Ошибка папки медиатеки: {e}": "Library folder error: {e}",
        "Ошибка скачивания: {e}": "Download error: {e}",
        "Не найден подходящий трек: {e}": "No suitable track found: {e}",
        "Превышено время скачивания ({sec} с)": "Download timed out ({sec} s)",
        "Файл не найден после скачивания": "File not found after download",
        "Скачано в медиатеку: {title}": "Downloaded to library: {title}",
        "Файл скачан, но не проиндексирован: {e}": "File downloaded but not indexed: {e}",
        "Нет данных о треке": "No track data",
        "Трек уже находится в локальной медиатеке": "The track is already in the local library",
        "У этого трека нет потоковой ссылки для скачивания": "This track has no stream link to download",
        "Не найдена исходная ссылка трека": "Source link of the track not found",
        "Нет данных для поиска потока": "No data to look up the stream",
        "Воспроизвести поток": "Play stream",
        "URL (YouTube, радио, .mp3) или текст для поиска": "URL (YouTube, radio, .mp3) or search text",
        "Не передана ссылка для воспроизведения": "No link to play was provided",
        "Не передана ссылка для скачивания": "No link to download was provided",
        "https://... или исполнитель — название": "https://... or artist — title",
        "Добавить поток в очередь": "Add stream to queue",
        "Трек не выбран": "No track selected",
        "Сейчас ничего не играет": "Nothing is playing right now",
        "Запись устарела, обновите список": "This entry is outdated, refresh the list",
        "Не найдена ссылка для этого потока": "No link found for this stream",
    },
    "de": {
        "Музыка и потоки (YT / SoundCloud)": "Musik und Streams (YT / SoundCloud)",
        "Поток / URL": "Stream / URL",
        "Потоковое аудио": "Audio-Streaming",
        "Воспроизвести URL или поиск": "URL abspielen oder suchen",
        "Добавить в очередь": "Zur Warteschlange hinzufügen",
        "Скачать в медиатеку": "In die Mediathek herunterladen",
        "Скачать текущий поток": "Aktuellen Stream herunterladen",
        "недавний": "zuletzt",
        "{source}: превышено время ожидания ({sec} с)": "{source}: Zeitüberschreitung ({sec} s)",
        "{source}: ошибка запуска yt-dlp ({e})": "{source}: yt-dlp konnte nicht gestartet werden ({e})",
        "{source}: некорректный JSON ({e})": "{source}: ungültiges JSON ({e})",
        "код возврата {code}": "Exit-Code {code}",
        "yt-dlp не найден в PATH. Установите yt-dlp для поиска и потоков.": "yt-dlp wurde im PATH nicht gefunden. Installiere yt-dlp für Suche und Streaming.",
        "yt-dlp не найден в PATH. Установите yt-dlp для поиска.": "yt-dlp wurde im PATH nicht gefunden. Installiere yt-dlp für die Suche.",
        "yt-dlp не найден в PATH. Установите yt-dlp для скачивания.": "yt-dlp wurde im PATH nicht gefunden. Installiere yt-dlp zum Herunterladen.",
        "По запросу ничего не найдено": "Zu dieser Anfrage wurde nichts gefunden",
        "Пустой запрос": "Leere Anfrage",
        "{source}: превышено время ожидания yt-dlp ({sec} с)": "{source}: Zeitüberschreitung bei yt-dlp ({sec} s)",
        "Ошибка запуска yt-dlp: {e}": "yt-dlp konnte nicht gestartet werden: {e}",
        "Некорректный JSON от yt-dlp: {e}": "Ungültiges JSON von yt-dlp: {e}",
        "Неожиданный ответ yt-dlp": "Unerwartete Antwort von yt-dlp",
        "Найден длинный сборник или запись без длительности вместо трека. Уточните запрос или откройте нужную запись по ссылке.": "Statt eines Titels wurde ein langer Sampler oder ein Eintrag ohne Dauer gefunden. Präzisiere die Anfrage oder öffne den passenden Eintrag per Link.",
        "Не удалось получить прямой URL аудиопотока": "Die direkte Audio-Stream-URL konnte nicht ermittelt werden",
        "Источник": "Die Quelle",
        "{source} не ответил вовремя. Повторите запуск позже или выберите другую запись.": "{source} hat nicht rechtzeitig geantwortet. Versuche es später erneut oder wähle einen anderen Eintrag.",
        "SoundCloud не ответил. Ищу эту запись на YouTube...": "SoundCloud hat nicht geantwortet. Suche den Titel auf YouTube...",
        "Поиск в каталогах и потоках...": "Suche in Katalogen und Streams...",
        "Получение потока...": "Stream wird abgerufen...",
        "Скачивание в медиатеку...": "Download in die Mediathek...",
        "В очереди: {label}": "In der Warteschlange: {label}",
        "Играет: {label}": "Läuft: {label}",
        "Ошибка доступа к медиатеке: {e}": "Zugriffsfehler auf die Mediathek: {e}",
        "Сначала выберите папку локальной медиатеки в настройках Lettudio": "Wähle zuerst den Ordner der lokalen Mediathek in den Lettudio-Einstellungen",
        "Ошибка папки медиатеки: {e}": "Fehler beim Mediathek-Ordner: {e}",
        "Ошибка скачивания: {e}": "Download-Fehler: {e}",
        "Не найден подходящий трек: {e}": "Kein passender Titel gefunden: {e}",
        "Превышено время скачивания ({sec} с)": "Zeitüberschreitung beim Download ({sec} s)",
        "Файл не найден после скачивания": "Datei nach dem Download nicht gefunden",
        "Скачано в медиатеку: {title}": "In die Mediathek heruntergeladen: {title}",
        "Файл скачан, но не проиндексирован: {e}": "Datei heruntergeladen, aber nicht indiziert: {e}",
        "Нет данных о треке": "Keine Titeldaten",
        "Трек уже находится в локальной медиатеке": "Der Titel ist bereits in der lokalen Mediathek",
        "У этого трека нет потоковой ссылки для скачивания": "Dieser Titel hat keinen Stream-Link zum Herunterladen",
        "Не найдена исходная ссылка трека": "Ursprungslink des Titels nicht gefunden",
        "Нет данных для поиска потока": "Keine Daten zur Stream-Suche",
        "Воспроизвести поток": "Stream abspielen",
        "URL (YouTube, радио, .mp3) или текст для поиска": "URL (YouTube, Radio, .mp3) oder Suchtext",
        "Не передана ссылка для воспроизведения": "Es wurde kein Link zum Abspielen übergeben",
        "Не передана ссылка для скачивания": "Es wurde kein Link zum Herunterladen übergeben",
        "https://... или исполнитель — название": "https://... oder Interpret — Titel",
        "Добавить поток в очередь": "Stream zur Warteschlange hinzufügen",
        "Трек не выбран": "Kein Titel ausgewählt",
        "Сейчас ничего не играет": "Gerade läuft nichts",
        "Запись устарела, обновите список": "Der Eintrag ist veraltet, aktualisiere die Liste",
        "Не найдена ссылка для этого потока": "Für diesen Stream wurde kein Link gefunden",
    },
}
T = p.translator(STRINGS)

PLUGIN_DIR = Path(__file__).resolve().parent
RECENT_FILE = PLUGIN_DIR / "recent.json"
MAX_RECENT_HOME = 5
MAX_RECENT_STORE = 50
MAX_META_CACHE = 250
DIRECT_AUDIO_EXTS = (".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav")
CATALOG_TIMEOUT_SEC = 4.5
SEARCH_TIMEOUT_SEC = 20
RESOLVE_TIMEOUT_SEC = 25
DOWNLOAD_TIMEOUT_SEC = 300
COVER_TIMEOUT_SEC = 6
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
USER_AGENT = "Lettudio-StreamYT/1.1"

_state_lock = threading.Lock()
_recent_items = []           # список словарей недавних потоков (новые в начале)
_stream_to_page = {}         # streamUrl -> webpage_url
_meta_cache = OrderedDict()  # normalized page_url -> canonical metadata dict

# Шумовые пометки видео-загрузок (удаляются только из скобок/хвостов, не затрагивая версии вроде Remix/Acoustic/Live)
_NOISE_WORDS = {
    "official", "music", "video", "lyric", "lyrics", "audio", "visualizer",
    "visualiser", "hd", "4k", "hq", "1080p", "720p", "explicit", "clean",
    "traducao", "tradução", "legendado", "sub", "subs", "subtitles",
    "espanol", "español", "rus", "mv", "m/v", "clip", "original", "full",
    "high", "quality", "remastered", "cc", "subtitled", "letra", "track",
}
_BRACKET_RE = re.compile(r"\s*[\(\[\{]([^\)\]\}]*)[\)\]\}]")
_TRAILING_NOISE_RE = re.compile(
    r"\s*(?:\||//)\s*(?:official\b.*|music\s+video\b.*|lyric\s+video\b.*|audio\b.*|lyrics\b.*)\s*$",
    re.IGNORECASE,
)
_TOPIC_RE = re.compile(r"\s*-\s*topic$", re.IGNORECASE)
_VERSION_QUALIFIER_RE = re.compile(
    r"^(?:part|pt\.?|vol\.?|remix|edit|version|ver\.?|live|acoustic|"
    r"instrumental|intro|outro|skit|interlude|demo|remaster)\b",
    re.IGNORECASE,
)

# Нежелательные слова, которые пессимизируются, если пользователь явно не искал их
_JUNK_PENALTIES = (
    ("full album", 0.60),
    ("1 hour", 0.60),
    ("10 hours", 0.60),
    ("reaction", 0.55),
    ("nightcore", 0.55),
    ("slowed", 0.50),
    ("sped up", 0.50),
    ("speed up", 0.50),
    ("reverb", 0.45),
    ("8d audio", 0.55),
    ("mashup", 0.50),
    ("megamix", 0.50),
    ("karaoke", 0.50),
    ("tutorial", 0.55),
    ("teaser", 0.45),
    ("trailer", 0.45),
    ("snippet", 0.45),
    ("instrumental", 0.40),
    ("remake", 0.40),
    ("cover", 0.35),
    ("live", 0.35),
    ("concert", 0.40),
    ("mix", 0.35),
    ("remix", 0.30),
    ("loop", 0.40),
)
_LONG_OK_HINTS = ("album", "альбом", "mix", "микс", "live", "лайв", "concert", "концерт", "set", "сет", "hour", "hours", "час", "часа", "часов", "podcast", "подкаст", "playlist", "плейлист")


def _is_http_url(text):
    lower = text.strip().lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _is_direct_audio_url(url):
    if not _is_http_url(url):
        return False
    try:
        path = urllib.parse.urlparse(url).path.lower()
    except Exception:
        return False
    return path.endswith(DIRECT_AUDIO_EXTS)


def _normalize_url_key(url):
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parsed = urllib.parse.urlparse(u)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host in ("youtube.com", "m.youtube.com", "music.youtube.com") and parsed.path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            vid = (qs.get("v") or [None])[0]
            if vid:
                return f"https://www.youtube.com/watch?v={vid}"
        if host == "youtu.be" and parsed.path.strip("/"):
            vid = parsed.path.strip("/").split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        return urllib.parse.urlunparse((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", parsed.query, ""))
    except Exception:
        return u


def _cache_meta_put(page_url, meta):
    key = _normalize_url_key(page_url)
    if not key or not isinstance(meta, dict):
        return
    clean = {
        "title": (meta.get("title") or "").strip(),
        "artist": (meta.get("artist") or "").strip(),
        "album": (meta.get("album") or "").strip(),
        "year": str(meta.get("year") or "").strip(),
        "genre": (meta.get("genre") or "").strip(),
        "coverArt": (meta.get("coverArt") or "").strip(),
        "durationMs": int(meta.get("durationMs") or 0),
    }
    with _state_lock:
        if key in _meta_cache:
            _meta_cache.move_to_end(key)
        _meta_cache[key] = clean
        while len(_meta_cache) > MAX_META_CACHE:
            _meta_cache.popitem(last=False)


def _cache_meta_get(page_url):
    key = _normalize_url_key(page_url)
    if not key:
        return None
    with _state_lock:
        val = _meta_cache.get(key)
        if val is not None:
            _meta_cache.move_to_end(key)
            return dict(val)
    return None


def _normalize_text(text):
    if not text:
        return ""
    s = str(text).lower().replace("_", " ")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def _tokenize(text):
    norm = _normalize_text(text)
    return norm.split() if norm else []


def _fuzzy_token_score(q_tok, cand_tokens):
    if not q_tok or not cand_tokens:
        return 0.0
    if q_tok in cand_tokens:
        return 1.0
    best = 0.0
    for c_tok in cand_tokens:
        if len(q_tok) >= 3 and len(c_tok) >= 3 and (c_tok.startswith(q_tok) or q_tok.startswith(c_tok)):
            score = 0.86
        else:
            ratio = SequenceMatcher(None, q_tok, c_tok).ratio()
            score = ratio if ratio >= 0.72 else 0.0
        if score > best:
            best = score
    return best


def _query_similarity(query, artist, title):
    q_norm = _normalize_text(query)
    if not q_norm:
        return 0.0
    q_tokens = q_norm.split()
    a_tokens = _tokenize(artist)
    t_tokens = _tokenize(title)
    all_tokens = a_tokens + t_tokens
    if not all_tokens:
        return 0.0

    token_scores = [_fuzzy_token_score(qt, all_tokens) for qt in q_tokens]
    coverage = sum(token_scores) / len(q_tokens)

    # Проверяем, совпали ли отдельно артист и название (важно при >= 2 токенах в запросе)
    artist_hit = max((_fuzzy_token_score(qt, a_tokens) for qt in q_tokens), default=0.0) if a_tokens else 0.0
    title_hit = max((_fuzzy_token_score(qt, t_tokens) for qt in q_tokens), default=0.0) if t_tokens else 0.0
    both_bonus = 0.08 if (len(q_tokens) >= 2 and artist_hit >= 0.75 and title_hit >= 0.75) else 0.0

    cand_at = _normalize_text(f"{artist} {title}")
    cand_ta = _normalize_text(f"{title} {artist}")
    seq_sim = max(
        SequenceMatcher(None, q_norm, cand_at).ratio(),
        SequenceMatcher(None, q_norm, cand_ta).ratio(),
    )

    # Штраф, если все токены совпали только в одном длинном списке лишних слов
    extra_len_penalty = 0.0
    if len(t_tokens) > len(q_tokens) + 3:
        extra_len_penalty = min(0.15, 0.03 * (len(t_tokens) - len(q_tokens) - 3))

    return max(0.0, min(1.2, 0.65 * coverage + 0.35 * seq_sim + both_bonus - extra_len_penalty))


def _is_noise_bracket(inner_text):
    words = _tokenize(inner_text)
    if not words:
        return True
    # Не трогаем (feat. ...), (Remix), (Acoustic), (Live), (Pt. 2) и т.п.
    noise_hits = sum(1 for w in words if w in _NOISE_WORDS)
    return noise_hits == len(words)


def _strip_upload_noise(title):
    if not title:
        return ""
    cleaned = _TRAILING_NOISE_RE.sub("", title).strip()

    def _repl(match):
        inner = match.group(1)
        return "" if _is_noise_bracket(inner) else match.group(0)

    cleaned = _BRACKET_RE.sub(_repl, cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–—|")
    return cleaned or title.strip()


def _clean_uploader(uploader):
    if not uploader:
        return ""
    u = _TOPIC_RE.sub("", str(uploader)).strip()
    if u.lower() in ("various artists", "unknown", ""):
        return ""
    return u


def _split_artist_title(cleaned_title, raw_artist="", clean_uploader="", query=""):
    raw_artist = (raw_artist or "").strip()
    clean_uploader = (clean_uploader or "").strip()

    # Если yt-dlp уже дал artist, просто уберём дублирующийся префикс "Artist - " из title
    if raw_artist:
        for sep in (" - ", " — ", " – "):
            if sep in cleaned_title:
                left, right = cleaned_title.split(sep, 1)
                if SequenceMatcher(None, _normalize_text(left), _normalize_text(raw_artist)).ratio() >= 0.8:
                    return raw_artist, right.strip() or cleaned_title
        return raw_artist, cleaned_title

    for sep in (" - ", " — ", " – "):
        if sep in cleaned_title:
            left, right = cleaned_title.split(sep, 1)
            left = left.strip()
            right = right.strip()
            if not left or not right:
                continue
            # Не делим, если правая часть — это просто "Part 2" / "Remix" / "Acoustic"
            if _VERSION_QUALIFIER_RE.match(right):
                continue
            return left, right

    return clean_uploader, cleaned_title


def _compute_junk_penalty(raw_title, uploader, duration_ms, raw_query, cat_duration_ms=0):
    q_norm = _normalize_text(raw_query)
    haystack = _normalize_text(f"{raw_title} {uploader}")
    penalty = 0.0

    for kw, weight in _JUNK_PENALTIES:
        kw_norm = _normalize_text(kw)
        if re.search(rf"\b{re.escape(kw_norm)}\b", haystack) and not re.search(rf"\b{re.escape(kw_norm)}\b", q_norm):
            penalty += weight

    if duration_ms > 0:
        wants_long = any(h in q_norm for h in _LONG_OK_HINTS)
        if duration_ms > 10 * 60 * 1000 and not wants_long:
            penalty += 0.55
        elif duration_ms < 25 * 1000:
            penalty += 0.30

        if cat_duration_ms > 0:
            diff_ms = abs(duration_ms - cat_duration_ms)
            if diff_ms > 45 * 1000:
                penalty += 0.35

    return penalty


def _accept_search_entry(entry, query):
    """Не заменяем песню сборником, даже если больше результатов нет."""
    if entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming"):
        return False
    try:
        seconds = float(entry.get("duration") or 0)
    except (TypeError, ValueError):
        return False
    if seconds <= 0:
        return False
    q = _normalize_text(query)
    wants_long = any(re.search(rf"\b{re.escape(h)}\b", q) for h in _LONG_OK_HINTS)
    return seconds <= 12 * 60 or wants_long


def _http_get_json(url, timeout=CATALOG_TIMEOUT_SEC):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _fetch_deezer(query):
    try:
        q = urllib.parse.quote(query)
        data = _http_get_json(f"https://api.deezer.com/search?q={q}&limit=8")
        out = []
        for item in (data.get("data") or []):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("title_short") or "").strip()
            artist_obj = item.get("artist") if isinstance(item.get("artist"), dict) else {}
            artist = (artist_obj.get("name") or "").strip()
            album_obj = item.get("album") if isinstance(item.get("album"), dict) else {}
            album = (album_obj.get("title") or "").strip()
            cover = (
                album_obj.get("cover_xl")
                or album_obj.get("cover_big")
                or album_obj.get("cover_medium")
                or ""
            ).strip()
            dur_sec = item.get("duration") or 0
            try:
                dur_ms = max(0, int(float(dur_sec) * 1000))
            except (TypeError, ValueError):
                dur_ms = 0
            if artist and title:
                out.append({
                    "source": "deezer",
                    "artist": artist,
                    "title": title,
                    "album": album,
                    "year": "",
                    "genre": "",
                    "durationMs": dur_ms,
                    "coverArt": cover,
                })
        return out
    except Exception:
        return []


def _fetch_itunes(query):
    try:
        q = urllib.parse.quote(query)
        data = _http_get_json(f"https://itunes.apple.com/search?term={q}&entity=song&limit=8")
        out = []
        for item in (data.get("results") or []):
            if not isinstance(item, dict):
                continue
            artist = (item.get("artistName") or "").strip()
            title = (item.get("trackName") or "").strip()
            album = (item.get("collectionName") or "").strip()
            rel_date = (item.get("releaseDate") or "").strip()
            year = rel_date[:4] if len(rel_date) >= 4 and rel_date[:4].isdigit() else ""
            genre = (item.get("primaryGenreName") or "").strip()
            art = (item.get("artworkUrl100") or item.get("artworkUrl60") or "").strip()
            if art:
                art = re.sub(r"/\d+x\d+bb(\.[a-zA-Z0-9]+)$", r"/600x600bb\1", art)
            dur_ms = 0
            if item.get("trackTimeMillis") is not None:
                try:
                    dur_ms = max(0, int(item["trackTimeMillis"]))
                except (TypeError, ValueError):
                    dur_ms = 0
            if artist and title:
                out.append({
                    "source": "itunes",
                    "artist": artist,
                    "title": title,
                    "album": album,
                    "year": year,
                    "genre": genre,
                    "durationMs": dur_ms,
                    "coverArt": art,
                })
        return out
    except Exception:
        return []


def _fetch_musicbrainz(query):
    try:
        q = urllib.parse.quote(query)
        data = _http_get_json(f"https://musicbrainz.org/ws/2/recording/?query={q}&fmt=json&limit=5")
        out = []
        for rec in (data.get("recordings") or []):
            if not isinstance(rec, dict):
                continue
            title = (rec.get("title") or "").strip()
            credits = rec.get("artist-credit") or []
            artist_parts = []
            for cr in credits:
                if isinstance(cr, str):
                    artist_parts.append(cr)
                elif isinstance(cr, dict):
                    name = (cr.get("name") or (cr.get("artist") or {}).get("name") or "").strip()
                    if name:
                        artist_parts.append(name + (cr.get("joinphrase") or ""))
            artist = "".join(artist_parts).strip()

            album = ""
            year = ""
            first_date = (rec.get("first-release-date") or "").strip()
            if len(first_date) >= 4 and first_date[:4].isdigit():
                year = first_date[:4]
            for rel in (rec.get("releases") or []):
                if not isinstance(rel, dict):
                    continue
                if not album and rel.get("title"):
                    album = str(rel["title"]).strip()
                if not year and rel.get("date"):
                    d = str(rel["date"]).strip()
                    if len(d) >= 4 and d[:4].isdigit():
                        year = d[:4]
                if album and year:
                    break

            dur_ms = 0
            if rec.get("length") is not None:
                try:
                    dur_ms = max(0, int(rec["length"]))
                except (TypeError, ValueError):
                    dur_ms = 0

            if artist and title:
                out.append({
                    "source": "musicbrainz",
                    "artist": artist,
                    "title": title,
                    "album": album,
                    "year": year,
                    "genre": "",
                    "durationMs": dur_ms,
                    "coverArt": "",
                })
        return out
    except Exception:
        return []


def _merge_catalog_entries(entries, query):
    merged = {}
    for item in entries:
        key = (_normalize_text(item["artist"]), _normalize_text(item["title"]))
        if not key[0] or not key[1]:
            continue
        score = _query_similarity(query, item["artist"], item["title"])
        # Лёгкий приоритет iTunes/Deezer как более полным источникам с обложками и жанром
        src_bonus = {"itunes": 0.04, "deezer": 0.03, "musicbrainz": 0.01}.get(item["source"], 0.0)
        existing = merged.get(key)
        if not existing:
            rec = dict(item)
            rec["_score"] = score + src_bonus
            merged[key] = rec
        else:
            existing["_score"] = max(existing["_score"], score + src_bonus)
            # Дополняем недостающие поля из остальных каталогов
            for field in ("album", "year", "genre", "coverArt"):
                if not existing.get(field) and item.get(field):
                    existing[field] = item[field]
            # Предпочитаем обложку iTunes 600x600 или Deezer xl
            if item.get("source") == "itunes" and item.get("coverArt"):
                existing["coverArt"] = item["coverArt"]
            if not existing.get("durationMs") and item.get("durationMs"):
                existing["durationMs"] = item["durationMs"]

    ranked = sorted(merged.values(), key=lambda x: x["_score"], reverse=True)
    return ranked


def _search_catalogs(query):
    raw_items = []
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futures = [
            pool.submit(_fetch_deezer, query),
            pool.submit(_fetch_itunes, query),
            pool.submit(_fetch_musicbrainz, query),
        ]
        done, _ = futures_wait(futures, timeout=CATALOG_TIMEOUT_SEC)
        for fut in done:
            try:
                res = fut.result()
                if isinstance(res, list):
                    raw_items.extend(res)
            except Exception:
                pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    ranked = _merge_catalog_entries(raw_items, query)
    best_query = query
    if ranked and ranked[0]["_score"] >= 0.72:
        top = ranked[0]
        candidate_q = f"{top['artist']} {top['title']}".strip()
        if candidate_q:
            best_query = candidate_q
    return best_query, ranked


def _pick_thumbnail_from_entry(entry):
    thumb = (entry.get("thumbnail") or "").strip()
    if thumb and _is_http_url(thumb):
        return thumb
    thumbs = entry.get("thumbnails")
    if isinstance(thumbs, list):
        for t in reversed(thumbs):
            if isinstance(t, dict):
                u = (t.get("url") or "").strip()
                if u and _is_http_url(u):
                    return u
    return ""


def _run_ytdlp_search(yt_dlp, search_expr, source_name):
    cmd = [yt_dlp, "--flat-playlist", "--no-warnings", "-J", search_expr]
    try:
        proc = _run_subprocess(cmd, timeout=SEARCH_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return [], T("{source}: превышено время ожидания ({sec} с)", source=source_name, sec=SEARCH_TIMEOUT_SEC)
    except OSError as e:
        return [], T("{source}: ошибка запуска yt-dlp ({e})", source=source_name, e=e)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = err[-1] if err else T("код возврата {code}", code=proc.returncode)
        return [], f"{source_name}: {msg}"

    try:
        data = json.loads(proc.stdout)
    except ValueError as e:
        return [], T("{source}: некорректный JSON ({e})", source=source_name, e=e)

    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        entries = [data] if isinstance(data, dict) else []
    valid = [e for e in entries if isinstance(e, dict)]
    return valid, None


def _match_catalog_for_candidate(cand_artist, cand_title, duration_ms, raw_query, catalog_list):
    if not catalog_list:
        return None, 0.0
    best_cat = None
    best_score = 0.0
    cand_q = f"{cand_artist} {cand_title}".strip()

    for cat in catalog_list[:10]:
        c_artist = cat["artist"]
        c_title = cat["title"]
        t_sim = _query_similarity(cand_title or raw_query, "", c_title)
        # Если у видео указан артист (или распарсен), сверяем и артиста, и название
        if cand_artist:
            a_sim = _query_similarity(cand_artist, c_artist, "")
            full_sim = _query_similarity(cand_q, c_artist, c_title)
            score = max(0.55 * t_sim + 0.45 * a_sim, full_sim)
        else:
            score = _query_similarity(f"{raw_query} {cand_title}", c_artist, c_title)

        cat_dur = int(cat.get("durationMs") or 0)
        if duration_ms > 0 and cat_dur > 0:
            diff = abs(duration_ms - cat_dur)
            if diff <= 5000:
                score += 0.08
            elif diff <= 15000:
                score += 0.03
            elif diff > 45000:
                score -= 0.20

        if score > best_score:
            best_score = score
            best_cat = cat

    if best_cat and best_score >= 0.72:
        return best_cat, best_score
    return None, best_score


def _search_streams_and_rank(raw_query, yt_dlp, youtube_only=False):
    best_query, catalog_list = _search_catalogs(raw_query)

    yt_expr = f"ytsearch8:{best_query}"
    sc_expr = f"scsearch4:{best_query}"

    all_entries = []
    errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_yt = pool.submit(_run_ytdlp_search, yt_dlp, yt_expr, "YouTube")
        searches = [(fut_yt, "youtube")]
        if not youtube_only:
            searches.append((pool.submit(_run_ytdlp_search, yt_dlp, sc_expr, "SoundCloud"), "soundcloud"))
        for fut, platform in searches:
            try:
                entries, err = fut.result(timeout=SEARCH_TIMEOUT_SEC + 2)
                if err:
                    errors.append(err)
                for e in entries:
                    e["_platform"] = platform
                    all_entries.append(e)
            except Exception as ex:
                errors.append(f"{platform}: {ex}")

    if not all_entries and errors:
        raise RuntimeError("; ".join(errors))

    seen_urls = set()
    scored = []
    for entry in all_entries:
        if not _accept_search_entry(entry, raw_query):
            continue
        page_url = (entry.get("webpage_url") or entry.get("url") or "").strip()
        if not page_url or not _is_http_url(page_url):
            continue
        norm_url = _normalize_url_key(page_url)
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)

        raw_title = (entry.get("title") or "").strip()
        if not raw_title:
            continue
        raw_artist = (entry.get("artist") or "").strip()
        raw_uploader = (entry.get("uploader") or entry.get("channel") or "").strip()
        clean_uploader = _clean_uploader(raw_uploader)
        cleaned_title = _strip_upload_noise(raw_title)

        cand_artist, cand_title = _split_artist_title(
            cleaned_title,
            raw_artist=raw_artist,
            clean_uploader=clean_uploader,
            query=raw_query,
        )

        duration_ms = 0
        dur = entry.get("duration")
        if dur is not None:
            try:
                duration_ms = max(0, int(float(dur) * 1000))
            except (TypeError, ValueError):
                duration_ms = 0

        matched_cat, cat_match_score = _match_catalog_for_candidate(
            cand_artist, cand_title, duration_ms, raw_query, catalog_list
        )
        cat_dur_ms = int(matched_cat.get("durationMs") or 0) if matched_cat else 0

        # Базовый скор близости к запросу пользователя (и к каноническому best_query)
        sim_raw = _query_similarity(raw_query, cand_artist, cand_title)
        sim_best = _query_similarity(best_query, cand_artist, cand_title) if best_query != raw_query else sim_raw
        score = max(sim_raw, sim_best)

        # Проверка длительности и шумовых слов (full album, slowed, live, mashup, reaction...)
        penalty = _compute_junk_penalty(raw_title, raw_uploader, duration_ms, raw_query, cat_dur_ms)
        score -= penalty

        if matched_cat:
            score += 0.14 * min(1.0, cat_match_score)
            if duration_ms > 0 and cat_dur_ms > 0:
                diff = abs(duration_ms - cat_dur_ms)
                if diff <= 5000:
                    score += 0.15
                elif diff <= 15000:
                    score += 0.07

        # Небольшой бонус официальным/авторским каналам (Topic, или имя канала совпадает с артистом)
        if _TOPIC_RE.search(raw_uploader):
            score += 0.05
        elif clean_uploader and cand_artist and SequenceMatcher(None, _normalize_text(clean_uploader), _normalize_text(cand_artist)).ratio() >= 0.8:
            score += 0.04

        if raw_title != cleaned_title:
            # Слегка ниже, чем чисто названный трек, если оба равнозначны
            score -= 0.02

        final_title = (matched_cat["title"] if matched_cat else cand_title) or cand_title or raw_title
        final_artist = (matched_cat["artist"] if matched_cat else cand_artist) or cand_artist or clean_uploader or "Поток"
        final_album = (matched_cat.get("album") or "") if matched_cat else (entry.get("album") or "").strip()
        final_year = (matched_cat.get("year") or "") if matched_cat else ""
        final_genre = (matched_cat.get("genre") or "") if matched_cat else ""
        final_cover = (matched_cat.get("coverArt") or "") if matched_cat else ""
        if not final_cover:
            final_cover = _pick_thumbnail_from_entry(entry)
        final_duration_ms = duration_ms or cat_dur_ms

        meta_record = {
            "title": final_title,
            "artist": final_artist,
            "album": final_album,
            "year": final_year,
            "genre": final_genre,
            "coverArt": final_cover,
            "durationMs": final_duration_ms,
        }
        _cache_meta_put(page_url, meta_record)

        scored.append((
            score,
            {
                "title": final_title,
                "artist": final_artist,
                "album": final_album,
                "durationMs": final_duration_ms,
                "coverArt": final_cover,
                "action": "play_url",
                "downloadAction": "download_url",
                "arg": page_url,
                "_meta": meta_record,
            },
        ))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:10]]


def _find_best_stream_match(raw_query):
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError(T("yt-dlp не найден в PATH. Установите yt-dlp для поиска и потоков."))
    items = _search_streams_and_rank(raw_query, yt_dlp)
    if not items:
        raise RuntimeError(T("По запросу ничего не найдено"))
    top = items[0]
    return top["arg"], top.get("_meta") or {}


def _format_query(raw_query):
    q = raw_query.strip()
    if _is_http_url(q):
        return q
    if q.startswith(("ytsearch", "scsearch")):
        return q
    return f"ytsearch1:{q}"


def _load_recent():
    global _recent_items, _stream_to_page
    loaded_items = []
    with _state_lock:
        if not RECENT_FILE.exists():
            _recent_items = []
            _stream_to_page = {}
            return
        try:
            data = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _recent_items = [x for x in data if isinstance(x, dict)]
            elif isinstance(data, dict) and isinstance(data.get("recent"), list):
                _recent_items = [x for x in data["recent"] if isinstance(x, dict)]
            else:
                _recent_items = []
            _stream_to_page = {}
            for item in _recent_items:
                su = item.get("streamUrl")
                wu = item.get("webpage_url")
                if su and wu:
                    _stream_to_page[su] = wu
            loaded_items = list(_recent_items)
        except Exception as e:
            p.log(f"Не удалось прочитать recent.json: {e}")
            _recent_items = []
            _stream_to_page = {}
            return

    for item in reversed(loaded_items):
        wu = (item.get("webpage_url") or "").strip()
        if wu and not item.get("is_direct") and (item.get("title") or item.get("coverArt")):
            _cache_meta_put(wu, item)


def _save_recent_locked():
    tmp = RECENT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_recent_items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, RECENT_FILE)


def _record_stream(track, webpage_url, is_direct=False):
    stream_url = track.get("streamUrl") or ""
    source_url = webpage_url or stream_url
    entry = {
        "title": track.get("title") or source_url or "Поток",
        "artist": track.get("artist") or "Поток",
        "album": track.get("album") or "",
        "coverArt": track.get("coverArt") or "",
        "durationMs": int(track.get("durationMs") or 0),
        "webpage_url": source_url,
        "streamUrl": stream_url,
        "is_direct": bool(is_direct),
    }
    with _state_lock:
        if stream_url and source_url:
            _stream_to_page[stream_url] = source_url
        filtered = []
        for item in _recent_items:
            same_page = source_url and item.get("webpage_url") == source_url
            same_stream = stream_url and item.get("streamUrl") == stream_url
            if not (same_page or same_stream):
                filtered.append(item)
        _recent_items[:] = [entry] + filtered[: MAX_RECENT_STORE - 1]
        try:
            _save_recent_locked()
        except Exception as e:
            p.log(f"Не удалось сохранить recent.json: {e}")


def _lookup_source_url(stream_url):
    if not stream_url:
        return None
    with _state_lock:
        if stream_url in _stream_to_page:
            return _stream_to_page[stream_url]
        for item in _recent_items:
            if item.get("streamUrl") == stream_url and item.get("webpage_url"):
                return item["webpage_url"]
    return stream_url


def _get_recent_snapshot():
    with _state_lock:
        return [dict(item) for item in _recent_items[:MAX_RECENT_HOME]]


def refresh_home():
    items = [
        {"title": T("Воспроизвести URL или поиск"), "action": "play_prompt"},
        {"title": T("Добавить в очередь"), "action": "queue_prompt"},
        {"title": T("Скачать в медиатеку"), "action": "download_prompt"},
        {"title": T("Скачать текущий поток"), "action": "save_current"},
    ]
    for idx, entry in enumerate(_get_recent_snapshot()):
        title = entry.get("title") or entry.get("webpage_url") or "Поток"
        artist = (entry.get("artist") or "").strip()
        items.append({
            "title": title,
            "subtitle": artist if artist else T("недавний"),
            "action": f"recent:{idx}",
        })
    p.home_section("stream_yt", T("Потоковое аудио"), items)


def _run_subprocess(args, timeout):
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def _direct_track(url):
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).stem.strip()
    title = name or url
    artist = parsed.netloc or "Поток"
    track = {
        "streamUrl": url,
        "title": title,
        "artist": artist,
        "album": "",
        "durationMs": 0,
    }
    return track, url, True


def _enrich_from_info_if_uncached(info, raw_query, page_url):
    cached = _cache_meta_get(page_url) or _cache_meta_get(raw_query)
    if cached:
        return cached

    raw_title = (info.get("title") or raw_query or "").strip()
    raw_artist = (info.get("artist") or "").strip()
    raw_uploader = (info.get("uploader") or info.get("channel") or "").strip()
    clean_uploader = _clean_uploader(raw_uploader)
    cleaned_title = _strip_upload_noise(raw_title)
    cand_artist, cand_title = _split_artist_title(
        cleaned_title,
        raw_artist=raw_artist,
        clean_uploader=clean_uploader,
        query=raw_query,
    )

    duration_ms = 0
    dur = info.get("duration")
    if dur is not None:
        try:
            duration_ms = max(0, int(float(dur) * 1000))
        except (TypeError, ValueError):
            duration_ms = 0

    lookup_q = f"{cand_artist} {cand_title}".strip() or cleaned_title
    matched_cat = None
    if lookup_q and not _is_http_url(lookup_q):
        _, catalog_list = _search_catalogs(lookup_q)
        matched_cat, _ = _match_catalog_for_candidate(
            cand_artist, cand_title, duration_ms, lookup_q, catalog_list
        )

    cover = (matched_cat.get("coverArt") or "") if matched_cat else ""
    if not cover:
        cover = _pick_thumbnail_from_entry(info)

    meta = {
        "title": (matched_cat["title"] if matched_cat else cand_title) or raw_title,
        "artist": (matched_cat["artist"] if matched_cat else cand_artist) or clean_uploader or "Поток",
        "album": (matched_cat.get("album") or "") if matched_cat else (info.get("album") or "").strip(),
        "year": (matched_cat.get("year") or "") if matched_cat else "",
        "genre": (matched_cat.get("genre") or "") if matched_cat else "",
        "coverArt": cover,
        "durationMs": duration_ms or (int(matched_cat.get("durationMs") or 0) if matched_cat else 0),
    }
    _cache_meta_put(page_url, meta)
    return meta


def _is_source_timeout(error):
    message = str(error).lower()
    return any(s in message for s in ("timed out", "timeout", "время ожидания", "zeitüberschreitung"))


def _playback_error(error):
    message = str(error)
    if _is_source_timeout(error):
        source = "SoundCloud" if "soundcloud" in message.lower() else T("Источник")
        return T("{source} не ответил вовремя. Повторите запуск позже или выберите другую запись.", source=source)
    return message


def _try_youtube_alternative(source_url, meta, error, yt_dlp):
    host = (urllib.parse.urlparse(source_url).hostname or "").lower()
    if not (host == "soundcloud.com" or host.endswith(".soundcloud.com")) or not _is_source_timeout(error):
        return None
    meta = meta or {}
    artist = _normalize_text(meta.get("artist") or "")
    title = _normalize_text(meta.get("title") or "")
    duration = int(meta.get("durationMs") or 0)
    if not artist or not title or artist in ("поток", "неизвестный исполнитель") or duration <= 0:
        return None
    p.status(T("SoundCloud не ответил. Ищу эту запись на YouTube..."))
    try:
        matches = _search_streams_and_rank(f"{meta['artist']} {meta['title']}", yt_dlp, youtube_only=True)
        for item in matches:
            candidate = item.get("_meta") or {}
            if (_normalize_text(candidate.get("artist") or "") != artist or
                    _normalize_text(candidate.get("title") or "") != title):
                continue
            if abs(int(candidate.get("durationMs") or 0) - duration) > max(5000, duration * .05):
                continue
            # Один проверенный альтернативный источник, без цепочки повторных поисков.
            return _resolve_query(item["arg"])
    except Exception as ex:
        p.log(f"Не удалось получить альтернативу YouTube: {ex}")
    return None


def _resolve_query(raw_query):
    raw_query = (raw_query or "").strip()
    if not raw_query:
        raise ValueError(T("Пустой запрос"))

    yt_dlp = shutil.which("yt-dlp")
    is_url = _is_http_url(raw_query)

    if is_url and (_is_direct_audio_url(raw_query) or not yt_dlp):
        if not yt_dlp:
            p.log(f"yt-dlp не найден, пробую прямой поток: {raw_query}")
        return _direct_track(raw_query)

    if not yt_dlp:
        raise RuntimeError(T("yt-dlp не найден в PATH. Установите yt-dlp для поиска и потоков."))

    cached_meta = None
    target_source = raw_query
    if not is_url and not raw_query.startswith(("ytsearch", "scsearch")):
        target_source, cached_meta = _find_best_stream_match(raw_query)
    elif is_url:
        cached_meta = _cache_meta_get(target_source)

    query = _format_query(target_source)
    cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "-f", "bestaudio/best", "-J", query]
    try:
        proc = _run_subprocess(cmd, timeout=RESOLVE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        error = T("{source}: превышено время ожидания yt-dlp ({sec} с)", source=target_source, sec=RESOLVE_TIMEOUT_SEC)
        alternative = _try_youtube_alternative(target_source, cached_meta, error, yt_dlp)
        if alternative is not None:
            return alternative
        raise RuntimeError(error)
    except OSError as e:
        raise RuntimeError(T("Ошибка запуска yt-dlp: {e}", e=e))

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = err[-1] if err else T("код возврата {code}", code=proc.returncode)
        alternative = _try_youtube_alternative(target_source, cached_meta, msg, yt_dlp)
        if alternative is not None:
            return alternative
        raise RuntimeError(f"yt-dlp: {msg}")

    try:
        data = json.loads(proc.stdout)
    except ValueError as e:
        raise RuntimeError(T("Некорректный JSON от yt-dlp: {e}", e=e))

    if isinstance(data, dict) and "entries" in data:
        entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
        if not entries:
            raise RuntimeError(T("По запросу ничего не найдено"))
        info = entries[0]
    elif isinstance(data, dict):
        info = data
    else:
        raise RuntimeError(T("Неожиданный ответ yt-dlp"))

    if not is_url and not _accept_search_entry(info, raw_query):
        raise RuntimeError(T("Найден длинный сборник или запись без длительности вместо трека. Уточните запрос или откройте нужную запись по ссылке."))

    stream_url = info.get("url")
    if not stream_url:
        req_formats = info.get("requested_formats") or []
        if req_formats and isinstance(req_formats[0], dict):
            stream_url = req_formats[0].get("url")
    if not stream_url or not _is_http_url(str(stream_url)):
        raise RuntimeError(T("Не удалось получить прямой URL аудиопотока"))

    webpage_url = (
        info.get("webpage_url")
        or info.get("original_url")
        or (target_source if _is_http_url(target_source) else stream_url)
    )

    meta = cached_meta or _enrich_from_info_if_uncached(info, raw_query, webpage_url)
    _cache_meta_put(webpage_url, meta)

    duration_ms = int(meta.get("durationMs") or 0)
    if not duration_ms:
        dur = info.get("duration")
        if dur is not None:
            try:
                duration_ms = max(0, int(float(dur) * 1000))
            except (TypeError, ValueError):
                duration_ms = 0

    raw_headers = info.get("http_headers")
    if not isinstance(raw_headers, dict):
        req_formats = info.get("requested_formats") or []
        if req_formats and isinstance(req_formats[0], dict):
            raw_headers = req_formats[0].get("http_headers")
    http_headers = {}
    if isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            if isinstance(k, str) and isinstance(v, str) and k and v:
                http_headers[k] = v

    track = {
        "streamUrl": stream_url,
        "title": meta.get("title") or (info.get("title") or raw_query).strip(),
        "artist": meta.get("artist") or "Поток",
        "album": meta.get("album") or "",
        "durationMs": duration_ms,
    }
    if _is_http_url(str(webpage_url)):
        track["sourceUrl"] = webpage_url
        track["sourcePlugin"] = "stream-yt"
    if meta.get("coverArt"):
        track["coverArt"] = meta["coverArt"]
    if meta.get("genre"):
        track["genre"] = meta["genre"]
    if http_headers:
        track["httpHeaders"] = http_headers
    return track, webpage_url, False


def _search_yt(raw_query):
    query = (raw_query or "").strip()
    if not query:
        return []

    if _is_http_url(query):
        if _is_direct_audio_url(query) or not shutil.which("yt-dlp"):
            track, page_url, _ = _direct_track(query)
        else:
            track, page_url, _ = _resolve_query(query)
        return [{
            "title": track.get("title") or query,
            "artist": track.get("artist") or "Поток",
            "album": track.get("album") or "",
            "durationMs": int(track.get("durationMs") or 0),
            "coverArt": track.get("coverArt") or "",
            "action": "play_url",
            "downloadAction": "download_url",
            "arg": page_url or query,
        }]

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError(T("yt-dlp не найден в PATH. Установите yt-dlp для поиска."))

    if query.startswith(("ytsearch", "scsearch")):
        entries, err = _run_ytdlp_search(yt_dlp, query, "yt-dlp")
        if err and not entries:
            raise RuntimeError(err)
        results = []
        for entry in entries:
            page_url = (entry.get("webpage_url") or entry.get("url") or "").strip()
            if not page_url:
                continue
            raw_title = (entry.get("title") or query).strip()
            clean_up = _clean_uploader(entry.get("uploader") or entry.get("channel") or "")
            c_art, c_tit = _split_artist_title(_strip_upload_noise(raw_title), entry.get("artist") or "", clean_up, query)
            dur_ms = 0
            if entry.get("duration") is not None:
                try:
                    dur_ms = max(0, int(float(entry["duration"]) * 1000))
                except (TypeError, ValueError):
                    pass
            results.append({
                "title": c_tit,
                "artist": c_art,
                "album": (entry.get("album") or "").strip(),
                "durationMs": dur_ms,
                "coverArt": _pick_thumbnail_from_entry(entry),
                "action": "play_url",
                "downloadAction": "download_url",
                "arg": page_url,
            })
        return results

    items = _search_streams_and_rank(query, yt_dlp)
    for item in items:
        item.pop("_meta", None)
    return items


def _play_or_queue(raw_query, queue_mode=False):
    p.status(T("Поиск в каталогах и потоках..."))
    try:
        track, webpage_url, is_direct = _resolve_query(raw_query)
    except Exception as e:
        p.log(f"Ошибка разрешения '{raw_query}': {e}")
        p.toast(_playback_error(e))
        return
    finally:
        p.status(None)

    _record_stream(track, webpage_url, is_direct=is_direct)
    refresh_home()

    label = f"{track['artist']} — {track['title']}" if track.get("artist") else track["title"]
    if queue_mode:
        p.queue_add([track])
        p.log(f"Добавлено в очередь: {label} ({webpage_url})")
        p.toast(T("В очереди: {label}", label=label))
    else:
        p.play_tracks([track], title=T("Потоковое аудио"))
        p.log(f"Запуск потока: {label} ({webpage_url})")
        p.toast(T("Играет: {label}", label=label))


def _sanitize_filename(name):
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip().strip(".")
    return cleaned or "stream_track"


def _download_direct_fallback(url, lib_dir):
    parsed = urllib.parse.urlparse(url)
    raw_name = Path(urllib.parse.unquote(parsed.path)).name or "stream_track.mp3"
    safe_name = _sanitize_filename(raw_name)
    dest = Path(lib_dir) / safe_name
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    return str(dest)


def _download_cover_bytes(cover_url):
    if not cover_url or not _is_http_url(cover_url):
        return None, None
    try:
        req = urllib.request.Request(cover_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=COVER_TIMEOUT_SEC) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read(6 * 1024 * 1024)
        if not data:
            return None, None
        if data[:8] == b"\x89PNG\r\n\x1a\n" or "png" in ctype:
            mime = "image/png"
        else:
            mime = "image/jpeg"
        return data, mime
    except Exception:
        return None, None


def _apply_mutagen_tags(filepath, meta):
    if not meta or not filepath or not os.path.isfile(filepath):
        return
    try:
        import mutagen
        from mutagen.flac import FLAC, Picture
        from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1
        from mutagen.mp3 import MP3
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen.oggopus import OggOpus
        from mutagen.oggvorbis import OggVorbis
    except ImportError:
        return

    title = (meta.get("title") or "").strip()
    artist = (meta.get("artist") or "").strip()
    if artist == "Поток":
        artist = ""
    album = (meta.get("album") or "").strip()
    year = str(meta.get("year") or "").strip()
    genre = (meta.get("genre") or "").strip()

    cover_bytes, cover_mime = _download_cover_bytes(meta.get("coverArt") or "")

    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return

        if isinstance(audio, MP3):
            if audio.tags is None:
                audio.add_tags()
            tags = audio.tags
            if not isinstance(tags, ID3):
                audio.add_tags()
                tags = audio.tags
            if title:
                tags.delall("TIT2")
                tags.add(TIT2(encoding=3, text=title))
            if artist:
                tags.delall("TPE1")
                tags.add(TPE1(encoding=3, text=artist))
            if album:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=album))
            if year:
                tags.delall("TDRC")
                tags.add(TDRC(encoding=3, text=year))
            if genre:
                tags.delall("TCON")
                tags.add(TCON(encoding=3, text=genre))
            if cover_bytes:
                tags.delall("APIC")
                tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_bytes))
            audio.save()
            return

        if isinstance(audio, MP4):
            if title:
                audio["\xa9nam"] = [title]
            if artist:
                audio["\xa9ART"] = [artist]
            if album:
                audio["\xa9alb"] = [album]
            if year:
                audio["\xa9day"] = [year]
            if genre:
                audio["\xa9gen"] = [genre]
            if cover_bytes:
                fmt = MP4Cover.FORMAT_PNG if cover_mime == "image/png" else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
            audio.save()
            return

        if isinstance(audio, FLAC):
            if title:
                audio["title"] = [title]
            if artist:
                audio["artist"] = [artist]
            if album:
                audio["album"] = [album]
            if year:
                audio["date"] = [year]
            if genre:
                audio["genre"] = [genre]
            if cover_bytes:
                audio.clear_pictures()
                pic = Picture()
                pic.type = 3
                pic.mime = cover_mime
                pic.desc = "Cover"
                pic.data = cover_bytes
                audio.add_picture(pic)
            audio.save()
            return

        if isinstance(audio, (OggOpus, OggVorbis)):
            if title:
                audio["title"] = [title]
            if artist:
                audio["artist"] = [artist]
            if album:
                audio["album"] = [album]
            if year:
                audio["date"] = [year]
            if genre:
                audio["genre"] = [genre]
            if cover_bytes:
                pic = Picture()
                pic.type = 3
                pic.mime = cover_mime
                pic.desc = "Cover"
                pic.data = cover_bytes
                encoded = base64.b64encode(pic.write()).decode("ascii")
                audio["metadata_block_picture"] = [encoded]
            audio.save()
            return

        # Общий fallback (например, для прочих контейнеров, поддерживаемых mutagen)
        easy = mutagen.File(filepath, easy=True)
        if easy is not None:
            if title:
                easy["title"] = [title]
            if artist:
                easy["artist"] = [artist]
            if album:
                easy["album"] = [album]
            if year:
                easy["date"] = [year]
            if genre:
                easy["genre"] = [genre]
            easy.save()
    except Exception as e:
        p.log(f"Не удалось записать теги mutagen для '{filepath}': {e}")


def _fetch_yt_info_only(yt_dlp, url):
    try:
        cmd = [yt_dlp, "--no-playlist", "--no-warnings", "--skip-download", "-J", url]
        proc = _run_subprocess(cmd, timeout=RESOLVE_TIMEOUT_SEC)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        if isinstance(data, dict) and "entries" in data:
            entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
            return entries[0] if entries else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _download_to_library(raw_query):
    raw_query = (raw_query or "").strip()
    if not raw_query:
        return

    p.status(T("Скачивание в медиатеку..."))
    try:
        _download_to_library_impl(raw_query)
    finally:
        p.status(None)


def _download_to_library_impl(raw_query):
    try:
        lib_dir = p.library_folder()
    except Exception as e:
        p.log(f"Не удалось получить папку медиатеки: {e}")
        p.toast(T("Ошибка доступа к медиатеке: {e}", e=e))
        return

    if not lib_dir:
        p.log("Папка медиатеки не задана")
        p.toast(T("Сначала выберите папку локальной медиатеки в настройках Lettudio"))
        return

    try:
        Path(lib_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        p.log(f"Не удалось создать папку медиатеки '{lib_dir}': {e}")
        p.toast(T("Ошибка папки медиатеки: {e}", e=e))
        return

    yt_dlp = shutil.which("yt-dlp")
    meta = None
    if not yt_dlp:
        if _is_direct_audio_url(raw_query):
            try:
                filepath = _download_direct_fallback(raw_query, lib_dir)
            except Exception as e:
                p.log(f"Ошибка скачивания '{raw_query}': {e}")
                p.toast(T("Ошибка скачивания: {e}", e=e))
                return
        else:
            msg = T("yt-dlp не найден в PATH. Установите yt-dlp для скачивания.")
            p.log(msg)
            p.toast(msg)
            return
    else:
        is_url = _is_http_url(raw_query)
        source = raw_query
        if not is_url and not raw_query.startswith(("ytsearch", "scsearch")):
            try:
                source, meta = _find_best_stream_match(raw_query)
            except Exception as e:
                p.log(f"Поиск не удался: {e}")
                p.toast(T("Не найден подходящий трек: {e}", e=e))
                return
        else:
            source = _format_query(raw_query)
            if is_url and not _is_direct_audio_url(raw_query):
                meta = _cache_meta_get(raw_query)
                if not meta:
                    info = _fetch_yt_info_only(yt_dlp, raw_query)
                    if info:
                        page_url = info.get("webpage_url") or info.get("original_url") or raw_query
                        meta = _enrich_from_info_if_uncached(info, raw_query, page_url)

        if meta and meta.get("artist") and meta.get("title") and meta["artist"] != "Поток":
            safe_stem = _sanitize_filename(f"{meta['artist']} - {meta['title']}")
            out_tmpl = os.path.join(lib_dir, f"{safe_stem}.%(ext)s")
        else:
            out_tmpl = os.path.join(lib_dir, "%(artist,uploader)s - %(title)s.%(ext)s")

        has_ffmpeg = bool(shutil.which("ffmpeg"))
        p.log(f"Начинаю загрузку: {source}")

        if has_ffmpeg:
            # Берём лучший доступный исходник без искусственного апскейла / перекодирования:
            # если есть lossless (FLAC/WAV) — сохранится оригинал; если lossy (Opus/AAC/MP3) —
            # извлекается без потери качества и раздувания битрейта (--audio-format best).
            cmd = [
                yt_dlp, "--no-playlist", "--no-warnings",
                "-f", "bestaudio/best",
                "-x", "--audio-format", "best",
                "--embed-metadata", "--embed-thumbnail",
                "-o", out_tmpl,
                "--print", "after_move:filepath",
                source,
            ]
        else:
            p.log("ffmpeg не найден: скачиваю исходный bestaudio без перекодирования в opus")
            cmd = [
                yt_dlp, "--no-playlist", "--no-warnings",
                "-f", "bestaudio/best",
                "-o", out_tmpl,
                "--print", "after_move:filepath",
                source,
            ]

        try:
            proc = _run_subprocess(cmd, timeout=DOWNLOAD_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            msg = T("Превышено время скачивания ({sec} с)", sec=DOWNLOAD_TIMEOUT_SEC)
            p.log(msg)
            p.toast(msg)
            return
        except OSError as e:
            msg = T("Ошибка запуска yt-dlp: {e}", e=e)
            p.log(msg)
            p.toast(msg)
            return

        # Если с ffmpeg не получилось (например, ошибка постпроцессора), пробуем fallback без -x
        if proc.returncode != 0 and has_ffmpeg:
            err_preview = (proc.stderr or "").strip()
            p.log(f"Ошибка yt-dlp с ffmpeg ({err_preview}), пробую fallback -f bestaudio/best")
            fallback_cmd = [
                yt_dlp, "--no-playlist", "--no-warnings",
                "-f", "bestaudio/best",
                "-o", out_tmpl,
                "--print", "after_move:filepath",
                source,
            ]
            try:
                proc = _run_subprocess(fallback_cmd, timeout=DOWNLOAD_TIMEOUT_SEC)
            except Exception as e:
                p.log(f"Ошибка fallback-загрузки: {e}")
                p.toast(T("Ошибка скачивания: {e}", e=e))
                return

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            msg = err[-1] if err else T("код возврата {code}", code=proc.returncode)
            p.log(f"Ошибка скачивания '{source}': {msg}")
            p.toast(T("Ошибка скачивания: {e}", e=msg))
            return

        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        filepath = None
        for ln in reversed(lines):
            if os.path.isfile(ln):
                filepath = ln
                break
        if not filepath and lines:
            filepath = lines[-1]

        if not filepath or not os.path.isfile(filepath):
            p.log(f"Не удалось определить путь скачанного файла. stdout={proc.stdout!r}")
            p.toast(T("Файл не найден после скачивания"))
            return

        if meta:
            _apply_mutagen_tags(filepath, meta)

    try:
        added = p.add_file(filepath)
        title = (added or {}).get("title") or (meta or {}).get("title") or Path(filepath).name
        p.log(f"Добавлен в медиатеку: {filepath}")
        p.toast(T("Скачано в медиатеку: {title}", title=title))
    except Exception as e:
        p.log(f"Файл скачан ({filepath}), но add_file вернул ошибку: {e}")
        p.toast(T("Файл скачан, но не проиндексирован: {e}", e=e))


def _prompt_text(title, hint):
    try:
        text = p.prompt(title, hint=hint)
    except Exception as e:
        p.log(f"Ошибка диалога ввода: {e}")
        return None
    if not text or not text.strip():
        return None
    return text.strip()


def _download_from_track(track):
    if not isinstance(track, dict):
        p.toast(T("Нет данных о треке"))
        return
    if track.get("path"):
        p.toast(T("Трек уже находится в локальной медиатеке"))
        return
    stream_url = track.get("streamUrl")
    if not stream_url:
        p.toast(T("У этого трека нет потоковой ссылки для скачивания"))
        return
    source_url = _lookup_source_url(stream_url)
    if not source_url:
        p.toast(T("Не найдена исходная ссылка трека"))
        return
    _download_to_library(source_url)


def register_ui():
    """Кнопки, поиск и секция на главной — на языке интерфейса (вызывается и при смене языка)."""
    p.add_action("stream", T("Поток / URL"), icon="cloud", where="search")
    # Пункт меню трека «Скачать в медиатеку» убран: в Lettudio есть встроенное
    # «Скачать на устройство» (кладёт файл туда же и работает на телефоне).
    p.register_search(T("Музыка и потоки (YT / SoundCloud)"))
    refresh_home()


@p.on("hello")
def on_hello(_):
    _load_recent()
    register_ui()
    p.log("Плагин stream-yt готов")


@p.on("lang")
def on_lang(_):
    register_ui()


@p.on("search")
def on_search(ev):
    req_id = ev.get("reqId")
    query = (ev.get("query") or "").strip()
    if req_id is None:
        return
    if not query:
        p.reply(req_id, ok=True, data=[])
        return
    p.status(T("Поиск в каталогах и потоках..."))
    try:
        results = _search_yt(query)
        p.reply(req_id, ok=True, data=results)
    except Exception as e:
        p.log(f"Ошибка поиска '{query}': {e}")
        p.reply(req_id, ok=False, error=str(e))
    finally:
        p.status(None)


def _is_ephemeral_url(url):
    u = (url or "").lower()
    return (
        "googlevideo.com" in u
        or "/videoplayback" in u
        or "sndcdn.com" in u
        or "expire=" in u
        or "expires=" in u
    )


def _fallback_query(track):
    """«Исполнитель Название» для поиска, когда ссылка трека не открывается."""
    title = (track.get("title") or "").strip()
    artist = (track.get("artist") or "").strip()
    if artist in ("Поток", "Неизвестный исполнитель"):
        artist = ""
    return f"{artist} {title}".strip() if title else ""


@p.on("resolve_track")
def on_resolve_track(ev):
    req_id = ev.get("reqId")
    if req_id is None:
        return
    track = ev.get("track") or {}
    if not isinstance(track, dict):
        track = {}

    target = (track.get("sourceUrl") or "").strip()
    if not target:
        candidate = (_lookup_source_url(track.get("streamUrl") or "") or "").strip()
        if candidate and not _is_ephemeral_url(candidate):
            target = candidate
    if not target:
        title = (track.get("title") or "").strip()
        artist = (track.get("artist") or "").strip()
        if artist in ("Поток", "Неизвестный исполнитель"):
            artist = ""
        target = f"{artist} {title}".strip()
    if not target:
        p.reply(req_id, ok=False, error=T("Нет данных для поиска потока"))
        return

    p.status(T("Получение потока..."))
    try:
        if _is_http_url(target) and not _cache_meta_get(target):
            _cache_meta_put(target, track)
        try:
            resolved_track, webpage_url, is_direct = _resolve_query(target)
        except Exception as first_error:
            # Сохранённая ссылка больше не работает (ролик удалён или закрыт, сбой
            # сети у одного сервиса) — ищем тот же трек по исполнителю и названию.
            query = _fallback_query(track) if _is_http_url(target) else ""
            if not query:
                raise
            p.log(f"Ссылка '{target}' не открылась ({first_error}); ищу по названию: {query}")
            resolved_track, webpage_url, is_direct = _resolve_query(query)
        in_title = (track.get("title") or "").strip()
        in_artist = (track.get("artist") or "").strip()
        in_album = (track.get("album") or "").strip()
        in_cover = (track.get("coverArt") or "").strip()
        if in_title:
            resolved_track["title"] = in_title
        if in_artist and in_artist not in ("Поток", "Неизвестный исполнитель"):
            resolved_track["artist"] = in_artist
        if in_album:
            resolved_track["album"] = in_album
        if in_cover:
            resolved_track["coverArt"] = in_cover
        _record_stream(resolved_track, webpage_url, is_direct=is_direct)
        p.reply(req_id, ok=True, data=resolved_track)
    except Exception as e:
        p.log(f"Ошибка повторного разрешения потока '{target}': {e}")
        p.reply(req_id, ok=False, error=_playback_error(e))
    finally:
        p.status(None)


@p.on_action("stream")
def on_stream_action(ev):
    arg = (ev.get("arg") or "").strip()
    q = arg or _prompt_text(T("Воспроизвести поток"), T("URL (YouTube, радио, .mp3) или текст для поиска"))
    if q:
        _play_or_queue(q, queue_mode=False)


@p.on_action("play_url")
def on_play_url(ev):
    url = (ev.get("arg") or "").strip()
    if not url:
        p.toast(T("Не передана ссылка для воспроизведения"))
        return
    _play_or_queue(url, queue_mode=False)


@p.on_action("download_url")
def on_download_url(ev):
    url = (ev.get("arg") or "").strip()
    if not url:
        p.toast(T("Не передана ссылка для скачивания"))
        return
    _download_to_library(url)


@p.on_action("play_prompt")
def on_play_prompt(_):
    q = _prompt_text(T("Воспроизвести URL или поиск"), T("https://... или исполнитель — название"))
    if q:
        _play_or_queue(q, queue_mode=False)


@p.on_action("queue_prompt")
def on_queue_prompt(_):
    q = _prompt_text(T("Добавить поток в очередь"), T("https://... или исполнитель — название"))
    if q:
        _play_or_queue(q, queue_mode=True)


@p.on_action("download_prompt")
def on_download_prompt(_):
    q = _prompt_text(T("Скачать в медиатеку"), T("https://... или исполнитель — название"))
    if q:
        _download_to_library(q)


@p.on_action("save_track")
def on_save_track(ev):
    track = ev.get("track")
    if not track:
        try:
            cur = p.request("current") or {}
            track = cur.get("track")
        except Exception:
            track = (p.state or {}).get("track")
    if not track:
        p.toast(T("Трек не выбран"))
        return
    _download_from_track(track)


@p.on_action("save_current")
def on_save_current(ev):
    track = ev.get("track")
    if not track:
        try:
            cur = p.request("current") or {}
            track = cur.get("track")
        except Exception:
            track = (p.state or {}).get("track")
    if not track:
        p.toast(T("Сейчас ничего не играет"))
        return
    _download_from_track(track)


def _make_recent_handler(idx):
    def _handler(_):
        items = _get_recent_snapshot()
        if idx >= len(items):
            p.toast(T("Запись устарела, обновите список"))
            refresh_home()
            return
        entry = items[idx]
        source_url = entry.get("webpage_url") or entry.get("streamUrl")
        if not source_url:
            p.toast(T("Не найдена ссылка для этого потока"))
            return
        _play_or_queue(source_url, queue_mode=False)
    return _handler


for _idx in range(MAX_RECENT_HOME):
    p.on_action(f"recent:{_idx}")(_make_recent_handler(_idx))


if __name__ == "__main__":
    p.run()
