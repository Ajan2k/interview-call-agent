from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QuestionSchema(BaseModel):
    id: str
    category: str = "technical"  # "behavioral" or "technical"
    text: str
    competency: str = ""
    order: int = 1
    completed: bool = False
    answer_notes: Optional[str] = None


class ScorecardSchema(BaseModel):
    overall_score: int
    recommendation: str  # "Strong Hire", "Hire", "Consider", "Do Not Hire"
    technical_score: int
    behavioral_score: int
    communication_score: int
    summary: str
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    question_evaluations: List[Dict[str, Any]] = Field(default_factory=list)
    evaluated_at: str


class CandidateCreate(BaseModel):
    name: str
    phone: str
    position: str
    job_description: str
    behavioral_questions: Optional[List[str]] = None


class CandidateResponse(BaseModel):
    id: str
    name: str
    phone: str
    position: str
    job_description: str
    resume_filename: str
    resume_text: Optional[str] = None
    status: str
    questions: List[QuestionSchema] = Field(default_factory=list)
    scorecard: Optional[ScorecardSchema] = None
    call_id: Optional[str] = None
    created_at: str
    updated_at: str


class QuestionsUpdateRequest(BaseModel):
    questions: List[QuestionSchema]
