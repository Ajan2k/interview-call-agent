"""Unit tests for models and schemas."""
import pytest
from models.contact import Contact
from models.campaign import Campaign
from models.call import Call
from models.meeting import Meeting
from models.callback import Callback
from models.voice_config import VoiceConfig
from schemas.contact import ContactCreateSchema, ContactResponseSchema
from schemas.translate import TranslateRequestSchema, TranslateResponseSchema
from schemas.health import HealthResponseSchema

pytestmark = pytest.mark.unit


class TestDomainModels:
    def test_contact_serialization(self):
        c = Contact(
            id="1",
            name="John Doe",
            phone="+919876543210",
            status="Pending",
            last_called="Never",
            notes="Follow up",
            is_incoming=True,
        )
        d = c.to_dict()
        assert d["id"] == "1"
        assert d["name"] == "John Doe"
        assert d["isIncoming"] is True
        assert d["lastCalled"] == "Never"

        restored = Contact.from_dict(d)
        assert restored.id == c.id
        assert restored.name == c.name
        assert restored.is_incoming is True

    def test_campaign_serialization(self):
        camp = Campaign(id="camp-1", name="Outbound Tech", status="Active", contacts_count=42, date="Today")
        d = camp.to_dict()
        assert d["id"] == "camp-1"
        assert d["contacts_count"] == 42
        restored = Campaign.from_dict(d)
        assert restored.name == camp.name

    def test_call_lead_status_resolution(self):
        c1 = Call(id="call-1", direction="outgoing", phone="+919876", lead="status=HOT | very interested")
        assert c1.resolved_lead_status() == "HOT"

        c2 = Call(id="call-2", direction="incoming", phone="+919876", lead_status="cold")
        assert c2.resolved_lead_status() == "COLD"

    def test_meeting_and_callback_models(self):
        m = Meeting(time="2026-10-03 18:00:00", call_id="c-1", direction="incoming", phone="+91", language="Tamil", details="Demo Friday")
        assert m.to_dict()["call_id"] == "c-1"

        cb = Callback(time="2026-10-03 18:00:00", call_id="c-2", direction="outgoing", phone="+91", language="English", callback_time="Tomorrow 10am")
        assert cb.to_dict()["done"] is False
        cb.done = True
        assert cb.to_dict()["done"] is True


class TestSchemas:
    def test_contact_create_schema(self):
        data = {"name": "Asha", "phone": "+919999999999", "notes": "VIP client"}
        schema = ContactCreateSchema(**data)
        assert schema.name == "Asha"
        assert schema.status == "Pending"
        assert schema.lastCalled == "Never"

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
        # Test paths default_factory
        assert custom_settings.BACKEND_DIR.exists()
        assert custom_settings.LOGS_DIR.name == "logs"

