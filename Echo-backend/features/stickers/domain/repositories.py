from typing import Protocol


class StickerGenerationRepository(Protocol):
    def claim_generation_jobs(self, limit: int) -> list[dict]: ...
    def complete_generation(
        self,
        job_id: str,
        user_id: str,
        storage_key: str,
        public_url: str,
        content_type: str,
        byte_size: int,
        content_hash: str,
        intent: str,
    ) -> None: ...
    def fail_generation(self, job_id: str, error_code: str) -> None: ...
