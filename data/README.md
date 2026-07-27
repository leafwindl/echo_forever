# Echo 数据目录

Echo 1.0 仅使用 PostgreSQL + pgvector，业务数据不再写入本目录。

`data/backups/postgres/` 由 `echo-postgres-backup` 容器保存定时数据库备份。备份文件不会提交到 Git；恢复和保留策略见 `scripts/postgres_restore.sh` 与根目录 Compose 配置。

后端运行日志使用 Docker `json-file` 驱动并启用轮转，因此项目不维护单独的 `log/` 目录。生成的语音文件位于 `Echo-backend/static/voices/`，由后端定时清理。
