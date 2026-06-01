from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_SYSTEM_PROMPT = (
	"You are describing live screen content for a blind NVDA user. "
	"Be concise and focus on meaningful visual changes. "
	"Read important on-screen text. "
	"Maintain continuity across frames by reusing short labels for recurring people, objects, menus, and places. "
	"If the frame has not meaningfully changed, respond exactly with [NO CHANGE]."
)


def normalize_base_url(base_url: str) -> str:
	value = base_url.strip()
	if not value:
		raise ValueError("Ollama base URL cannot be empty.")
	if "://" not in value:
		value = "http://" + value
	parsed = urlparse(value)
	if not parsed.netloc:
		raise ValueError(f"Invalid Ollama base URL: {base_url}")
	return value.rstrip("/")


def _json_request(url: str, payload: dict[str, Any] | None = None, timeout: float = 10) -> dict[str, Any]:
	data = None if payload is None else json.dumps(payload).encode("utf-8")
	headers = {"Accept": "application/json"}
	if data is not None:
		headers["Content-Type"] = "application/json"
	request = Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
	try:
		with urlopen(request, timeout=timeout) as response:
			raw = response.read()
	except HTTPError as e:
		body = e.read().decode("utf-8", errors="replace").strip()
		detail = f": {body}" if body else ""
		raise RuntimeError(f"Ollama returned HTTP {e.code} for {url}{detail}") from e
	except TimeoutError as e:
		raise TimeoutError(f"Ollama request timed out after {timeout:g} seconds at {url}") from e
	except URLError as e:
		raise ConnectionError(f"Could not connect to Ollama at {url}: {e}") from e
	if not raw:
		return {}
	try:
		decoded = json.loads(raw.decode("utf-8"))
	except json.JSONDecodeError as e:
		raise ValueError(f"Ollama returned invalid JSON from {url}") from e
	if not isinstance(decoded, dict):
		raise ValueError(f"Ollama returned unexpected JSON from {url}")
	return decoded


def list_models(base_url: str, timeout: float = 5) -> list[str]:
	url = urljoin(normalize_base_url(base_url) + "/", "api/tags")
	response = _json_request(url, timeout=timeout)
	models = response.get("models", [])
	if not isinstance(models, list):
		return []
	names = []
	for model in models:
		if isinstance(model, dict) and isinstance(model.get("name"), str):
			names.append(model["name"])
	return names


def describe_image(
	base_url: str,
	model: str,
	image_base64: str,
	context_text: str,
	system_prompt: str = DEFAULT_SYSTEM_PROMPT,
	timeout: float = 10,
) -> str:
	url = urljoin(normalize_base_url(base_url) + "/", "api/generate")
	payload = {
		"model": model,
		"stream": False,
		"system": system_prompt,
		"prompt": (
			f"{context_text}\n\n"
			"Describe the current frame in one short sentence. "
			"Use the continuity context above. "
			"Do not repeat details already established unless they changed. "
			"For a recurring subject, use the same short label, such as 'the woman wearing headphones'. "
			"Only mention visible details that matter right now."
		),
		"images": [image_base64],
		"options": {
			"num_predict": 80,
			"temperature": 0.3,
		},
	}
	response = _json_request(url, payload=payload, timeout=timeout)
	text = response.get("response", "")
	return text.strip() if isinstance(text, str) else ""
