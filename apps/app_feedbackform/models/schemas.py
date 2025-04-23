from pydantic import BaseModel

class InputFeedbackForm(BaseModel):
    id: str
    taskId: str
    language: str
    text: str

class OutputFeedbackForm(BaseModel):
    id: str
    ai_hashtag: str
    hashtag: str
    summary: str

    

