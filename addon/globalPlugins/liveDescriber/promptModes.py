from __future__ import annotations


PROMPT_MODE_AUTO = "Automatic"
PROMPT_MODE_GENERAL = "General"
PROMPT_MODE_VIDEO = "Video"
PROMPT_MODE_GAME = "Game"
PROMPT_MODES = (
	PROMPT_MODE_AUTO,
	PROMPT_MODE_GENERAL,
	PROMPT_MODE_VIDEO,
	PROMPT_MODE_GAME,
)


VIDEO_PROMPT = (
	"You are providing audio description for a blind viewer. "
	"Describe important visual information not conveyed by dialogue or sound: setting, scene changes, actions, "
	"characters, facial expressions, costumes, on-screen text, and visual jokes or reveals. "
	"Use present tense, one concise sentence, and prioritize what matters to understanding the story. "
	"Maintain continuity by reusing previously established short labels for recurring characters, objects, and places. "
	"Describe what changed instead of reintroducing the same subject. "
	"Do not speculate beyond visible evidence. "
	"If the frame has not meaningfully changed, respond exactly with [NO CHANGE]."
)


GAME_PROMPT = (
	"You are describing a game screen for a blind player. "
	"Prioritize playable information: menu text and selected item, current area, hazards, enemies, pathways, doors, "
	"objectives, interactable objects, characters, and directions using left/right/above/below/center and approximate distance. "
	"For characters, mention appearance only when useful for identification. "
	"Maintain continuity by reusing previously established names for menus, areas, characters, enemies, objects, and hazards. "
	"Describe what changed or what is newly actionable instead of repeating known details. "
	"Keep the response short and actionable. "
	"If the frame has not meaningfully changed, respond exactly with [NO CHANGE]."
)


STREAMING_TITLE_PATTERNS = (
	"youtube",
	"netflix",
	"hulu",
	"disney+",
	"disney plus",
	"prime video",
	"amazon prime",
	"max",
	"hbo max",
	"peacock",
	"paramount+",
	"paramount plus",
	"apple tv",
	"twitch",
	"vimeo",
	"crunchyroll",
	"plex",
	"jellyfin",
)


GAME_TITLE_PATTERNS = (
	"ppsspp",
	"retroarch",
	"dolphin",
	"pcsx2",
	"rpcs3",
	"duckstation",
	"dosbox",
	"cemu",
	"citra",
	"ryujinx",
	"yuzu",
	"mame",
	"mednafen",
	"xemu",
	"melonds",
	"mgba",
)


def select_prompt_mode(configured_mode: str, window_title: str) -> str:
	if configured_mode in (PROMPT_MODE_GENERAL, PROMPT_MODE_VIDEO, PROMPT_MODE_GAME):
		return configured_mode
	title = window_title.lower()
	if _contains_any(title, GAME_TITLE_PATTERNS):
		return PROMPT_MODE_GAME
	if _contains_any(title, STREAMING_TITLE_PATTERNS):
		return PROMPT_MODE_VIDEO
	return PROMPT_MODE_GENERAL


def get_prompt_for_mode(effective_mode: str, general_prompt: str) -> str:
	if effective_mode == PROMPT_MODE_VIDEO:
		return VIDEO_PROMPT
	if effective_mode == PROMPT_MODE_GAME:
		return GAME_PROMPT
	return general_prompt.strip()


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
	return any(pattern in value for pattern in patterns)
