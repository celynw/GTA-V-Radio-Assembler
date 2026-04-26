"""Speech chain scheduling."""

from .types import ChainSlot
from .utilities import fail, spread_indices


class Scheduler:
	"""Allocate speech chains across music units."""

	@staticmethod
	def allocate(  # noqa: C901,PLR0912,PLR0915
		unit_count: int,
		speech_pools: dict[str, list[str]],
		duration_by_token: dict[str, float] | None = None,
	) -> list[ChainSlot]:
		"""Allocate speech chains across music units."""
		chains = [ChainSlot() for _ in range(unit_count)]
		if duration_by_token is None:
			duration_by_token = {}

		def _token_duration(token: str) -> float:
			# Unknown durations are treated as long so they are less likely
			# to be placed in consecutive overflow slots.
			return duration_by_token.get(token, 10_000.0)

		def _allocate_single_slot_category(
			category: str,
			field_name: str,
			indices: list[int],
		) -> None:
			tracks = speech_pools[category]
			if not tracks:
				return

			chosen_indices = spread_indices(len(tracks), indices)
			for track, index in zip(tracks, chosen_indices, strict=True):
				chain = chains[index]
				target = getattr(chain, field_name)
				if isinstance(target, list):
					target.append(track)
				else:
					setattr(chain, field_name, track)
			speech_pools[category] = []

		def _allocate_multi_slot_category(category: str, field_name: str) -> None:
			tracks = speech_pools[category]
			if not tracks:
				return

			for offset, track in enumerate(tracks):
				index = offset % unit_count
				chain = chains[index]
				bucket: list[str] = getattr(chain, field_name)
				bucket.append(track)
			speech_pools[category] = []

		# Opening chain prioritization.
		if speech_pools["ID"]:
			chains[0].id_track = speech_pools["ID"].pop(0)

		if speech_pools["MORNING"]:
			chains[0].daypart_track = speech_pools["MORNING"].pop(0)
			chains[0].daypart_kind = "MORNING"
		elif speech_pools["EVENING"]:
			chains[0].daypart_track = speech_pools["EVENING"].pop(0)
			chains[0].daypart_kind = "EVENING"

		available_indices = list(range(1, unit_count)) if unit_count > 1 else []

		id_tracks = speech_pools["ID"]
		if id_tracks:
			if len(id_tracks) > len(available_indices):
				remaining_ids = len(id_tracks)
				available_chains = len(available_indices)
				message = (
					"Could not place all ID tracks with one-per-chain spacing. "
					f"Remaining IDs: {remaining_ids}, "
					f"available chains: {available_chains}."
				)
				fail(message)

			_allocate_single_slot_category("ID", "id_track", available_indices)

		# Allocate MORNING with front bias.
		morning_tracks = speech_pools["MORNING"]
		if morning_tracks:
			if not available_indices and morning_tracks:
				message = "No remaining chain slots for MORNING tracks."
				fail(message)

			front_window = max(1, unit_count // 2)
			morning_candidates = [
				index for index in available_indices if index < front_window
			]
			if len(morning_candidates) < len(morning_tracks):
				morning_candidates = available_indices.copy()

			chosen = spread_indices(len(morning_tracks), morning_candidates)
			for track, index in zip(morning_tracks, chosen, strict=True):
				chains[index].daypart_track = track
				chains[index].daypart_kind = "MORNING"
			speech_pools["MORNING"] = []

		# Allocate EVENING with back bias, never overlapping MORNING chains.
		evening_tracks = speech_pools["EVENING"]
		if evening_tracks:
			if not available_indices and evening_tracks:
				message = "No remaining chain slots for EVENING tracks."
				fail(message)

			back_window_start = unit_count // 2
			evening_candidates = [
				index
				for index in available_indices
				if index >= back_window_start and chains[index].daypart_track is None
			]
			if len(evening_candidates) < len(evening_tracks):
				evening_candidates = [
					index
					for index in available_indices
					if chains[index].daypart_track is None
				]

			chosen = spread_indices(len(evening_tracks), evening_candidates)
			for track, index in zip(evening_tracks, chosen, strict=True):
				chains[index].daypart_track = track
				chains[index].daypart_kind = "EVENING"
			speech_pools["EVENING"] = []

		# Minimax makespan optimisation for GENERAL and MONO_SOLO.
		# All tokens are sorted longest-first (LPT heuristic) and assigned one at a
		# time to the chain with the lowest current speech duration, minimising the
		# worst-case segment length globally. MONO_SOLO is constrained to at most one
		# per chain.
		variable_tokens: list[tuple[str, str]] = [
			(t, "GENERAL") for t in speech_pools["GENERAL"]
		]
		variable_tokens += [(t, "MONO_SOLO") for t in speech_pools["MONO_SOLO"]]
		speech_pools["GENERAL"] = []
		speech_pools["MONO_SOLO"] = []

		variable_tokens.sort(
			key=lambda pair: (_token_duration(pair[0]), pair[0]),
			reverse=True,
		)

		chain_totals: list[float] = [
			sum(
				_token_duration(t)
				for t in (
					chain.id_track,
					chain.daypart_track,
					*chain.general_tracks,
					*chain.mono_tracks,
				)
				if t is not None
			)
			for chain in chains
		]

		for token, category in variable_tokens:
			token_dur = _token_duration(token)
			if category == "GENERAL":
				target = min(range(unit_count), key=lambda i: chain_totals[i])
				chains[target].general_tracks.append(token)
				chain_totals[target] += token_dur
			else:
				# MONO_SOLO placement:
				# - Chains WITH an ID track can have multiple MONOs (separated by ID).
				# - Chains WITHOUT an ID track can have at most one MONO.
				# - This allows much higher flexibility in mono placement.
				chains_with_id = [
					i for i in range(unit_count) if chains[i].id_track is not None
				]
				chains_no_id_no_mono = [
					i
					for i in range(unit_count)
					if chains[i].id_track is None and not chains[i].mono_tracks
				]
				# Prioritize chains with ID (can hold multiples), then
				# chains without ID that have no mono yet (fallback).
				mono_candidates = chains_with_id + chains_no_id_no_mono

				if mono_candidates:
					target = min(mono_candidates, key=lambda i: chain_totals[i])
					chains[target].mono_tracks.append(token)
					chain_totals[target] += token_dur

		# Fail if anything was left unallocated.
		leftovers: dict[str, list[str]] = {
			category: items for category, items in speech_pools.items() if items
		}
		if leftovers:
			details = ", ".join(
				f"{cat}: {len(items)}" for cat, items in sorted(leftovers.items())
			)
			message = (
				"Could not place all speech tracks. "
				f"Unplaced counts -> {details}. "
				"Increase music units or relax slot constraints."
			)
			fail(message)

		return chains
