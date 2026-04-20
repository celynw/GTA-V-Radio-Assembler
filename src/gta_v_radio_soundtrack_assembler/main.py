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


@app.command()
def main(
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
) -> None:
	"""Assemble a station playlist from a token list file."""
	rendered_timeline: list[Path] = []
	generated_speech_count = 0
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
			rendered_timeline, generated_speech_count = TimelineRenderer.render(
				input_file=input_file,
				audio_root=audio_root,
				output_dir=output_dir,
				units=units,
				chains=chains,
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


if __name__ == "__main__":
	# Typer handles CLI lifecycle and exits.
	app(prog_name=Path(sys.argv[0]).name)
