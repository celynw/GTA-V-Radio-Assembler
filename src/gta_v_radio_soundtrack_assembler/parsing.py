"""Token parsing and classification."""

from typing import TYPE_CHECKING

from .types import EXCLUDED_CATEGORIES, SPEECH_CATEGORIES, MusicGroup
from .utilities import fail, sort_tokens, split_base_and_suffix

if TYPE_CHECKING:
	from pathlib import Path


class TokenParser:
	"""Parse and classify tokens from input file."""

	@staticmethod
	def read_tokens(input_file: Path) -> list[str]:
		"""Read and normalize raw tokens."""
		if not input_file.exists():
			message = f"Input file not found: {input_file}"
			fail(message)

		raw_tokens = [line.strip() for line in input_file.read_text().splitlines()]
		tokens = [token for token in raw_tokens if token]
		if not tokens:
			message = "Input file is empty after removing blank lines."
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
