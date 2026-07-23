import os
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional

logger = logging.getLogger("database")

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "1234")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "skyagent")

_conn_cache = None

def get_db_connection():
    passwords_to_try = [POSTGRES_PASSWORD, "postgres", "admin", "root", "123456", "1234"]
    # Remove duplicates while preserving order
    passwords = list(dict.fromkeys(passwords_to_try))

    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            return conn
        except Exception:
            pass

    for pwd in passwords:
        try:
            conn = psycopg2.connect(
                user=POSTGRES_USER,
                password=pwd,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB
            )
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as oe:
            err_msg = str(oe)
            if 'database "' in err_msg and 'does not exist' in err_msg:
                # Database missing — connect to 'postgres' and create 'teleforce_db'
                try:
                    conn_sys = psycopg2.connect(
                        user=POSTGRES_USER,
                        password=pwd,
                        host=POSTGRES_HOST,
                        port=POSTGRES_PORT,
                        dbname="postgres"
                    )
                    conn_sys.autocommit = True
                    with conn_sys.cursor() as cur:
                        cur.execute(f'CREATE DATABASE "{POSTGRES_DB}";')
                    conn_sys.close()

                    conn = psycopg2.connect(
                        user=POSTGRES_USER,
                        password=pwd,
                        host=POSTGRES_HOST,
                        port=POSTGRES_PORT,
                        dbname=POSTGRES_DB
                    )
                    conn.autocommit = True
                    return conn
                except Exception:
                    pass
        except Exception:
            pass

    return None

_db_initialized = False

def init_db():
    global _db_initialized
    if _db_initialized:
        return True

    conn = get_db_connection()
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

            # Calls Table — one row per completed AI call (the call history)
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
            # Add columns to pre-existing calls tables (idempotent)
            cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS callback TEXT;")
            cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS transcript JSONB;")

            # Meetings Table — demos booked by the agent
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

            # Callbacks Table — customers who asked to be called back later
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

        _migrate_jsonl_history(conn)
        _db_initialized = True
        logger.info("[POSTGRES] Database tables initialized successfully!")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[POSTGRES] Error initializing tables: {e}")
        if conn:
            conn.close()
        return False

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_CALLS_JSONL = os.path.join(_BACKEND_DIR, "logs", "calls.jsonl")
_MEETINGS_JSONL = os.path.join(_BACKEND_DIR, "logs", "meetings.jsonl")

import re as _re


def _lead_status(lead: str) -> str:
    m = _re.search(r"status\s*=\s*([A-Za-z_]+)", lead or "")
    return m.group(1).upper() if m else ""


def _migrate_jsonl_history(conn):
    """One-time import of the old calls.jsonl / meetings.jsonl history into
    PostgreSQL so nothing recorded before the DB switch is lost."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM calls;")
            if cur.fetchone()[0] == 0 and os.path.exists(_CALLS_JSONL):
                n = 0
                with open(_CALLS_JSONL, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                            cur.execute("""
                                INSERT INTO calls (id, direction, phone, start_time, end_time,
                                    duration_sec, language, lead, lead_status, meeting, ended_by, recording)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (id) DO NOTHING;
                            """, (r.get("id"), r.get("direction"), r.get("phone", ""), r.get("start"),
                                  r.get("end"), r.get("duration_sec", 0), r.get("language"),
                                  r.get("lead", ""), _lead_status(r.get("lead", "")),
                                  r.get("meeting", ""), r.get("ended_by", ""), r.get("recording")))
                            n += 1
                        except Exception:
                            pass
                if n:
                    logger.info(f"[POSTGRES] Migrated {n} calls from calls.jsonl into DB.")

            cur.execute("SELECT COUNT(*) FROM meetings;")
            if cur.fetchone()[0] == 0 and os.path.exists(_MEETINGS_JSONL):
                n = 0
                with open(_MEETINGS_JSONL, "r", encoding="utf-8") as f:
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


# CRUD Helpers for Calls (call history)
def db_save_call(record: Dict[str, Any]) -> bool:
    conn = get_db_connection()
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
            """, (record.get("id"), record.get("direction"), record.get("phone", ""),
                  record.get("start"), record.get("end"), record.get("duration_sec", 0),
                  record.get("language"), record.get("lead", ""), _lead_status(record.get("lead", "")),
                  record.get("meeting", ""), record.get("callback", ""),
                  record.get("ended_by", ""), record.get("recording"),
                  json.dumps(record.get("transcript", []), ensure_ascii=False)))
        return True
    except Exception as e:
        logger.error(f"db_save_call error: {e}")
        return False
    finally:
        conn.close()


