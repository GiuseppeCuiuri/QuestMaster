from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field, model_validator


class Range(BaseModel):
    """Min/max bounds read from the lore; numeric strings such as "2" are coerced to int"""
    min: int
    max: int

    @model_validator(mode="after")
    def _ordered(self):
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) is greater than max ({self.max})")
        return self


class LoreInfo(BaseModel):
    """Validated output of the lore parser"""
    quest_description: str = Field(..., min_length=1, description="Descrizione della quest")
    branching_factor: Optional[Range] = Field(None, description="Limiti sul branching factor")
    depth_constraints: Optional[Range] = Field(None, description="Limiti sulla profondità")


class SimpleQuestData(BaseModel):
    """Base Model for initial PDDL quest data"""
    destination: str = Field(..., description="Luogo da raggiungere")
    required_item: Optional[str] = Field(None, description="Oggetto richiesto")
    success_condition: str = Field(..., description="Condizione di successo")
    obstacle: str = Field(..., description="Ostacolo principale")
    obstacle_key: str = Field(..., description="Chiave dell'ostacolo")


class EnhancedQuestData(BaseModel):
    """Advanced Model for complete PDDL quest data"""
    locations: List[str] = Field(default_factory=list, description="Tutti i luoghi")
    items: List[str] = Field(default_factory=list, description="Tutti gli oggetti")
    obstacles: Dict[str, str] = Field(default_factory=dict, description="Mapping location->obstacle")
    item_locations: Dict[str, str] = Field(default_factory=dict, description="Mapping item->location")
    defeats: Dict[str, str] = Field(default_factory=dict, description="Mapping item->obstacle it defeats")
    display_names: Dict[str, str] = Field(default_factory=dict, description="Mapping PDDL id->name shown to players")
    descriptions: Dict[str, str] = Field(default_factory=dict, description="Mapping location/obstacle id->flavor text")
    connections: List[Tuple[str, str]] = Field(default_factory=list, description="Collegamenti tra luoghi")
    initial_location: str = Field(default="start", description="Posizione iniziale")
    goal_conditions: List[str] = Field(default_factory=list, description="Condizioni di goal")
    branching_factor: Optional[Dict[str, int]] = Field(default=None, description="Limiti sul branching factor")
    depth_constraints: Optional[Dict[str, int]] = Field(default=None, description="Limiti sulla profondità")