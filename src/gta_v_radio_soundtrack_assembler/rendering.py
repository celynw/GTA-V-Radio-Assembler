"""Output rendering to console."""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
	from .types import AssemblySummary, ChainSlot, MusicUnit

console = Console()


class OutputRenderer:
	"""Render assembled output and statistics."""

	@staticmethod
	def fmt_duration(seconds: float | None) -> str:
		"""Format seconds as M:SS.s or SS.s (when under a minute), or —."""
		if seconds is None:
			return "—"
		minutes = int(seconds) // 60
		secs = seconds % 60
		if minutes:
			return f"{minutes}:{secs:04.1f}"
		return f"{secs:4.1f}"

	@staticmethod
	def render(
		summary_data: AssemblySummary,
		units: list[MusicUnit],
		chains: list[ChainSlot],
		duration_by_token: dict[str, float],
		warnings: list[str],
	) -> None:
		"""Render assembled output in a compact rich table."""
		if warnings:
			for warning in warnings:
				console.print(f"[yellow]Warning:[/yellow] {warning}")

		total_tokens = sum(
			len(chain.as_list()) + (1 if unit.intro else 0) + 1
			for chain, unit in zip(chains, units, strict=True)
		)

		summary = Table(title="Assembly Summary", show_header=True)
		summary.add_column("Metric")
		summary.add_column("Value", justify="right")
		summary.add_row("Input file", str(summary_data.input_file))
		summary.add_row("Input tokens", str(summary_data.total_tokens))
		summary.add_row("Excluded tokens", str(summary_data.excluded_count))
		summary.add_row("Omitted intro variants", str(summary_data.omitted_intro_count))
		summary.add_row("Final sequence length", str(total_tokens))
		if summary_data.rendered_track_count > 0:
			summary.add_row(
				"Rendered timeline tracks", str(summary_data.rendered_track_count)
			)
			summary.add_row(
				"Generated speech clips",
				str(summary_data.generated_speech_count),
			)
		console.print(summary)

		table = Table(title="Assembled Sequence", show_lines=False)
		table.add_column("#", justify="right", style="cyan")
		table.add_column("Track", style="white")
		table.add_column("Duration", justify="right", style="green")

		track_num = 0
		for chain, unit in zip(chains, units, strict=True):
			speech_tokens = chain.as_list()
			if speech_tokens:
				track_num += 1
				token_dur = sum(
					duration_by_token[t]
					for t in speech_tokens
					if t in duration_by_token
				)
				known = all(t in duration_by_token for t in speech_tokens)
				dur_str = OutputRenderer.fmt_duration(token_dur)
				if not known:
					dur_str = "~" + dur_str
				table.add_row(
					str(track_num),
					"[dim] + [/dim]".join(speech_tokens),
					dur_str,
				)
			if unit.intro is not None:
				track_num += 1
				table.add_row(
					str(track_num),
					unit.intro,
					OutputRenderer.fmt_duration(duration_by_token.get(unit.intro)),
				)
			track_num += 1
			table.add_row(
				str(track_num),
				unit.main_track,
				OutputRenderer.fmt_duration(duration_by_token.get(unit.main_track)),
			)

		console.print(table)
