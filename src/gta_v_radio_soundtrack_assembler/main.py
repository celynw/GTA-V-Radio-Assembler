"""GTA V Radio Soundtrack Assembler."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()

console = Console()

SPEECH_CATEGORIES = {"EVENING", "GENERAL", "ID", "MONO_SOLO", "MORNING"}
EXCLUDED_CATEGORIES = {"TO_AD", "TO_NEWS"}
_SUFFIX_PATTERN = re.compile(r"^(?P<base>.+)_(?P<num>\d+)$")


class AssemblerError(Exception):
	"""Raised when the playlist cannot be assembled with the current rules."""


def _fail(message: str) -> None:
	"""Raise a standard assembly error."""
	raise AssemblerError(message)


@dataclass(slots=True)
class MusicGroup:
	"""Represents one music base key and its available tokens."""

	base: str
	main_tracks: list[str]
	intros: list[str]


@dataclass(slots=True)
class MusicUnit:
	"""Represents one assembled music unit."""

	base: str
	main_track: str
	intro: str | None


@dataclass(slots=True)
class ChainSlot:
	"""Represents one speech chain before one music unit."""

	id_tracks: list[str] = field(default_factory=list)
	daypart_track: str | None = None
	daypart_kind: Literal["MORNING", "EVENING"] | None = None
	general_tracks: list[str] = field(default_factory=list)
	mono_tracks: list[str] = field(default_factory=list)

	def as_list(self) -> list[str]:
		"""Return speech items in fixed chain order."""
		items: list[str] = []
		items.extend(self.id_tracks)
		if self.daypart_track is not None:
			items.append(self.daypart_track)
		items.extend(self.general_tracks)
		items.extend(self.mono_tracks)
		return items


@dataclass(slots=True)
class AssemblySummary:
	"""Small summary payload for rendering output."""

	input_file: Path
	total_tokens: int
	excluded_count: int
	omitted_intro_count: int


def _sort_tokens(tokens: list[str]) -> list[str]:
	"""Sort tokens by numeric suffix when present, then lexically."""

	def _key(token: str) -> tuple[str, int, str]:
		base, suffix = _split_base_and_suffix(token)
		return (base, suffix if suffix is not None else -1, token)

	return sorted(tokens, key=_key)


def _split_base_and_suffix(token: str) -> tuple[str, int | None]:
	"""Split TOKEN_01 into (TOKEN, 1)."""
	match = _SUFFIX_PATTERN.match(token)
	if match is None:
		return (token, None)
	return (match.group("base"), int(match.group("num")))


def _spread_indices(item_count: int, candidate_indices: list[int]) -> list[int]:
	"""Select item_count unique indices spread across candidate_indices."""
	if item_count == 0:
		return []
	if item_count > len(candidate_indices):
		message = (
			"Not enough candidate slots for allocation "
			f"(needed {item_count}, available {len(candidate_indices)})."
		)
		_fail(message)

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


def _read_tokens(input_file: Path) -> list[str]:
	"""Read and normalize raw tokens."""
	if not input_file.exists():
		message = f"Input file not found: {input_file}"
		_fail(message)

	raw_tokens = [line.strip() for line in input_file.read_text().splitlines()]
	tokens = [token for token in raw_tokens if token]
	if not tokens:
		message = "Input file is empty after removing blank lines."
		_fail(message)
	return tokens


def _classify_tokens(
	tokens: list[str],
) -> tuple[dict[str, list[str]], dict[str, MusicGroup], list[str]]:
	"""Classify tokens into speech pools, music groups, and exclusions."""
	speech_pools: dict[str, list[str]] = {
		category: [] for category in SPEECH_CATEGORIES
	}
	music_groups: dict[str, MusicGroup] = {}
	excluded: list[str] = []

	for token in tokens:
		base, suffix = _split_base_and_suffix(token)

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
		speech_pools[category] = _sort_tokens(items)

	return speech_pools, music_groups, _sort_tokens(excluded)


def _build_music_units(
	music_groups: dict[str, MusicGroup],
) -> tuple[list[MusicUnit], list[str], list[str]]:
	"""Build one music unit per valid music group."""
	units: list[MusicUnit] = []
	warnings: list[str] = []
	omitted_intros: list[str] = []

	for base in sorted(music_groups):
		group = music_groups[base]
		intros = _sort_tokens(group.intros)
		mains = _sort_tokens(group.main_tracks)

		if not mains:
			warnings.append(
				"Skipping orphan intro group "
				f"{base}: intros exist but no main track token.",
			)
			omitted_intros.extend(intros)
			continue

		if len(mains) > 1:
			message = (
				f"Multiple main tracks detected for base {base}: {', '.join(mains)}"
			)
			_fail(message)

		selected_intro = intros[0] if intros else None
		omitted_intros.extend(intro for intro in intros[1:])
		units.append(MusicUnit(base=base, main_track=mains[0], intro=selected_intro))

	if not units:
		message = "No valid music units were built from the input."
		_fail(message)

	return units, warnings, omitted_intros


def _allocate_speech_chains(  # noqa: C901, PLR0912, PLR0915
	unit_count: int,
	speech_pools: dict[str, list[str]],
) -> list[ChainSlot]:
	"""Allocate speech chains across music units."""
	chains = [ChainSlot() for _ in range(unit_count)]

	def _allocate_single_slot_category(
		category: str,
		field_name: str,
		indices: list[int],
	) -> None:
		tracks = speech_pools[category]
		if not tracks:
			return

		chosen_indices = _spread_indices(len(tracks), indices)
		for track, index in zip(tracks, chosen_indices, strict=True):
			chain = chains[index]
			target = getattr(chain, field_name)
			if isinstance(target, list):
				target.append(track)
			else:
				setattr(chain, field_name, track)
		speech_pools[category] = []

	def _allocate_multi_slot_category(category: str, field_name: str) -> None:
		tracks = speech_pools[category]
		if not tracks:
			return

		for offset, track in enumerate(tracks):
			index = offset % unit_count
			chain = chains[index]
			bucket: list[str] = getattr(chain, field_name)
			bucket.append(track)
		speech_pools[category] = []

	# Opening chain prioritization.
	if speech_pools["ID"]:
		chains[0].id_tracks.append(speech_pools["ID"].pop(0))

	if speech_pools["MORNING"]:
		chains[0].daypart_track = speech_pools["MORNING"].pop(0)
		chains[0].daypart_kind = "MORNING"
	elif speech_pools["EVENING"]:
		chains[0].daypart_track = speech_pools["EVENING"].pop(0)
		chains[0].daypart_kind = "EVENING"

	if speech_pools["GENERAL"]:
		chains[0].general_tracks.append(speech_pools["GENERAL"].pop(0))

	if speech_pools["MONO_SOLO"]:
		chains[0].mono_tracks.append(speech_pools["MONO_SOLO"].pop(0))

	available_indices = list(range(1, unit_count)) if unit_count > 1 else []

	_allocate_multi_slot_category("ID", "id_tracks")

	# Allocate MORNING with front bias.
	morning_tracks = speech_pools["MORNING"]
	if morning_tracks:
		if not available_indices and morning_tracks:
			message = "No remaining chain slots for MORNING tracks."
			_fail(message)

		front_window = max(1, unit_count // 2)
		morning_candidates = [
			index for index in available_indices if index < front_window
		]
		if len(morning_candidates) < len(morning_tracks):
			morning_candidates = available_indices.copy()

		chosen = _spread_indices(len(morning_tracks), morning_candidates)
		for track, index in zip(morning_tracks, chosen, strict=True):
			chains[index].daypart_track = track
			chains[index].daypart_kind = "MORNING"
		speech_pools["MORNING"] = []

	# Allocate EVENING with back bias, never overlapping MORNING chains.
	evening_tracks = speech_pools["EVENING"]
	if evening_tracks:
		if not available_indices and evening_tracks:
			message = "No remaining chain slots for EVENING tracks."
			_fail(message)

		back_window_start = unit_count // 2
		evening_candidates = [
			index
			for index in available_indices
			if index >= back_window_start and chains[index].daypart_track is None
		]
		if len(evening_candidates) < len(evening_tracks):
			evening_candidates = [
				index
				for index in available_indices
				if chains[index].daypart_track is None
			]

		chosen = _spread_indices(len(evening_tracks), evening_candidates)
		for track, index in zip(evening_tracks, chosen, strict=True):
			chains[index].daypart_track = track
			chains[index].daypart_kind = "EVENING"
		speech_pools["EVENING"] = []

	_allocate_multi_slot_category("GENERAL", "general_tracks")

	mono_tracks = speech_pools["MONO_SOLO"]
	if mono_tracks:
		if available_indices:
			_allocate_single_slot_category(
				"MONO_SOLO", "mono_tracks", available_indices
			)
		else:
			message = (
				"No remaining chain slots for MONO_SOLO tracks. "
				"MONO_SOLO currently allows at most one track per chain."
			)
			_fail(message)

	# Fail if anything was left unallocated.
	leftovers: dict[str, list[str]] = {
		category: items for category, items in speech_pools.items() if items
	}
	if leftovers:
		details = ", ".join(
			f"{cat}: {len(items)}" for cat, items in sorted(leftovers.items())
		)
		message = (
			"Could not place all speech tracks. "
			f"Unplaced counts -> {details}. "
			"Increase music units or relax slot constraints."
		)
		_fail(message)

	return chains


def _assemble_sequence(units: list[MusicUnit], chains: list[ChainSlot]) -> list[str]:
	"""Emit final ordered sequence."""
	sequence: list[str] = []
	for chain, unit in zip(chains, units, strict=True):
		sequence.extend(chain.as_list())
		if unit.intro is not None:
			sequence.append(unit.intro)
		sequence.append(unit.main_track)
	return sequence


def _render_output(
	summary_data: AssemblySummary,
	sequence: list[str],
	warnings: list[str],
) -> None:
	"""Render assembled output in a compact rich table."""
	if warnings:
		for warning in warnings:
			console.print(f"[yellow]Warning:[/yellow] {warning}")

	summary = Table(title="Assembly Summary", show_header=True)
	summary.add_column("Metric")
	summary.add_column("Value", justify="right")
	summary.add_row("Input file", str(summary_data.input_file))
	summary.add_row("Input tokens", str(summary_data.total_tokens))
	summary.add_row("Excluded tokens", str(summary_data.excluded_count))
	summary.add_row("Omitted intro variants", str(summary_data.omitted_intro_count))
	summary.add_row("Final sequence length", str(len(sequence)))
	console.print(summary)

	table = Table(title="Assembled Sequence", show_lines=False)
	table.add_column("#", justify="right", style="cyan")
	table.add_column("Token", style="white")
	for index, token in enumerate(sequence, start=1):
		table.add_row(str(index), token)
	console.print(table)


def _build_playlist(input_file: Path) -> tuple[list[str], list[str], int, int, int]:
	"""Build final playlist sequence and summary counters."""
	tokens = _read_tokens(input_file)
	speech_pools, music_groups, excluded = _classify_tokens(tokens)
	units, warnings, omitted_intros = _build_music_units(music_groups)
	chains = _allocate_speech_chains(len(units), speech_pools)
	sequence = _assemble_sequence(units, chains)

	return sequence, warnings, len(tokens), len(excluded), len(omitted_intros)


@app.command()
def main(
	input_file: Path = typer.Argument(
		...,
		exists=True,
		file_okay=True,
		dir_okay=False,
		readable=True,
		help="Path to station list file.",
	),
) -> None:
	"""Assemble a station playlist from a token list file."""
	try:
		sequence, warnings, total, excluded, omitted = _build_playlist(input_file)
	except AssemblerError as exc:
		console.print(f"[red]Error:[/red] {exc}")
		raise typer.Exit(code=1) from exc

	_render_output(
		summary_data=AssemblySummary(
			input_file=input_file,
			total_tokens=total,
			excluded_count=excluded,
			omitted_intro_count=omitted,
		),
		sequence=sequence,
		warnings=warnings,
	)


if __name__ == "__main__":
	# Typer handles CLI lifecycle and exits.
	app(prog_name=Path(sys.argv[0]).name)
