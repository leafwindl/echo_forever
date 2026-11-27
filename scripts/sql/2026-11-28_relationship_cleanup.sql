-- Echo 关系/主动消息旧结构清理
-- 执行前必须备份；本文件不会由应用启动自动执行。
-- 目标库：PostgreSQL 15+
--
-- 前置检查（人工执行）：
--   SELECT COUNT(*) FROM relationship_proposals;
--   SELECT COUNT(*) FROM relationship_direction_boundaries;
--   SELECT COUNT(*) FROM proactive_goals WHERE draft_text <> '';
--   SELECT COUNT(*) FROM presence_thoughts WHERE draft_text <> '';
--
-- 备份示例：
--   pg_dump --data-only --table=relationship_states --table=relationship_proposals \
--     --table=relationship_direction_boundaries --table=proactive_goals \
--     --table=presence_thoughts <db> > relationship_cleanup_backup.sql

BEGIN;

-- 旧关系模式/类型/分数：代码已不读，全部由 stage + affection 取代。
ALTER TABLE relationship_states DROP COLUMN IF EXISTS relationship_mode;
ALTER TABLE relationship_states DROP COLUMN IF EXISTS relationship_type;
ALTER TABLE relationship_states DROP COLUMN IF EXISTS relationship_type_updated_at;
ALTER TABLE relationship_states DROP COLUMN IF EXISTS score;

-- 主动消息草案：新链路只保存 intent/plan/action_intent。
ALTER TABLE proactive_goals DROP COLUMN IF EXISTS draft_text;
ALTER TABLE presence_thoughts DROP COLUMN IF EXISTS draft_text;

-- 旧方向 proposal 与边界表：历史数据如不再需要，随备份一起删除。
DROP TABLE IF EXISTS relationship_proposals;
DROP TABLE IF EXISTS relationship_direction_boundaries;

COMMIT;
