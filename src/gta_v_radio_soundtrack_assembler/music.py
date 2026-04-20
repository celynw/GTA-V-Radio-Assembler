"""Music unit building."""

from .types import MusicGroup, MusicUnit
from .utilities import fail, sort_tokens


class MusicUnitBuilder:
	"""Build music units from music groups."""

	@staticmethod
	def build(
		music_groups: dict[str, MusicGroup],
	) -> tuple[list[MusicUnit], list[str], list[str]]:
		"""Build one music unit per valid music group."""
		units: list[MusicUnit] = []
		warnings: list[str] = []
		omitted_intros: list[str] = []

		for base in sorted(music_groups):
			group = music_groups[base]
			intros = sort_tokens(group.intros)
			mains = sort_tokens(group.main_tracks)

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
				fail(message)

			selected_intro = intros[0] if intros else None
			omitted_intros.extend(intro for intro in intros[1:])
			units.append(
				MusicUnit(base=base, main_track=mains[0], intro=selected_intro)
			)

		if not units:
			message = "No valid music units were built from the input."
			fail(message)

		return units, warnings, omitted_intros
