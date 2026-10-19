"""Self-check: generated quests are solvable and their optimal plan length respects the depth constraints.

Run from this directory: python test_pddl.py
"""
import random
import re
from collections import deque
from unittest import mock

from quest_master.generators.pddl_domain import DOMAIN
from quest_master.generators.pddl_problem import PDDLProblemGenerator
from pydantic import ValidationError

from quest_master.models.quest_data import LoreInfo, SimpleQuestData
from quest_master.parsers.quest_parser import QuestParser
from quest_master.validators.pddl_validator import PDDLValidator


def optimal_plan_length(problem: str) -> int | None:
    """Breadth-first search applying the quest domain rules to the facts of a generated problem."""
    init_text, goal_text = problem.split("(:goal")
    facts = [f.split() for f in re.findall(r"\(([a-z_]+ [^()]*)\)", init_text)]
    by = lambda pred: [args for name, *args in facts if name == pred]
    edges: dict[str, list[str]] = {}
    for a, b in by("connected"):
        edges.setdefault(a, []).append(b)
    clear = {loc for (loc,) in by("clear")}
    item_at = {loc: item for item, loc in by("item_at")}
    guard = {loc: obstacle for loc, obstacle in by("guarded_by")}
    defeats = {tuple(pair) for pair in by("defeats")}
    goals = [g.split() for g in re.findall(r"\(([a-z_]+ [^()]*)\)", goal_text)]

    def done(loc, held, beaten):
        return all(loc == g[2] if g[0] == "at" else g[2] in held if g[0] == "has" else g[1] in beaten
                   for g in goals)

    start = (by("at")[0][1], frozenset(), frozenset())
    frontier, seen = deque([(start, 0)]), {start}
    while frontier:
        (loc, held, beaten), cost = frontier.popleft()
        if done(loc, held, beaten):
            return cost
        successors = []
        for to in edges.get(loc, []):
            if to in clear or guard.get(to) in beaten:
                successors.append((to, held, beaten))
            elif any((item, guard[to]) in defeats for item in held):
                successors.append((loc, held, beaten | {guard[to]}))
        if loc in item_at:
            successors.append((loc, held | {item_at[loc]}, beaten))
        for state in successors:
            if state not in seen:
                seen.add(state)
                frontier.append((state, cost + 1))
    return None


def check(required_item, obstacle_key, depth, branching):
    simple = SimpleQuestData(destination="Crystal Caverns", required_item=required_item,
                             success_condition="shatter the Dark Crystal", obstacle="sealed gate",
                             obstacle_key=obstacle_key)
    parser = QuestParser.__new__(QuestParser)  # skip the LLM client setup
    # The fake LLM returns PDDL-breaking, duplicate and clashing names, and sometimes too few or too many:
    # the generator must still produce valid unique identifiers, name every place and honour the depth.
    hostile = [("Elyria's Hollow", "Mist\nand stone"), ("Château; (Doom)", ""), ("3 Towers", ""),
               ("Elyria's Hollow", "duplicate"), ("Golem", "clash"), ("", "nameless"), ("Crystal Caverns", "clash")]
    with mock.patch.object(QuestParser, "_generate_places",
                           lambda self, n, theme: hostile + [(f"Place {i}", "") for i in range(n // 2)]):
        quest = parser.enhance_quest_data(simple, branching, depth)
    problem = PDDLProblemGenerator(quest).generate()

    objects = re.findall(r"^\s+(\S+) - \w+", problem.split("(:init")[0], re.M)
    assert len(objects) == len(set(objects)), f"object names must be unique: {objects}"
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", o) for o in objects), objects
    assert all(loc in quest.display_names for loc in quest.locations), "every place needs a name for players"
    assert quest.descriptions.get("elyria_s_hollow") == "Mist and stone"
    assert problem.count("(") == problem.count(")")
    assert not any(f"(at {item} " in problem for item in quest.items), "items must use item_at"
    length = optimal_plan_length(problem)
    assert length is not None, "quest must be solvable"
    assert depth["min"] <= length <= depth["max"], (length, depth, branching)
    assert length == quest.depth_constraints["max"], "optimal plan must match the selected depth"


if __name__ == "__main__":
    assert DOMAIN.count("(") == DOMAIN.count(")")
    for seed in range(50):
        random.seed(seed)
        check(None, "golem", {"min": 3, "max": 8}, {"min": 2, "max": 4})              # synthesized item
        check("Flame of Eternity", "golem", {"min": 6, "max": 6}, {"min": 1, "max": 3})
        check("Flame of Eternity", "", {"min": 4, "max": 7}, {"min": 1, "max": 1})  # no side branches
        check(None, "", {"min": 1, "max": 5}, None)

    parser = QuestParser.__new__(QuestParser)
    parser.world_llm = mock.Mock(invoke=lambda prompt: mock.Mock(content='Sure! ["Elyria\'s Hollow", oops]'))
    assert parser._generate_places(2, "theme") == [], "malformed JSON must not crash"
    parser.world_llm = mock.Mock(invoke=lambda prompt: mock.Mock(
        content='Here: [{"name": "Ash Ford", "description": "Grey water."}, "Old Mill"]'))
    assert parser._generate_places(2, "theme") == [("Ash Ford", "Grey water."), ("Old Mill", "")]

    validator = PDDLValidator.__new__(PDDLValidator)  # skip the WSL setup
    validator.depth_constraints = {"min": 3, "max": 4}
    assert validator._check_depth("Plan length: 4 step(s).") is None
    assert "outside depth constraints" in validator._check_depth("Plan length: 5 step(s).")

    lore = LoreInfo.model_validate_json('{"quest_description": "q", "branching_factor": {"min": "2", "max": 4}}')
    assert lore.branching_factor.min == 2 and lore.depth_constraints is None
    for bad in ('{"branching_factor": {"min": 1, "max": 2}}',
                '{"quest_description": "q", "depth_constraints": {"min": 8, "max": 3}}'):
        try:
            LoreInfo.model_validate_json(bad)
            raise AssertionError(f"invalid lore output accepted: {bad}")
        except ValidationError:
            pass
    print("ok")
