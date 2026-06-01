import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
	"contextManager",
	ROOT / "addon" / "globalPlugins" / "privateEye" / "contextManager.py",
)
contextManager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contextManager
spec.loader.exec_module(contextManager)
DescriptionContext = contextManager.DescriptionContext


def test_context_max_length_and_formatting():
	context = DescriptionContext(max_entries=2)
	context.add("one", timestamp=1)
	context.add("two", timestamp=2)
	context.add("three", timestamp=3)

	formatted = context.format_for_prompt()
	assert "one" not in formatted
	assert "two" in formatted
	assert "three" in formatted
	assert formatted.startswith("Continuity context")


def test_clear_and_empty_formatting():
	context = DescriptionContext(max_entries=3)
	assert context.is_empty()
	assert "no previous descriptions" in context.format_for_prompt()
	context.add("visible change", timestamp=1)
	assert not context.is_empty()
	context.clear()
	assert context.is_empty()
	assert "no previous descriptions" in context.format_for_prompt()


def test_context_format_includes_continuity_instruction():
	context = DescriptionContext(max_entries=2)
	context.add("A woman wearing headphones appears.", timestamp=1)
	formatted = context.format_for_prompt()
	assert "Continuity context" in formatted
	assert "same short label" in formatted
	assert "woman wearing headphones" in formatted
