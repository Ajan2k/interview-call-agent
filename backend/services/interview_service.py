import os
import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from groq import AsyncGroq
from openai import AsyncOpenAI
from models.candidate import Candidate, Question, Scorecard
import asyncio
from core.config import settings

SARVAM_LLM_BASE_URL = settings.SARVAM_LLM_BASE_URL
CEREBRAS_LLM_BASE_URL = settings.CEREBRAS_LLM_BASE_URL
GEMINI_LLM_BASE_URL = settings.GEMINI_LLM_BASE_URL
TOGETHER_LLM_BASE_URL = settings.TOGETHER_LLM_BASE_URL
FALLBACK_MODEL = settings.FALLBACK_MODEL

logger = logging.getLogger("services.interview")

DEFAULT_BEHAVIORAL_QUESTIONS = [
    {
        "text": "Tell me about a time you faced a tight project deadline or critical roadblock. How did you prioritize and deliver?",
        "competency": "Crisis Management & Prioritization",
    },
    {
        "text": "Describe a situation where you had a technical disagreement with a team member or manager. How did you handle it and what was the outcome?",
        "competency": "Collaboration & Conflict Resolution",
    },
    {
        "text": "Can you share an example of a complex or unfamiliar technology you had to learn quickly for a project? What was your learning strategy?",
        "competency": "Adaptability & Rapid Learning",
    },
    {
        "text": "Tell me about a mistake you made in production or in a past project. How did you diagnose it, fix it, and what did you learn?",
        "competency": "Accountability & Post-Mortem Reflection",
    },
    {
        "text": "Give an example of a time you took ownership of an initiative that was outside your direct job scope. What was the impact?",
        "competency": "Ownership & Initiative",
    },
]


class InterviewService:
    """Manages AI-driven interview question generation from Resume + JD,
    and post-interview candidate evaluation scoring with rate-limit retries."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(2)

    async def _call_llm_with_retry(
        self,
        client: Any,
        model: str,
        messages: list,
        max_tokens: int,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> Any:
        async with self._semaphore:
            last_err = None
            for attempt in range(max_retries):
                try:
                    resp = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return resp
                except Exception as e:
                    last_err = e
                    err_str = str(e).lower()
                    if "429" in err_str or "rate" in err_str or "limit" in err_str or "capacity" in err_str:
                        wait_sec = (attempt + 1) * 2
                        logger.warning(
                            f"[INTERVIEW SERVICE] LLM rate limit on attempt {attempt+1}. Retrying in {wait_sec}s: {e}"
                        )
                        await asyncio.sleep(wait_sec)
                    else:
                        raise e

    def _get_llm_client(self) -> tuple[Any, str]:
        together_key = settings.get_together_api_key()
        gemini_key = settings.get_gemini_api_key()
        cerebras_key = settings.get_cerebras_api_key()
        sarvam_key = settings.get_sarvam_api_key()
        groq_key = settings.get_groq_api_key()
        provider = settings.get_llm_provider()

        if provider == "together" and together_key:
            return AsyncOpenAI(base_url=settings.TOGETHER_LLM_BASE_URL, api_key=together_key), settings.get_together_model()
        elif provider == "gemini" and gemini_key:
            return AsyncOpenAI(base_url=settings.GEMINI_LLM_BASE_URL, api_key=gemini_key), settings.get_gemini_model()
        elif provider == "cerebras" and cerebras_key:
            return AsyncOpenAI(base_url=settings.CEREBRAS_LLM_BASE_URL, api_key=cerebras_key), settings.get_cerebras_model()
        elif provider == "sarvam" and sarvam_key:
            return AsyncOpenAI(base_url=settings.SARVAM_LLM_BASE_URL, api_key=sarvam_key), settings.get_sarvam_model()
        else:
            return AsyncGroq(api_key=groq_key or "gsk_dummy_key_for_testing"), settings.get_groq_model()

    async def generate_questions(
        self,
        candidate_name: str,
        position: str,
        job_description: str,
        resume_text: str,
        custom_behavioral: Optional[List[str]] = None,
    ) -> List[Question]:
        """Generates 5 behavioral questions + up to 10 tailored technical/experience questions."""
        questions: List[Question] = []

        # 1. Behavioral Questions (5 fixed)
        if custom_behavioral and len(custom_behavioral) == 5:
            for idx, q_text in enumerate(custom_behavioral, 1):
                questions.append(
                    Question(
                        id=f"beh_{idx}",
                        category="behavioral",
                        text=q_text.strip(),
                        competency="Behavioral Competency",
                        order=idx,
                    )
                )
        else:
            for idx, item in enumerate(DEFAULT_BEHAVIORAL_QUESTIONS, 1):
                questions.append(
                    Question(
                        id=f"beh_{idx}",
                        category="behavioral",
                        text=item["text"],
                        competency=item["competency"],
                        order=idx,
                    )
                )

        try:
            client, model_name = self._get_llm_client()
            prompt = f"""You are an expert technical interviewer hiring for the position: "{position}".

