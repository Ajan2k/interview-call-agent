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
                        updated_at VARCHAR(100)
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidate_responses_cand_id ON candidate_responses(candidate_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_candidate_responses_qid ON candidate_responses(question_id);")
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

                # Persist normalized responses into candidate_responses table tracked by candidate_id
                for q in candidate.questions:
                    resp_id = f"{candidate.id}_{q.id}"
                    cur.execute("""
                        INSERT INTO candidate_responses (
                            id, candidate_id, question_id, category, question_text,
                            competency, order_num, completed, response_text, score, feedback,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
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
        """Retrieves a candidate by ID using a SQL JOIN with candidate_responses."""
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            cand_dict = data.get(candidate_id)
            return Candidate.from_dict(cand_dict) if cand_dict else None

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # JOIN candidates with candidate_responses on candidate_id
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
                    return None

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

    def get_responses(self, candidate_id: str) -> List[Dict[str, Any]]:
        """Retrieves all question responses for a candidate using a SQL JOIN on candidates and candidate_responses."""
        conn = self.db_manager.get_connection()
        if not conn:
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

                # Fallback to candidate table if candidate_responses is empty
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
            return []
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
            result["calls"] = []
            return result
        finally:
            conn.close()

    def get_by_phone(self, phone: str) -> Optional[Candidate]:
        """Looks up candidate by phone number."""
        clean_phone = phone.strip()
        conn = self.db_manager.get_connection()
        if not conn:
            data = self._load_fallback()
            for cand_dict in data.values():
                c_phone = cand_dict.get("phone", "")
                if c_phone and (clean_phone in c_phone or c_phone in clean_phone):
                    return self.get_by_id(cand_dict.get("id"))
            return None

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM candidates WHERE phone = %s LIMIT 1;", (clean_phone,))
                row = cur.fetchone()
                if row:
                    return self.get_by_id(row[0])

                # Partial match fallback
                cur.execute("SELECT id FROM candidates WHERE phone ILIKE %s LIMIT 1;", (f"%{clean_phone[-8:]}%",))
                row = cur.fetchone()
                if row:
                    return self.get_by_id(row[0])
                return None
        except Exception as e:
            logger.error(f"CandidateRepository.get_by_phone error: {e}")
            return None
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
                # Delete candidate responses first (also cascading in PostgreSQL)
                cur.execute("DELETE FROM candidate_responses WHERE candidate_id = %s;", (candidate_id,))
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

