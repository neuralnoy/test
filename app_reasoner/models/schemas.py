from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class InputReasoner(BaseModel):
    id: str
    taskId: Optional[str] = None
    language: Optional[str] = None
    text: str

class Speaker(BaseModel):
    speaker_1: Optional[Literal["Agent", "Client"]] = Field(
        None, 
        description="Identifies whether Speaker 1 is an Agent or Client. Leave None if uncertain."
    )
    speaker_2: Optional[Literal["Agent", "Client"]] = Field(
        None, 
        description="Identifies whether Speaker 2 is an Agent or Client. Leave None if uncertain."
    )

class ResolutionFlag(BaseModel):
    resolution_type: Literal["CLIENT MANAGER", "BRANCH", "SELF SERVICE", "RESOLVED", "OTHER"] = Field(
        description=(
            "Identifies the resolution scenario that best describes the transcript outcome:\n"
            "- CLIENT MANAGER: The client is redirected to another client manager\n"
            "- BRANCH: The client was introduced to go to the UBS branch\n"
            "- SELF SERVICE: The client was introduced to go to the UBS website or mobile app\n"
            "- RESOLVED: The client's problem is resolved with no further action needed\n"
            "- OTHER: Any other scenario not covered by the above options"
        )
    )

class SelfServiceFlag(BaseModel):
    tried_self_service: Literal["Yes", "No"] = Field(
        description="Indicates whether the client tried to use self service on website or digital banking"
    )

class FurtherSentiment(BaseModel):
    pass

class ReasonerProcessingResponse(BaseModel):
    """Pydantic model for validating OpenAI call transcript processing responses."""
    category: str
    product: str
    product_category: str
    product_topic: str
    call_reason: str
    summary: str
    summary_native: str
    call_triggers: str
    call_triggers_native: str
    caller_authentication: str
    call_flags: str
    sentiment: str
    ai_generated: str
    speaker: Speaker
    resolution: Resolution
    resolution_flag: ResolutionFlag
    live_help: str
    client_lifecycle_event: str
    self_service: SelfServiceFlag
    ai_hashtags: str
    hashtags: str
    ai_hashtags_native: str
    further_sentiment: FurtherSentiment
    contains_pii_or_cid: str



class OutputReasoner(BaseModel):
    pass
    