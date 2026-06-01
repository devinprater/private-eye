import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
	"ollamaClient",
	ROOT / "addon" / "globalPlugins" / "liveDescriber" / "ollamaClient.py",
)
ollamaClient = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ollamaClient
spec.loader.exec_module(ollamaClient)


class FakeResponse:
	def __init__(self, payload):
		self.payload = payload

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		return False

	def read(self):
		return self.payload


def test_normalize_base_url():
	assert ollamaClient.normalize_base_url("192.168.0.199:11434") == "http://192.168.0.199:11434"
	assert ollamaClient.normalize_base_url("http://192.168.0.199:11434") == "http://192.168.0.199:11434"
	assert ollamaClient.normalize_base_url("http://192.168.0.199:11434/") == "http://192.168.0.199:11434"


def test_list_models_returns_names():
	payload = json.dumps({"models": [{"name": "b"}, {"name": "a"}, {"bad": "x"}]}).encode("utf-8")
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(payload)) as urlopen:
		assert ollamaClient.list_models("host:11434") == ["b", "a"]
		request = urlopen.call_args.args[0]
		assert request.full_url == "http://host:11434/api/tags"


def test_list_models_handles_empty_or_malformed_model_arrays():
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(b"{}")):
		assert ollamaClient.list_models("host:11434") == []
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(b"")):
		assert ollamaClient.list_models("host:11434") == []
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(b'{"models":{}}')):
		assert ollamaClient.list_models("host:11434") == []
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(b"not json")):
		try:
			ollamaClient.list_models("host:11434")
		except ValueError:
			pass
		else:
			raise AssertionError("Expected ValueError")


def test_list_models_raises_on_connection_failure():
	with mock.patch.object(ollamaClient, "urlopen", side_effect=URLError("down")):
		try:
			ollamaClient.list_models("host:11434")
		except ConnectionError:
			pass
		else:
			raise AssertionError("Expected ConnectionError")


def test_list_models_raises_clear_timeout():
	with mock.patch.object(ollamaClient, "urlopen", side_effect=TimeoutError("timed out")):
		try:
			ollamaClient.list_models("host:11434", timeout=12)
		except TimeoutError as e:
			assert "12 seconds" in str(e)
			assert "/api/tags" in str(e)
		else:
			raise AssertionError("Expected TimeoutError")


def test_describe_image_payload():
	payload = json.dumps({"response": "A person enters."}).encode("utf-8")
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(payload)) as urlopen:
		text = ollamaClient.describe_image("host:11434", "gemma4", "abc123", "previous")

	assert text == "A person enters."
	request = urlopen.call_args.args[0]
	body = json.loads(request.data.decode("utf-8"))
	assert request.full_url == "http://host:11434/api/generate"
	assert body["model"] == "gemma4"
	assert body["stream"] is False
	assert body["system"] == ollamaClient.DEFAULT_SYSTEM_PROMPT
	assert "previous" in body["prompt"]
	assert "continuity context" in body["prompt"].lower()
	assert "same short label" in body["prompt"]
	assert body["images"] == ["abc123"]
	assert body["options"]["num_predict"] == 80
	assert body["options"]["temperature"] == 0.3


def test_describe_image_uses_custom_system_prompt():
	payload = json.dumps({"response": "A screen is visible."}).encode("utf-8")
	with mock.patch.object(ollamaClient, "urlopen", return_value=FakeResponse(payload)) as urlopen:
		ollamaClient.describe_image("host:11434", "gemma4", "abc123", "previous", system_prompt="custom")

	body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
	assert body["system"] == "custom"
