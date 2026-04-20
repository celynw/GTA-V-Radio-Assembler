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

if TYPE_CHECKING:
	from pathlib import Path

	from .types import ChainSlot, MusicUnit

console = Console()


class TimelineRenderer:
	"""Render timeline audio from units and chains."""

	@staticmethod
	def render(
		input_file: Path,
		audio_root: Path,
		output_dir: Path,
		units: list[MusicUnit],
		chains: list[ChainSlot],
	) -> tuple[list[Path], int]:
		"""Render timeline: speech blocks, intros, and mains."""
		station_audio_dir = AudioProcessor.find_station_audio_dir(
			audio_root, input_file
		)
		audio_index = AudioProcessor.index_station_audio_files(station_audio_dir)

		output_dir.mkdir(parents=True, exist_ok=True)
		timeline: list[Path] = []
		generated_speech_count = 0

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
					speech_out = output_dir / speech_name
					rendered_speech = AudioProcessor.render_speech_block(
						speech_tokens,
						audio_index,
						speech_out,
					)
					timeline.append(rendered_speech)
					generated_speech_count += 1

				if unit.intro is not None:
					intro_file = AudioProcessor.resolve_audio_file(
						unit.intro, audio_index
					)
					timeline.append(intro_file)

				music_file = AudioProcessor.resolve_audio_file(
					unit.main_track, audio_index
				)
				timeline.append(music_file)
				progress.advance(task_id)

		playlist_file = output_dir / "timeline.m3u"
		playlist_file.write_text("\n".join(path.as_posix() for path in timeline) + "\n")

		return timeline, generated_speech_count
