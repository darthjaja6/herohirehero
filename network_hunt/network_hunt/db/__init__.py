from supabase import create_client, Client
from ..config import config

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.supabase.url, config.supabase.secret_key)
    return _client


supabase = get_supabase()
