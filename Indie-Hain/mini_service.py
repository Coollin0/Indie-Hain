# mini_service.py (neben deiner GUI, getrennt startbar)
from fastapi import FastAPI
import sqlite3

app = FastAPI()

def has_license(user_id: int, slug: str) -> bool:
    # indizierter Lookup z.B. via game_id; demo: slug->id mapping vorausgesetzt
    with sqlite3.connect("data/indiehain.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute("""
            SELECT 1 FROM library
            JOIN games ON games.id = library.game_id
            WHERE library.user_id = ? AND games.slug = ?
            """, (user_id, slug)).fetchone()
    return bool(row)

@app.get("/api/licenses/has")
def api_has_license(user_id: int, slug: str):
    return {"ok": True, "has": has_license(user_id, slug)}
