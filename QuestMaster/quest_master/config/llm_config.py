from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Centralized configuration for LLM models used in the application."""
    # Lore parser config
    LORE_PARSER_MODEL: str = "llama3:8b"
    LORE_PARSER_TEMP: float = 0.1
    LORE_PARSER_MAX_TOKENS: int = 512

    # Quest parser config
    PARSER_MODEL: str = "llama3:8b"
    PARSER_TEMP: float = 0.2
    PARSER_MAX_TOKENS: int = 256

    # Narrative config
    NARRATIVE_MODEL: str = "llama3:8b"
    NARRATIVE_TEMP: float = 0.8
    NARRATIVE_MAX_TOKENS: int = 1536

    # Reflection agent config
    REFLECTION_MODEL: str = "llama3:8b"
    REFLECTION_TEMP: float = 0.3
    REFLECTION_MAX_TOKENS: int = 256

    # World builder config (names and descriptions of the places on the quest map)
    WORLD_MODEL: str = "llama3:8b"
    WORLD_TEMP: float = 0.9
    WORLD_MAX_TOKENS: int = 2048

    # Context window for the long generations (Ollama's default is too small for them)
    LONG_CONTEXT: int = 4096


# Singleton instance
llm_config = LLMConfig()