"""روتر رایگان تولید تصویر و ویدیو باکیفیت (v0.17.1) با زنجیرهٔ پشتیبان چندارائه‌دهنده.

تولید تصویر باکیفیت (ترتیب اولویت خودکار):
  1) Pollinations.ai Authenticated (`POLLINATIONS_API_KEY` از https://enter.pollinations.ai/keys → مدل FLUX)
  2) Cloudflare Workers AI (`@cf/black-forest-labs/flux-1-schnell`) — 10,000 Neurons/day رایگان بدون کارت
  3) NVIDIA NIM (`NVIDIA_API_KEY` → `black-forest-labs/flux.1-schnell`) — 1,000 اعتبار رایگان ماهانه بدون کارت
  4) Replicate (`black-forest-labs/flux-schnell`) — $5 اعتبار رایگان بدون کارت
  5) Stability AI (`stable-image/generate/core`) — 25 اعتبار رایگان ماهانه
  6) Hugging Face Inference (`black-forest-labs/FLUX.1-schnell`) — توکن رایگان HF
  7) Pollinations.ai Public (`flux`, `nologo=true`) — بدون نیاز به کلید API

تولید ویدیو باکیفیت (ترتیب اولویت خودکار):
  1) Pollinations.ai Video (`POLLINATIONS_API_KEY` → مدل `seedance` / `veo`)
  2) Replicate (`wan-video/wan-2.1-t2v-480p`) — $5 اعتبار رایگان بدون کارت
  3) Hugging Face Inference (`Wan-AI/Wan2.1-T2V-1.3B` و `Lightricks/LTX-Video`) — توکن رایگان HF
  4) موتور محلی FFmpeg Ken-Burns (تبدیل کارت PNG یا تصویر تولیدی به ویدیوی ریلز/استوری 1080p با زوم نرم — ۱۰۰٪ رایگان و بدون واترمارک)
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class MediaGenerationResult:
    ok: bool
    provider: str = ""
    output_path: Path | None = None
    errors: list[str] | None = None


class FreeImageRouter:
    """روتر تولید تصویر باکیفیت رایگان با سوییچ خودکار بین ارائه‌دهندگان."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def available_providers(self) -> list[str]:
        provs: list[str] = []
        if os.environ.get("POLLINATIONS_API_KEY"):
            provs.append("pollinations_auth_flux")
        if os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"):
            provs.append("cloudflare_flux")
        if os.environ.get("NVIDIA_API_KEY"):
            provs.append("nvidia_nim_flux")
        if os.environ.get("REPLICATE_API_TOKEN"):
            provs.append("replicate_flux")
        if os.environ.get("STABILITY_API_KEY"):
            provs.append("stability_core")
        if os.environ.get("HF_TOKEN"):
            provs.append("huggingface_flux")
        provs.append("pollinations_flux")  # همیشه فعال بدون نیاز به کلید
        return provs

    def generate(
        self,
        prompt: str,
        out_path: str | Path,
        *,
        width: int = 1080,
        height: int = 1350,
    ) -> MediaGenerationResult:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []

        for prov in self.available_providers():
            try:
                img_bytes = self._call_provider(prov, prompt, width, height)
                if not img_bytes or len(img_bytes) < 2048:
                    raise ValueError("empty or invalid image payload")
                out.write_bytes(img_bytes)
                return MediaGenerationResult(ok=True, provider=prov, output_path=out)
            except Exception as e:
                errors.append(f"{prov}: {type(e).__name__}: {str(e)[:120]}")
                continue

        return MediaGenerationResult(ok=False, errors=errors)

    def _call_provider(self, prov: str, prompt: str, width: int, height: int) -> bytes:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            if prov == "pollinations_auth_flux":
                key = os.environ["POLLINATIONS_API_KEY"].strip()
                enc = urllib.parse.quote(prompt, safe="")
                url = (
                    f"https://gen.pollinations.ai/image/{enc}"
                    f"?model=flux&width={width}&height={height}&nologo=true&enhance=true&key={urllib.parse.quote(key, safe='')}"
                )
                r = client.get(url, headers={"Authorization": f"Bearer {key}"})
                r.raise_for_status()
                return r.content

            if prov == "cloudflare_flux":
                acc = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
                tok = os.environ["CLOUDFLARE_API_TOKEN"].strip()
                r = client.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"prompt": prompt, "num_steps": 4},
                )
                r.raise_for_status()
                ct = r.headers.get("content-type", "")
                if "application/json" in ct:
                    b64 = r.json()["result"]["image"]
                    return base64.b64decode(b64)
                return r.content

            if prov == "nvidia_nim_flux":
                key = os.environ["NVIDIA_API_KEY"].strip()
                r = client.post(
                    "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell",
                    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                    json={"prompt": prompt, "width": min(1024, width), "height": min(1024, height), "steps": 4},
                )
                r.raise_for_status()
                data = r.json()
                b64 = data["artifacts"][0]["base64"]
                return base64.b64decode(b64)

            if prov == "replicate_flux":
                tok = os.environ["REPLICATE_API_TOKEN"].strip()
                ar = "4:5" if height > width else ("16:9" if width > height else "1:1")
                r = client.post(
                    "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                    headers={"Authorization": f"Bearer {tok}", "Prefer": "wait"},
                    json={"input": {"prompt": prompt, "aspect_ratio": ar, "output_format": "png"}},
                )
                r.raise_for_status()
                data = r.json()
                out_url = data["output"][0] if isinstance(data.get("output"), list) else data.get("output")
                if not out_url:
                    raise ValueError("replicate returned no output url")
                img_r = client.get(out_url)
                img_r.raise_for_status()
                return img_r.content

            if prov == "stability_core":
                key = os.environ["STABILITY_API_KEY"].strip()
                ar = "4:5" if height > width else ("16:9" if width > height else "1:1")
                r = client.post(
                    "https://api.stability.ai/v2beta/stable-image/generate/core",
                    headers={"Authorization": f"Bearer {key}", "Accept": "image/*"},
                    files={"none": ""},
                    data={"prompt": prompt, "aspect_ratio": ar, "output_format": "png"},
                )
                r.raise_for_status()
                return r.content

            if prov == "huggingface_flux":
                tok = os.environ["HF_TOKEN"].strip()
                r = client.post(
                    "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"inputs": prompt},
                )
                r.raise_for_status()
                return r.content

            if prov == "pollinations_flux":
                enc = urllib.parse.quote(prompt, safe="")
                url = (
                    f"https://image.pollinations.ai/prompt/{enc}"
                    f"?model=flux&width={width}&height={height}&nologo=true&enhance=true"
                )
                r = client.get(url)
                r.raise_for_status()
                return r.content

        raise ValueError(f"unknown image provider: {prov}")


