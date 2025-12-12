import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env from network_hunt directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


class SupabaseConfig(BaseModel):
    url: str
    secret_key: str


class ProductHuntConfig(BaseModel):
    token: str
    api_url: str = "https://api.producthunt.com/v2/api/graphql"
    requests_per_second: float = 1.0


class SerpConfig(BaseModel):
    api_key: str
    base_url: str = "https://serpapi.com/search"


class GitHubConfig(BaseModel):
    token: str
    api_url: str = "https://api.github.com"


class ArxivConfig(BaseModel):
    api_url: str = "http://export.arxiv.org/api/query"
    delay_seconds: float = 3.0


class Config(BaseModel):
    supabase: SupabaseConfig
    product_hunt: ProductHuntConfig
    serp: SerpConfig
    github: GitHubConfig
    arxiv: ArxivConfig


def load_config() -> Config:
    return Config(
        supabase=SupabaseConfig(
            url=require_env("SUPABASE_URL"),
            secret_key=require_env("SUPABASE_SECRET_KEY"),
        ),
        product_hunt=ProductHuntConfig(
            token=require_env("PRODUCT_HUNT_DEVELOPER_TOKEN"),
        ),
        serp=SerpConfig(
            api_key=require_env("SERP_API_KEY"),
        ),
        github=GitHubConfig(
            token=require_env("GITHUB_TOKEN"),
        ),
        arxiv=ArxivConfig(),
    )


config = load_config()
