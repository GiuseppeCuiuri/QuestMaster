from typing import List, Dict, Tuple
import itertools
import json
import random
import re
import unicodedata
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama import ChatOllama
from ..models.quest_data import SimpleQuestData, EnhancedQuestData
from ..config.llm_config import llm_config

_ADJECTIVES = ["Ashen", "Whispering", "Forgotten", "Moonlit", "Sunken", "Thorned", "Silent", "Ember", "Frostbound", "Gloaming"]
_NOUNS = ["Glade", "Barrow", "Ford", "Spire", "Crossroads", "Grotto", "Watchtower", "Marsh", "Shrine", "Pass"]


def _normalize(text) -> str:
    """Turn any text into a valid PDDL identifier: lowercase ASCII letters, digits and underscores, starting with a letter."""
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return name if name[:1].isalpha() else f"loc_{name}".rstrip("_")


def _fallback_places():
    """Endless supply of (name, description) pairs for when the LLM returns too few places."""
    names = [f"{adjective} {noun}" for adjective in _ADJECTIVES for noun in _NOUNS]
    for round_ in itertools.count(1):
        for name in random.sample(names, len(names)):
            yield (name if round_ == 1 else f"{name} {round_}"), ""


class QuestParser:
    def __init__(self):
        self.llm = ChatOllama(
            model=llm_config.PARSER_MODEL,
            temperature=llm_config.PARSER_TEMP,
            num_predict=llm_config.PARSER_MAX_TOKENS,
        )
        self.world_llm = ChatOllama(
            model=llm_config.WORLD_MODEL,
            temperature=llm_config.WORLD_TEMP,
            num_predict=llm_config.WORLD_MAX_TOKENS,
            num_ctx=llm_config.LONG_CONTEXT,
        )
        self.simple_parser = self.llm.with_structured_output(schema=SimpleQuestData)

    def parse_simple(self, description: str) -> SimpleQuestData:
        """Parse a simple quest description using few-shot prompts."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Extract quest components from the description."),
            MessagesPlaceholder("examples"),
            ("human", "{input}"),
        ])
        formatted = prompt.invoke({"input": description, "examples": self._get_few_shot_examples()})
        return self.simple_parser.invoke(formatted)

    def _get_few_shot_examples(self) -> List:
        """Provide examples for the LLM simple parser."""
        return [
            HumanMessage(
                content=(
                    "The hero must reach the Dark Tower with the Crystal Sword and defeat the Dragon."
                    " The bridge is guarded by trolls."
                )
            ),
            AIMessage(
                content=(
                    "SimpleQuestData(\n"
                    "  destination='Dark Tower',\n"
                    "  required_item='Crystal Sword',\n"
                    "  success_condition='defeat the Dragon',\n"
                    "  obstacle='The bridge is guarded by trolls',\n"
                    "  obstacle_key='trolls'\n)"
                )
            ),
        ]

    def _select_depth(self, constraints: Dict[str, int] | None) -> int:
        """Randomly select a depth value within the given constraints."""
        if constraints:
            min_d = max(1, constraints.get("min", 1))
            max_d = max(min_d, constraints.get("max", min_d))
        else:
            min_d = max_d = 1
        return random.randint(min_d, max_d)

    def _select_branching(self, factor: Dict[str, int] | None) -> Tuple[int, int]:
        """Determine the min and max branching factor."""
        if factor:
            min_b = max(1, factor.get("min", 1))
            max_b = max(min_b, factor.get("max", min_b))
        else:
            min_b = max_b = 1
        return min_b, max_b

    def enhance_quest_data(
            self,
            simple_data: SimpleQuestData,
            branching_factor: Dict[str, int] | None = None,
            depth_constraints: Dict[str, int] | None = None,
    ) -> EnhancedQuestData:
        """Enhance parsed quest data: select dynamic depth and branching, build and name the map, preserve solvability."""
        # Normalize destination, obstacle and item into PDDL ids, keeping the original names for players
        dest_norm = _normalize(simple_data.destination)
        display_names = {dest_norm: simple_data.destination}
        descriptions = {}
        obs_key = _normalize(simple_data.obstacle_key) if simple_data.obstacle_key else None
        if obs_key:
            display_names[obs_key] = simple_data.obstacle_key
            descriptions[obs_key] = simple_data.obstacle

        # Every obstacle needs an item that defeats it: synthesize one if the lore names none
        item_name = simple_data.required_item or (f"Bane of the {simple_data.obstacle_key}" if obs_key else None)
        item_norm = _normalize(item_name) if item_name else None
        if item_norm:
            display_names[item_norm] = item_name

        # Select branching
        min_b, max_b = self._select_branching(branching_factor)

        # Plan length = main path moves + take (plus a 2-move detour when the item sits on a side branch) + defeat
        detour = 2 if item_norm and max_b > 1 else 0
        overhead = (1 + detour if item_norm else 0) + (1 if obs_key else 0)

        # Select depth (target length of the optimal plan) within the constraints, but never below the
        # shortest plan this quest allows; if that exceeds the max, the validator's depth check rejects it
        constraints = depth_constraints or {}
        min_depth = max(1 + overhead, constraints.get("min", 1))
        depth = self._select_depth({"min": min_depth, "max": constraints.get("max", min_depth)})
        main_edges = depth - overhead

        # Shape the map: side branches leaving each main-path place (at least one, to hide the item)
        branch_counts = [random.randint(min_b, max_b) - 1 for _ in range(main_edges)]
        if detour:
            branch_counts[0] = max(branch_counts[0], 1)

        # Name every place but the destination in one LLM call: start, the main path, then the side branches.
        # PDDL object names must be unique across all types, so skip ids already taken by other objects.
        needed = main_edges + sum(branch_counts)
        theme = f"{simple_data.destination}: {simple_data.success_condition}. {simple_data.obstacle}"
        places: Dict[str, Tuple[str, str]] = {}
        for name, description in itertools.chain(self._generate_places(needed, theme), _fallback_places()):
            place_id = _normalize(name)
            if name.strip() and place_id not in places and place_id not in display_names:
                places[place_id] = (" ".join(name.split()), " ".join(description.split()))
            if len(places) == needed:
                break
        display_names.update({place_id: name for place_id, (name, _) in places.items()})
        descriptions.update({place_id: text for place_id, (_, text) in places.items() if text})

        # Build connections: the main path to the destination, plus the side branches of each main-path place
        ids = list(places)
        locations = ids[:main_edges] + [dest_norm]
        side_ids = iter(ids[main_edges:])
        branches: List[str] = []
        connections: List[Tuple[str, str]] = []
        for loc, next_loc, n_branches in zip(locations, locations[1:], branch_counts):
            connections.append((loc, next_loc))
            for _ in range(n_branches):
                branches.append(next(side_ids))
                connections.append((loc, branches[-1]))
        locations += branches

        # The item hides on a random side branch (or at the start if no branches are allowed)
        items = [item_norm] if item_norm else []
        item_locations = {item_norm: random.choice(branches) if detour else locations[0]} if item_norm else {}
        obstacles = {dest_norm: obs_key} if obs_key else {}
        defeats = {item_norm: obs_key} if obs_key else {}

        # Compose goal conditions
        goal_conditions = [f"at hero {dest_norm}"]
        if item_norm:
            goal_conditions.append(f"has hero {item_norm}")
        if obs_key:
            goal_conditions.append(f"defeated {obs_key}")

        return EnhancedQuestData(
            locations=locations,
            items=items,
            item_locations=item_locations,
            obstacles=obstacles,
            defeats=defeats,
            display_names=display_names,
            descriptions=descriptions,
            connections=connections,
            initial_location=locations[0],
            goal_conditions=goal_conditions,
            branching_factor=branching_factor,
            depth_constraints={"min": 1 if not depth_constraints else depth_constraints.get("min"),
                               "max": depth},
        )

    def _generate_places(self, count: int, theme: str) -> list[tuple[str, str]]:
        """Ask the LLM for evocative places as (name, description) pairs; [] if its answer is unusable."""
        prompt = f"""You are the world-builder of a fantasy quest: "{theme}"
Invent {count} distinct places the hero may wander through on the way there.
For each place give an evocative name (2-4 words) and one atmospheric sentence about what the hero sees, hears or feels there.
Answer only with a JSON list, like:
[{{"name": "Mistveil Hollow", "description": "Pale fog coils between leaning stones that seem to whisper your name."}}]"""
        response = self.world_llm.invoke(prompt)
        match = re.search(r"\[.*\]", response.content, re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else []
        except json.JSONDecodeError:
            return []  # malformed LLM output: the caller falls back to built-in names
        return [(str(p.get("name", "")), str(p.get("description", ""))) if isinstance(p, dict) else (str(p), "")
                for p in data]
