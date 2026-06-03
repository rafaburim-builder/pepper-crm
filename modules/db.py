"""
Pepper — local SQLite database for persisting suggestions and settings.
"""
import json
import os
import sqlite3
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE, "data", "pepper.db")


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        self._conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                nome       TEXT    NOT NULL,
                data       TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo       TEXT    NOT NULL,
                nome         TEXT    NOT NULL,
                campanha     TEXT    NOT NULL DEFAULT '',
                contacted_at TEXT    NOT NULL
            )
        """)
        self._conn.commit()

    # ── Sugestões de Mix ──────────────────────────────────────────────────────

    def save_suggestion(self, nome: str, data: dict) -> int:
        """Persist a tier-distribution suggestion. Returns the new row id."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        cur = self._conn.execute(
            "INSERT INTO suggestions (nome, data, created_at) VALUES (?, ?, ?)",
            (nome, json.dumps(data, ensure_ascii=False), now),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_suggestions(self) -> list:
        """Return list of dicts: id, nome, created_at (newest first)."""
        cur = self._conn.execute(
            "SELECT id, nome, created_at FROM suggestions ORDER BY id DESC LIMIT 20"
        )
        return [{"id": row[0], "nome": row[1], "created_at": row[2]} for row in cur.fetchall()]

    def load_suggestion(self, suggestion_id: int) -> dict:
        """Return the data dict for a saved suggestion."""
        cur = self._conn.execute(
            "SELECT data FROM suggestions WHERE id = ?", (suggestion_id,)
        )
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
        return {}

    def delete_suggestion(self, suggestion_id: int) -> None:
        self._conn.execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
        self._conn.commit()

    # ── Histórico de Contatos WhatsApp ────────────────────────────────────────

    def log_contact(self, codigo: str, nome: str, campanha: str = "") -> None:
        """Registra que um cliente foi contatado agora."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        self._conn.execute(
            "INSERT INTO contact_history (codigo, nome, campanha, contacted_at) VALUES (?, ?, ?, ?)",
            (str(codigo), nome, campanha, now),
        )
        self._conn.commit()

    def was_contacted_this_month(self, codigo: str) -> bool:
        """Retorna True se o cliente foi contatado no mês/ano atual."""
        # contacted_at format: "DD/MM/YYYY HH:MM"
        # substr(contacted_at, 4, 7) extrai "MM/YYYY"
        month_year = datetime.now().strftime("%m/%Y")
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM contact_history "
            "WHERE codigo = ? AND substr(contacted_at, 4, 7) = ?",
            (str(codigo), month_year),
        )
        return cur.fetchone()[0] > 0

    def days_since_last_contact(self, codigo: str) -> int:
        """Retorna quantos dias desde o último contato. -1 se nunca contatado."""
        cur = self._conn.execute(
            "SELECT contacted_at FROM contact_history "
            "WHERE codigo = ? ORDER BY id DESC LIMIT 1",
            (str(codigo),),
        )
        row = cur.fetchone()
        if not row:
            return -1
        try:
            dt = datetime.strptime(row[0], "%d/%m/%Y %H:%M")
            return max(0, (datetime.now() - dt).days)
        except Exception:
            return -1

    def list_contacts(self, limit: int = 200) -> list:
        """Retorna os últimos contatos registrados (mais recentes primeiro)."""
        cur = self._conn.execute(
            "SELECT codigo, nome, campanha, contacted_at "
            "FROM contact_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            {"Código": r[0], "Cliente": r[1], "Campanha": r[2], "Data/Hora": r[3]}
            for r in cur.fetchall()
        ]
