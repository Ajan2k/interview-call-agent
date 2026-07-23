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
        _db_initialized = True
        logger.info("[POSTGRES] Database tables initialized successfully!")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[POSTGRES] Error initializing tables: {e}")
        if conn:
            conn.close()
        return False

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