class FreeVideoRouter:
    """روتر تولید ویدیوی باکیفیت رایگان (Pollinations Seedance / Replicate Wan / HuggingFace / FFmpeg محلی)."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def available_providers(self) -> list[str]:
        provs: list[str] = []
        if os.environ.get("POLLINATIONS_API_KEY"):
            provs.append("pollinations_video")
        if os.environ.get("REPLICATE_API_TOKEN"):
            provs.append("replicate_wan")
        if os.environ.get("HF_TOKEN"):
            provs.append("huggingface_wan")
            provs.append("huggingface_ltx")
        if shutil.which("ffmpeg"):
            provs.append("local_ffmpeg_motion")
        return provs

    def generate(
        self,
        prompt: str,
        out_path: str | Path,
        *,
        source_image: str | Path | None = None,
        duration_sec: int = 6,
        width: int = 1080,
        height: int = 1920,
    ) -> MediaGenerationResult:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []

        if source_image and Path(source_image).exists() and shutil.which("ffmpeg"):
            try:
                self._render_local_ffmpeg_motion(Path(source_image), out, duration_sec, width, height)
                return MediaGenerationResult(ok=True, provider="local_ffmpeg_motion", output_path=out)
            except Exception as e:
                errors.append(f"local_ffmpeg_motion: {type(e).__name__}: {str(e)[:120]}")

        for prov in self.available_providers():
            try:
                if prov == "pollinations_video":
                    data = self._call_pollinations_video(prompt)
                    out.write_bytes(data)
                    return MediaGenerationResult(ok=True, provider=prov, output_path=out)
                if prov == "replicate_wan":
                    data = self._call_replicate_wan(prompt)
                    out.write_bytes(data)
                    return MediaGenerationResult(ok=True, provider=prov, output_path=out)
                if prov == "huggingface_wan":
                    data = self._call_hf_video("Wan-AI/Wan2.1-T2V-1.3B", prompt)
                    out.write_bytes(data)
                    return MediaGenerationResult(ok=True, provider=prov, output_path=out)
                if prov == "huggingface_ltx":
                    data = self._call_hf_video("Lightricks/LTX-Video", prompt)
                    out.write_bytes(data)
                    return MediaGenerationResult(ok=True, provider=prov, output_path=out)
                if prov == "local_ffmpeg_motion":
                    tmp_img = out.with_suffix(".frame.png")
                    img_res = FreeImageRouter().generate(prompt, tmp_img, width=width, height=height)
                    if not img_res.ok or not img_res.output_path:
                        raise RuntimeError(f"base image failed: {img_res.errors}")
                    self._render_local_ffmpeg_motion(img_res.output_path, out, duration_sec, width, height)
                    try:
                        tmp_img.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return MediaGenerationResult(
                        ok=True, provider=f"{img_res.provider}+local_ffmpeg_motion", output_path=out
                    )
            except Exception as e:
                errors.append(f"{prov}: {type(e).__name__}: {str(e)[:120]}")
                continue

        return MediaGenerationResult(ok=False, errors=errors)

    def _call_pollinations_video(self, prompt: str) -> bytes:
        key = os.environ["POLLINATIONS_API_KEY"].strip()
        enc = urllib.parse.quote(prompt, safe="")
        url = f"https://gen.pollinations.ai/video/{enc}?model=seedance&key={urllib.parse.quote(key, safe='')}"
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            r = client.get(url, headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            if len(r.content) < 4096:
                raise ValueError("pollinations returned empty video")
            return r.content

    def _call_replicate_wan(self, prompt: str) -> bytes:
        tok = os.environ["REPLICATE_API_TOKEN"].strip()
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            r = client.post(
                "https://api.replicate.com/v1/models/wan-video/wan-2.1-t2v-480p/predictions",
                headers={"Authorization": f"Bearer {tok}"},
                json={"input": {"prompt": prompt}},
            )
            r.raise_for_status()
            pred = r.json()
            poll_url = pred.get("urls", {}).get("get")
            deadline = time.time() + self.timeout
            while pred.get("status") not in {"succeeded", "failed", "canceled"} and time.time() < deadline:
                time.sleep(3.0)
                pr = client.get(poll_url, headers={"Authorization": f"Bearer {tok}"})
                pr.raise_for_status()
                pred = pr.json()
            if pred.get("status") != "succeeded":
                raise RuntimeError(f"replicate status={pred.get('status')} error={pred.get('error')}")
            out_url = pred["output"][0] if isinstance(pred.get("output"), list) else pred.get("output")
            vr = client.get(out_url)
            vr.raise_for_status()
            return vr.content

    def _call_hf_video(self, model_id: str, prompt: str) -> bytes:
        tok = os.environ["HF_TOKEN"].strip()
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            r = client.post(
                f"https://router.huggingface.co/hf-inference/models/{model_id}",
                headers={"Authorization": f"Bearer {tok}"},
                json={"inputs": prompt},
            )
            r.raise_for_status()
            return r.content

    def _render_local_ffmpeg_motion(
        self, src_img: Path, out_mp4: Path, duration_sec: int, width: int, height: int
    ) -> None:
        fps = 30
        frames = max(30, duration_sec * fps)
        vf = (
            f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
            f"crop={width * 2}:{height * 2},"
            f"zoompan=z='min(zoom+0.0008,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps},"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.5, duration_sec - 0.5):.1f}:d=0.5"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(src_img),
            "-vf", vf, "-t", str(duration_sec),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out_mp4),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-300:])


def generate_free_image(
    prompt: str, out_path: str | Path, *, width: int = 1080, height: int = 1350
) -> MediaGenerationResult:
    return FreeImageRouter().generate(prompt, out_path, width=width, height=height)


def generate_free_video(
    prompt: str,
    out_path: str | Path,
    *,
    source_image: str | Path | None = None,
    duration_sec: int = 6,
    width: int = 1080,
    height: int = 1920,
) -> MediaGenerationResult:
    return FreeVideoRouter().generate(
        prompt, out_path, source_image=source_image, duration_sec=duration_sec, width=width, height=height
    )