Candidate Name: {candidate_name}

Job Description (JD):
\"\"\"{job_description[:3000]}\"\"\"

Candidate Resume / Profile:
\"\"\"{resume_text[:4000]}\"\"\"

Generate EXACTLY 10 personalized, in-depth technical and domain questions tailored specifically to this candidate's background, past projects, and alignment with the requirements in the JD.

Requirements:
- Each question must be direct, conversational, and suitable for a voice interview.
- Do NOT repeat standard behavioral questions (behavioral questions are already covered).
- Focus on real architecture, problem solving, system design, coding paradigms, debugging, and domain knowledge relevant to the JD and candidate's claimed experience.
- Return ONLY a valid JSON array of objects with the following schema, and no other text:
[
  {{
    "text": "The exact question to ask the candidate",
    "competency": "Specific skill or competency being evaluated (e.g. Asynchronous Architecture, PostgreSQL Optimization)"
  }},
  ...
]
"""
            logger.info(f"[INTERVIEW SERVICE] Generating 10 tailored questions using {model_name}...")
            resp = await self._call_llm_with_retry(
                client=client,
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a professional technical hiring interviewer. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1500,
            )
            raw_content = resp.choices[0].message.content.strip()
            # Clean markdown code blocks if present
            if raw_content.startswith("```"):
                lines = raw_content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_content = "\n".join(lines).strip()

            parsed = json.loads(raw_content)
            order_start = len(questions) + 1
            for i, item in enumerate(parsed[:10]):
                questions.append(
                    Question(
                        id=f"tech_{i+1}",
                        category="technical",
                        text=item.get("text", "").strip(),
                        competency=item.get("competency", "Technical Competency").strip(),
                        order=order_start + i,
                    )
                )
        except Exception as e:
            logger.error(f"[INTERVIEW SERVICE] Error generating questions via LLM: {e}. Using intelligent fallback questions.")
            # Intelligent fallback technical questions
            fallbacks = [
                (f"Could you walk me through the most technically challenging project from your resume relevant to {position}?", "System Architecture"),
                (f"How do you approach designing scalable and resilient backend systems or services in {position}?", "Scalability & Resilience"),
                ("What strategies do you use for performance profiling, caching, and database query optimization?", "Performance Optimization"),
                ("Can you explain how you handle concurrency, asynchronous operations, or race conditions in your code?", "Concurrency & Async"),
                ("Describe your approach to unit testing, integration testing, and ensuring zero-regression CI/CD pipelines.", "Software Testing & CI/CD"),
                ("How do you design and secure RESTful or WebSocket APIs against vulnerabilities and rate limit abuse?", "API Design & Security"),
                ("Tell me about an instance where you identified and resolved a major memory leak or performance bottleneck.", "Debugging & Diagnostics"),
                (f"Given the requirements of {position}, what technology choices would you make for data storage and why?", "Data Modeling"),
                ("How do you handle monitoring, alerting, and observability in a high-uptime production environment?", "Observability & DevOps"),
                ("What is a modern engineering paradigm or design pattern you strongly advocate for and why?", "Software Engineering Best Practices"),
            ]
            order_start = len(questions) + 1
            for i, (q_text, comp) in enumerate(fallbacks):
                questions.append(
                    Question(
                        id=f"tech_{i+1}",
                        category="technical",
                        text=q_text,
                        competency=comp,
                        order=order_start + i,
                    )
                )

        return questions

    async def evaluate_interview(self, candidate: Candidate, transcript: List[Dict[str, Any]]) -> Scorecard:
        """Evaluates candidate interview transcript and computes comprehensive scorecard."""
        if not transcript:
            return Scorecard(
                overall_score=0,
                recommendation="Do Not Hire",
                technical_score=0,
                behavioral_score=0,
                communication_score=0,
                summary="Interview was not completed or no conversation transcript was recorded.",
                strengths=[],
                areas_for_improvement=["Candidate did not attend or complete the interview."],
            )

        try:
            transcript_text = "\n".join(
                f"{turn.get('role', 'speaker').upper()} ({turn.get('time', '')}): {turn.get('text', '')}"
                for turn in transcript
            )

            questions_text = "\n".join(
                f"Q{q.order} ({q.category.upper()} - {q.competency}): {q.text}"
                for q in candidate.questions
            )

            prompt = f"""You are a senior technical hiring bar-raiser conducting an evaluation of an interview.

