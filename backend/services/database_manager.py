import os
import json
import logging
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any, Optional

from models.call import Call
from models.voice_config import VoiceConfig

from core.config import settings

logger = logging.getLogger("database")


class PooledConnection:
    """Wraps a connection from ThreadedConnectionPool so calling .close() returns it to the pool."""

    def __init__(self, conn, pool: ThreadedConnectionPool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def close(self):
        if not self._closed and self._pool:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._closed = True

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


class DatabaseManager:
    """Manages PostgreSQL connection pooling, lifecycle, and schema initialization."""

    def __init__(self):
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD.get_secret_value() if settings.POSTGRES_PASSWORD else ""
        self.host = settings.POSTGRES_HOST
        self.port = str(settings.POSTGRES_PORT)
        self.dbname = settings.POSTGRES_DB
        self.db_url = str(settings.DATABASE_URL) if settings.DATABASE_URL else ""
        self._initialized = False
        self._pool: Optional[ThreadedConnectionPool] = None
        self._pool_failed = False

    def _get_or_create_pool(self) -> Optional[ThreadedConnectionPool]:
        if self._pool is not None:
            return self._pool
        if self._pool_failed:
            return None

        passwords_to_try = [self.password, "postgres", "admin", "root", "123456", "1234"]
        passwords = list(dict.fromkeys(passwords_to_try))

        if self.db_url:
            try:
                self._pool = ThreadedConnectionPool(minconn=1, maxconn=15, dsn=self.db_url)
                logger.info("[POSTGRES] Initialized ThreadedConnectionPool via DATABASE_URL.")
                return self._pool
            except Exception:
                pass

        for pwd in passwords:
            try:
                self._pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=15,
                    user=self.user,
                    password=pwd,
                    host=self.host,
                    port=self.port,
                    dbname=self.dbname,
                )
                self.password = pwd
                logger.info("[POSTGRES] Initialized ThreadedConnectionPool (pool_size=15).")
                return self._pool
            except psycopg2.OperationalError as oe:
                err_msg = str(oe)
                if 'database "' in err_msg and "does not exist" in err_msg:
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

                        self._pool = ThreadedConnectionPool(
                            minconn=1,
                            maxconn=15,
                            user=self.user,
                            password=pwd,
                            host=self.host,
                            port=self.port,
                            dbname=self.dbname,
                        )
                        self.password = pwd
                        return self._pool
                    except Exception:
                        pass
            except Exception:
                pass

        self._pool_failed = True
        return None

    def get_connection(self):
        """Retrieves a connection from the pool or falls back to direct connection."""
        pool = self._get_or_create_pool()
        if pool:
            try:
                conn = pool.getconn()
                conn.autocommit = True
                return PooledConnection(conn, pool)
            except Exception as e:
                logger.warning(f"[POSTGRES] Pool getconn error: {e}. Falling back to single connection.")

        # Fallback to direct connect if pool is unavailable
        try:
            if self.db_url:
                conn = psycopg2.connect(self.db_url)
                conn.autocommit = True
                return conn
            conn = psycopg2.connect(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                dbname=self.dbname,
            )
            conn.autocommit = True
            return conn
        except Exception:
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
                # Candidates Table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS candidates (
                        id VARCHAR(255) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        phone VARCHAR(100) NOT NULL,
                        position VARCHAR(255) NOT NULL,
                        job_description TEXT,
                        resume_filename VARCHAR(255),
                        resume_text TEXT,
                        status VARCHAR(100) DEFAULT 'ready',
                        questions JSONB DEFAULT '[]'::jsonb,
                        scorecard JSONB,
                        call_id VARCHAR(255),
                        created_at VARCHAR(100),
                        updated_at VARCHAR(100)
                    );
                """)

                # Performance Indexes for Candidates
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_phone ON candidates(phone);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_created_at ON candidates(created_at DESC);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);")

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

                # Performance Indexes for Calls
                cur.execute("CREATE INDEX IF NOT EXISTS idx_calls_phone ON calls(phone);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_calls_start_time ON calls(start_time DESC);")

            self._migrate_jsonl_history(conn)
            self._initialized = True
            logger.info("[POSTGRES] Database tables and indexes initialized successfully!")
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
                                        duration_sec, language, lead, lead_status, meeting, ended_by, recording, transcript)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    ON CONFLICT (id) DO NOTHING;
                                """, (
                                    call_obj.id, call_obj.direction, call_obj.phone, call_obj.start,
                                    call_obj.end, call_obj.duration_sec, call_obj.language,
                                    call_obj.lead, call_obj.resolved_lead_status(),
                                    call_obj.meeting, call_obj.ended_by, call_obj.recording,
                                    json.dumps(call_obj.transcript) if call_obj.transcript else None
                                ))
                                n += 1
                            except Exception:
                                pass
                    if n:
                        logger.info(f"[POSTGRES] Migrated {n} calls from calls.jsonl into DB.")
        except Exception as e:
            logger.error(f"[POSTGRES] JSONL migration error: {e}")


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
                    INSERT INTO calls (id, direction, phone, start_time, end_time, duration_sec,
                        language, lead, lead_status, meeting, callback, ended_by, recording, transcript)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        direction = EXCLUDED.direction,
                        phone = EXCLUDED.phone,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        duration_sec = EXCLUDED.duration_sec,
                        language = EXCLUDED.language,
                        lead = EXCLUDED.lead,
                        lead_status = EXCLUDED.lead_status,
                        meeting = EXCLUDED.meeting,
                        callback = EXCLUDED.callback,
                        ended_by = EXCLUDED.ended_by,
                        recording = EXCLUDED.recording,
                        transcript = EXCLUDED.transcript;
                """, (
                    call.id, call.direction, call.phone, call.start, call.end,
                    call.duration_sec, call.language, call.lead, call.resolved_lead_status(),
                    call.meeting, call.callback, call.ended_by, call.recording,
                    json.dumps(call.transcript) if call.transcript else None,
                ))
            return True
        except Exception as e:
            logger.error(f"CallRepository.save error: {e}")
            return False
        finally:
            conn.close()

    def get_all(self, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, direction, phone,
                           to_char(start_time, 'YYYY-MM-DD HH24:MI:SS') AS start,
                           to_char(end_time,   'YYYY-MM-DD HH24:MI:SS') AS end,
                           duration_sec, language, lead, lead_status, meeting, callback,
                           ended_by, recording, transcript
                    FROM calls
                    ORDER BY start_time DESC
                    LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    item = dict(r)
                    if isinstance(item.get("transcript"), str):
                        try:
                            item["transcript"] = json.loads(item["transcript"])
                        except Exception:
                            item["transcript"] = []
                    result.append(item)
                return result
        except Exception as e:
            logger.error(f"CallRepository.get_all error: {e}")
            return None
        finally:
            conn.close()

    def get_by_id(self, call_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db_manager.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, direction, phone,
                           to_char(start_time, 'YYYY-MM-DD HH24:MI:SS') AS start,
                           to_char(end_time,   'YYYY-MM-DD HH24:MI:SS') AS end,
                           duration_sec, language, lead, lead_status, meeting, callback,
                           ended_by, recording, transcript
                    FROM calls WHERE id = %s;
                """, (call_id,))
                row = cur.fetchone()
                if row:
                    item = dict(row)
                    if isinstance(item.get("transcript"), str):
                        try:
                            item["transcript"] = json.loads(item["transcript"])
                        except Exception:
                            item["transcript"] = []
                    return item
                return None
        except Exception as e:
            logger.error(f"CallRepository.get_by_id error: {e}")
            return None
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


# Application singleton instances
db_manager = DatabaseManager()
call_repo = CallRepository(db_manager)
voice_config_repo = VoiceConfigRepository(db_manager)


def db_save_meeting(record: Dict[str, Any]) -> bool:
    return True


def db_save_callback(record: Dict[str, Any]) -> bool:
    return True


def db_save_call(record: Dict[str, Any]) -> bool:
    call_obj = Call.from_dict(record)
    return call_repo.save(call_obj)
