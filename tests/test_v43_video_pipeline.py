"""تست‌های نسخه v0.43.0 (فاز ۶) — موتور ویدیوساز ریلز و شورتس خودکار (`video_pipeline.py`)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.xgpedia.media import video_pipeline as vp


def test_build_slideshow_ffmpeg_cmd_single_and_multi_slide_with_audio() -> None:
    with tempfile.TemporaryDirectory() as td:
        p1 = Path(td) / "s1.png"
        p2 = Path(td) / "s2.png"
        p3 = Path(td) / "s3.png"
        aud = Path(td) / "bgm.mp3"
        out = Path(td) / "reel.mp4"
        for p in (p1, p2, p3, aud):
            p.write_bytes(b"FAKE")

        # تک‌اسلاید بدون صدا
        cmd1, dur1 = vp.build_slideshow_ffmpeg_cmd([p1], out, slide_duration=4.0)
        assert dur1 == 4.0
        assert "-an" in cmd1
        assert "libx264" in cmd1
        assert "yuv420p" in cmd1

        # ۳ اسلاید با xfade و موزیک پس‌زمینه
        cmd3, dur3 = vp.build_slideshow_ffmpeg_cmd([p1, p2, p3], out, slide_duration=3.5, fade_duration=0.5, audio_path=aud)
        assert dur3 == 9.5  # 3*3.5 - 2*0.5
        joined = " ".join(cmd3)
        assert "xfade=transition=smoothleft" in joined
        assert "[aout]" in joined
        assert "aac" in cmd3
        assert "+faststart" in cmd3


def test_build_watermark_ffmpeg_cmd() -> None:
    cmd = vp.build_watermark_ffmpeg_cmd(Path("in.mp4"), Path("wm.png"), Path("out.mp4"), position="bottom-right", scale_width=140, opacity=0.8)
    joined = " ".join(cmd)
    assert "overlay=W-w-28:H-h-28" in joined
    assert "colorchannelmixer=aa=0.80" in joined
    assert "libx264" in cmd


def test_build_slideshow_reel_returns_helpful_persian_hint_when_ffmpeg_missing() -> None:
    with patch.object(vp, "find_ffmpeg", return_value=None):
        res = vp.build_slideshow_reel(["a.png"], "out.mp4")
    assert res.ok is False
    assert "FFmpeg" in res.error
    assert "winget" in res.error


def test_modular_cards_bot_and_telegram_bot_wired_for_reels() -> None:
    mb_src = Path("src/xgpedia/publishers/modular_cards_bot.py").read_text(encoding="utf-8")
    assert "ساخت ریلز (MP4)" in mb_src
    assert 'action == "reel"' in mb_src
    assert "render_modular_card_reel_async" in mb_src
    assert "reel:pub:" in mb_src
    assert "broadcast_video" in mb_src

    tb_src = Path("src/xgpedia/publishers/telegram_bot.py").read_text(encoding="utf-8")
    assert "async def send_video(" in tb_src


def test_kinetic_motion_html_and_audio_synth() -> None:
    from src.xgpedia.media.audio_synth import synthesize_sports_beat_wav
    from src.xgpedia.media.motion_reel import extract_motion_story, render_kinetic_motion_html

    sample_quote = {
        "speaker": "میکل آرتتا",
        "role": "سرمربی آرسنال",
        "clubCode": "ARS",
        "color": "#EF0107",
        "competition": "لیگ برتر انگلیس",
        "quote": "ما باید در *لحظات کلیدی* بازی دقیق‌تر باشیم.",
        "stats": [{"label": "گل زده فصل", "val": "42"}, {"label": "امید گل تیم", "val": "38.4"}],
    }
    story = extract_motion_story("quote", sample_quote)
    assert story["headline"] == "میکل آرتتا"
    assert len(story["metrics"]) == 2

    html = render_kinetic_motion_html("quote", sample_quote, duration_sec=14.0)
    assert "window.__setTime" in html
    assert "scIntro" in html and "scOutro" in html
    assert "@XGPedia" in html
    assert "https://cdn." not in html

    with tempfile.TemporaryDirectory() as td:
        wav_p = synthesize_sports_beat_wav(Path(td) / "beat.wav", duration_sec=2.0)
        assert wav_p.exists()
        assert wav_p.stat().st_size > 100_000


def test_live_progress_reporter_and_no_stderr_pipe_deadlock() -> None:
    from src.xgpedia.publishers.progress_utils import progress_bar
    assert progress_bar(5, 10) == "█████░░░░░"
    assert progress_bar(10, 10) == "██████████"
    vp_src = Path("src/xgpedia/media/video_pipeline.py").read_text(encoding="utf-8")
    assert "stderr=err_fh" in vp_src
    assert "stdout=subprocess.DEVNULL" in vp_src