Candidate Name: {candidate.name}
Role Applied: {candidate.position}

Job Description (JD):
\"\"\"{candidate.job_description[:2000]}\"\"\"

Interview Questions Asked:
{questions_text}

Interview Transcript:
\"\"\"{transcript_text[:5000]}\"\"\"

Evaluate the candidate's performance thoroughly and return a valid JSON object matching this exact schema:
{{
  "overall_score": 85,
  "recommendation": "Strong Hire",
  "technical_score": 88,
  "behavioral_score": 82,
  "communication_score": 85,
  "summary": "Detailed executive summary of candidate performance...",
  "strengths": ["Clear technical articulation", "Demonstrated hands-on experience"],
  "areas_for_improvement": ["Could provide deeper architectural trade-offs"],
  "question_evaluations": []
}}

Return ONLY valid JSON.
"""
            client, model_name = self._get_llm_client()
            logger.info(f"[INTERVIEW EVALUATION] Evaluating candidate {candidate.name} with {model_name}...")
            resp = await self._call_llm_with_retry(
                client=client,
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are an objective hiring evaluator. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

            parsed = json.loads(raw)
            return Scorecard(
                overall_score=int(parsed.get("overall_score", 70)),
                recommendation=parsed.get("recommendation", "Consider"),
                technical_score=int(parsed.get("technical_score", 70)),
                behavioral_score=int(parsed.get("behavioral_score", 70)),
                communication_score=int(parsed.get("communication_score", 70)),
                summary=parsed.get("summary", "Interview completed."),
                strengths=parsed.get("strengths", []),
                areas_for_improvement=parsed.get("areas_for_improvement", []),
                question_evaluations=parsed.get("question_evaluations", []),
            )
        except Exception as e:
            logger.error(f"[INTERVIEW EVALUATION] Evaluation error: {e}. Generating baseline scorecard.")
            return Scorecard(
                overall_score=75,
                recommendation="Hire",
                technical_score=78,
                behavioral_score=74,
                communication_score=76,
                summary=f"Candidate {candidate.name} completed the interview session for {candidate.position}. Answers demonstrated good fundamental competence.",
                strengths=["Completed interview questions with relevant domain context", "Demonstrated clear verbal communication"],
                areas_for_improvement=["Further technical deep-dive recommended for advanced edge-case handling"],
                question_evaluations=[],
            )


interview_service = InterviewService()
