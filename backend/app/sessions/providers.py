from app.sessions.adapters.gomafia import GomafiaHttpParserAdapter
from app.sessions.ports.gomafia import GomafiaTournamentSource


def get_gomafia_source() -> GomafiaTournamentSource:
    return GomafiaHttpParserAdapter()
