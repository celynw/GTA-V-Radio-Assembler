"""Sequence assembly."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .types import ChainSlot, MusicUnit


class SequenceBuilder:
	"""Build final ordered sequence from units and chains."""

	@staticmethod
	def assemble(units: list[MusicUnit], chains: list[ChainSlot]) -> list[str]:
		"""Emit final ordered sequence."""
		sequence: list[str] = []
		for chain, unit in zip(chains, units, strict=True):
			sequence.extend(chain.as_list())
			if unit.intro is not None:
				sequence.append(unit.intro)
			sequence.append(unit.main_track)
		return sequence
