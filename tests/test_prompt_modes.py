import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
	"promptModes",
	ROOT / "addon" / "globalPlugins" / "privateEye" / "promptModes.py",
)
promptModes = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = promptModes
spec.loader.exec_module(promptModes)


def test_auto_selects_video_for_streaming_titles():
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_AUTO, "Video - YouTube - Firefox") == promptModes.PROMPT_MODE_VIDEO
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_AUTO, "Netflix - Movie") == promptModes.PROMPT_MODE_VIDEO


def test_auto_selects_game_for_emulator_titles():
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_AUTO, "PPSSPP v1.18") == promptModes.PROMPT_MODE_GAME
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_AUTO, "Dolphin 5.0") == promptModes.PROMPT_MODE_GAME
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_AUTO, "RetroArch") == promptModes.PROMPT_MODE_GAME


def test_manual_prompt_mode_overrides_title():
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_VIDEO, "PPSSPP") == promptModes.PROMPT_MODE_VIDEO
	assert promptModes.select_prompt_mode(promptModes.PROMPT_MODE_GAME, "YouTube") == promptModes.PROMPT_MODE_GAME


def test_prompt_selection_returns_expected_prompt():
	assert promptModes.get_prompt_for_mode(promptModes.PROMPT_MODE_VIDEO, "custom") == promptModes.VIDEO_PROMPT
	assert promptModes.get_prompt_for_mode(promptModes.PROMPT_MODE_GAME, "custom") == promptModes.GAME_PROMPT
	assert promptModes.get_prompt_for_mode(promptModes.PROMPT_MODE_GENERAL, "custom") == "custom"
