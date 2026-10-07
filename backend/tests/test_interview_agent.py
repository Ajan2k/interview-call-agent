import io
import json
import pytest
from fastapi.testclient import TestClient
import main
from models.candidate import Candidate, Question, Scorecard
from services.document_parser import DocumentParser
from services.candidate_repository import CandidateRepository
from services.interview_service import InterviewService, DEFAULT_BEHAVIORAL_QUESTIONS
from services.database_manager import DatabaseManager

pytestmark = pytest.mark.unit


class TestDocumentParser:
    def test_parse_txt(self):
        content = b"John Doe\nSoftware Engineer with 5 years experience in Python and FastAPI."
        result = DocumentParser.parse("resume.txt", content)
        assert "John Doe" in result
        assert "Python" in result

    def test_parse_docx(self):
        # Create a real in-memory docx
        import docx
        doc = docx.Document()
        doc.add_paragraph("Jane Smith")
        doc.add_paragraph("Senior AI Engineer with experience in PyTorch and LLMs.")
        bio = io.BytesIO()
        doc.save(bio)
        data = bio.getvalue()

        result = DocumentParser.parse("resume.docx", data)
        assert "Jane Smith" in result
        assert "Senior AI Engineer" in result

    def test_parse_fallback(self):
        content = b"Candidate Profile plain bytes"
        result = DocumentParser.parse("unknown_ext.xyz", content)
        assert "Candidate Profile" in result


class TestCandidateRepository:
    def test_save_and_retrieve_fallback(self, tmp_path, monkeypatch):
        db_mgr = DatabaseManager()
        # Force offline db to test file fallback
        monkeypatch.setattr(db_mgr, "get_connection", lambda: None)
        repo = CandidateRepository(db_mgr)
        repo.fallback_file = str(tmp_path / "candidates.json")

        cand = Candidate(
            id="cand_test_001",
            name="Alice Walker",
            phone="+1234567890",
            position="Staff ML Engineer",
            job_description="Lead ML infra",
            resume_filename="resume.pdf",
            resume_text="Alice's Resume content",
            questions=[
                Question(id="q1", category="behavioral", text="Tell me about a crisis", order=1),
                Question(id="q2", category="technical", text="Explain Transformers", order=2),
            ],
        )

        assert repo.save(cand) is True
        retrieved = repo.get_by_id("cand_test_001")
        assert retrieved is not None
        assert retrieved.name == "Alice Walker"
        assert retrieved.position == "Staff ML Engineer"
        assert len(retrieved.questions) == 2
        assert retrieved.questions[0].text == "Tell me about a crisis"

        # Test responses query tracked by candidate_id
        responses = repo.get_responses("cand_test_001")
        assert len(responses) == 2
        assert responses[0]["candidate_id"] == "cand_test_001"
        assert responses[0]["candidate_name"] == "Alice Walker"
        assert responses[0]["candidate_position"] == "Staff ML Engineer"

        # Test phone lookup
        by_phone = repo.get_by_phone("+1234567890")
        assert by_phone is not None
        assert by_phone.id == "cand_test_001"

        all_cands = repo.get_all()
        assert len(all_cands) == 1

        assert repo.delete("cand_test_001") is True
        assert repo.get_by_id("cand_test_001") is None

    def test_pagination_and_search_fallback(self, tmp_path, monkeypatch):
        db_mgr = DatabaseManager()
        monkeypatch.setattr(db_mgr, "get_connection", lambda: None)
        repo = CandidateRepository(db_mgr)
        repo.fallback_file = str(tmp_path / "candidates_page.json")

        for i in range(5):
            repo.save(Candidate(
                id=f"c_{i}",
                name=f"Candidate {i}",
                phone=f"1000{i}",
                position="Dev" if i % 2 == 0 else "Designer",
                job_description="JD",
                status="ready" if i < 3 else "evaluated",
            ))

        assert repo.get_count() == 5
        assert repo.get_count(status="ready") == 3
        assert repo.get_count(search="Candidate 1") == 1

        # Page 1 (limit 2)
        p1 = repo.get_all(limit=2, offset=0)
        assert len(p1) == 2

        # Filter by status
        ready = repo.get_all(status="ready")
        assert len(ready) == 3


