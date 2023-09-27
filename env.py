from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    baseurl: str
    min_age: int = 3600
    excluded_headers: set[str] = set()
    replace: str = ""
    proxy_slug: str = "proxy"
    proxy_sites: set[str] = set()
    bypass_sites: set[str] = set()

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


env = Settings()

env.excluded_headers |= {
    "content-encoding",
    "content-length",
    "content-security-policy",
    "connection",
}
