"""GTA V Radio Soundtrack Assembler CLI."""

import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .assembler import PlaylistAssembler
from .audio import AudioProcessor
from .rendering import OutputRenderer
from .timeline import TimelineRenderer
from .types import AssemblerError, AssemblySummary

app = typer.Typer()
console = Console()
MIN_FLAC_COMPRESSION_LEVEL = 0
MAX_FLAC_COMPRESSION_LEVEL = 12


@app.command()
def main(
	audio_dir: Annotated[
		Path,
		typer.Argument(
			exists=True,
			file_okay=False,
			dir_okay=True,
			readable=True,
			help="Directory containing audio WAV files.",
		),
	],
	*,
	render: Annotated[
		Path | None,
		typer.Option(
			help="Render to this directory (final FLAC album). Omit to skip rendering.",
		),
	] = None,
	sample_rate: Annotated[
		int,
		typer.Option(
			help="Sample rate (Hz) for final album FLAC export.",
		),
	] = 32000,
	compression_level: Annotated[
		int,
		typer.Option(
			help="FLAC compression level for final album export (0-12).",
		),
	] = 8,
) -> None:
	"""Assemble a radio station playlist from WAV audio files."""
	if not (
		MIN_FLAC_COMPRESSION_LEVEL <= compression_level <= MAX_FLAC_COMPRESSION_LEVEL
	):
		console.print(
			"[red]Error:[/red] --compression-level must be between "
			f"{MIN_FLAC_COMPRESSION_LEVEL} and {MAX_FLAC_COMPRESSION_LEVEL}.",
		)
		raise typer.Exit(code=1)

	if sample_rate <= 0:
		console.print(
			"[red]Error:[/red] --sample-rate must be positive.",
		)
		raise typer.Exit(code=1)

	rendered_timeline: list[Path] = []
	generated_speech_count = 0
	rendered_album_track_count = 0
	try:
		console.print("[cyan]Probing audio durations...[/cyan]")
		duration_index, duration_warnings = AudioProcessor.build_duration_index(
			audio_dir,
		)
		(
			_,
			units,
			chains,
			warnings,
			total,
			excluded,
			omitted,
		) = PlaylistAssembler.build_plan(audio_dir, duration_by_token=duration_index)
		warnings.extend(duration_warnings)
	except AssemblerError as exc:
		console.print(f"[red]Error:[/red] {exc}")
		raise typer.Exit(code=1) from exc

	OutputRenderer.render(
		summary_data=AssemblySummary(
			audio_dir=audio_dir,
			total_tokens=total,
			excluded_count=excluded,
			omitted_intro_count=omitted,
			rendered_track_count=len(rendered_timeline),
			generated_speech_count=generated_speech_count,
		),
		units=units,
		chains=chains,
		duration_by_token=duration_index,
		warnings=warnings,
	)

	if render:
		console.print("[cyan]Starting audio render...[/cyan]")
		with tempfile.TemporaryDirectory(prefix="gta_radio_render_") as tmp_dir:
			try:
				(
					rendered_timeline,
					generated_speech_count,
					rendered_album_track_count,
				) = TimelineRenderer.render(
					audio_dir=audio_dir,
					temp_dir=Path(tmp_dir),
					units=units,
					chains=chains,
					output_dir=render,
					sample_rate=sample_rate,
					compression_level=compression_level,
				)
			except AssemblerError as exc:
				console.print(f"[red]Error:[/red] {exc}")
				raise typer.Exit(code=1) from exc

			console.print(
				"[green]Render complete:[/green] "
				f"{generated_speech_count} speech clips, "
				f"{len(rendered_timeline)} timeline entries.",
			)
			console.print(
				"[green]Final album rendered:[/green] "
				f"{rendered_album_track_count} FLAC files in "
				f"{render.as_posix()}",
			)


if __name__ == "__main__":
	# Typer handles CLI lifecycle and exits.
	app(prog_name=Path(sys.argv[0]).name)
