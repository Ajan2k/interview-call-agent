import os
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional

from models.contact import Contact
from models.campaign import Campaign
from models.call import Call
from models.meeting import Meeting
from models.callback import Callback
from models.voice_config import VoiceConfig

from core.config import settings

logger = logging.getLogger("database")


class DatabaseManager:
    """Manages PostgreSQL connection lifecycle, schema initialization, and migration."""

    def __init__(self):
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD.get_secret_value() if settings.POSTGRES_PASSWORD else ""
        self.host = settings.POSTGRES_HOST
        self.port = str(settings.POSTGRES_PORT)
        self.dbname = settings.POSTGRES_DB
        self.db_url = str(settings.DATABASE_URL) if settings.DATABASE_URL else ""
        self._initialized = False

    def get_connection(self):
        """Attempts connection using DATABASE_URL or configured host/credentials."""
        passwords_to_try = [self.password, "postgres", "admin", "root", "123456", "1234"]
        passwords = list(dict.fromkeys(passwords_to_try))

        if self.db_url:
            try:
                conn = psycopg2.connect(self.db_url)
                conn.autocommit = True
                return conn
            except Exception:
                pass

        for pwd in passwords:
            try:
                conn = psycopg2.connect(
                    user=self.user,
                    password=pwd,
                    host=self.host,
                    port=self.port,
                    dbname=self.dbname,
                )
                conn.autocommit = True
                return conn
            except psycopg2.OperationalError as oe:
                err_msg = str(oe)
                if 'database "' in err_msg and "does not exist" in err_msg:
                    # Database missing — connect to default 'postgres' db and create the target DB
                    try:
                        conn_sys = psycopg2.connect(
                            user=self.user,
                            password=pwd,
                            host=self.host,
                            port=self.port,
                            dbname="postgres",
                        )
                        conn_sys.autocommit = True
                        with conn_sys.cursor() as cur:
                            cur.execute(f'CREATE DATABASE "{self.dbname}";')
                        conn_sys.close()

                        conn = psycopg2.connect(
                            user=self.user,
                            password=pwd,
                            host=self.host,
                            port=self.port,
                            dbname=self.dbname,
                        )
                        conn.autocommit = True
                        return conn
                    except Exception:
                        pass
            except Exception:
                pass

        return None

    def init_db(self) -> bool:
        if self._initialized:
            return True

        conn = self.get_connection()
        if not conn:
            logger.warning("[POSTGRES] Running in fallback mode (PostgreSQL unavailable).")
            return False

        try:
            with conn.cursor() as cur:
                # Contacts Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        id VARCHAR(255) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        phone VARCHAR(255) NOT NULL,
                        status VARCHAR(100) DEFAULT 'Pending',
                        last_called VARCHAR(100) DEFAULT 'Never',
                        notes TEXT,
                        is_incoming BOOLEAN DEFAULT FALSE
                    );
                """)

                # Campaigns Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS campaigns (
                        id VARCHAR(255) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        status VARCHAR(100) DEFAULT 'Active',
                        contacts_count INT DEFAULT 0,
                        date VARCHAR(100) DEFAULT 'Today'
                    );
                """)

                # Call Logs Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS call_logs (
                        id VARCHAR(255) PRIMARY KEY,
                        contact_name VARCHAR(255),
                        phone VARCHAR(100),
                        campaign_name VARCHAR(255),
                        duration INT DEFAULT 0,
                        outcome VARCHAR(100),
                        sentiment VARCHAR(100),
                        time VARCHAR(100),
                        notes TEXT,
                        transcript JSONB
                    );
                """)

                # Voice Config Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS voice_config (
                        id INT PRIMARY KEY DEFAULT 1,
                        speech_mode VARCHAR(255),
                        language_focus VARCHAR(255),
                        prompt_template TEXT
                    );
                """)

                # Calls Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS calls (
                        id VARCHAR(255) PRIMARY KEY,
                        direction VARCHAR(20),
                        phone VARCHAR(100),
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        duration_sec INT DEFAULT 0,
                        language VARCHAR(20),
                        lead TEXT,
                        lead_status VARCHAR(30),
                        meeting TEXT,
                        callback TEXT,
                        ended_by VARCHAR(20),
                        recording VARCHAR(255),
                        transcript JSONB
                    );
                """)
                cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS callback TEXT;")
                cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS transcript JSONB;")

                # Meetings Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS meetings (
                        id SERIAL PRIMARY KEY,
                        time TIMESTAMP,
                        call_id VARCHAR(255),
                        direction VARCHAR(20),
                        phone VARCHAR(100),
                        language VARCHAR(20),
                        details TEXT
                    );
                """)

                # Callbacks Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS callbacks (
                        id SERIAL PRIMARY KEY,
                        time TIMESTAMP,
                        call_id VARCHAR(255),
                        direction VARCHAR(20),
                        phone VARCHAR(100),
                        language VARCHAR(20),
                        callback_time TEXT,
                        done BOOLEAN DEFAULT FALSE
                    );
                """)

            self._migrate_jsonl_history(conn)
            self._initialized = True
            logger.info("[POSTGRES] Database tables initialized successfully!")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[POSTGRES] Error initializing tables: {e}")
            if conn:
                conn.close()
            return False

    def _migrate_jsonl_history(self, conn):
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        calls_jsonl = os.path.join(backend_dir, "logs", "calls.jsonl")
        meetings_jsonl = os.path.join(backend_dir, "logs", "meetings.jsonl")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM calls;")
                if cur.fetchone()[0] == 0 and os.path.exists(calls_jsonl):
                    n = 0
                    with open(calls_jsonl, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                r = json.loads(line)
                                call_obj = Call.from_dict(r)
                                cur.execute("""
                                    INSERT INTO calls (id, direction, phone, start_time, end_time,
                                        duration_sec, language, lead, lead_status, meeting, ended_by, recording)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    ON CONFLICT (id) DO NOTHING;
                                """, (
                                    call_obj.id, call_obj.direction, call_obj.phone, call_obj.start,
                                    call_obj.end, call_obj.duration_sec, call_obj.language,
                                    call_obj.lead, call_obj.resolved_lead_status(),
                                    call_obj.meeting, call_obj.ended_by, call_obj.recording
                                ))
                                n += 1
                            except Exception:
                                pass
                    if n:
                        logger.info(f"[POSTGRES] Migrated {n} calls from calls.jsonl into DB.")

                cur.execute("SELECT COUNT(*) FROM meetings;")
                if cur.fetchone()[0] == 0 and os.path.exists(meetings_jsonl):
                    n = 0
                    with open(meetings_jsonl, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                r = json.loads(line)
                                cur.execute("""
                                    INSERT INTO meetings (time, call_id, direction, phone, language, details)
                                    VALUES (%s,%s,%s,%s,%s,%s);
                                """, (r.get("time"), r.get("call_id", ""), r.get("direction", ""),
                                      r.get("phone", ""), r.get("language", ""), r.get("details", "")))
                                n += 1
                            except Exception:
                                pass
                    if n:
                        logger.info(f"[POSTGRES] Migrated {n} meetings from meetings.jsonl into DB.")
        except Exception as e:
            logger.error(f"[POSTGRES] JSONL migration error: {e}")


class ContactRepository:
    """Encapsulates Contact database operations."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_all(self) -> List[Contact]:
        conn = self.db_manager.get_connection()
        if not conn:
            return []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, name, phone, status,
                           last_called AS "lastCalled",
                           notes,
                           is_incoming AS "isIncoming"
                    FROM contacts ORDER BY id DESC;
                """)
                rows = cur.fetchall()
                return [Contact.from_dict(dict(r)) for r in rows]
        except Exception as e:
            logger.error(f"ContactRepository.get_all error: {e}")
            return []
        finally:
            conn.close()

    def save(self, contact: Contact) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO contacts (id, name, phone, status, last_called, notes, is_incoming)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        phone = EXCLUDED.phone,
                        status = EXCLUDED.status,
                        last_called = EXCLUDED.last_called,
                        notes = EXCLUDED.notes,
                        is_incoming = EXCLUDED.is_incoming;
                """, (
                    contact.id, contact.name, contact.phone, contact.status,
                    contact.last_called, contact.notes, contact.is_incoming,
                ))
            return True
        except Exception as e:
            logger.error(f"ContactRepository.save error: {e}")
            return False
        finally:
            conn.close()

    def delete(self, contact_id: str) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM contacts WHERE id = %s;", (contact_id,))
            return True
        except Exception as e:
            logger.error(f"ContactRepository.delete error: {e}")
            return False
        finally:
            conn.close()


