from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import time
import uuid


@dataclass
class Question:
    id: str
    category: str  # "behavioral" or "technical"
    text: str
    competency: str = ""
    order: int = 1
    completed: bool = False
    answer_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "text": self.text,
            "competency": self.competency,
            "order": self.order,
            "completed": self.completed,
            "answer_notes": self.answer_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            category=data.get("category", "technical"),
            text=data.get("text", ""),
            competency=data.get("competency", ""),
            order=data.get("order", 1),
            completed=data.get("completed", False),
            answer_notes=data.get("answer_notes"),
        )


@dataclass
class Scorecard:
    overall_score: int  # 0 to 100
    recommendation: str  # "Strong Hire", "Hire", "Consider", "Do Not Hire"
    technical_score: int
    behavioral_score: int
    communication_score: int
    summary: str
    strengths: List[str] = field(default_factory=list)
    areas_for_improvement: List[str] = field(default_factory=list)
    question_evaluations: List[Dict[str, Any]] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "recommendation": self.recommendation,
            "technical_score": self.technical_score,
            "behavioral_score": self.behavioral_score,
            "communication_score": self.communication_score,
            "summary": self.summary,
            "strengths": self.strengths,
            "areas_for_improvement": self.areas_for_improvement,
            "question_evaluations": self.question_evaluations,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scorecard":
        return cls(
            overall_score=data.get("overall_score", 0),
            recommendation=data.get("recommendation", "Consider"),
            technical_score=data.get("technical_score", 0),
            behavioral_score=data.get("behavioral_score", 0),
            communication_score=data.get("communication_score", 0),
            summary=data.get("summary", ""),
            strengths=data.get("strengths", []),
            areas_for_improvement=data.get("areas_for_improvement", []),
            question_evaluations=data.get("question_evaluations", []),
            evaluated_at=data.get("evaluated_at", time.strftime("%Y-%m-%d %H:%M:%S")),
        )


@dataclass
class Candidate:
    id: str
    name: str
    phone: str
    position: str
    job_description: str = ""
    resume_filename: str = ""
    resume_text: str = ""
    status: str = "ready"  # ready, in_progress, completed, evaluated
    questions: List[Question] = field(default_factory=list)
    scorecard: Optional[Scorecard] = None
    call_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "position": self.position,
            "job_description": self.job_description,
            "resume_filename": self.resume_filename,
            "resume_text": self.resume_text,
            "status": self.status,
            "questions": [q.to_dict() for q in self.questions],
            "scorecard": self.scorecard.to_dict() if self.scorecard else None,
            "call_id": self.call_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Candidate":
        questions_raw = data.get("questions") or []
        questions = [Question.from_dict(q) if isinstance(q, dict) else q for q in questions_raw]
        scorecard_raw = data.get("scorecard")
        scorecard = Scorecard.from_dict(scorecard_raw) if isinstance(scorecard_raw, dict) else None

        return cls(
            id=data.get("id", f"cand_{uuid.uuid4().hex[:8]}"),
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            position=data.get("position", ""),
            job_description=data.get("job_description", ""),
            resume_filename=data.get("resume_filename", ""),
            resume_text=data.get("resume_text", ""),
            status=data.get("status", "ready"),
            questions=questions,
            scorecard=scorecard,
            call_id=data.get("call_id"),
            created_at=data.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=data.get("updated_at", time.strftime("%Y-%m-%d %H:%M:%S")),
        )
