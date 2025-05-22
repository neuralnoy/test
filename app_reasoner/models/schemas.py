from pydantic import BaseModel

class InputReasoner(BaseModel):
    id: str
    taskId: str
    language: str
    text: str

class OutputReasoner(BaseModel):
    id: str
    taskId: str
    ai_reason: str
    reason: str
    summary: str
    message: str

class InternalReasonerResult(BaseModel):
    id: str
    taskId: str
    ai_reason: str
    reason: str
    summary: str
    message: str
    contains_pii_or_cid: str 