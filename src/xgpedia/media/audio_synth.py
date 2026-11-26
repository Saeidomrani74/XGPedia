"""سنتزکنندهٔ موزیک پس‌زمینهٔ ورزشی-الکترونیک (۱۲۴ BPM) بدون کپی‌رایت — ۱۰۰٪ آفلاین با Python stdlib.

اگر کاربر فایل دلخواه `.mp3` در `assets/audio/` قرار نداده باشد، این ماژول به‌صورت خودکار
یک ترک استریو پرانرژی (کیک عمیق، های‌هت شانزدهم، بیس مدرن مینور، آرپژ ظریف و ضربهٔ ترنزیشن)
متناسب با طول دقیق ریلز تولید می‌کند تا هیچ ویدیویی بی‌صدا نباشد.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


def synthesize_sports_beat_wav(
    output_wav: Path | str,
    *,
    duration_sec: float = 14.5,
    bpm: float = 124.0,
    sample_rate: int = 44100,
    impact_times: tuple[float, ...] = (1.8, 5.6, 10.6, 12.6),
) -> Path:
    """تولید فایل صوتی استریو ۴۴.۱ کیلوهرتز با بیت مدرن ورزشی-تحلیلی و ایمپکت در لحظهٔ تغییر صحنه‌ها."""
    out = Path(output_wav)
    out.parent.mkdir(parents=True, exist_ok=True)

    total_samples = max(sample_rate, int(duration_sec * sample_rate))
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0
    step_sec = beat_sec / 4.0  # نُت شانزدهم

    # خط بیس مدرن در گام ر مینور (D2, Bb1, C2, A1)
    bass_freqs = (73.42, 58.27, 65.41, 55.00)
    arp_notes = (293.66, 349.23, 440.00, 523.25, 440.00, 349.23, 329.63, 293.66)

    rng = random.Random(42)
    frames = bytearray()
    two_pi = 2.0 * math.pi

    for n in range(total_samples):
        t = n / sample_rate
        # محو ورود و خروج نرم
        env_master = 1.0
        if t < 0.35:
            env_master = t / 0.35
        elif t > duration_sec - 1.1:
            env_master = max(0.0, (duration_sec - t) / 1.1)

        beat_pos = t % beat_sec
        bar_idx = int(t // bar_sec) % len(bass_freqs)
        beat_in_bar = int((t % bar_sec) // beat_sec)
        step_pos = t % step_sec
        step_idx = int(t // step_sec)

        # ۱) کیک درام کوبنده روی ضرب‌های ۱ و ۳ (و سینکوپهٔ خفیف)
        kick = 0.0
        if beat_pos < 0.19:
            k_env = math.exp(-beat_pos * 19.0)
            k_freq = 44.0 + 118.0 * math.exp(-beat_pos * 34.0)
            kick = math.sin(two_pi * k_freq * beat_pos) * k_env * 0.62

        # ۲) اسنیر/کلپ مدرن روی ضرب‌های ۲ و ۴
        snare = 0.0
        if beat_in_bar in (1, 3) and beat_pos < 0.14:
            s_env = math.exp(-beat_pos * 26.0)
            noise = rng.uniform(-1.0, 1.0)
            body = math.sin(two_pi * 195.0 * beat_pos) * 0.35
            snare = (noise * 0.65 + body) * s_env * 0.28

        # ۳) های‌هت شانزدهم پرانرژی
        hihat = 0.0
        if step_pos < 0.045:
            accent = 1.0 if (step_idx % 4 == 2) else 0.55
            h_env = math.exp(-step_pos * 85.0)
            hihat = rng.uniform(-1.0, 1.0) * h_env * 0.11 * accent

        # ۴) بیس پالسی مدرن (سایدچین‌شده با کیک برای پمپ جذاب!)
        bf = bass_freqs[bar_idx]
        sidechain = min(1.0, beat_pos / 0.12)
        b_wave = (
            math.sin(two_pi * bf * t) * 0.72
            + math.sin(two_pi * bf * 2.0 * t) * 0.22
            + math.sin(two_pi * bf * 3.0 * t) * 0.06
        )
        bass = b_wave * sidechain * 0.34

        # ۵) آرپژ سینتی‌سایزر ملایم پخش زنده
        af = arp_notes[step_idx % len(arp_notes)]
        arp_env = math.exp(-step_pos * 12.0)
        arp = (math.sin(two_pi * af * t) * 0.7 + math.sin(two_pi * af * 2.0 * t) * 0.3) * arp_env * 0.11

        # ۶) افکت ایمپکت / سووش در لحظات تغییر صحنه
        fx = 0.0
        for it_t in impact_times:
            dt = t - it_t
            if -0.35 <= dt < 0.0:
                # رایزر کوتاه قبل از تغییر صحنه
                p = (dt + 0.35) / 0.35
                fx += rng.uniform(-1.0, 1.0) * (p * p) * 0.16
            elif 0.0 <= dt < 0.30:
                # ضربهٔ ساب-بوم در لحظهٔ ورود صحنه جدید
                fx += math.sin(two_pi * (78.0 - 38.0 * dt) * dt) * math.exp(-dt * 11.0) * 0.36

        mix_l = (kick + snare * 0.95 + hihat * 1.1 + bass + arp * 0.85 + fx) * env_master
        mix_r = (kick + snare * 1.05 + hihat * 0.9 + bass + arp * 1.15 + fx) * env_master

        # لیمیتر نرم (soft clip) برای حجم صدای استاندارد بدون دیستورشن
        sl = int(max(-1.0, min(1.0, math.tanh(mix_l * 1.15))) * 30000)
        sr = int(max(-1.0, min(1.0, math.tanh(mix_r * 1.15))) * 30000)
        frames.extend(struct.pack("<hh", sl, sr))

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))
    return out
