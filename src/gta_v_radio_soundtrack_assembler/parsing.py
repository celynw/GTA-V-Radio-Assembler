"""Token parsing and classification."""

from typing import TYPE_CHECKING

from .types import EXCLUDED_CATEGORIES, SPEECH_CATEGORIES, MusicGroup
from .utilities import fail, sort_tokens, split_base_and_suffix

if TYPE_CHECKING:
	from pathlib import Path


class TokenParser:
	"""Parse and classify tokens from input file."""

	@staticmethod
	def read_tokens_from_folder(audio_dir: Path) -> list[str]:
		"""Read tokens from audio folder by listing file stems."""
		if not audio_dir.exists() or not audio_dir.is_dir():
			message = f"Audio directory not found: {audio_dir}"
			fail(message)

		audio_extensions = {".wav", ".mp3", ".flac", ".aac"}
		tokens = [
			file_path.stem
			for file_path in sorted(audio_dir.iterdir())
			if file_path.is_file() and file_path.suffix.lower() in audio_extensions
		]

		if not tokens:
			message = f"No audio files found in {audio_dir}"
			fail(message)
		return tokens

	@staticmethod
	def classify_tokens(
		tokens: list[str],
	) -> tuple[dict[str, list[str]], dict[str, MusicGroup], list[str]]:
		"""Classify tokens into speech pools, music groups, and exclusions."""
		speech_pools: dict[str, list[str]] = {
			category: [] for category in SPEECH_CATEGORIES
		}
		music_groups: dict[str, MusicGroup] = {}
		excluded: list[str] = []

		for token in tokens:
			base, suffix = split_base_and_suffix(token)

			if base in EXCLUDED_CATEGORIES:
				excluded.append(token)
				continue

			if base in SPEECH_CATEGORIES:
				speech_pools[base].append(token)
				continue

			group = music_groups.setdefault(
				base,
				MusicGroup(base=base, main_tracks=[], intros=[]),
			)
			if suffix is None:
				group.main_tracks.append(token)
			else:
				group.intros.append(token)

		for category, items in speech_pools.items():
			speech_pools[category] = sort_tokens(items)

		return speech_pools, music_groups, sort_tokens(excluded)
