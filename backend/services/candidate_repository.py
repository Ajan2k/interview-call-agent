import os
import json
import logging
from typing import List, Optional, Dict, Any
from psycopg2.extras import RealDictCursor
from models.candidate import Candidate
from services.database_manager import DatabaseManager, db_manager
from core.config import settings

logger = logging.getLogger("services.candidate_repo")


class CandidateRepository:
    """Manages Candidate persistence in PostgreSQL with indexing, pagination, and JSON file fallback."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.fallback_file = str(settings.LOGS_DIR / "candidates.json")
        self._ensure_table()

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
        except Exception as e:
            logger.warning(f"Could not create candidates table or indexes: {e}")
        finally:
            conn.close()

    def _load_fallback(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.fallback_file):
            return {}
        try:
            with open(self.fallback_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_fallback(self, data: Dict[str, Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.fallback_file), exist_ok=True)
        with open(self.fallback_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save(self, candidate: Candidate) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            data[candidate.id] = candidate.to_dict()
            self._save_fallback(data)
            return True

        try:
            with conn.cursor() as cur:
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
            return True
        except Exception as e:
            logger.error(f"CandidateRepository.save error: {e}")
            # Fall back to file
            data = self._load_fallback()
            data[candidate.id] = candidate.to_dict()
            self._save_fallback(data)
            return True
        finally:
            conn.close()

    def get_by_id(self, candidate_id: str) -> Optional[Candidate]:
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            cand_dict = data.get(candidate_id)
            return Candidate.from_dict(cand_dict) if cand_dict else None

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM candidates WHERE id = %s;", (candidate_id,))
                row = cur.fetchone()
                if row:
                    return Candidate.from_dict(dict(row))
                return None
        except Exception as e:
            logger.error(f"CandidateRepository.get_by_id error: {e}")
            data = self._load_fallback()
            cand_dict = data.get(candidate_id)
            return Candidate.from_dict(cand_dict) if cand_dict else None
        finally:
            conn.close()

    def get_count(self, search: Optional[str] = None, status: Optional[str] = None) -> int:
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            items = list(data.values())
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
            return 0
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
            data = self._load_fallback()
            items = list(data.values())
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
            sliced = items[offset : offset + limit] if limit else items
            return [Candidate.from_dict(c) for c in sliced]

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
                return [Candidate.from_dict(dict(r)) for r in rows]
        except Exception as e:
            logger.error(f"CandidateRepository.get_all error: {e}")
            data = self._load_fallback()
            return [Candidate.from_dict(c) for c in list(data.values())[:limit]]
        finally:
            conn.close()

    def delete(self, candidate_id: str) -> bool:
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            if candidate_id in data:
                del data[candidate_id]
                self._save_fallback(data)
                return True
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM candidates WHERE id = %s;", (candidate_id,))
            return True
        except Exception as e:
            logger.error(f"CandidateRepository.delete error: {e}")
            data = self._load_fallback()
            if candidate_id in data:
                del data[candidate_id]
                self._save_fallback(data)
                return True
            return False
        finally:
            conn.close()


candidate_repo = CandidateRepository(db_manager)
