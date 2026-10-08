import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    mongo_url: str
    db_name: str
    api_key: str
    upload_dir: Path
    max_upload_mb: int
    retention_hours: int
    cors_origins: tuple[str, ...]
    model_checkpoint: str

    @classmethod
    def from_env(cls):
        key = os.getenv('API_KEY', '')
        if len(key) < 24 or key.lower() in {'changeme', 'replace-me'} or key.startswith('replace_'):
            raise RuntimeError('API_KEY must be a random value of at least 24 characters')
        return cls(
            os.getenv('MONGO_URL', 'mongodb://localhost:27017'),
            os.getenv('DB_NAME', 'ligand_demo'), key,
            Path(os.getenv('UPLOAD_DIR', './data/uploads')).resolve(),
            int(os.getenv('MAX_UPLOAD_MB', '25')),
            int(os.getenv('RETENTION_HOURS', '24')),
            tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',') if x.strip()),
            os.getenv('MODEL_CHECKPOINT', ''),
        )
