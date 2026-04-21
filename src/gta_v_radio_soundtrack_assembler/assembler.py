"""Playlist assembly orchestration."""

from typing import TYPE_CHECKING

from .music import MusicUnitBuilder
from .parsing import TokenParser
from .scheduling import Scheduler
from .sequence import SequenceBuilder

if TYPE_CHECKING:
	from pathlib import Path

	from .types import ChainSlot, MusicUnit


class PlaylistAssembler:
	"""Orchestrate full playlist assembly process."""

	@staticmethod
	def build_plan(
		audio_dir: Path,
		duration_by_token: dict[str, float] | None = None,
	) -> tuple[list[str], list[MusicUnit], list[ChainSlot], list[str], int, int, int]:
		"""Build sequence and structured unit/chain plan."""
		tokens = TokenParser.read_tokens_from_folder(audio_dir)
		speech_pools, music_groups, excluded = TokenParser.classify_tokens(tokens)
		units, warnings, omitted_intros = MusicUnitBuilder.build(music_groups)
		chains = Scheduler.allocate(
			len(units),
			speech_pools,
			duration_by_token=duration_by_token,
		)
		sequence = SequenceBuilder.assemble(units, chains)
		return (
			sequence,
			units,
			chains,
			warnings,
			len(tokens),
			len(excluded),
			len(omitted_intros),
		)
