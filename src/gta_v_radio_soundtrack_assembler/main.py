"""GTA V Radio Soundtrack Assembler CLI."""

import sys
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
def main(  # noqa: PLR0913
	input_file: Annotated[
		Path,
		typer.Argument(
			exists=True,
			file_okay=True,
			dir_okay=False,
			readable=True,
			help="Path to station list file.",
		),
	],
	audio_root: Annotated[
		Path,
		typer.Option(
			help="Root directory containing station audio folders.",
		),
	] = Path("audio"),
	output_dir: Annotated[
		Path,
		typer.Option(
			help="Directory for generated speech clips and timeline playlist.",
		),
	] = Path("build/assembled"),
	*,
	render: Annotated[
		bool,
		typer.Option(
			help="Render real timeline audio files from token plan.",
		),
	] = False,
	final_album_dir: Annotated[
		Path | None,
		typer.Option(
			help=(
				"Render one numbered FLAC per final sequence row into this "
				"directory. Requires --render."
			),
		),
	] = None,
	final_album_sample_rate: Annotated[
		int,
		typer.Option(
			help="Sample rate (Hz) for final album FLAC export.",
		),
	] = 32000,
	final_album_compression_level: Annotated[
		int,
		typer.Option(
			help="FLAC compression level for final album export (0-12).",
		),
	] = 8,
) -> None:
	"""Assemble a station playlist from a token list file."""
	if final_album_dir is not None and not render:
		console.print(
			"[red]Error:[/red] --final-album-dir requires --render so speech "
			"blocks can be materialized.",
		)
		raise typer.Exit(code=1)

	if not (
		MIN_FLAC_COMPRESSION_LEVEL
		<= final_album_compression_level
		<= MAX_FLAC_COMPRESSION_LEVEL
	):
		console.print(
			"[red]Error:[/red] --final-album-compression-level must be between "
			f"{MIN_FLAC_COMPRESSION_LEVEL} and {MAX_FLAC_COMPRESSION_LEVEL}.",
		)
		raise typer.Exit(code=1)

	if final_album_sample_rate <= 0:
		console.print(
			"[red]Error:[/red] --final-album-sample-rate must be positive.",
		)
		raise typer.Exit(code=1)

	rendered_timeline: list[Path] = []
	generated_speech_count = 0
	rendered_album_track_count = 0
	try:
		console.print("[cyan]Probing audio durations...[/cyan]")
		duration_index, duration_warnings = AudioProcessor.build_duration_index(
			audio_root,
			input_file,
		)
		(
			_,
			units,
			chains,
			warnings,
			total,
			excluded,
			omitted,
		) = PlaylistAssembler.build_plan(input_file, duration_by_token=duration_index)
		warnings.extend(duration_warnings)
	except AssemblerError as exc:
		console.print(f"[red]Error:[/red] {exc}")
		raise typer.Exit(code=1) from exc

	OutputRenderer.render(
		summary_data=AssemblySummary(
			input_file=input_file,
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
		try:
			(
				rendered_timeline,
				generated_speech_count,
				rendered_album_track_count,
			) = TimelineRenderer.render(
				input_file=input_file,
				audio_root=audio_root,
				output_dir=output_dir,
				units=units,
				chains=chains,
				final_album_dir=final_album_dir,
				final_album_sample_rate=final_album_sample_rate,
				final_album_compression_level=final_album_compression_level,
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
			f"[green]Rendered timeline:[/green] "
			f"{(output_dir / 'timeline.m3u').as_posix()}",
		)
		if final_album_dir is not None:
			console.print(
				"[green]Final album rendered:[/green] "
				f"{rendered_album_track_count} FLAC files in "
				f"{final_album_dir.as_posix()}",
			)


if __name__ == "__main__":
	# Typer handles CLI lifecycle and exits.
	app(prog_name=Path(sys.argv[0]).name)
