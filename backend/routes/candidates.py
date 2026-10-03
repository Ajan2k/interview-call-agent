import json
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Response
from models.candidate import Candidate, Question
from schemas.candidate import (
    CandidateResponse,
    QuestionSchema,
    ScorecardSchema,
    QuestionsUpdateRequest,
)
from services.document_parser import document_parser
from services.candidate_repository import candidate_repo
from services.interview_service import interview_service, DEFAULT_BEHAVIORAL_QUESTIONS
from services.database_manager import call_repo

logger = logging.getLogger("routes.candidates")
router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/behavioral-defaults")
async def get_default_behavioral_questions():
    """Returns the default 5 STAR-method behavioral questions."""
    return {"questions": DEFAULT_BEHAVIORAL_QUESTIONS}


@router.post("", response_model=CandidateResponse)
async def create_candidate(
    name: str = Form(...),
    phone: str = Form(...),
    position: str = Form(...),
    job_description: str = Form(...),
    resume: UploadFile = File(...),
    behavioral_questions: Optional[str] = Form(None),
):
    """Uploads candidate resume (PDF/DOCX), parses content, autonomously generates
    10 personalized technical questions + 5 behavioral questions, and persists candidate."""
    try:
        content = await resume.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded resume file is empty")

        filename = resume.filename or "resume.pdf"
        resume_text = document_parser.parse(filename, content)
        if not resume_text:
            raise HTTPException(status_code=400, detail="Could not extract readable text from resume")

        custom_beh_list = None
        if behavioral_questions:
            try:
                parsed_beh = json.loads(behavioral_questions)
                if isinstance(parsed_beh, list):
                    custom_beh_list = [str(q) for q in parsed_beh]
            except Exception:
                pass

        logger.info(f"[CANDIDATE] Generating interview questions for {name} ({position})...")
        questions = await interview_service.generate_questions(
            candidate_name=name,
            position=position,
            job_description=job_description,
            resume_text=resume_text,
            custom_behavioral=custom_beh_list,
        )

        candidate = Candidate(
            id=f"cand_{resume.filename[:6].lower().replace('.', '')}_{phone[-4:]}",
            name=name.strip(),
            phone=phone.strip(),
            position=position.strip(),
            job_description=job_description.strip(),
            resume_filename=filename,
            resume_text=resume_text,
            status="ready",
            questions=questions,
        )

        candidate_repo.save(candidate)
        logger.info(f"[CANDIDATE] Candidate {candidate.id} created with {len(questions)} questions.")
        return candidate.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CANDIDATE] Error creating candidate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create candidate: {str(e)}")




@router.get("", response_model=List[CandidateResponse])
async def list_candidates(
    response: Response,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    """Returns paginated candidates with optional search and status filtering."""
    candidates = candidate_repo.get_all(limit=limit, offset=offset, search=search, status=status)
    total = candidate_repo.get_count(search=search, status=status)
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return [c.to_dict() for c in candidates]


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str):
    """Returns detailed candidate profile, questions, and evaluation scorecard."""
    cand = candidate_repo.get_by_id(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return cand.to_dict()


@router.put("/{candidate_id}/questions", response_model=CandidateResponse)
async def update_candidate_questions(candidate_id: str, req: QuestionsUpdateRequest):
    """Allows recruiters to review and edit/reorder candidate questions before an interview."""
    cand = candidate_repo.get_by_id(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    updated_questions = [
        Question(
            id=q.id,
            category=q.category,
            text=q.text,
            competency=q.competency,
            order=q.order,
            completed=q.completed,
            answer_notes=q.answer_notes,
        )
        for q in req.questions
    ]
    cand.questions = updated_questions
    candidate_repo.save(cand)
    return cand.to_dict()


@router.post("/{candidate_id}/evaluate", response_model=CandidateResponse)
async def evaluate_candidate(candidate_id: str):
    """Triggers an AI evaluation scorecard generation from the candidate's call transcript."""
    cand = candidate_repo.get_by_id(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Fetch transcript from call history if available
    transcript = []
    if cand.call_id:
        call_rec = call_repo.get_by_id(cand.call_id)
        if call_rec and call_rec.transcript:
            transcript = call_rec.transcript
    else:
        # Search calls for candidate phone
        all_calls = call_repo.get_all() or []
        for c in all_calls:
            if c and getattr(c, "phone", None) and cand.phone and (cand.phone in c.phone or c.phone in cand.phone):
                if getattr(c, "transcript", None):
                    transcript = c.transcript
                    cand.call_id = c.id
                    break

    logger.info(f"[EVALUATE] Running scorecard evaluation for {cand.name} ({len(transcript)} turns)...")
    scorecard = await interview_service.evaluate_interview(cand, transcript)
    cand.scorecard = scorecard
    cand.status = "evaluated"
    candidate_repo.save(cand)
    return cand.to_dict()


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: str):
    """Deletes candidate profile and scorecard."""
    success = candidate_repo.delete(candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"message": "Candidate deleted successfully"}
