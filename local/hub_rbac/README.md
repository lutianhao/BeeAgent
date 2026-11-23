# BeeAgent Hub RBAC 扩展（方案 B）

在 QwenPaw Hub 上叠加业界常见的 **RBAC + 配额**，不替换原有 `admin`/`user` 布尔角色。

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
rbac:manage               # 管理角色/配额（通常仅 admin）
quota:bypass              # 不受日配额限制
```

## 内置角色

| role_id | 含义 |
|---------|------|
| `bee.member` | 默认可聊天 + 全部官方 Skill + 联网工具 |
| `bee.restricted` | 仅 `chat:use`，无专项 Skill / 联网工具 |
| `bee.operator` | member + `rbac:manage`（业务管理员，非 Hub 超管） |
| `custom.<user_id>` | 成员页勾选偏离模板时自动生成的用户自定义角色 |

Hub 原生 `role=admin` **不依赖**上表，直接旁路全部检查。

## 配额

用户级（可空=继承组织默认）：

- `daily_chat_limit`：每日对话请求次数（-1 不限）
- `daily_token_limit`：每日 Token（-1 不限；与 Hub 月度组织预算叠加，先过日限再过月限）

组织默认写在 `hub_settings.beeagent_rbac_defaults`。

## 强制点（分阶段）

1. **已做**：库表、解析、Admin/Me API、同步 Skills 时按权限 enable/disable  
2. **已做**：  
   - `POST /api/console/chat`（经 Hub 反代）校验 `chat:use` + 日对话次数并记账  
   - Hub 组织模型网关：日 Token 预检 + settle 后累加；与月度组织预算叠加  
3. **已做**：Hub Console「权限控制」页（成员角色/配额、角色目录、组织默认）  
4. **下一步**：与汇银 SSO 角色映射  
5. **说明**：个人供应商 Key（不经 Hub 模型网关）只受日对话次数约束，不受日 Token 约束

## 管理 UI

Hub 管理中心侧栏 → **权限控制**（admin）：

- 成员：应用角色模板，或直接勾选 Skill / 工具；勾选与模板不一致时保存为 `custom.<user_id>`  
- 角色：维护可复用模板（系统角色 + 自建模板）  
- 组织默认：全员继承的日对话/Token 上限与时区  

改 Skill/工具权限后，建议执行 `./local/scripts/manage.sh sync-skills --force`。

## 新账号默认模型 / 工具

新创建用户的个人运行时在 **首次启动** 时会自动注入（需 Hub 进程已加载 `DEEPSEEK_API_KEY`）：

- 模型：`deepseek` / `deepseek-flash`（若仍是 Kilo 免费路由也会被纠正）
- 工具：`web_search`（provider=`deepseek`）、`web_fetch`

也可手动对全部已有运行时执行：

```bash
./local/scripts/manage.sh provision-defaults
# 或随 sync-skills 一并生效
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
