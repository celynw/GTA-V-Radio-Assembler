"""Utility functions."""

import re

from .types import AssemblerError

_SUFFIX_PATTERN = re.compile(r"^(?P<base>.+)_(?P<num>\d+)$")


def fail(message: str) -> None:
	"""Raise a standard assembly error."""
	raise AssemblerError(message)


def split_base_and_suffix(token: str) -> tuple[str, int | None]:
	"""Split TOKEN_01 into (TOKEN, 1)."""
	match = _SUFFIX_PATTERN.match(token)
	if match is None:
		return (token, None)
	return (match.group("base"), int(match.group("num")))


def sort_tokens(tokens: list[str]) -> list[str]:
	"""Sort tokens by numeric suffix when present, then lexically."""

	def _key(token: str) -> tuple[str, int, str]:
		base, suffix = split_base_and_suffix(token)
		return (base, suffix if suffix is not None else -1, token)

	return sorted(tokens, key=_key)


def spread_indices(item_count: int, candidate_indices: list[int]) -> list[int]:
	"""Select item_count unique indices spread across candidate_indices."""
	if item_count == 0:
		return []
	if item_count > len(candidate_indices):
		message = (
			"Not enough candidate slots for allocation "
			f"(needed {item_count}, available {len(candidate_indices)})."
		)
		fail(message)

	if item_count == len(candidate_indices):
		return candidate_indices.copy()

	selected: list[int] = []
	last_position = len(candidate_indices) - 1
	for idx in range(item_count):
		# Evenly distribute picks across the available range.
		position = (
			round(idx * (last_position / (item_count - 1))) if item_count > 1 else 0
		)
		selected.append(candidate_indices[position])

	# Round() can collide when density is high; repair deterministically.
	used: set[int] = set()
	repaired: list[int] = []
	for value in selected:
		if value not in used:
			used.add(value)
			repaired.append(value)
			continue
		for candidate in candidate_indices:
			if candidate not in used:
				used.add(candidate)
				repaired.append(candidate)
				break

	return repaired
