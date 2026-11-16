import importlib.util
from pathlib import Path
import sys
import subprocess
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("stream_yt", Path(__file__).with_name("main.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class SearchTests(unittest.TestCase):
    def test_soundcloud_timeout_resolves_matching_youtube_recording(self):
        meta = {"title": "Song", "artist": "Artist", "durationMs": 200000}
        youtube = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
        failed = subprocess.CompletedProcess([], 1, "", "ERROR: [soundcloud] Read timed out. (read timeout=20.0)")
        success = subprocess.CompletedProcess([], 0, json.dumps({
            "url": "https://cdn.example/audio.m4a", "webpage_url": youtube, "duration": 200,
        }), "")
        with patch.object(plugin.shutil, "which", return_value="yt-dlp"), \
                patch.object(plugin, "_cache_meta_get", return_value=meta), \
                patch.object(plugin, "_cache_meta_put"), \
                patch.object(plugin.p, "status"), \
                patch.object(plugin, "_search_streams_and_rank", return_value=[{"arg": youtube, "_meta": meta}]) as search, \
                patch.object(plugin, "_run_subprocess", side_effect=[failed, success]) as run:
            track, page, _ = plugin._resolve_query("https://soundcloud.com/artist/song")
        self.assertEqual(page, youtube)
        self.assertEqual(track["title"], "Song")
        self.assertEqual(run.call_count, 2)
        self.assertTrue(search.call_args.kwargs["youtube_only"])

    def test_fallback_rejects_other_artist_title_and_duration(self):
        meta = {"title": "Song", "artist": "Artist", "durationMs": 200000}
        wrong = [dict(meta, artist="Other"), dict(meta, title="Song live"), dict(meta, durationMs=3600000)]
        with patch.object(plugin.p, "status"), \
                patch.object(plugin, "_search_streams_and_rank", return_value=[
                    {"arg": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "_meta": m} for m in wrong
                ]), patch.object(plugin, "_resolve_query") as resolve:
            self.assertIsNone(plugin._try_youtube_alternative(
                "https://soundcloud.com/artist/song", meta, "Read timed out", "yt-dlp"))
            resolve.assert_not_called()

    def test_non_timeout_does_not_trigger_alternative_search(self):
        with patch.object(plugin, "_search_streams_and_rank") as search:
            self.assertIsNone(plugin._try_youtube_alternative(
                "https://soundcloud.com/artist/song", {}, "HTTP 403", "yt-dlp"))
            search.assert_not_called()
        message = plugin._playback_error("yt-dlp: ERROR: [soundcloud] Read timed out. HTTPSConnectionPool...")
        self.assertIn("SoundCloud не ответил вовремя", message)
        self.assertNotIn("HTTPSConnectionPool", message)

    def test_search_does_not_return_long_recording_even_as_only_match(self):
        with patch.object(plugin, "_search_catalogs", return_value=("Artist Song", [])), \
                patch.object(plugin, "_run_ytdlp_search", return_value=([{
                    "title": "Artist Song", "duration": 3600,
                    "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                }], None)):
            self.assertEqual(plugin._search_streams_and_rank("Artist Song", "yt-dlp"), [])

    def test_explicit_long_query_and_word_boundaries(self):
        entry = {"duration": 3600}
        self.assertTrue(plugin._accept_search_entry(entry, "Artist full album"))
        self.assertTrue(plugin._accept_search_entry(entry, "Artist микс"))
        self.assertFalse(plugin._accept_search_entry(entry, "Sunset remixed"))
        self.assertFalse(plugin._accept_search_entry({"duration": None}, "Artist"))
        self.assertFalse(plugin._accept_search_entry({"duration": 200, "is_live": True}, "live"))


if __name__ == "__main__":
    unittest.main()
