from pydantic import BaseModel

class InputFeedbackForm(BaseModel):
    id: str
    taskId: str
    language: str
    text: str

class OutputFeedbackForm(BaseModel):
    id: str
    taskId: str
    ai_hashtag: str
    hashtag: str
    summary: str
    message: str

class InternalFeedbackResult(BaseModel):
    id: str
    taskId: str
    ai_hashtag: str
    hashtag: str
    summary: str
    message: str
    contains_pii_or_cid: str
