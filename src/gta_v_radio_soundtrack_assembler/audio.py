"""Audio processing operations."""

import json
import re
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import (
	BarColumn,
	MofNCompleteColumn,
	Progress,
	SpinnerColumn,
	TextColumn,
	TimeElapsedColumn,
)

from .types import AudioFormat
from .utilities import fail

console = Console()
_SHORT_AUDIO_SECONDS = 0.5


class AudioProcessor:
	"""Handle all audio file operations."""

	_INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]")

	@staticmethod
	def run_subprocess(command: list[str], *, description: str) -> None:
		"""Run a subprocess command and raise a user-facing error on failure."""
		completed = subprocess.run(  # noqa: S603
			command,
			capture_output=True,
			text=True,
			check=False,
		)
		if completed.returncode == 0:
			return

		stderr = completed.stderr.strip()
		stdout = completed.stdout.strip()
		detail = stderr or stdout
		message = f"{description} failed: {detail or 'unknown error'}"
		fail(message)

	@staticmethod
	def run_subprocess_output(command: list[str], *, description: str) -> str:
		"""Run a subprocess command and return stdout."""
		completed = subprocess.run(  # noqa: S603
			command,
			capture_output=True,
			text=True,
			check=False,
		)
		if completed.returncode == 0:
			return completed.stdout

		stderr = completed.stderr.strip()
		stdout = completed.stdout.strip()
		detail = stderr or stdout
		message = f"{description} failed: {detail or 'unknown error'}"
		fail(message)
		return ""

	@staticmethod
	def probe_audio_format(audio_file: Path) -> AudioFormat:
		"""Probe audio format settings from a file."""
		output = AudioProcessor.run_subprocess_output(
			[
				"ffprobe",
				"-v",
				"error",
				"-select_streams",
				"a:0",
				"-show_entries",
				"stream=codec_name,sample_rate,channels",
				"-of",
				"json",
				str(audio_file),
			],
			description=f"Probing audio format for {audio_file.name}",
		)

		try:
			payload = json.loads(output)
			streams = payload.get("streams", [])
			if not streams:
				message = f"No audio stream found in {audio_file}"
				fail(message)
			stream = streams[0]
			codec_name = str(stream["codec_name"])
			sample_rate = int(stream["sample_rate"])
			channels = int(stream["channels"])
		except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
			message = f"Failed to parse ffprobe data for {audio_file}: {exc}"
			fail(message)

		return AudioFormat(
			codec_name=codec_name,
			sample_rate=sample_rate,
			channels=channels,
		)

	@staticmethod
	def probe_audio_duration_seconds(audio_file: Path) -> float:
		"""Return duration in seconds for one audio file."""
		output = AudioProcessor.run_subprocess_output(
			[
				"ffprobe",
				"-v",
				"error",
				"-show_entries",
				"format=duration",
				"-of",
				"default=noprint_wrappers=1:nokey=1",
				str(audio_file),
			],
			description=f"Probing duration for {audio_file.name}",
		)

		try:
			return float(output.strip())
		except ValueError as exc:
			message = f"Failed to parse duration for {audio_file}: {exc}"
			fail(message)
		return 0.0

	@staticmethod
	def trim_true_silence(
		input_file: Path,
		output_file: Path,
		audio_format: AudioFormat,
	) -> None:
		"""Trim digitally-zero leading/trailing silence from a speech clip."""
		filter_expr = (
			"silenceremove=window=0:detection=peak"
			":stop_mode=all:stop_periods=-1:stop_threshold=0"
		)
		AudioProcessor.run_subprocess(
			[
				"ffmpeg",
				"-y",
				"-i",
				str(input_file),
				"-af",
				filter_expr,
				"-c:a",
				audio_format.codec_name,
				"-ar",
				str(audio_format.sample_rate),
				"-ac",
				str(audio_format.channels),
				str(output_file),
			],
			description=f"Silence trimming for {input_file.name}",
		)

	@staticmethod
	def concat_audio_files(input_files: list[Path], output_file: Path) -> None:
		"""Concatenate already-format-aligned files without re-encoding."""
		if not input_files:
			message = "Cannot concatenate zero files."
			fail(message)

		with tempfile.TemporaryDirectory(prefix="gta_radio_concat_") as tmp_dir:
			concat_file = Path(tmp_dir) / "concat.txt"
			concat_lines = [f"file '{path.as_posix()}'" for path in input_files]
			concat_file.write_text("\n".join(concat_lines) + "\n")

			AudioProcessor.run_subprocess(
				[
					"ffmpeg",
					"-y",
					"-f",
					"concat",
					"-safe",
					"0",
					"-i",
					str(concat_file),
					"-c",
					"copy",
					str(output_file),
				],
				description=f"Concatenation into {output_file.name}",
			)

	@staticmethod
	def transcode_to_flac(
		input_file: Path,
		output_file: Path,
		*,
		sample_rate: int,
		compression_level: int,
	) -> None:
		"""Transcode one source file into FLAC with explicit output settings."""
		output_file.parent.mkdir(parents=True, exist_ok=True)
		AudioProcessor.run_subprocess(
			[
				"ffmpeg",
				"-y",
				"-i",
				str(input_file),
				"-ar",
				str(sample_rate),
				"-c:a",
				"flac",
				"-compression_level",
				str(compression_level),
				str(output_file),
			],
			description=f"FLAC transcode for {input_file.name}",
		)

	@staticmethod
	def sanitize_filename(raw_name: str) -> str:
		"""Return a filesystem-safe display name for generated album tracks."""
		sanitized = AudioProcessor._INVALID_FILENAME_CHARS.sub("_", raw_name)
		sanitized = " ".join(sanitized.split()).strip()
		return sanitized or "untitled"

	@staticmethod
	def render_final_album_flacs(
		tracks: list[tuple[str, Path]],
		album_dir: Path,
		*,
		sample_rate: int,
		compression_level: int,
	) -> int:
		"""Render one numbered FLAC file per timeline row into album_dir."""
		album_dir.mkdir(parents=True, exist_ok=True)
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
				"Converting final album to FLAC",
				total=len(tracks),
				current_track="",
			)
			for index, (display_name, source_file) in enumerate(tracks, start=1):
				safe_name = AudioProcessor.sanitize_filename(display_name)
				output_file = album_dir / f"{index:02d} {safe_name}.flac"
				progress.update(task_id, current_track=safe_name)
				AudioProcessor.transcode_to_flac(
					source_file,
					output_file,
					sample_rate=sample_rate,
					compression_level=compression_level,
				)
				progress.advance(task_id)

		return len(tracks)

	@staticmethod
	def index_station_audio_files(station_audio_dir: Path) -> dict[str, Path]:
		"""Index station audio files by stem name."""
		file_map: dict[str, Path] = {}
		for file_path in station_audio_dir.rglob("*"):
			if not file_path.is_file():
				continue

			stem = file_path.stem
			if stem in file_map:
				message = (
					"Duplicate audio stem detected: "
					f"{stem} -> {file_map[stem]} and {file_path}"
				)
				fail(message)
			file_map[stem] = file_path

		if not file_map:
			message = f"No audio files found in {station_audio_dir}"
			fail(message)

		return file_map

	@staticmethod
	def build_duration_index(
		audio_dir: Path,
	) -> tuple[dict[str, float], list[str]]:
		"""Best-effort token duration index used for scheduling optimization."""
		if not audio_dir.exists() or not audio_dir.is_dir():
			return {}, []

		audio_index = AudioProcessor.index_station_audio_files(audio_dir)
		duration_index: dict[str, float] = {}
		warnings: list[str] = []
		for token, audio_file in audio_index.items():
			try:
				duration = AudioProcessor.probe_audio_duration_seconds(audio_file)
				duration_index[token] = duration
				if duration < _SHORT_AUDIO_SECONDS:
					warnings.append(
						f"[white]{audio_file.name}[/white] is very short "
						f"({duration:.2f}s); it may be corrupted or empty."
					)
			except Exception:  # noqa: BLE001
				warnings.append(
					f"Duration probe failed for [white]{audio_file.name}[/white]; "
					"using fallback scheduling weight.",
				)

		return duration_index, warnings

	@staticmethod
	def resolve_audio_file(token: str, audio_index: dict[str, Path]) -> Path:
		"""Resolve one token to a real station audio file path."""
		resolved = audio_index.get(token)
		if resolved is not None:
			return resolved

		message = (
			f"Audio file for token {token} was not found in station audio directory."
		)
		fail(message)
		return Path()

	@staticmethod
	def render_speech_block(
		speech_tokens: list[str],
		audio_index: dict[str, Path],
		output_file: Path,
	) -> Path:
		"""Trim and concatenate speech block clips."""
		if not speech_tokens:
			message = "Speech block render requested without tokens."
			fail(message)

		input_files = [
			AudioProcessor.resolve_audio_file(token, audio_index)
			for token in speech_tokens
		]
		format_ref = AudioProcessor.probe_audio_format(input_files[0])

		with tempfile.TemporaryDirectory(prefix="gta_radio_trim_") as tmp_dir:
			tmp_dir_path = Path(tmp_dir)
			trimmed_files: list[tuple[Path, str]] = []
			for idx, (token, input_file) in enumerate(
				zip(speech_tokens, input_files, strict=True),
				start=1,
			):
				trimmed_path = tmp_dir_path / f"trim_{idx:03d}{output_file.suffix}"
				AudioProcessor.trim_true_silence(
					input_file,
					trimmed_path,
					format_ref,
				)
				trimmed_duration = AudioProcessor.probe_audio_duration_seconds(
					trimmed_path
				)
				if trimmed_duration < 0.1:  # noqa: PLR2004
					message = (
						f"Token '{token}' trimmed to near-silence "
						f"(duration: {trimmed_duration:.2f}s). "
						"The audio file may be empty or contain only digital silence."
					)
					fail(message)
				trimmed_files.append((trimmed_path, token))

			if not trimmed_files:
				message = "All speech tokens were trimmed to silence."
				fail(message)

			AudioProcessor.concat_audio_files(
				[path for path, _ in trimmed_files], output_file
			)

		return output_file
