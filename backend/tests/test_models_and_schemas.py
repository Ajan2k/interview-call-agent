"""Unit tests for interview agent models and schemas."""
import pytest
from models.call import Call
from models.voice_config import VoiceConfig
from models.candidate import Candidate, Question, Scorecard
from schemas.candidate import CandidateCreate, CandidateResponse, QuestionSchema, ScorecardSchema
from schemas.translate import TranslateRequestSchema, TranslateResponseSchema
from schemas.health import HealthResponseSchema

pytestmark = pytest.mark.unit


class TestDomainModels:
    def test_candidate_and_question_serialization(self):
        q = Question(
            id="q1",
            category="behavioral",
            text="Tell me about a time you handled a tight deadline.",
            competency="time management",
        )
        cand = Candidate(
            id="cand-1",
            name="Alice Smith",
            phone="+919876543210",
            position="Senior Backend Engineer",
            job_description="Seeking a FastAPI and PostgreSQL expert.",
            resume_text="5 years experience in building high concurrency systems.",
            questions=[q],
            status="questions_ready",
        )
        d = cand.to_dict()
        assert d["id"] == "cand-1"
        assert d["name"] == "Alice Smith"
        assert len(d["questions"]) == 1
        assert d["questions"][0]["category"] == "behavioral"

        restored = Candidate.from_dict(d)
        assert restored.id == cand.id
        assert restored.name == cand.name
        assert len(restored.questions) == 1
        assert restored.questions[0].text == q.text

    def test_scorecard_serialization(self):
        sc = Scorecard(
            overall_score=85,
            technical_score=90,
            behavioral_score=80,
            communication_score=85,
            recommendation="Hire",
            strengths=["Strong FastAPI knowledge", "Clear communication"],
            areas_for_improvement=["Could deepen distributed systems insight"],
            summary="Candidate demonstrated solid architecture skills.",
        )
        d = sc.to_dict()
        assert d["overall_score"] == 85
        assert d["recommendation"] == "Hire"
        assert len(d["strengths"]) == 2

        restored = Scorecard.from_dict(d)
        assert restored.overall_score == sc.overall_score
        assert restored.recommendation == sc.recommendation

    def test_voice_config_model(self):
        vc = VoiceConfig(
            speech_mode="Natural Female Voice",
            language_focus="English",
            prompt_template="You are Alex, an AI interviewer.",
        )
        d = vc.to_dict()
        assert d["speechMode"] == "Natural Female Voice"
        restored = VoiceConfig.from_dict(d)
        assert restored.speech_mode == "Natural Female Voice"

    def test_candidate_response_record_model(self):
        from models.candidate import CandidateResponseRecord
        cr = CandidateResponseRecord(
            id="cand-1_q1",
            candidate_id="cand-1",
            question_id="q1",
            question_text="Explain database normalization.",
            category="technical",
            competency="Database Design",
            order_num=1,
            completed=True,
            response_text="Normalization reduces data redundancy.",
            score=95,
            feedback="Clear explanation of 3NF.",
        )
        d = cr.to_dict()
        assert d["candidate_id"] == "cand-1"
        assert d["score"] == 95
        assert d["completed"] is True

        restored = CandidateResponseRecord.from_dict(d)
        assert restored.candidate_id == "cand-1"
        assert restored.score == 95
        assert restored.response_text == "Normalization reduces data redundancy."

    def test_call_model_with_candidate_tracking(self):
        call = Call(
            id="call_20261007_001",
            direction="outgoing",
            phone="+919876543210",
            candidate_id="cand-1",
            candidate_name="Alice Smith",
            candidate_position="Senior Backend Engineer",
            duration_sec=300,
        )
        d = call.to_dict()
        assert d["candidate_id"] == "cand-1"
        assert d["candidate_name"] == "Alice Smith"
        assert d["candidate_position"] == "Senior Backend Engineer"

        restored = Call.from_dict(d)
        assert restored.candidate_id == "cand-1"
        assert restored.candidate_name == "Alice Smith"
        assert restored.candidate_position == "Senior Backend Engineer"


class TestSchemas:
    def test_candidate_create_schema(self):
        data = {
            "name": "Jane Developer",
            "phone": "+919999999999",
            "position": "Frontend Lead",
            "job_description": "React 19 & TypeScript expert",
        }
        schema = CandidateCreate(**data)
        assert schema.name == "Jane Developer"
        assert schema.position == "Frontend Lead"

    def test_translate_schema(self):
        req = TranslateRequestSchema(text="Hello world")
        assert req.source_language_code == "auto"
        assert req.target_language_code == "en-IN"

        res = TranslateResponseSchema(translated="வணக்கம்", source="en-IN")
        assert res.translated == "வணக்கம்"


class TestCoreConfig:
    def test_settings_secretstr_and_dsn(self):
        from core.config import Settings
        from pydantic import SecretStr

        custom_settings = Settings(
            _env_file=None,
            DATABASE_URL=None,
            POSTGRES_USER="myuser",
            POSTGRES_PASSWORD=SecretStr("mypassword"),
            POSTGRES_HOST="127.0.0.1",
            POSTGRES_PORT=5433,
            POSTGRES_DB="mydb",
        )
        assert isinstance(custom_settings.POSTGRES_PASSWORD, SecretStr)
        assert custom_settings.POSTGRES_PASSWORD.get_secret_value() == "mypassword"
        assert custom_settings.postgres_dsn == "postgresql://myuser:mypassword@127.0.0.1:5433/mydb"
        assert custom_settings.BACKEND_DIR.exists()
        assert custom_settings.LOGS_DIR.name == "logs"
