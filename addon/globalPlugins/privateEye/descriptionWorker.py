from __future__ import annotations

import threading
import time

import wx
from logHandler import log

from .capturer import ScreenCapturer
from .contextManager import DescriptionContext
from .ollamaClient import describe_image, normalize_base_url


def _speak(text: str) -> None:
	import speech

	priority = getattr(getattr(speech, "priorities", None), "Spri", None)
	nowPriority = getattr(priority, "NOW", None)
	if nowPriority is not None:
		speech.speakText(text, priority=nowPriority)
	else:
		speech.speakText(text)


def _shortDetail(exception: Exception) -> str:
	detail = str(exception).strip().replace("\r", " ").replace("\n", " ")
	if len(detail) > 180:
		detail = detail[:177] + "..."
	return detail


class DescriptionWorker(threading.Thread):
	def __init__(
		self,
		base_url: str,
		model: str,
		interval: float,
		request_timeout: float,
		system_prompt: str,
		context: DescriptionContext,
		region=None,
	):
		super().__init__(name="PrivateEyeWorker", daemon=True)
		self.base_url = normalize_base_url(base_url)
		self.model = model
		self.interval = interval
		self.request_timeout = request_timeout
		self.system_prompt = system_prompt
		self.context = context
		self.capturer = ScreenCapturer(region=region)
		self._stopEvent = threading.Event()
		self._lastErrorAt = 0.0

	def stop(self) -> None:
		self._stopEvent.set()

	def _reportError(self, spokenMessage: str, exception: Exception, includeDetail: bool = False) -> None:
		log.error(f"Private Eye {spokenMessage}: {exception}", exc_info=True)
		now = time.monotonic()
		if now - self._lastErrorAt > 60:
			self._lastErrorAt = now
			message = f"Private Eye {spokenMessage}"
			if includeDetail:
				message = f"{message}: {_shortDetail(exception)}"
			wx.CallAfter(_speak, message)

	def run(self) -> None:
		while not self._stopEvent.is_set():
			started = time.monotonic()
			try:
				frame = self.capturer.capture()
				text = describe_image(
					self.base_url,
					self.model,
					frame.image_base64,
					self.context.format_for_prompt(),
					self.system_prompt,
					timeout=self.request_timeout,
				)
				if text and text != "[NO CHANGE]":
					self.context.add(text, frame.timestamp)
					wx.CallAfter(_speak, text)
			except ConnectionError as e:
				self._reportError(f"could not connect to Ollama at {self.base_url}", e)
			except TimeoutError as e:
				self._reportError("Ollama request timed out", e, includeDetail=True)
			except ImportError as e:
				self._reportError("could not load capture dependencies", e)
			except RuntimeError as e:
				self._reportError("Ollama request failed", e, includeDetail=True)
			except Exception as e:
				self._reportError("capture or description failed", e)
			remaining = self.interval - (time.monotonic() - started)
			if remaining > 0:
				self._stopEvent.wait(remaining)
