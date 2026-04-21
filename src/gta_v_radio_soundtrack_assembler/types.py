"""Data types for the assembler."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
	from pathlib import Path

SPEECH_CATEGORIES = {"EVENING", "GENERAL", "ID", "MONO_SOLO", "MORNING"}
EXCLUDED_CATEGORIES = {"TO_AD", "TO_NEWS"}


class AssemblerError(Exception):
	"""Raised when the playlist cannot be assembled with the current rules."""


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

	id_track: str | None = None
	daypart_track: str | None = None
	daypart_kind: Literal["MORNING", "EVENING"] | None = None
	general_tracks: list[str] = field(default_factory=list)
	mono_tracks: list[str] = field(default_factory=list)

	def as_list(self) -> list[str]:
		"""Return speech items in fixed chain order."""
		items: list[str] = []
		if self.id_track is not None:
			items.append(self.id_track)
		if self.daypart_track is not None:
			items.append(self.daypart_track)
		items.extend(self.general_tracks)
		items.extend(self.mono_tracks)
		return items


@dataclass(slots=True)
class AssemblySummary:
	"""Small summary payload for rendering output."""

	audio_dir: Path
	total_tokens: int
	excluded_count: int
	omitted_intro_count: int
	rendered_track_count: int = 0
	generated_speech_count: int = 0


@dataclass(slots=True)
class AudioFormat:
	"""Audio settings used for speech rendering."""

	codec_name: str
	sample_rate: int
	channels: int
