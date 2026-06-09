import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.memory.application.memory_management import MemoryManagementService
from features.memory.domain.entities import (
    InvalidMemoryStatusError,
    Memory,
    MemoryImportance,
    MemoryNotFoundError,
    MemoryValidationError,
)


class FakeMemoryRepository:
    def __init__(self):
        self.memory = Memory(
            memory_id="mem_a",
            user_id="user_a",
            memory_type="profile",
            content="用户喜欢被称呼为小安",
            source_message_id=1,
            confidence=0.9,
            importance=MemoryImportance(5),
            status="active",
            created_at="2026-01-01 00:00:00",
            updated_at="2026-01-01 00:00:00",
        )
        self.list_calls = []
        self.deleted_ids = []
        self.cleared_user_ids = []

    def list_memories(self, user_id, status, limit):
        self.list_calls.append((user_id, status, limit))
        return [self.memory]

    def list_active_memories(self, user_id, limit):
        return self.list_memories(user_id, "active", limit)

    def get_memory(self, user_id, memory_id):
        if memory_id == self.memory.memory_id:
            return self.memory
        return None

    def delete_memory(self, user_id, memory_id):
        self.deleted_ids.append(memory_id)
        return True

    def clear_memories(self, user_id):
        self.cleared_user_ids.append(user_id)
        return 3


class FakeVectorIndex:
    def __init__(self):
        self.deleted_ids = []
        self.cleared_user_ids = []
        self.backfill_calls = []

    def delete_memory_embedding(self, user_id, memory_id):
        self.deleted_ids.append((user_id, memory_id))
        return True

    def clear_memory_embeddings(self, user_id):
        self.cleared_user_ids.append(user_id)
        return 2

    async def backfill_user_memory_embeddings(self, user_id, limit):
        self.backfill_calls.append((user_id, limit))
        return 4


class MemoryManagementFeatureTests(unittest.IsolatedAsyncioTestCase):
    def build_service(self):
        repository = FakeMemoryRepository()
        vector_index = FakeVectorIndex()
        service = MemoryManagementService(
            memory_repository=repository,
            vector_index=vector_index,
        )
        return service, repository, vector_index

    def test_list_memories_normalizes_all_status_and_clamps_limit(self):
        service, repository, _ = self.build_service()

        result = service.list_memories("user_a", memory_status="ALL", limit=999)

        self.assertEqual(result.count, 1)
        self.assertEqual(repository.list_calls, [("user_a", None, 200)])

    def test_list_memories_rejects_invalid_status(self):
        service, _, _ = self.build_service()

        with self.assertRaises(InvalidMemoryStatusError):
            service.list_memories("user_a", memory_status="unknown", limit=10)

    def test_delete_memory_deletes_memory_and_vector_record(self):
        service, repository, vector_index = self.build_service()

        result = service.delete_memory("user_a", " mem_a ")

        self.assertEqual(result.memory_id, "mem_a")
        self.assertEqual(result.status, "deleted")
        self.assertEqual(repository.deleted_ids, ["mem_a"])
        self.assertEqual(vector_index.deleted_ids, [("user_a", "mem_a")])

    def test_delete_memory_rejects_missing_id(self):
        service, _, _ = self.build_service()

        with self.assertRaises(MemoryValidationError):
            service.delete_memory("user_a", " ")

    def test_delete_memory_reports_not_found(self):
        service, _, _ = self.build_service()

        with self.assertRaises(MemoryNotFoundError):
            service.delete_memory("user_a", "mem_missing")

    def test_clear_memories_clears_repository_and_vector_index(self):
        service, repository, vector_index = self.build_service()

        result = service.clear_memories("user_a")

        self.assertEqual(result.cleared_count, 3)
        self.assertEqual(repository.cleared_user_ids, ["user_a"])
        self.assertEqual(vector_index.cleared_user_ids, ["user_a"])

    async def test_backfill_memory_embeddings_clamps_limit(self):
        service, _, vector_index = self.build_service()

        result = await service.backfill_memory_embeddings("user_a", limit=999)

        self.assertEqual(result.backfilled_count, 4)
        self.assertEqual(vector_index.backfill_calls, [("user_a", 500)])


if __name__ == "__main__":
    unittest.main()
