from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from buildVars import addon_info


ROOT = Path(__file__).resolve().parents[1]


def render_manifest() -> Path:
	template = (ROOT / "manifest.ini.tpl").read_text(encoding="utf-8")
	manifest = template.format(**addon_info)
	target = ROOT / "addon" / "manifest.ini"
	target.write_text(manifest, encoding="utf-8", newline="\n")
	return target


def build_addon() -> Path:
	render_manifest()
	dist_dir = ROOT / "dist"
	dist_dir.mkdir(exist_ok=True)
	output = dist_dir / f"{addon_info['addon_name']}-{addon_info['addon_version']}.nvda-addon"
	if output.exists():
		output.unlink()

	with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
		for path in (ROOT / "addon").rglob("*"):
			if _should_skip(path):
				continue
			if path.is_file():
				archive.write(path, path.relative_to(ROOT / "addon").as_posix())
		archive.write(ROOT / "COPYING.txt", "COPYING.txt")

	print(f"Created {output}")
	return output


def _should_skip(path: Path) -> bool:
	parts = set(path.parts)
	return (
		"__pycache__" in parts
		or path.suffix in {".pyc", ".pyo"}
	)


def clean() -> None:
	for path in (ROOT / "addon" / "manifest.ini",):
		if path.exists():
			path.unlink()
	for directory in (ROOT / "dist", ROOT / "build"):
		if directory.exists():
			shutil.rmtree(directory)


if __name__ == "__main__":
	if os.environ.get("CLEAN"):
		clean()
	else:
		build_addon()
