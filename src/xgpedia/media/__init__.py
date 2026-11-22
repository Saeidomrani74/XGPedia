"""پکیج تولید رسانهٔ رایگان باکیفیت (تصویر و ویدیو) با زنجیرهٔ پشتیبان چندارائه‌دهنده."""
from src.xgpedia.media.free_media import (
    FreeImageRouter,
    FreeVideoRouter,
    MediaGenerationResult,
    generate_free_image,
    generate_free_video,
)

__all__ = [
    "FreeImageRouter",
    "FreeVideoRouter",
    "MediaGenerationResult",
    "generate_free_image",
    "generate_free_video",
]