class TestInterviewService:
    @pytest.mark.asyncio
    async def test_default_behavioral_questions(self):
        service = InterviewService()
        questions = await service.generate_questions(
            candidate_name="Bob",
            position="DevOps Engineer",
            job_description="Kubernetes, Terraform, AWS",
            resume_text="Bob's background in AWS and CI/CD",
        )
        assert len(questions) >= 5
        beh_questions = [q for q in questions if q.category == "behavioral"]
        assert len(beh_questions) == 5
        assert "deadline" in beh_questions[0].text.lower() or "crisis" in beh_questions[0].text.lower()

    @pytest.mark.asyncio
    async def test_custom_behavioral_questions(self):
        service = InterviewService()
        custom = [f"Custom Q{i}" for i in range(1, 6)]
        questions = await service.generate_questions(
            candidate_name="Carol",
            position="Frontend Lead",
            job_description="React, TypeScript, CSS",
            resume_text="Carol's React resume",
            custom_behavioral=custom,
        )
        beh_questions = [q for q in questions if q.category == "behavioral"]
        assert len(beh_questions) == 5
        assert beh_questions[0].text == "Custom Q1"
        assert beh_questions[4].text == "Custom Q5"

    @pytest.mark.asyncio
    async def test_evaluate_interview_empty_transcript(self):
        service = InterviewService()
        cand = Candidate(
            id="c1",
            name="Dan",
            phone="123",
            position="QA",
            job_description="Automation",
            resume_filename="r.pdf",
            resume_text="Dan resume",
        )
        scorecard = await service.evaluate_interview(cand, [])
        assert scorecard.recommendation == "Do Not Hire"
        assert scorecard.overall_score == 0


