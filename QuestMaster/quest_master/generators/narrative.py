from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM
from ..config.llm_config import llm_config
from ..models.quest_data import SimpleQuestData, EnhancedQuestData

# Format goal text for the narrative generation
def _format_goal(quest_data: SimpleQuestData) -> str:
    goal = f"The hero must reach {quest_data.destination}"

    if quest_data.required_item:
        goal += f" with the {quest_data.required_item}"

    goal += f" and {quest_data.success_condition}"

    return goal


def _journey(quest: EnhancedQuestData, plan: str) -> str:
    """Turn the planner's actions into numbered story beats, with the players' names and place descriptions."""
    def name(obj_id: str) -> str:
        return quest.display_names.get(obj_id, obj_id.replace("_", " "))

    def place(obj_id: str) -> str:
        description = quest.descriptions.get(obj_id)
        return f"{name(obj_id)} (atmosphere: {description})" if description else name(obj_id)

    beats = []
    for line in plan.splitlines():
        if not line.startswith("("):
            continue
        action, *args = line.strip("()").split()
        if action == "move":
            beats.append(f"travels to {place(args[2])}")
        elif action == "take":
            beats.append(f"finds the {name(args[1])} in {name(args[2])}")
        elif action == "defeat_obstacle":
            beats.append(f"wields the {name(args[2])} against the {name(args[1])} guarding {name(args[4])}")
    steps = "\n".join(f"{i}. The hero {beat}." for i, beat in enumerate(beats, 1))
    return (f"The hero sets out from {place(quest.initial_location)}, then, in exactly this order:\n{steps}\n"
            "Every one of these stages must appear in the story, in this order. Use the atmosphere notes only as "
            "inspiration: never copy them word for word, and when the hero returns to a place, describe it anew.")


class NarrativeGenerator:
    def __init__(self):
        self.llm = OllamaLLM(
            model=llm_config.NARRATIVE_MODEL,
            temperature=llm_config.NARRATIVE_TEMP,
            num_predict=llm_config.NARRATIVE_MAX_TOKENS,
            num_ctx=llm_config.LONG_CONTEXT,
        )

    # Generate a narrative story that follows the plan, so the story and the game tell the same journey
    def generate(self, quest_data: SimpleQuestData, quest: EnhancedQuestData | None = None,
                 plan: str | None = None) -> str:

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an acclaimed fantasy author. You write gripping, cinematic tales full of "
                       "sensory detail, rising tension and a few sharp lines of dialogue."),
            ("user", "Write the legend of this quest as 6 to 8 paragraphs of prose separated by blank lines. "
                     "No title, no headings, no lists, no introduction of your own.\n\n"
                     "Quest: {goal}\nDanger: {obstacle}\n{journey}\n\n"
                     "Give the hero a name and a personal reason to go. Make every stage feel more dangerous "
                     "than the last, make the confrontation the climax, and close with a triumphant final paragraph."),
        ])

        formatted = prompt.invoke({
            "goal": _format_goal(quest_data),
            "obstacle": quest_data.obstacle,
            "journey": _journey(quest, plan) if quest and plan else "",
        })
        story = self.llm.invoke(formatted)

        # Drop a leading title or "Here is the legend:" line, which the game would show as the prologue
        paragraphs = [p.strip() for p in story.split("\n\n") if p.strip()]
        while len(paragraphs) > 1 and (len(paragraphs[0]) < 80 or paragraphs[0].endswith(":")):
            paragraphs.pop(0)
        return "\n\n".join(paragraphs)
