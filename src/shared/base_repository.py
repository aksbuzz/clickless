class BaseRepository:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetch_one(self, query, params=()) -> dict | None:
        self.cursor.execute(query, params)
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, query, params=()) -> list[dict]:
        self.cursor.execute(query, params)
        return [dict(r) for r in self.cursor.fetchall()]

    def execute_returning(self, query, params=()) -> str:
        self.cursor.execute(query, params)
        return str(self.cursor.fetchone()["id"])

    def execute(self, query, params=()):
        self.cursor.execute(query, params)