class TestCandidateRoutes:
    def test_behavioral_defaults_endpoint(self):
        client = TestClient(main.app)
        resp = client.get("/api/candidates/behavioral-defaults")
        assert resp.status_code == 200
        body = resp.json()
        assert "questions" in body
        assert len(body["questions"]) == 5

    def test_candidate_crud_cycle(self, monkeypatch, tmp_path):
        from services.candidate_repository import candidate_repo
        candidate_repo.fallback_file = str(tmp_path / "candidates_test.json")
        monkeypatch.setattr(candidate_repo.db_manager, "get_connection", lambda: None)

        client = TestClient(main.app)

        # 1. Create candidate via multipart form
        file_payload = ("resume.txt", b"Jane Doe\nFull Stack Developer with Node and React", "text/plain")
        form_data = {
            "name": "Jane Doe",
            "phone": "+91 9988776655",
            "position": "Full Stack Developer",
            "job_description": "We are seeking a Full Stack Developer experienced with Node, React, and PostgreSQL.",
        }
        res = client.post("/api/candidates", data=form_data, files={"resume": file_payload})
        assert res.status_code == 200
        cand_data = res.json()
        cand_id = cand_data["id"]
        assert cand_data["name"] == "Jane Doe"
        assert cand_data["position"] == "Full Stack Developer"
        assert len(cand_data["questions"]) >= 5

        # 2. Get all candidates
        list_res = client.get("/api/candidates")
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(c["id"] == cand_id for c in items)

        # 3. Get candidate by id
        get_res = client.get(f"/api/candidates/{cand_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Jane Doe"

        # 4. Update questions
        updated_questions = [
            {"id": "q1", "category": "behavioral", "text": "Edited behavioral question", "order": 1, "completed": False}
        ]
        put_res = client.put(f"/api/candidates/{cand_id}/questions", json={"questions": updated_questions})
        assert put_res.status_code == 200
        assert len(put_res.json()["questions"]) == 1
        assert put_res.json()["questions"][0]["text"] == "Edited behavioral question"

        # 5. Get tracked candidate responses by candidate_id
        resp_res = client.get(f"/api/candidates/{cand_id}/responses")
        assert resp_res.status_code == 200
        assert resp_res.json()["candidate_id"] == cand_id
        assert len(resp_res.json()["responses"]) == 1
        assert resp_res.json()["responses"][0]["candidate_id"] == cand_id

        # 6. Get candidate calls by candidate_id
        calls_res = client.get(f"/api/candidates/{cand_id}/calls")
        assert calls_res.status_code == 200
        assert calls_res.json()["candidate_id"] == cand_id

        # 7. Evaluate candidate
        eval_res = client.post(f"/api/candidates/{cand_id}/evaluate")
        assert eval_res.status_code == 200
        assert eval_res.json()["status"] == "evaluated"
        assert eval_res.json()["scorecard"] is not None

        # 8. Delete candidate
        del_res = client.delete(f"/api/candidates/{cand_id}")
        assert del_res.status_code == 200

        # Verify deleted
        assert client.get(f"/api/candidates/{cand_id}").status_code == 404


class TestInterviewControlMarkers:
    def test_end_call_marker_sets_flag_and_is_stripped(self, session_state):
        from routes import voice
        out = voice.extract_control_markers("Thank you for joining today's interview. [END_CALL]", session_state)
        assert session_state["pending_end_call"] is True
        assert "END_CALL" not in out
        assert out == "Thank you for joining today's interview."

    def test_add_transcript_turn(self, session_state):
        from routes import voice
        voice.add_transcript(session_state, "caller", "I have 5 years experience with Python", "en-IN")
        assert len(session_state["transcript"]) == 1
        turn = session_state["transcript"][0]
        assert turn["role"] == "caller"
        assert turn["text"] == "I have 5 years experience with Python"
        assert turn["lang"] == "en-IN"


class TestSettingsUsageInServices:
    def test_interview_service_uses_settings(self):
        from services.interview_service import (
            SARVAM_LLM_BASE_URL,
            CEREBRAS_LLM_BASE_URL,
            GEMINI_LLM_BASE_URL,
            TOGETHER_LLM_BASE_URL,
            FALLBACK_MODEL,
        )
        from core.config import settings
        assert SARVAM_LLM_BASE_URL == settings.SARVAM_LLM_BASE_URL
        assert CEREBRAS_LLM_BASE_URL == settings.CEREBRAS_LLM_BASE_URL
        assert GEMINI_LLM_BASE_URL == settings.GEMINI_LLM_BASE_URL
        assert TOGETHER_LLM_BASE_URL == settings.TOGETHER_LLM_BASE_URL
        assert FALLBACK_MODEL == settings.FALLBACK_MODEL

    def test_voice_llm_uses_settings(self):
        from services.voice.llm import (
            SARVAM_LLM_BASE_URL,
            CEREBRAS_LLM_BASE_URL,
            GEMINI_LLM_BASE_URL,
            TOGETHER_LLM_BASE_URL,
            FALLBACK_MODEL,
        )
        from core.config import settings
        assert SARVAM_LLM_BASE_URL == settings.SARVAM_LLM_BASE_URL
        assert CEREBRAS_LLM_BASE_URL == settings.CEREBRAS_LLM_BASE_URL
        assert GEMINI_LLM_BASE_URL == settings.GEMINI_LLM_BASE_URL
        assert TOGETHER_LLM_BASE_URL == settings.TOGETHER_LLM_BASE_URL
        assert FALLBACK_MODEL == settings.FALLBACK_MODEL

    def test_voice_tts_and_stt_use_settings(self):
        from services.voice.tts import SARVAM_TTS_URL, CARTESIA_TTS_URL, CARTESIA_VERSION
        from services.voice.stt import SARVAM_STT_URL
        from services.translation_service import TranslationService
        from core.config import settings
        assert SARVAM_TTS_URL == settings.SARVAM_TTS_URL
        assert CARTESIA_TTS_URL == settings.CARTESIA_TTS_URL
        assert CARTESIA_VERSION == settings.CARTESIA_VERSION
        assert SARVAM_STT_URL == settings.SARVAM_STT_URL
        assert TranslationService.SARVAM_TRANSLATE_URL == settings.SARVAM_TRANSLATE_URL
