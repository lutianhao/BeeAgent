# （已弃用）BeeAgent 官方智能体包

专家能力已迁移为 Skills，见 [`../official_skills/`](../official_skills/)。

请使用：

```bash
./local/scripts/manage.sh sync-skills --force
```

本目录仅保留历史 SOUL 原文，供对照；Hub 启动时不再注入为独立 Agent（旧 profile 会被 `sync-skills` 设为 `enabled: false`）。
