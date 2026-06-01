from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass
from typing import Mapping

from PIL import Image
import mss


@dataclass(frozen=True)
class CapturedFrame:
	image_base64: str
	timestamp: float


class ScreenCapturer:
	def __init__(self, region: Mapping[str, int] | None = None, max_size: tuple[int, int] = (1280, 720), jpeg_quality: int = 75):
		self.region = dict(region) if region else None
		self.max_size = max_size
		self.jpeg_quality = jpeg_quality

	def capture(self) -> CapturedFrame:
		timestamp = time.time()
		with mss.mss() as sct:
			monitor = self.region or sct.monitors[1]
			raw = sct.grab(monitor)
			image = Image.frombytes("RGB", raw.size, raw.rgb)
		image.thumbnail(self.max_size, Image.Resampling.LANCZOS)
		buffer = io.BytesIO()
		image.save(buffer, format="JPEG", quality=self.jpeg_quality, optimize=True)
		return CapturedFrame(base64.b64encode(buffer.getvalue()).decode("ascii"), timestamp)

