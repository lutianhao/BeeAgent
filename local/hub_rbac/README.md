# BeeAgent Hub RBAC 扩展（方案 B）

在 QwenPaw Hub 上叠加业界常见的 **RBAC + 配额**，不替换原有 `admin`/`user` 布尔角色。

## 迭代期：按用户重建同步

声明式清单：[`user_sync_roster.yaml`](./user_sync_roster.yaml)

| 命令 | 作用 |
|------|------|
| `./local/scripts/manage.sh sync-users` | 按 roster 重申各用户角色 + 期望的组织技能安装 |
| `./local/scripts/manage.sh sync-users --dry-run` | 只打印将要做的变更 |
| `./local/scripts/manage.sh sync-skills --force` | **先** `sync-users`，再刷全部 runtime 官方 Skills/工具 ACL |
| `./local/scripts/manage.sh restart` | 重启 Hub 后自动走 `sync-skills`（含 roster） |

当前账号与期望（详见 yaml）：

| 用户 | 角色 | 同步刷新要点 |
|------|------|----------------|
| `admin` | Hub 超管 | 全量 Skills/工具；运营与审计自测 |
| `lutianhao` | `bee.member` | 主测：市场发布/安装/分享/沙箱；装 `bank-yuqing-daily-docx` |
| `tianmeng` | `bee.member` | 遂宁日报技能 owner；装同技能 |
| `dengshan` | `bee.member` | 标准成员全量同步 |
| `wangtao` | `bee.member` | 标准成员；装 `demo-org-skill` |
| `chenyanan` | `bee.member` | 标准成员；装 `bank-yuqing-daily-docx` |

改权限或加新用户：

1. 编辑 `user_sync_roster.yaml`
2. `./local/scripts/manage.sh sync-skills --force`
3. 让在线用户刷新页面 / 必要时重启其个人 runtime

查看现状对照：

```bash
python local/scripts/apply_user_sync_roster.py --dump
```

## 借鉴的行业模型

| 来源 | 借鉴点 |
|------|--------|
| RBAC (NIST / 云厂商 IAM) | 用户 ← 角色 ← 权限；权限为稳定字符串 |
| Kubernetes RBAC | `resource:verb` / `resource:verb:name`；支持 `*` |
| SaaS 配额 | 日调用次数、日 Token；与月度组织预算并存 |
| 默认拒绝 + 管理员旁路 | 细粒度资源默认需授权；Hub `admin` 始终放行 |

## 权限字符串

```
chat:use
skill:use                 # 任意官方 skill
skill:use:<skill_name>    # 如 skill:use:koujing-xiezhuan
skill:use:*               # 同 skill:use
tool:use                  # 任意可控 builtin 工具
tool:use:<tool_name>      # 如 tool:use:web_search / web_fetch
tool:use:*                # 同 tool:use
org_skill:publish         # 发布/更新自己的组织技能
org_skill:manage          # 运营货架（精选/代管）
org_kb:use|write|manage
rbac:manage               # 管理角色/配额（通常仅 admin）
quota:bypass              # 不受日配额限制
```

## 内置角色

| role_id | 含义 |
|---------|------|
| `bee.member` | 默认可聊天 + 全部官方 Skill + 联网工具 + 组织技能发布 + KB 读写 |
| `bee.restricted` | 仅 `chat:use`，无专项 Skill / 联网工具 |
| `bee.operator` | member + `org_skill:manage` / KB manage / `rbac:manage` |
| `custom.<user_id>` | 成员页勾选偏离模板时自动生成（迭代期尽量改回 roster 角色） |

Hub 原生 `role=admin` **不依赖**上表，直接旁路全部检查。

## 配额

用户级（可空=继承组织默认）：

- `daily_chat_limit`：每日对话请求次数（-1 不限）
- `daily_token_limit`：每日 Token（-1 不限；与 Hub 月度组织预算叠加）

组织默认写在 `hub_settings.beeagent_rbac_defaults`。

## 管理 UI

Hub 管理中心侧栏 → **权限控制**（admin）：

- 成员：应用角色模板，或直接勾选 Skill / 工具
- 角色：维护可复用模板
- 组织默认：日对话/Token 上限与时区

Console 临时改完后，请把结果回写到 `user_sync_roster.yaml`，否则下次 `sync-users` 会按清单覆盖。

## 新账号默认模型 / 工具

新创建用户的个人运行时在 **首次启动** 时会自动注入（需 Hub 进程已加载 `DEEPSEEK_API_KEY`）：

- 模型：`deepseek` / `deepseek-flash`
- 工具：`web_search`（provider=`deepseek`）、`web_fetch`

也可：

```bash
./local/scripts/manage.sh provision-defaults
./local/scripts/manage.sh sync-skills --force
```

## API 摘要

- `GET /api/hub/me/entitlements`
- `GET/POST /api/hub/admin/rbac/roles`
- `DELETE /api/hub/admin/rbac/roles/{role_id}`
- `PUT /api/hub/admin/rbac/users/{user_id}/roles`
- `GET /api/hub/admin/rbac/users/{user_id}/entitlements`
- `GET/PUT /api/hub/admin/rbac/users/{user_id}/quota`
- `GET/PUT /api/hub/admin/rbac/org-defaults`
