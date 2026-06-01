from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from threading import RLock


@dataclass(frozen=True)
class DescriptionEntry:
	timestamp: float
	text: str

	def formatted_time(self) -> str:
		return datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")


class DescriptionContext:
	def __init__(self, max_entries: int = 8):
		self._lock = RLock()
		self._entries = deque(maxlen=max_entries)

	@property
	def max_entries(self) -> int:
		return self._entries.maxlen or 0

	@max_entries.setter
	def max_entries(self, value: int):
		with self._lock:
			existing = list(self._entries)[-value:]
			self._entries = deque(existing, maxlen=value)

	def add(self, text: str, timestamp: float | None = None) -> None:
		text = text.strip()
		if not text:
			return
		with self._lock:
			self._entries.append(DescriptionEntry(timestamp or datetime.now().timestamp(), text))

	def clear(self) -> None:
		with self._lock:
			self._entries.clear()

	def is_empty(self) -> bool:
		with self._lock:
			return not self._entries

	def format_for_prompt(self) -> str:
		with self._lock:
			if not self._entries:
				return (
					"Continuity context: no previous descriptions yet. "
					"Introduce important visible people, objects, places, and text briefly."
				)
			lines = [
				"Continuity context from recent frames, oldest to newest:",
			]
			for entry in self._entries:
				lines.append(f"- {entry.formatted_time()}: {entry.text}")
			lines.append(
				"Use this context for continuity. If a person, object, game cover, menu, or place appears again, "
				"refer to it by the same short label instead of re-describing it. Describe only meaningful new visual "
				"information or changes in position, action, text, hazards, paths, or selected items."
			)
			return "\n".join(lines)