def db_get_calls(date_from: str = "", date_to: str = "", direction: str = "",
                 lead_status: str = "", language: str = "", limit: int = 500) -> Optional[List[Dict[str, Any]]]:
    """Returns None when the DB is unavailable (caller falls back to JSONL)."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        where, params = [], []
        if date_from:
            where.append("start_time >= %s"); params.append(date_from)
        if date_to:
            where.append("start_time <= %s"); params.append(date_to + " 23:59:59")
        if direction:
            where.append("direction = %s"); params.append(direction)
        if lead_status:
            where.append("lead_status = %s"); params.append(lead_status.upper())
        if language:
            where.append("language = %s"); params.append(language)
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
        logger.error(f"db_get_calls error: {e}")
        return None
    finally:
        conn.close()


def db_get_call_transcript(call_id: str) -> Optional[Dict[str, Any]]:
    """Return {found, transcript, phone, direction, start} for one call, or None if DB is down."""
    conn = get_db_connection()
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
        logger.error(f"db_get_call_transcript error: {e}")
        return None
    finally:
        conn.close()


# CRUD Helpers for Meetings
def db_save_meeting(record: Dict[str, Any]) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO meetings (time, call_id, direction, phone, language, details)
                VALUES (%s,%s,%s,%s,%s,%s);
            """, (record.get("time"), record.get("call_id", ""), record.get("direction", ""),
                  record.get("phone", ""), record.get("language", ""), record.get("details", "")))
        return True
    except Exception as e:
        logger.error(f"db_save_meeting error: {e}")
        return False
    finally:
        conn.close()


def db_get_meetings(limit: int = 200) -> Optional[List[Dict[str, Any]]]:
    """Returns None when the DB is unavailable (caller falls back to JSONL)."""
    conn = get_db_connection()
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
        logger.error(f"db_get_meetings error: {e}")
        return None
    finally:
        conn.close()


# CRUD Helpers for Callbacks
def db_save_callback(record: Dict[str, Any]) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO callbacks (time, call_id, direction, phone, language, callback_time)
                VALUES (%s,%s,%s,%s,%s,%s);
            """, (record.get("time"), record.get("call_id", ""), record.get("direction", ""),
                  record.get("phone", ""), record.get("language", ""), record.get("callback_time", "")))
        return True
    except Exception as e:
        logger.error(f"db_save_callback error: {e}")
        return False
    finally:
        conn.close()


def db_get_callbacks(limit: int = 200, include_done: bool = True) -> Optional[List[Dict[str, Any]]]:
    """Returns None when the DB is unavailable (caller falls back to JSONL)."""
    conn = get_db_connection()
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
        logger.error(f"db_get_callbacks error: {e}")
        return None
    finally:
        conn.close()


def db_mark_callback_done(callback_id: int, done: bool = True) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE callbacks SET done = %s WHERE id = %s;", (done, callback_id))
        return True
    except Exception as e:
        logger.error(f"db_mark_callback_done error: {e}")
        return False
    finally:
        conn.close()


def db_delete_callback(callback_id: int) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM callbacks WHERE id = %s;", (callback_id,))
        return True
    except Exception as e:
        logger.error(f"db_delete_callback error: {e}")
        return False
    finally:
        conn.close()


# CRUD Helpers for Contacts
def db_get_contacts() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name, phone, status, last_called as \"lastCalled\", notes, is_incoming as \"isIncoming\" FROM contacts ORDER BY id DESC;")
            return cur.fetchall()
    except Exception as e:
        logger.error(f"db_get_contacts error: {e}")
        return []
    finally:
        conn.close()

def db_save_contact(contact: Dict[str, Any]):
    conn = get_db_connection()
    if not conn: return
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
                str(contact.get("id")),
                contact.get("name", "Unknown"),
                contact.get("phone", ""),
                contact.get("status", "Pending"),
                contact.get("lastCalled", "Never"),
                contact.get("notes", ""),
                contact.get("isIncoming", False)
            ))
    except Exception as e:
        logger.error(f"db_save_contact error: {e}")
    finally:
        conn.close()

def db_delete_contact(contact_id: str):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s;", (contact_id,))
    except Exception as e:
        logger.error(f"db_delete_contact error: {e}")
    finally:
        conn.close()

# CRUD Helpers for Campaigns
def db_get_campaigns() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name, status, contacts_count as \"contactsCount\", date FROM campaigns ORDER BY id DESC;")
            return cur.fetchall()
    except Exception as e:
        logger.error(f"db_get_campaigns error: {e}")
        return []
    finally:
        conn.close()

# CRUD Helpers for Voice Config
def db_get_voice_config() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT speech_mode as \"speechMode\", language_focus as \"languageFocus\", prompt_template as \"promptTemplate\" FROM voice_config WHERE id = 1;")
            return cur.fetchone()
    except Exception as e:
        logger.error(f"db_get_voice_config error: {e}")
        return None
    finally:
        conn.close()

def db_save_voice_config(config: Dict[str, Any]):
    conn = get_db_connection()
    if not conn: return
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
                config.get("promptTemplate", "")
            ))
    except Exception as e:
        logger.error(f"db_save_voice_config error: {e}")
    finally:
        conn.close()

# Initialize tables on import
init_db()