class CallRepository:
    """Encapsulates Call records and transcript retrieval."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, call: Call) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calls (id, direction, phone, start_time, end_time,
                        duration_sec, language, lead, lead_status, meeting, callback, ended_by, recording, transcript)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                        end_time = EXCLUDED.end_time,
                        duration_sec = EXCLUDED.duration_sec,
                        lead = EXCLUDED.lead,
                        lead_status = EXCLUDED.lead_status,
                        meeting = EXCLUDED.meeting,
                        callback = EXCLUDED.callback,
                        recording = EXCLUDED.recording,
                        transcript = EXCLUDED.transcript;
                """, (
                    call.id, call.direction, call.phone, call.start, call.end,
                    call.duration_sec, call.language, call.lead, call.resolved_lead_status(),
                    call.meeting, call.callback, call.ended_by, call.recording,
                    json.dumps(call.transcript or [], ensure_ascii=False),
                ))
            return True
        except Exception as e:
            logger.error(f"CallRepository.save error: {e}")
            return False
        finally:
            conn.close()

    def get_all(
        self,
        date_from: str = "",
        date_to: str = "",
        direction: str = "",
        lead_status: str = "",
        language: str = "",
        limit: int = 500,
    ) -> Optional[List[Dict[str, Any]]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            where, params = [], []
            if date_from:
                where.append("start_time >= %s")
                params.append(date_from)
            if date_to:
                where.append("start_time <= %s")
                params.append(date_to + " 23:59:59")
            if direction:
                where.append("direction = %s")
                params.append(direction)
            if lead_status:
                where.append("lead_status = %s")
                params.append(lead_status.upper())
            if language:
                where.append("language = %s")
                params.append(language)
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT id, direction, phone,
                           to_char(start_time, 'YYYY-MM-DD HH24:MI:SS') AS start,
                           to_char(end_time, 'YYYY-MM-DD HH24:MI:SS') AS "end",
                           duration_sec, language, lead, lead_status, meeting, callback, ended_by, recording
                    FROM calls {where_sql}
                    ORDER BY start_time DESC
                    LIMIT %s;
                """, params + [limit])
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"CallRepository.get_all error: {e}")
            return None
        finally:
            conn.close()

    def get_transcript(self, call_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT phone, direction,
                           to_char(start_time, 'YYYY-MM-DD HH24:MI:SS') AS start,
                           transcript
                    FROM calls WHERE id = %s;
                """, (call_id,))
                row = cur.fetchone()
                if not row:
                    return {"found": False, "transcript": []}
                return {
                    "found": True,
                    "phone": row.get("phone", ""),
                    "direction": row.get("direction", ""),
                    "start": row.get("start", ""),
                    "transcript": row.get("transcript") or [],
                }
        except Exception as e:
            logger.error(f"CallRepository.get_transcript error: {e}")
            return None
        finally:
            conn.close()


