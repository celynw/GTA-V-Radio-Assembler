"""Timeline audio rendering."""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
	BarColumn,
	MofNCompleteColumn,
	Progress,
	SpinnerColumn,
	TextColumn,
	TimeElapsedColumn,
)

from .audio import AudioProcessor
from .utilities import format_track_name

if TYPE_CHECKING:
	from pathlib import Path

	from .types import ChainSlot, MusicUnit

console = Console()


class TimelineRenderer:
	"""Render timeline audio from units and chains."""

	@staticmethod
	def render(  # noqa: PLR0913
		audio_dir: Path,
		temp_dir: Path,
		units: list[MusicUnit],
		chains: list[ChainSlot],
		*,
		output_dir: Path | None = None,
		sample_rate: int = 32000,
		compression_level: int = 8,
	) -> tuple[list[Path], int, int]:
		"""Render timeline and optionally export one FLAC per final row."""
		audio_index = AudioProcessor.index_station_audio_files(audio_dir)

		temp_dir.mkdir(parents=True, exist_ok=True)
		timeline: list[Path] = []
		album_rows: list[tuple[str, Path]] = []
		generated_speech_count = 0
		talk_break_number = 0

		with Progress(
			SpinnerColumn(),
			TextColumn("[progress.description]{task.description}"),
			TextColumn("[cyan]{task.fields[current_track]:<40.40}"),
			BarColumn(),
			MofNCompleteColumn(),
			TimeElapsedColumn(),
			console=console,
		) as progress:
			task_id = progress.add_task(
				"Rendering timeline audio",
				total=len(units),
				current_track="",
			)
			for index, (chain, unit) in enumerate(
				zip(chains, units, strict=True),
				start=1,
			):
				progress.update(
					task_id,
					current_track=unit.main_track,
				)

				speech_tokens = chain.as_list()

				if speech_tokens:
					music_file = AudioProcessor.resolve_audio_file(
						unit.main_track, audio_index
					)
					speech_ext = music_file.suffix
					speech_name = (
						f"{index:03d}_speech_before_{unit.main_track}{speech_ext}"
					)
					speech_out = temp_dir / speech_name
					rendered_speech = AudioProcessor.render_speech_block(
						speech_tokens,
						audio_index,
						speech_out,
					)
					timeline.append(rendered_speech)
					talk_break_number += 1
					album_rows.append(
						(
							f"Talk break {talk_break_number}",
							rendered_speech,
						)
					)
					generated_speech_count += 1

				if unit.intro is not None:
					intro_file = AudioProcessor.resolve_audio_file(
						unit.intro, audio_index
					)
					timeline.append(intro_file)
					album_rows.append(
						(
							format_track_name(unit.intro, is_intro=True),
							intro_file,
						)
					)

				music_file = AudioProcessor.resolve_audio_file(
					unit.main_track, audio_index
				)
				timeline.append(music_file)
				album_rows.append((format_track_name(unit.main_track), music_file))
				progress.advance(task_id)

		rendered_album_track_count = 0
		if output_dir is not None:
			rendered_album_track_count = AudioProcessor.render_final_album_flacs(
				album_rows,
				output_dir,
				sample_rate=sample_rate,
				compression_level=compression_level,
			)

		return timeline, generated_speech_count, rendered_album_track_count
