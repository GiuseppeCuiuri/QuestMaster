import re
from pathlib import Path
import ollama
from ..config.llm_config import llm_config
from ..models.quest_data import LoreInfo


class LoreParser:
    def __init__(self):
        self.model = llm_config.LORE_PARSER_MODEL
        self.temperature = llm_config.LORE_PARSER_TEMP
        self.max_tokens = llm_config.LORE_PARSER_MAX_TOKENS

    def extract_informations(self, file_path: Path) -> dict:
        """Extract quest information from a lore document."""
        content = file_path.read_text(encoding="utf-8")
        prompt = f"""
        From this lore document, extract the following fields:
        - The quest description (a paragraph summarizing the goal, initial state, obstacles, and story context).
        - The branching factor (minimum and maximum number of actions available at each narrative state).
        - The depth constraints (minimum and maximum number of steps required to reach the goal).

        Document:
        {content}

        Return a JSON string object with the following structure:
        {{
          "quest_description": "<a textual description of the quest>",
          "branching_factor": {{"min": <min>, "max": <max>}},
          "depth_constraints": {{"min": <min>, "max": <max>}}
        }}
        """
        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            options={"temperature": self.temperature, "num_predict": self.max_tokens},
        )
        result = response["response"].strip()
        match = re.search(r"\{.*\}", result, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in LLM response")
        # Raises pydantic.ValidationError (a ValueError) naming the bad field on malformed or incomplete output
        return LoreInfo.model_validate_json(match.group(0)).model_dump()