class MeetingRepository:
    """Encapsulates Demo Meeting booking queries."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, meeting: Meeting) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO meetings (time, call_id, direction, phone, language, details)
                    VALUES (%s,%s,%s,%s,%s,%s);
                """, (meeting.time, meeting.call_id, meeting.direction, meeting.phone, meeting.language, meeting.details))
            return True
        except Exception as e:
            logger.error(f"MeetingRepository.save error: {e}")
            return False
        finally:
            conn.close()

    def get_all(self, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT to_char(time, 'YYYY-MM-DD HH24:MI:SS') AS time,
                           call_id, direction, phone, language, details
                    FROM meetings
                    ORDER BY time DESC
                    LIMIT %s;
                """, (limit,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"MeetingRepository.get_all error: {e}")
            return None
        finally:
            conn.close()


class CallbackRepository:
    """Encapsulates scheduled customer callback entries."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, callback: Callback) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO callbacks (time, call_id, direction, phone, language, callback_time)
                    VALUES (%s,%s,%s,%s,%s,%s);
                """, (callback.time, callback.call_id, callback.direction, callback.phone, callback.language, callback.callback_time))
            return True
        except Exception as e:
            logger.error(f"CallbackRepository.save error: {e}")
            return False
        finally:
            conn.close()

    def get_all(self, limit: int = 200, include_done: bool = True) -> Optional[List[Dict[str, Any]]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            where = "" if include_done else "WHERE done = FALSE"
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT id, to_char(time, 'YYYY-MM-DD HH24:MI:SS') AS time,
                           call_id, direction, phone, language, callback_time, done
                    FROM callbacks
                    {where}
                    ORDER BY done ASC, time DESC
                    LIMIT %s;
                """, (limit,))
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"CallbackRepository.get_all error: {e}")
            return None
        finally:
            conn.close()

    def mark_done(self, callback_id: int, done: bool = True) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE callbacks SET done = %s WHERE id = %s;", (done, callback_id))
            return True
        except Exception as e:
            logger.error(f"CallbackRepository.mark_done error: {e}")
            return False
        finally:
            conn.close()

    def delete(self, callback_id: int) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM callbacks WHERE id = %s;", (callback_id,))
            return True
        except Exception as e:
            logger.error(f"CallbackRepository.delete error: {e}")
            return False
        finally:
            conn.close()


