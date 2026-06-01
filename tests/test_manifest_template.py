from pathlib import Path

from buildVars import addon_info


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_values_do_not_parse_as_lists():
	template = (ROOT / "manifest.ini.tpl").read_text(encoding="utf-8")
	manifest = template.format(**addon_info)
	for line in manifest.splitlines():
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		if key.strip() in {"summary", "description", "author", "changelog", "license"}:
			assert "," not in value, f"{key.strip()} contains a comma and may parse as a list"

