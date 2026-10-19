from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict

from langgraph.graph import END, StateGraph

from quest_master.parsers.lore_parser import LoreParser
from quest_master.parsers.quest_parser import QuestParser
from quest_master.generators.pddl_domain import PDDLDomainGenerator
from quest_master.generators.pddl_problem import PDDLProblemGenerator
from quest_master.generators.narrative import NarrativeGenerator
from quest_master.validators.pddl_validator import PDDLValidator
from quest_master.refinement.interactive_loop import InteractiveRefinementLoop
from frontend.HTMLGenerator import generate_html
from quest_master.models.quest_data import SimpleQuestData, EnhancedQuestData

@dataclass
class GraphState:
    """State shared across the LangGraph workflow."""
    lore_path: Path
    output_dir: Path = Path("output")
    quest_description: Optional[str] = None
    branching_factor: Optional[Dict[str, int]] = None
    depth_constraints: Optional[Dict[str, int]] = None
    simple_quest: Optional[SimpleQuestData] = None
    enhanced_quest: Optional[EnhancedQuestData] = None
    domain_pddl: Optional[str] = None
    problem_pddl: Optional[str] = None
    plan: Optional[str] = None
    validation_error: Optional[str] = None
    iterations: int = 0
    narrative: Optional[str] = None
    html: Optional[str] = None
    success: bool = False

# Node Implementations

def lore_parser_node(state: GraphState) -> GraphState:
    parser = LoreParser()
    info = parser.extract_informations(state.lore_path)
    state.quest_description = info["quest_description"]
    state.branching_factor = info.get("branching_factor")
    state.depth_constraints = info.get("depth_constraints")
    print("[LoreParserNode] parsed lore")
    return state

def quest_parser_node(state: GraphState) -> GraphState:
    qp = QuestParser()
    simple = qp.parse_simple(state.quest_description)
    enhanced = qp.enhance_quest_data(
        simple,
        branching_factor=state.branching_factor,
        depth_constraints=state.depth_constraints,
    )
    state.simple_quest = simple
    state.enhanced_quest = enhanced
    print("[QuestParserNode] generated quest data")
    return state

def domain_generator_node(state: GraphState) -> GraphState:
    generator = PDDLDomainGenerator()
    state.domain_pddl = generator.generate(state.enhanced_quest)
    print("[DomainGeneratorNode] domain generated")
    return state

def problem_generator_node(state: GraphState) -> GraphState:
    generator = PDDLProblemGenerator(state.enhanced_quest)
    state.problem_pddl = generator.generate()
    print("[ProblemGeneratorNode] problem generated")
    return state

def pddl_validator_node(state: GraphState) -> GraphState:
    validator = PDDLValidator(depth_constraints=state.depth_constraints)
    ok, err, state.plan = validator.validate(state.domain_pddl, state.problem_pddl)
    state.success = ok
    state.validation_error = err
    print(f"[PDDLValidatorNode] valid={ok}")
    return state

def refinement_loop_node(state: GraphState) -> GraphState:
    loop = InteractiveRefinementLoop(PDDLValidator(depth_constraints=state.depth_constraints))
    result = loop.run(state.domain_pddl, state.problem_pddl, state.quest_description)
    state.domain_pddl = result["final_domain"]
    state.problem_pddl = result["final_problem"]
    state.plan = result.get("plan")
    state.iterations += result.get("iterations", 0)
    state.success = result.get("success", False)
    if state.success:
        state.validation_error = None
    else:
        state.validation_error = result.get("reason")
    print(f"[RefinementLoopNode] success={state.success} iterations={state.iterations}")
    return state

def narrative_generator_node(state: GraphState) -> GraphState:
    generator = NarrativeGenerator()
    state.narrative = generator.generate(state.simple_quest, state.enhanced_quest, state.plan)
    print("[NarrativeGeneratorNode] narrative created")
    return state

def html_generator_node(state: GraphState) -> GraphState:
    quest_data = state.enhanced_quest.model_dump()
    forward = quest_data.get("connections", [])
    backward = [[dst, src] for src, dst in forward]

    quest_data["connections"] = forward + backward

    metadata = {
        "quest_data": quest_data,
        "branching_factor": state.branching_factor,
        "depth_constraints": state.depth_constraints,
        # Length of the optimal plan: the game challenges the player to match it
        "optimal_steps": sum(line.startswith("(") for line in (state.plan or "").splitlines()),
    }
    state.html = generate_html(metadata, state.narrative or "")
    print("[HTMLGeneratorNode] HTML generated")
    return state

def file_writer_node(state: GraphState) -> GraphState:
    out = state.output_dir
    out.mkdir(parents=True, exist_ok=True)
    if state.domain_pddl:
        (out / "domain.pddl").write_text(state.domain_pddl, encoding="utf-8")
    if state.problem_pddl:
        (out / "problem.pddl").write_text(state.problem_pddl, encoding="utf-8")
    if state.plan:
        (out / "problem_plan.txt").write_text(state.plan, encoding="utf-8")
    if state.narrative:
        (out / "narrative.txt").write_text(state.narrative, encoding="utf-8")
    if state.html:
        (out / "index.html").write_text(state.html, encoding="utf-8")

    quest_data = state.enhanced_quest.model_dump()
    forward = quest_data.get("connections", [])
    backward = [[dst, src] for src, dst in forward]

    quest_data["connections"] = forward + backward
    meta = {
        "quest_data": quest_data,
        "branching_factor": state.branching_factor,
        "depth_constraints": state.depth_constraints,
        "iterations": state.iterations,
        "status": "success" if state.success else "failure",
        "validation_error": state.validation_error,
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("[FileWriterNode] files written")
    return state

# Decision helper

def validation_decider(state: GraphState) -> str:
    return "valid" if state.success else "invalid"

# Flow builder

def build_quest_flow():
    graph = StateGraph(GraphState)
    graph.add_node("lore_parser", lore_parser_node)
    graph.add_node("quest_parser", quest_parser_node)
    graph.add_node("domain_generator", domain_generator_node)
    graph.add_node("problem_generator", problem_generator_node)
    graph.add_node("pddl_validator", pddl_validator_node)
    graph.add_node("refinement_loop", refinement_loop_node)
    graph.add_node("narrative_generator", narrative_generator_node)
    graph.add_node("html_generator", html_generator_node)
    graph.add_node("file_writer", file_writer_node)

    graph.set_entry_point("lore_parser")
    graph.add_edge("lore_parser", "quest_parser")
    graph.add_edge("quest_parser", "domain_generator")
    graph.add_edge("domain_generator", "problem_generator")
    graph.add_edge("problem_generator", "pddl_validator")
    graph.add_conditional_edges(
        "pddl_validator",
        validation_decider,
        {"valid": "narrative_generator", "invalid": "refinement_loop"},
    )
    # The refinement loop validates its own result, so success goes straight on; failure still writes the files
    graph.add_conditional_edges(
        "refinement_loop",
        lambda s: "ok" if s.success else "fail",
        {"ok": "narrative_generator", "fail": "file_writer"},
    )
    graph.add_edge("narrative_generator", "html_generator")
    graph.add_edge("html_generator", "file_writer")
    graph.add_edge("file_writer", END)

    return graph.compile()


def run_flow(lore_path: str, output_dir: str = "output") -> GraphState:
    flow = build_quest_flow()
    initial = GraphState(lore_path=Path(lore_path), output_dir=Path(output_dir))

    result_dict = flow.invoke(initial)

    final_state = GraphState(**result_dict)
    return final_state
