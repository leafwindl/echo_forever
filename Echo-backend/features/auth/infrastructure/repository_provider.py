from shared.config import settings


def get_repository_module():
    provider = settings.db_provider.strip().lower()
    if provider == "postgres":
        from features.auth.infrastructure import postgres_repositories

        return postgres_repositories
    raise RuntimeError(f"Unsupported DB_PROVIDER for auth: {settings.db_provider}")
