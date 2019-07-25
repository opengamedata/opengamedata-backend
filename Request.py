from datetime import date

# Dumb struct to hold data related to requests for data export.
# This way, we've at least got a list of what is available in a request.
class Request:
    def __init__(self, game_id: str = None, start_date: date = None, end_date: date = None,
                 max_sessions: int = None, min_moves: int = None, read_cache: bool = False, write_cache: bool = False):
        self.game_id = game_id
        self.start_date = start_date
        self.end_date = end_date
        self.max_sessions = max_sessions
        self.min_moves = min_moves
        self.read_cache = read_cache
        self.write_cache = write_cache

    def __str__(self):
        fmt = "%Y%m%d"
        return f"{self.game_id}: {self.start_date.strftime(fmt)}-{self.end_date.strftime(fmt)}"