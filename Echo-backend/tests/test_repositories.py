import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.schema import init_db
from repositories.conversation_repository import get_or_create_active_conversation
from repositories.job_repository import (
    claim_job,
    complete_job,
    create_job,
    get_job,
    list_runnable_jobs,
    reset_running_jobs,
)
from repositories.memory_repository import add_user_memory, clear_user_memories, list_user_memories
from repositories.message_repository import add_chat_turn, get_conversation_messages
from repositories.vector_repository import list_memory_embedding_records, upsert_memory_embedding_record
from features.memory.public import MEMORY_EXTRACTION_JOB_TYPE, schedule_memory_extraction


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = os.environ.get("ECHO_DB_PATH")
        os.environ["ECHO_DB_PATH"] = str(Path(self.temp_dir.name) / "echo_test.db")
        init_db()

    def tearDown(self):
        if self.previous_db_path is None:
            os.environ.pop("ECHO_DB_PATH", None)
        else:
            os.environ["ECHO_DB_PATH"] = self.previous_db_path
        self.temp_dir.cleanup()

    def test_add_chat_turn_persists_both_messages(self):
        conversation_id = get_or_create_active_conversation("user_repo_test")

        user_message_id, assistant_message_id = add_chat_turn(
            user_id="user_repo_test",
            conversation_id=conversation_id,
            user_message="hello",
            assistant_reply="hi",
            user_message_type="text",
            assistant_message_type="text",
        )

        messages = get_conversation_messages("user_repo_test", conversation_id)
        self.assertLess(user_message_id, assistant_message_id)
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertEqual([message["content"] for message in messages], ["hello", "hi"])

    def test_memory_clear_soft_deletes_records(self):
        add_user_memory("user_repo_test", "preference", "用户喜欢简洁回复。")

        self.assertEqual(len(list_user_memories("user_repo_test", status="active")), 1)
        self.assertEqual(clear_user_memories("user_repo_test"), 1)
        self.assertEqual(len(list_user_memories("user_repo_test", status="active")), 0)
        self.assertEqual(len(list_user_memories("user_repo_test", status="deleted")), 1)

    def test_vector_repository_round_trip(self):
        upsert_memory_embedding_record(
            user_id="user_repo_test",
            memory_id="mem_test",
            embedding_model="test-model",
            embedding=[0.1, 0.2, 0.3],
        )

        records = list_memory_embedding_records("user_repo_test", embedding_model="test-model")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["memory_id"], "mem_test")
        self.assertEqual(records[0]["embedding"], [0.1, 0.2, 0.3])

    def test_background_job_lifecycle(self):
        job_id = create_job("unit_test", {"hello": "world"}, max_attempts=2)

        self.assertEqual(len(list_runnable_jobs("unit_test")), 1)
        self.assertTrue(claim_job(job_id))
        self.assertEqual(get_job(job_id)["status"], "running")
        self.assertEqual(reset_running_jobs("unit_test"), 1)
        self.assertEqual(get_job(job_id)["status"], "retry")
        self.assertTrue(claim_job(job_id))
        self.assertTrue(complete_job(job_id))
        self.assertEqual(get_job(job_id)["status"], "completed")

    def test_memory_extraction_schedule_queues_without_running_loop(self):
        result = schedule_memory_extraction(
            user_id="user_repo_test",
            user_message="以后叫我小安吧",
            assistant_reply="好的，小安。",
            source_message_id=123,
        )

        self.assertTrue(result.should_extract)
        self.assertTrue(result.job_id.startswith("job_"))
        job = get_job(result.job_id)
        self.assertEqual(job["job_type"], MEMORY_EXTRACTION_JOB_TYPE)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["payload"]["source_message_id"], 123)


if __name__ == "__main__":
    unittest.main()