class VoiceConfigRepository:
    """Encapsulates voice and AI prompt configuration."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get(self) -> Optional[Dict[str, Any]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT speech_mode, language_focus, prompt_template FROM voice_config WHERE id = 1;")
                row = cur.fetchone()
                if row:
                    return {
                        "speechMode": row.get("speech_mode", ""),
                        "languageFocus": row.get("language_focus", ""),
                        "promptTemplate": row.get("prompt_template", ""),
                    }
                return None
        except Exception as e:
            logger.error(f"VoiceConfigRepository.get error: {e}")
            return None
        finally:
            conn.close()

    def save(self, config: Dict[str, Any]) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO voice_config (id, speech_mode, language_focus, prompt_template)
                    VALUES (1, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        speech_mode = EXCLUDED.speech_mode,
                        language_focus = EXCLUDED.language_focus,
                        prompt_template = EXCLUDED.prompt_template;
                """, (
                    config.get("speechMode", ""),
                    config.get("languageFocus", ""),
                    config.get("promptTemplate", ""),
                ))
            return True
        except Exception as e:
            logger.error(f"VoiceConfigRepository.save error: {e}")
            return False
        finally:
            conn.close()


class CampaignRepository:
    """Encapsulates marketing/outbound campaign queries."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_all(self) -> List[Dict[str, Any]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return []
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, status, contacts_count, date FROM campaigns ORDER BY id DESC;")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"CampaignRepository.get_all error: {e}")
            return []
        finally:
            conn.close()

    def save(self, campaign: Campaign) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO campaigns (id, name, status, contacts_count, date)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        contacts_count = EXCLUDED.contacts_count,
                        date = EXCLUDED.date;
                """, (campaign.id, campaign.name, campaign.status, campaign.contacts_count, campaign.date))
            return True
        except Exception as e:
            logger.error(f"CampaignRepository.save error: {e}")
            return False
        finally:
            conn.close()


# Application singleton instances
db_manager = DatabaseManager()
contact_repo = ContactRepository(db_manager)
call_repo = CallRepository(db_manager)
meeting_repo = MeetingRepository(db_manager)
callback_repo = CallbackRepository(db_manager)
voice_config_repo = VoiceConfigRepository(db_manager)
campaign_repo = CampaignRepository(db_manager)


def db_save_meeting(record: Dict[str, Any]) -> bool:
    meeting_obj = Meeting.from_dict(record)
    return meeting_repo.save(meeting_obj)


def db_save_callback(record: Dict[str, Any]) -> bool:
    callback_obj = Callback.from_dict(record)
    return callback_repo.save(callback_obj)


def db_save_call(record: Dict[str, Any]) -> bool:
    call_obj = Call.from_dict(record)
    return call_repo.save(call_obj)

