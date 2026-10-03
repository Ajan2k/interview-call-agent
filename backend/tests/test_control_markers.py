"""Unit tests for extract_control_markers and add_transcript in voice.py.

extract_control_markers is the parser that strips [END_CALL] / [MEETING_BOOKED] /
[CALLBACK] / [LEAD] tags out of LLM output before TTS, recording their side effects
on session_state. The log_* helpers it calls write to disk/DB, so they're patched.
"""
import pytest

from routes import voice

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _stub_loggers(monkeypatch):
    """Replace the side-effecting log_* helpers with recorders so we can assert on
    what extract_control_markers decided to log, without touching disk or Postgres."""
    calls = {"meeting": [], "callback": [], "lead": []}
    monkeypatch.setattr(voice, "log_meeting", lambda d, s: calls["meeting"].append(d))
    monkeypatch.setattr(voice, "log_callback", lambda d, s: calls["callback"].append(d))
    monkeypatch.setattr(voice, "log_lead", lambda d, s: calls["lead"].append(d))
    return calls


class TestEndCall:
    def test_end_call_sets_flag_and_is_stripped(self, session_state):
        out = voice.extract_control_markers("Goodbye! [END_CALL]", session_state)
        assert session_state["pending_end_call"] is True
        assert "END_CALL" not in out
        assert out == "Goodbye!"

    def test_end_call_space_variant(self, session_state):
        out = voice.extract_control_markers("Bye END CALL", session_state)
        assert session_state.get("pending_end_call") is True
        assert "CALL" not in out

    def test_no_marker_leaves_text_and_flag_untouched(self, session_state):
        out = voice.extract_control_markers("Just a normal reply.", session_state)
        assert out == "Just a normal reply."
        assert "pending_end_call" not in session_state


class TestMeeting:
    def test_real_booking_logged_and_stripped(self, session_state, _stub_loggers):
        out = voice.extract_control_markers(
            "See you then! [MEETING_BOOKED: Monday 3pm]", session_state
        )
        assert _stub_loggers["meeting"] == ["Monday 3pm"]
        assert "MEETING_BOOKED" not in out
        assert out == "See you then!"

    def test_placeholder_angle_brackets_not_logged(self, session_state, _stub_loggers):
        out = voice.extract_control_markers(
            "[MEETING_BOOKED: <day and time>]", session_state
        )
        assert _stub_loggers["meeting"] == []  # hallucinated placeholder ignored
        assert "MEETING_BOOKED" not in out  # ...but still stripped from spoken text

    def test_placeholder_phrase_not_logged(self, session_state, _stub_loggers):
        voice.extract_control_markers(
            "[MEETING_BOOKED: day and time]", session_state
        )
        assert _stub_loggers["meeting"] == []


class TestCallback:
    def test_callback_logged_and_stripped(self, session_state, _stub_loggers):
        out = voice.extract_control_markers(
            "I'll call back. [CALLBACK: tomorrow evening]", session_state
        )
        assert _stub_loggers["callback"] == ["tomorrow evening"]
        assert "CALLBACK" not in out

    def test_callback_placeholder_ignored(self, session_state, _stub_loggers):
        voice.extract_control_markers("[CALLBACK: <time>]", session_state)
        assert _stub_loggers["callback"] == []


class TestLead:
    def test_lead_logged_and_stripped(self, session_state, _stub_loggers):
        out = voice.extract_control_markers(
            "Thanks! [LEAD: status=interested]", session_state
        )
        assert _stub_loggers["lead"] == ["status=interested"]
        assert "LEAD" not in out


class TestCombinedAndEdgeCases:
    def test_multiple_markers_in_one_reply(self, session_state, _stub_loggers):
        text = "Great, done! [MEETING_BOOKED: Tue 10am] [LEAD: status=hot] [END_CALL]"
        out = voice.extract_control_markers(text, session_state)
        assert _stub_loggers["meeting"] == ["Tue 10am"]
        assert _stub_loggers["lead"] == ["status=hot"]
        assert session_state["pending_end_call"] is True
        assert out == "Great, done!"

    def test_unterminated_trailing_marker_fragment_dropped(self, session_state):
        # LLM cut off mid-marker; the trailing fragment must not be spoken.
        out = voice.extract_control_markers("Okay sure [MEETING_BOOKED: Mon", session_state)
        assert "[" not in out
        assert out == "Okay sure"

    def test_result_is_stripped_of_whitespace(self, session_state):
        out = voice.extract_control_markers("  spaced reply  ", session_state)
        assert out == "spaced reply"


class TestAddTranscript:
    def test_appends_turn_with_metadata(self, session_state):
        voice.add_transcript(session_state, "caller", "hello there", "en-IN")
        assert len(session_state["transcript"]) == 1
        turn = session_state["transcript"][0]
        assert turn["role"] == "caller"
        assert turn["text"] == "hello there"
        assert turn["lang"] == "en-IN"
        assert "time" in turn

    def test_blank_text_is_ignored(self, session_state):
        voice.add_transcript(session_state, "agent", "   ", "en-IN")
        assert session_state["transcript"] == []

    def test_none_text_is_ignored(self, session_state):
        voice.add_transcript(session_state, "agent", None, "en-IN")
        assert session_state["transcript"] == []

    def test_creates_transcript_list_if_absent(self):
        state = {}
        voice.add_transcript(state, "caller", "hi", "en-IN")
        assert state["transcript"][0]["text"] == "hi"
