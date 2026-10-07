import re
import os
import json
import time
import uuid
import logging
import tempfile
import threading
import contextlib
from typing import List, Optional, Dict, Any, Callable
from psycopg2.extras import RealDictCursor
from models.candidate import Candidate, Question
from services.database_manager import DatabaseManager, db_manager
from core.config import settings

logger = logging.getLogger("services.candidate_repo")


def normalize_phone_e164(phone: Optional[str]) -> str:
    """Normalizes a phone number to standard E.164 (+<country><national>) format where possible.
    Leaves non-standard / short numbers as-is if they cannot be formatted.
    """
    if not phone or not isinstance(phone, str):
        return ""
    clean = phone.strip()
    digits = re.sub(r"\D", "", clean)
    if len(digits) < 7:
        return clean
    if clean.startswith("00") and len(digits) > 2:
        return f"+{digits[2:]}"
    if clean.startswith("+"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return digits


def get_phone_lookup_variants(phone: Optional[str]) -> List[str]:
    """Generates exact canonical string variants for phone matching.
    
    Guarantees:
    - Rejects empty, whitespace-only, or short (<7 digits) inputs (returns empty list).
    - Generates exact E.164 (+<digits>) and plain digit variants without wildcards.
    - Enables PostgreSQL to perform exact B-tree index scans (phone = ANY(%s)).
    - Eliminates false positive substring matching.
    """
    if not phone or not isinstance(phone, str):
        return []

    clean = phone.strip()
    if not clean:
        return []

    digits = re.sub(r"\D", "", clean)
    if len(digits) < 7:
        return []

    variants = set()
    variants.add(clean)

    if clean.startswith("+"):
        variants.add(f"+{digits}")
        variants.add(digits)
        if digits.startswith("1") and len(digits) == 11:
            variants.add(digits[1:])
        elif digits.startswith("91") and len(digits) == 12:
            variants.add(digits[2:])
    elif clean.startswith("00"):
        d = digits[2:]
        variants.add(f"+{d}")
        variants.add(d)
    else:
        variants.add(digits)
        variants.add(f"+{digits}")
        if len(digits) == 10:
            variants.add(f"+1{digits}")
            variants.add(f"+91{digits}")
        elif len(digits) == 11 and digits.startswith("1"):
            variants.add(digits[1:])
            variants.add(f"+{digits}")
        elif len(digits) == 12 and digits.startswith("91"):
            variants.add(digits[2:])
            variants.add(f"+{digits}")

    return list(variants)



class CrossProcessFileLock:
    """Inter-process and inter-thread file lock protecting fallback storage operations."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._thread_lock = threading.RLock()
        self._file_handle = None

    @contextlib.contextmanager
    def acquire(self):
        with self._thread_lock:
            try:
                os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
                self._file_handle = open(self.lock_path, "a+")
                if os.name == "nt":
                    import msvcrt
                    self._file_handle.seek(0)
                    if os.path.getsize(self.lock_path) == 0:
                        self._file_handle.write("0")
                        self._file_handle.flush()
                    self._file_handle.seek(0)
                    msvcrt.locking(self._file_handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._file_handle.fileno(), fcntl.LOCK_EX)
            except Exception as e:
                logger.debug(f"FileLock acquire notice for {self.lock_path}: {e}")

            try:
                yield
            finally:
                if self._file_handle:
                    try:
                        if os.name == "nt":
                            import msvcrt
                            self._file_handle.seek(0)
                            msvcrt.locking(self._file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(self._file_handle.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                    try:
                        self._file_handle.close()
                    except Exception:
                        pass
                    self._file_handle = None


class CandidateRepository:
    """Manages Candidate persistence with PostgreSQL as primary and resilient JSON fallback.
    
    Provides:
    - ACID PostgreSQL persistence with normalized candidate_responses joins.
    - Concurrency-protected JSON fallback storage (inter-process file lock + atomic writes).
    - Status visibility (storage mode, connection state, pending sync count, last write store).
    - Automatic and manual replay/synchronization of offline fallback records into PostgreSQL.
    - Uniform search, filter, and pagination handling across both database and fallback.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.fallback_file = str(settings.LOGS_DIR / "candidates.json")
        self.last_write_storage: str = "postgres"
        self.last_sync_time: Optional[str] = None
        self.last_error: Optional[str] = None
        self._locks: Dict[str, CrossProcessFileLock] = {}
        self._ensure_table()

    def _get_lock(self) -> CrossProcessFileLock:
        lock_path = f"{self.fallback_file}.lock"
        if lock_path not in self._locks:
            self._locks[lock_path] = CrossProcessFileLock(lock_path)
        return self._locks[lock_path]

    def _load_fallback_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.fallback_file):
            return {}
        try:
            with open(self.fallback_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            logger.warning(f"Error loading fallback file {self.fallback_file}: {e}")
            return {}

    def _save_fallback_unlocked(self, data: Dict[str, Dict[str, Any]]) -> None:
        dirname = os.path.dirname(self.fallback_file)
        os.makedirs(dirname, exist_ok=True)
        tf_name = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False, encoding="utf-8") as tf:
                tf_name = tf.name
                json.dump(data, tf, indent=2, ensure_ascii=False)
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(tf_name, self.fallback_file)
        except Exception as e:
            if tf_name and os.path.exists(tf_name):
                try:
                    os.remove(tf_name)
                except Exception:
                    pass
            logger.error(f"Error saving fallback file {self.fallback_file}: {e}")
            raise

    def _load_fallback(self) -> Dict[str, Dict[str, Any]]:
        lock = self._get_lock()
        with lock.acquire():
            return self._load_fallback_unlocked()

    def _save_fallback(self, data: Dict[str, Dict[str, Any]]) -> None:
        lock = self._get_lock()
        with lock.acquire():
            self._save_fallback_unlocked(data)

    def _atomic_update_fallback(self, mutator_fn: Callable[[Dict[str, Dict[str, Any]]], Any]) -> Any:
        """Executes a thread-safe and process-safe read-modify-write on fallback storage."""
        lock = self._get_lock()
        with lock.acquire():
            data = self._load_fallback_unlocked()
            result = mutator_fn(data)
            self._save_fallback_unlocked(data)
            return result

    def _delete_from_fallback(self, candidate_id: str) -> bool:
        """Removes a candidate from the fallback store if present."""
        def _mutator(data: Dict[str, Dict[str, Any]]) -> bool:
            if candidate_id in data:
                del data[candidate_id]
                return True
            return False
        return bool(self._atomic_update_fallback(_mutator))

    def is_db_connected(self) -> bool:
        """Checks whether PostgreSQL is currently reachable."""
        conn = self.db_manager.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def get_pending_sync_count(self) -> int:
        """Returns the number of candidates in fallback pending sync to PostgreSQL."""
        data = self._load_fallback()
        return sum(1 for c in data.values() if isinstance(c, dict) and c.get("_pending_sync", False))

    @property
    def is_fallback_active(self) -> bool:
        return not self.is_db_connected()

    @property
    def storage_mode(self) -> str:
        """Current operational mode: 'postgres', 'recovering', or 'fallback'."""
        db_ok = self.is_db_connected()
        if not db_ok:
            return "fallback"
        if self.get_pending_sync_count() > 0:
            return "recovering"
        return "postgres"

    def get_storage_status(self) -> Dict[str, Any]:
        """Provides full transparency into whether storage is running against PostgreSQL or fallback."""
        db_ok = self.is_db_connected()
        pending = self.get_pending_sync_count()
        mode = "postgres" if db_ok else "fallback"
        if db_ok and pending > 0:
            mode = "recovering"

        fallback_count = len(self._load_fallback())
        return {
            "mode": mode,
            "is_db_connected": db_ok,
            "fallback_file": self.fallback_file,
            "fallback_records_count": fallback_count,
            "pending_sync_count": pending,
            "last_write_storage": self.last_write_storage,
            "last_sync_time": self.last_sync_time,
            "last_error": self.last_error,
        }

    def _ensure_table(self):
        conn = self.db_manager.get_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
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
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_phone ON candidates(phone);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_created_at ON candidates(created_at DESC);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);")

                # Candidate Responses table for tracking each question response by candidate_id
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS candidate_responses (
                        id VARCHAR(255) PRIMARY KEY,
                        candidate_id VARCHAR(255) NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                        question_id VARCHAR(255) NOT NULL,
                        category VARCHAR(50) DEFAULT 'technical',
                        question_text TEXT NOT NULL,
                        competency VARCHAR(255) DEFAULT '',
                        order_num INT DEFAULT 1,
                        completed BOOLEAN DEFAULT FALSE,
                        response_text TEXT,
                        score INT,
                        feedback TEXT,
                        created_at VARCHAR(100),
                        updated_at VARCHAR(100),
                        CONSTRAINT uq_candidate_responses_cand_qid UNIQUE (candidate_id, question_id)
                    );
                """)
                cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'uq_candidate_responses_cand_qid'
                        ) THEN
                            ALTER TABLE candidate_responses ADD CONSTRAINT uq_candidate_responses_cand_qid UNIQUE (candidate_id, question_id);
                        END IF;
                    END $$;
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidate_responses_cand_id ON candidate_responses(candidate_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidate_responses_qid ON candidate_responses(question_id);")

            # Try to auto-sync any pending fallback candidates when connection is established
            self._auto_sync_pending(conn)
        except Exception as e:
            logger.warning(f"Could not create candidates table or indexes: {e}")
        finally:
            conn.close()

    def _save_to_postgres(self, candidate: Candidate, conn) -> None:
        """Persists a candidate and normalized responses in PostgreSQL within an atomic transaction."""
        was_autocommit = getattr(conn, "autocommit", True)
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                # 1. Upsert candidate row (and synchronize JSONB representation in same transaction)
                cur.execute("""
                    INSERT INTO candidates (
                        id, name, phone, position, job_description,
                        resume_filename, resume_text, status,
                        questions, scorecard, call_id, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        phone = EXCLUDED.phone,
                        position = EXCLUDED.position,
                        job_description = EXCLUDED.job_description,
                        resume_filename = EXCLUDED.resume_filename,
                        resume_text = EXCLUDED.resume_text,
                        status = EXCLUDED.status,
                        questions = EXCLUDED.questions,
                        scorecard = EXCLUDED.scorecard,
                        call_id = EXCLUDED.call_id,
                        updated_at = EXCLUDED.updated_at;
                """, (
                    candidate.id,
                    candidate.name,
                    candidate.phone,
                    candidate.position,
                    candidate.job_description,
                    candidate.resume_filename,
                    candidate.resume_text,
                    candidate.status,
                    json.dumps([q.to_dict() for q in candidate.questions]),
                    json.dumps(candidate.scorecard.to_dict()) if candidate.scorecard else None,
                    candidate.call_id,
                    candidate.created_at,
                    candidate.updated_at,
                ))

                # 2. Prune rows from candidate_responses that were deleted from candidate.questions
                current_q_ids = [q.id for q in candidate.questions if getattr(q, "id", None)]
                if current_q_ids:
                    cur.execute(
                        "DELETE FROM candidate_responses WHERE candidate_id = %s AND NOT (question_id = ANY(%s));",
                        (candidate.id, current_q_ids),
                    )
                else:
                    cur.execute(
                        "DELETE FROM candidate_responses WHERE candidate_id = %s;",
                        (candidate.id,),
                    )

                # 3. Upsert current questions into candidate_responses using UNIQUE (candidate_id, question_id)
                for q in candidate.questions:
                    resp_id = f"resp_{uuid.uuid4().hex[:12]}"
                    cur.execute("""
                        INSERT INTO candidate_responses (
                            id, candidate_id, question_id, category, question_text,
                            competency, order_num, completed, response_text, score, feedback,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (candidate_id, question_id) DO UPDATE SET
                            category = EXCLUDED.category,
                            question_text = EXCLUDED.question_text,
                            competency = EXCLUDED.competency,
                            order_num = EXCLUDED.order_num,
                            completed = EXCLUDED.completed,
                            response_text = EXCLUDED.response_text,
                            score = EXCLUDED.score,
                            feedback = EXCLUDED.feedback,
                            updated_at = EXCLUDED.updated_at;
                    """, (
                        resp_id,
                        candidate.id,
                        q.id,
                        q.category,
                        q.text,
                        q.competency,
                        q.order,
                        q.completed,
                        q.answer_notes,
                        getattr(q, "score", None),
                        getattr(q, "feedback", None),
                        candidate.created_at,
                        candidate.updated_at,
                    ))

            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.autocommit = was_autocommit
            except Exception:
                pass

    def _auto_sync_pending(self, conn) -> int:
        """Best-effort opportunistic replay of pending records when an active DB connection is present."""
        data = self._load_fallback()
        pending_ids = [cid for cid, c in data.items() if isinstance(c, dict) and c.get("_pending_sync")]
        if not pending_ids:
            return 0

        synced_count = 0
        def _sync_mutator(sync_data: Dict[str, Dict[str, Any]]):
            nonlocal synced_count
            for cid in pending_ids:
                c_item = sync_data.get(cid)
                if not c_item or not c_item.get("_pending_sync"):
                    continue
                try:
                    c_obj = Candidate.from_dict(c_item)
                    self._save_to_postgres(c_obj, conn)
                    c_item["_pending_sync"] = False
                    c_item["_synced_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    synced_count += 1
                except Exception as ex:
                    logger.warning(f"[CANDIDATE REPO] Auto-sync failed for {cid}: {ex}")
                    break

        self._atomic_update_fallback(_sync_mutator)
        if synced_count > 0:
            self.last_sync_time = time.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[CANDIDATE REPO] Replayed {synced_count} pending offline candidates into PostgreSQL.")
        return synced_count

    def sync_fallback_to_db(self) -> Dict[str, Any]:
        """Manually or periodically triggers synchronization of pending fallback candidates into PostgreSQL."""
        conn = self.db_manager.get_connection()
        if not conn:
            return {
                "status": "db_unavailable",
                "synced_count": 0,
                "pending_count": self.get_pending_sync_count(),
                "error": "Cannot establish database connection",
            }

        try:
            synced = self._auto_sync_pending(conn)
            pending = self.get_pending_sync_count()
            return {
                "status": "completed" if pending == 0 else "partial",
                "synced_count": synced,
                "pending_count": pending,
                "last_sync_time": self.last_sync_time,
            }
        finally:
            conn.close()

    def save(self, candidate: Candidate, raise_on_error: bool = False) -> bool:
        """Saves a candidate profile and questions.
        
        Persists to PostgreSQL if available. If database is offline or encounters an error,
        safely persists to concurrency-protected JSON fallback marked with a dirty sync flag.
        """
        if getattr(candidate, "phone", None):
            norm_phone = normalize_phone_e164(candidate.phone)
            if norm_phone:
                candidate.phone = norm_phone

        conn = self.db_manager.get_connection()
        if not conn:
            if raise_on_error:
                raise ConnectionError("Database connection unavailable; fallback not allowed by caller.")
            def _save_offline(data: Dict[str, Dict[str, Any]]):
                cdict = candidate.to_dict()
                cdict["_pending_sync"] = True
                cdict["_fallback_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                data[candidate.id] = cdict
            self._atomic_update_fallback(_save_offline)
            self.last_write_storage = "fallback"
            logger.info(f"[CANDIDATE REPO] Saved candidate {candidate.id} to offline fallback store (pending DB sync).")
            return True

        try:
            self._save_to_postgres(candidate, conn)
            self.last_write_storage = "postgres"
            self.last_error = None

            # Mark any fallback copy as synced
            def _mark_synced(data: Dict[str, Dict[str, Any]]):
                if candidate.id in data:
                    data[candidate.id]["_pending_sync"] = False
                    data[candidate.id]["_synced_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._atomic_update_fallback(_mark_synced)

            # Auto-replay any remaining pending records if DB is healthy
            self._auto_sync_pending(conn)
            return True
        except Exception as e:
            logger.error(f"[CANDIDATE REPO] PostgreSQL save error for {candidate.id}: {e}")
            self.last_error = str(e)
            if raise_on_error:
                raise

            def _save_on_error(data: Dict[str, Dict[str, Any]]):
                cdict = candidate.to_dict()
                cdict["_pending_sync"] = True
                cdict["_fallback_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                data[candidate.id] = cdict
            self._atomic_update_fallback(_save_on_error)
            self.last_write_storage = "fallback"
            logger.warning(
                f"[CANDIDATE REPO] PostgreSQL write failed ({e}). Candidate {candidate.id} saved to JSON fallback (marked pending sync)."
            )
            return True
        finally:
            conn.close()

    def _query_fallback(
        self,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Candidate]:
        """Filters, sorts, and slices candidates from fallback storage identically to PostgreSQL."""
        data = self._load_fallback()
        items = [c for c in data.values() if isinstance(c, dict)]
        if status:
            items = [c for c in items if c.get("status") == status]
        if search:
            s = search.lower()
            items = [
                c for c in items
                if s in c.get("name", "").lower()
                or s in c.get("phone", "").lower()
                or s in c.get("position", "").lower()
            ]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        sliced = items[offset : offset + limit] if limit else items[offset:]
        return [Candidate.from_dict(c) for c in sliced]

    def _count_fallback(self, search: Optional[str] = None, status: Optional[str] = None) -> int:
        """Calculates candidate count from fallback storage identically to PostgreSQL."""
        data = self._load_fallback()
        items = [c for c in data.values() if isinstance(c, dict)]
        if status:
            items = [c for c in items if c.get("status") == status]
        if search:
            s = search.lower()
            items = [
                c for c in items
                if s in c.get("name", "").lower()
                or s in c.get("phone", "").lower()
                or s in c.get("position", "").lower()
            ]
        return len(items)

    def _get_fallback_responses(self, candidate_id: str) -> List[Dict[str, Any]]:
        """Constructs response items for candidate from fallback store."""
        data = self._load_fallback()
        cand_dict = data.get(candidate_id)
        if not cand_dict:
            return []
        cand = Candidate.from_dict(cand_dict)
        return [
            {
                "id": f"{cand.id}_{q.id}",
                "candidate_id": cand.id,
                "candidate_name": cand.name,
                "candidate_position": cand.position,
                "question_id": q.id,
                "category": q.category,
                "question_text": q.text,
                "competency": q.competency,
                "order_num": q.order,
                "completed": q.completed,
                "response_text": q.answer_notes,
                "score": getattr(q, "score", None),
                "feedback": getattr(q, "feedback", None),
                "created_at": cand.created_at,
                "updated_at": cand.updated_at,
            }
            for q in cand.questions
        ]

    def get_by_id(self, candidate_id: str) -> Optional[Candidate]:
        """Retrieves a candidate by ID using a SQL JOIN with candidate_responses."""
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            cand_dict = data.get(candidate_id)
            return Candidate.from_dict(cand_dict) if cand_dict else None

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        c.id, c.name, c.phone, c.position, c.job_description,
                        c.resume_filename, c.resume_text, c.status, c.questions AS raw_questions,
                        c.scorecard, c.call_id, c.created_at, c.updated_at,
                        cr.id AS resp_id, cr.question_id, cr.category AS resp_category,
                        cr.question_text, cr.competency AS resp_competency,
                        cr.order_num, cr.completed AS resp_completed,
                        cr.response_text, cr.score AS resp_score, cr.feedback AS resp_feedback
                    FROM candidates c
                    LEFT JOIN candidate_responses cr ON c.id = cr.candidate_id
                    WHERE c.id = %s
                    ORDER BY cr.order_num ASC;
                """, (candidate_id,))
                rows = cur.fetchall()
                if not rows:
                    data = self._load_fallback()
                    cand_dict = data.get(candidate_id)
                    return Candidate.from_dict(cand_dict) if cand_dict else None

                first_row = dict(rows[0])
                cand_data = {
                    "id": first_row.get("id"),
                    "name": first_row.get("name"),
                    "phone": first_row.get("phone"),
                    "position": first_row.get("position"),
                    "job_description": first_row.get("job_description"),
                    "resume_filename": first_row.get("resume_filename"),
                    "resume_text": first_row.get("resume_text"),
                    "status": first_row.get("status"),
                    "scorecard": first_row.get("scorecard"),
                    "call_id": first_row.get("call_id"),
                    "created_at": first_row.get("created_at"),
                    "updated_at": first_row.get("updated_at"),
                }

                # Construct Question items from joined candidate_responses rows
                joined_questions = []
                for r in rows:
                    if r.get("resp_id"):
                        joined_questions.append({
                            "id": r.get("question_id"),
                            "candidate_id": candidate_id,
                            "category": r.get("resp_category") or "technical",
                            "text": r.get("question_text") or "",
                            "competency": r.get("resp_competency") or "",
                            "order": r.get("order_num") or 1,
                            "completed": r.get("resp_completed") or False,
                            "answer_notes": r.get("response_text"),
                            "score": r.get("resp_score"),
                            "feedback": r.get("resp_feedback"),
                        })

                if joined_questions:
                    cand_data["questions"] = joined_questions
                else:
                    cand_data["questions"] = first_row.get("raw_questions") or []

                return Candidate.from_dict(cand_data)
        except Exception as e:
            logger.error(f"CandidateRepository.get_by_id error: {e}")
            self.last_error = str(e)
            data = self._load_fallback()
            cand_dict = data.get(candidate_id)
            return Candidate.from_dict(cand_dict) if cand_dict else None
        finally:
            conn.close()

    def get_count(self, search: Optional[str] = None, status: Optional[str] = None) -> int:
        conn = self.db_manager.get_connection()
        if not conn:
            return self._count_fallback(search=search, status=status)

        try:
            with conn.cursor() as cur:
                where_clauses = []
                params = []
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)
                if search:
                    where_clauses.append("(name ILIKE %s OR phone ILIKE %s OR position ILIKE %s)")
                    s_pat = f"%{search}%"
                    params.extend([s_pat, s_pat, s_pat])

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                cur.execute(f"SELECT COUNT(*) FROM candidates {where_sql};", tuple(params))
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"CandidateRepository.get_count error: {e}")
            self.last_error = str(e)
            return self._count_fallback(search=search, status=status)
        finally:
            conn.close()

    def get_all(
        self,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Candidate]:
        conn = self.db_manager.get_connection()
        if not conn:
            return self._query_fallback(limit=limit, offset=offset, search=search, status=status)

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                where_clauses = []
                params = []
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)
                if search:
                    where_clauses.append("(name ILIKE %s OR phone ILIKE %s OR position ILIKE %s)")
                    s_pat = f"%{search}%"
                    params.extend([s_pat, s_pat, s_pat])

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                limit_sql = "LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(
                    f"SELECT * FROM candidates {where_sql} ORDER BY created_at DESC {limit_sql};",
                    tuple(params),
                )
                rows = cur.fetchall()
                if not rows:
                    return []

                # Hydrate questions from candidate_responses so candidate_responses is the single authoritative source of truth
                cand_ids = [r["id"] for r in rows]
                responses_by_cand: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in cand_ids}
                if cand_ids:
                    try:
                        cur.execute("""
                            SELECT candidate_id, question_id, category, question_text, competency,
                                   order_num, completed, response_text, score, feedback
                            FROM candidate_responses
                            WHERE candidate_id = ANY(%s)
                            ORDER BY order_num ASC;
                        """, (cand_ids,))
                        for cr in cur.fetchall():
                            cid = cr["candidate_id"]
                            if cid in responses_by_cand:
                                responses_by_cand[cid].append({
                                    "id": cr["question_id"],
                                    "candidate_id": cid,
                                    "category": cr.get("category") or "technical",
                                    "text": cr.get("question_text") or "",
                                    "competency": cr.get("competency") or "",
                                    "order": cr.get("order_num") or 1,
                                    "completed": cr.get("completed") or False,
                                    "answer_notes": cr.get("response_text"),
                                    "score": cr.get("score"),
                                    "feedback": cr.get("feedback"),
                                })
                    except Exception as cr_err:
                        logger.warning(f"Failed to hydrate responses in get_all: {cr_err}")

                result = []
                for r in rows:
                    c_dict = dict(r)
                    cid = c_dict["id"]
                    if responses_by_cand.get(cid):
                        c_dict["questions"] = responses_by_cand[cid]
                    result.append(Candidate.from_dict(c_dict))
                return result
        except Exception as e:
            logger.error(f"CandidateRepository.get_all error: {e}")
            self.last_error = str(e)
            return self._query_fallback(limit=limit, offset=offset, search=search, status=status)
        finally:
            conn.close()

    def get_responses(self, candidate_id: str) -> List[Dict[str, Any]]:
        """Retrieves all question responses for a candidate using a SQL JOIN on candidates and candidate_responses."""
        conn = self.db_manager.get_connection()
        if not conn:
            return self._get_fallback_responses(candidate_id)

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        cr.id, cr.candidate_id, cr.question_id, cr.category,
                        cr.question_text, cr.competency, cr.order_num, cr.completed,
                        cr.response_text, cr.score, cr.feedback, cr.created_at, cr.updated_at,
                        c.name AS candidate_name, c.position AS candidate_position
                    FROM candidate_responses cr
                    JOIN candidates c ON cr.candidate_id = c.id
                    WHERE cr.candidate_id = %s
                    ORDER BY cr.order_num ASC;
                """, (candidate_id,))
                rows = cur.fetchall()
                if rows:
                    return [dict(r) for r in rows]

                cand = self.get_by_id(candidate_id)
                if not cand:
                    return []
                return [
                    {
                        "id": f"{cand.id}_{q.id}",
                        "candidate_id": cand.id,
                        "candidate_name": cand.name,
                        "candidate_position": cand.position,
                        "question_id": q.id,
                        "category": q.category,
                        "question_text": q.text,
                        "competency": q.competency,
                        "order_num": q.order,
                        "completed": q.completed,
                        "response_text": q.answer_notes,
                        "score": getattr(q, "score", None),
                        "feedback": getattr(q, "feedback", None),
                        "created_at": cand.created_at,
                        "updated_at": cand.updated_at,
                    }
                    for q in cand.questions
                ]
        except Exception as e:
            logger.error(f"CandidateRepository.get_responses error: {e}")
            self.last_error = str(e)
            return self._get_fallback_responses(candidate_id)
        finally:
            conn.close()

    def get_candidate_with_calls(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves candidate profile together with all linked calls using a SQL JOIN."""
        cand = self.get_by_id(candidate_id)
        if not cand:
            return None

        result = cand.to_dict()
        conn = self.db_manager.get_connection()
        if not conn:
            result["calls"] = []
            return result

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        calls.id AS call_id, calls.candidate_id, calls.direction, calls.phone,
                        to_char(calls.start_time, 'YYYY-MM-DD HH24:MI:SS') AS start,
                        to_char(calls.end_time,   'YYYY-MM-DD HH24:MI:SS') AS end,
                        calls.duration_sec, calls.language, calls.lead, calls.lead_status,
                        calls.meeting, calls.callback, calls.ended_by, calls.recording,
                        calls.transcript
                    FROM calls
                    JOIN candidates c ON calls.candidate_id = c.id
                    WHERE c.id = %s
                    ORDER BY calls.start_time DESC;
                """, (candidate_id,))
                rows = cur.fetchall()
                calls_list = []
                for r in rows:
                    item = dict(r)
                    if isinstance(item.get("transcript"), str):
                        try:
                            item["transcript"] = json.loads(item["transcript"])
                        except Exception:
                            item["transcript"] = []
                    calls_list.append(item)
                result["calls"] = calls_list
                return result
        except Exception as e:
            logger.error(f"CandidateRepository.get_candidate_with_calls error: {e}")
            self.last_error = str(e)
            result["calls"] = []
            return result
        finally:
            conn.close()

    def _get_fallback_by_phone(self, variants: List[str]) -> Optional[Candidate]:
        """Performs exact variant lookup in fallback storage without broad substring matching."""
        if not variants:
            return None
        variants_set = set(variants)
        data = self._load_fallback()
        for cand_dict in data.values():
            if not isinstance(cand_dict, dict):
                continue
            c_phone = cand_dict.get("phone", "")
            if not c_phone:
                continue
            if c_phone in variants_set:
                return self.get_by_id(cand_dict.get("id"))
            c_variants = set(get_phone_lookup_variants(c_phone))
            if variants_set.intersection(c_variants):
                return self.get_by_id(cand_dict.get("id"))
        return None

    def get_by_phone(self, phone: str) -> Optional[Candidate]:
        """Looks up candidate by phone number using normalized exact matching.
        
        Guarantees:
        - Validates phone input: empty, whitespace-only, or short (<7 digits) inputs return None immediately.
        - Generates exact E.164 and canonical variants to perform index-backed exact match queries (phone = ANY(%s)).
        - Eliminates leading-wildcard ILIKE scans so PostgreSQL utilizes the B-tree idx_candidates_phone index.
        - Prevents accidental broad substring matches in offline fallback storage.
        """
        variants = get_phone_lookup_variants(phone)
        if not variants:
            return None

        conn = self.db_manager.get_connection()
        if not conn:
            return self._get_fallback_by_phone(variants)

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM candidates WHERE phone = ANY(%s) LIMIT 1;",
                    (variants,),
                )
                row = cur.fetchone()
                if row:
                    return self.get_by_id(row[0])
                return None
        except Exception as e:
            logger.error(f"CandidateRepository.get_by_phone error: {e}")
            self.last_error = str(e)
            return self._get_fallback_by_phone(variants)
        finally:
            conn.close()

    def _purge_recording_files(self, recordings: List[Optional[str]]) -> int:
        """Deletes physical audio recording files from disk associated with deleted calls."""
        purged = 0
        recordings_dir = str(settings.RECORDINGS_DIR)
        for rec in recordings:
            if not rec:
                continue
            try:
                candidates_paths = []
                if os.path.isabs(rec):
                    candidates_paths.append(rec)
                else:
                    candidates_paths.append(os.path.join(recordings_dir, rec))
                    candidates_paths.append(os.path.join(recordings_dir, os.path.basename(rec)))

                for path in candidates_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        os.remove(path)
                        purged += 1
                        logger.info(f"[CANDIDATE DELETE] Removed audio recording file: {path}")
                        break
            except Exception as e:
                logger.warning(f"[CANDIDATE DELETE] Failed to remove recording file {rec}: {e}")
        return purged

    def _purge_calls_from_jsonl(self, candidate_id: str) -> int:
        """Purges or disassociates candidate entries from logs/calls.jsonl fallback file."""
        calls_jsonl = os.path.join(str(settings.LOGS_DIR), "calls.jsonl")
        if not os.path.exists(calls_jsonl):
            return 0
        purged = 0
        try:
            lines_to_keep = []
            modified = False
            with open(calls_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        call_item = json.loads(line_str)
                        if call_item.get("candidate_id") == candidate_id:
                            modified = True
                            purged += 1
                            rec_file = call_item.get("recording")
                            if rec_file:
                                self._purge_recording_files([rec_file])
                            continue
                    except Exception:
                        pass
                    lines_to_keep.append(line_str)

            if modified:
                with open(calls_jsonl, "w", encoding="utf-8") as f:
                    for l in lines_to_keep:
                        f.write(l + "\n")
        except Exception as e:
            logger.warning(f"[CANDIDATE DELETE] Error cleaning calls.jsonl for {candidate_id}: {e}")
        return purged

    def delete(
        self,
        candidate_id: str,
        purge_linked_calls: bool = True,
        purge_recordings: bool = True,
    ) -> bool:
        """Deletes candidate from database and fallback storage.
        
        Guarantees:
        - Returns True only if a candidate row actually existed and was deleted; returns False if not found.
        - Deletes candidate_responses.
        - When purge_linked_calls is True: deletes linked records from 'calls', 'call_logs', and 'calls.jsonl'.
        - When purge_recordings is True: safely removes associated physical audio recording WAV files from disk.
        - Guarantees any copy in the fallback JSON file is removed.
        """
        conn = self.db_manager.get_connection()
        if not conn:
            # Check if candidate exists in fallback
            fallback_data = self._load_fallback()
            cand_item = fallback_data.get(candidate_id)
            if not cand_item:
                return False

            if purge_recordings and isinstance(cand_item, dict):
                call_id = cand_item.get("call_id")
                if call_id:
                    self._purge_calls_from_jsonl(candidate_id)

            return self._delete_from_fallback(candidate_id)

        try:
            with conn.cursor() as cur:
                # 1. Check existence in DB and fallback
                cur.execute("SELECT id FROM candidates WHERE id = %s;", (candidate_id,))
                exists_in_db = cur.fetchone() is not None

                fallback_data = self._load_fallback()
                exists_in_fallback = candidate_id in fallback_data

                if not exists_in_db and not exists_in_fallback:
                    return False

                # 2. Gather linked recordings if media purge is requested
                if purge_recordings:
                    cur.execute(
                        "SELECT recording FROM calls WHERE candidate_id = %s AND recording IS NOT NULL;",
                        (candidate_id,),
                    )
                    rec_rows = cur.fetchall()
                    recordings_to_delete = [r[0] for r in rec_rows if r[0]]
                    if recordings_to_delete:
                        self._purge_recording_files(recordings_to_delete)

                # 3. Purge linked calls and call_logs if requested
                if purge_linked_calls:
                    cur.execute("DELETE FROM calls WHERE candidate_id = %s;", (candidate_id,))
                    cur.execute("DELETE FROM call_logs WHERE candidate_id = %s;", (candidate_id,))
                    self._purge_calls_from_jsonl(candidate_id)

                # 4. Delete candidate responses and candidate
                cur.execute("DELETE FROM candidate_responses WHERE candidate_id = %s;", (candidate_id,))
                cur.execute("DELETE FROM candidates WHERE id = %s;", (candidate_id,))
                deleted_rows = cur.rowcount

            # 5. Clean up fallback file copy
            fallback_deleted = self._delete_from_fallback(candidate_id)
            return (deleted_rows > 0) or fallback_deleted
        except Exception as e:
            logger.error(f"CandidateRepository.delete error: {e}")
            self.last_error = str(e)
            return self._delete_from_fallback(candidate_id)
        finally:
            conn.close()


candidate_repo = CandidateRepository(db_manager)
