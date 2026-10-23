import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.stickers.domain.entities import Sticker  # noqa: E402
from features.stickers.domain.services import (  # noqa: E402
    build_sticker_query_text,
    build_sticker_semantic_text,
)
from features.stickers.infrastructure import vector_index  # noqa: E402


def _sticker(
    sticker_id: str,
    *,
    owner_type: str = "echo",
    description: str = "",
    tags: tuple[str, ...] = ("加油",),
) -> Sticker:
    return Sticker(
        sticker_id=sticker_id,
        owner_type=owner_type,
        source="builtin" if owner_type == "echo" else "uploaded",
        url=f"https://example.test/{sticker_id}.png",
        content_type="image/png",
        description=description,
        semantic_tags=tags,
        status="active",
        created_at=datetime.now(UTC),
    )


class FakeEmbeddingProvider:
    def __init__(self):
        self.inputs = []

    async def create_embedding(self, text, model=None):
        self.inputs.append((text, model))
        return [1.0, 0.0, 0.0]


class FakeStickerRepository:
    def __init__(self):
        self.active = []
        self.embedding_metadata = {}
        self.upserts = []
        self.vector_requests = []
        self.vector_matches = []
        self.lexical_requests = []

    def list_active_for_embedding(self, limit):
        return self.active[:limit]

    def list_embedding_metadata(self, embedding_model):
        del embedding_model
        return dict(self.embedding_metadata)

    def upsert_embedding(
        self,
        sticker_id,
        embedding_model,
        semantic_text,
        embedding,
    ):
        self.upserts.append(
            (sticker_id, embedding_model, semantic_text, list(embedding))
        )

    def list_vector_matches(
        self,
        user_id,
        query,
        query_embedding,
        embedding_model,
        limit,
        **kwargs,
    ):
        self.vector_requests.append(
            (user_id, query, list(query_embedding), embedding_model, limit, kwargs)
        )
        return list(self.vector_matches)

    def list(self, user_id, query, limit, **kwargs):
        self.lexical_requests.append((user_id, query, limit, kwargs))
        return []


class StickerEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def test_semantic_text_preserves_user_labels_and_description(self):
        text = build_sticker_semantic_text(
            "深夜工作时给对方打气",
            ("加油", "鼓励"),
        )

        self.assertIn("加油", text)
        self.assertIn("鼓励", text)
        self.assertIn("深夜工作时给对方打气", text)

    def test_query_text_marks_agent_intent_as_retrieval_query(self):
        text = build_sticker_query_text("轻松地鼓励正在加班的用户")

        self.assertIn("Instruct:", text)
        self.assertIn("Query:", text)
        self.assertIn("轻松地鼓励正在加班的用户", text)

    async def test_backfill_skips_unchanged_embedding_and_indexes_missing_sticker(self):
        repository = FakeStickerRepository()
        provider = FakeEmbeddingProvider()
        existing = _sticker("stk_existing", tags=("开心",))
        missing = _sticker(
            "stk_missing",
            owner_type="user",
            description="适合鼓励辛苦工作的朋友",
        )
        repository.active = [existing, missing]
        repository.embedding_metadata = {
            existing.sticker_id: build_sticker_semantic_text(
                existing.description,
                existing.semantic_tags,
            )
        }

        with (
            patch.object(vector_index.settings, "sticker_vector_search_enabled", True),
            patch.object(vector_index.settings, "embedding_api_key", "configured"),
            patch.object(
                vector_index,
                "PostgresStickerRepository",
                return_value=repository,
            ),
            patch.object(vector_index, "get_embedding_provider", return_value=provider),
        ):
            completed = await vector_index.backfill_sticker_embeddings(limit=10)

        self.assertEqual(completed, 1)
        self.assertEqual(repository.upserts[0][0], "stk_missing")
        self.assertEqual(len(provider.inputs), 1)

    async def test_vector_search_passes_current_user_scope_to_repository(self):
        repository = FakeStickerRepository()
        provider = FakeEmbeddingProvider()
        repository.vector_matches = [
            _sticker("stk_user_b", owner_type="user", tags=("晚安",))
        ]

        with (
            patch.object(vector_index.settings, "sticker_vector_search_enabled", True),
            patch.object(vector_index.settings, "embedding_api_key", "configured"),
            patch.object(
                vector_index,
                "PostgresStickerRepository",
                return_value=repository,
            ),
            patch.object(vector_index, "get_embedding_provider", return_value=provider),
        ):
            result = await vector_index.search_sticker_embeddings(
                "user_b",
                "想让熬夜的朋友早点休息",
                3,
            )

        self.assertEqual([item.sticker_id for item in result], ["stk_user_b"])
        self.assertEqual(repository.vector_requests[0][0], "user_b")
        self.assertNotIn("conversation_id", repository.vector_requests[0][5])


if __name__ == "__main__":
    unittest.main()
