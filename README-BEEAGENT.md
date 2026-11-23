# BeeAgent 部署说明

本仓库（`lutianhao/BeeAgent`）在 QwenPaw 之上加入了 BeeAgent Hub 定制：品牌、RBAC、组织技能库、官方专项技能，以及本机部署脚本。

目标：**其他服务器 `git pull` 后，复制密钥模板 → 填 key → 构建 console → 启动**。

## 仓库布局

```text
.
├── console/                 # 前端源码
├── src/qwenpaw/             # 后端源码
├── hub.yaml.example         # Hub 配置模板（复制为 hub.yaml）
├── local/                   # 部署资产（进 git；密钥除外）
│   ├── official_skills/     # 官方专项技能包
│   ├── official_default/    # 默认人格文案
│   ├── official_agents/     # 历史专家 agent（默认同步时会停用）
│   ├── brand/               # 品牌素材
│   ├── docs/                # 内部说明
│   ├── scripts/             # manage / bootstrap / sync
│   ├── secrets/             # 仅 *.example + README（真实密钥 gitignore）
│   └── run/                 # 运行时 pid/日志（gitignore）
└── README-BEEAGENT.md
```

## 新机器快速上手

```bash
git clone git@github.com:lutianhao/BeeAgent.git
cd BeeAgent
git checkout beeagent   # 当前 BeeAgent 改动在该分支

# 1) 生成本机配置（不覆盖已有文件）
chmod +x local/scripts/*.sh
./local/scripts/bootstrap.sh

# 2) 填写密钥与公网地址
$EDITOR local/secrets/deepseek.env
$EDITOR hub.yaml

# 3) Python 环境（示例：已有 conda env 名 qwenpaw）
conda activate qwenpaw
pip install -e .

# 4) 构建并同步 Console（Hub 读 src/qwenpaw/console）
cd console && npm ci && npm run build && cd ..
rsync -a --delete console/dist/ src/qwenpaw/console/

# 5) 启动
./local/scripts/manage.sh start
./local/scripts/manage.sh status
```

浏览器打开 `http://<主机>:8100/`。首次管理员账号以你填写的 `local/secrets/hub-admin.txt` / Hub 引导为准。

## 日常命令

| 命令 | 作用 |
|------|------|
| `./local/scripts/manage.sh start` | 启动 Hub |
| `./local/scripts/manage.sh stop` | 停止 |
| `./local/scripts/manage.sh restart` | 重启并同步官方 skills |
| `./local/scripts/manage.sh status` | 健康检查 |
| `./local/scripts/manage.sh logs -f` | 跟日志 |

## 密钥清单

| 文件 | 用途 |
|------|------|
| `local/secrets/deepseek.env` | DeepSeek API（对话 / 搜索） |
| `local/secrets/ark.env` | 火山方舟（可选） |
| `local/secrets/hub.env` | Hub 监听 host/port |
| `local/secrets/hub-admin.txt` | 管理员备忘（勿提交） |
| `hub.yaml` | `public_base_url` 等 Hub 配置 |

真实密钥已被 `.gitignore` 排除；只提交 `*.example`。

## 与旧「兄弟目录」布局兼容

若你仍使用 `BeeAgent/local` + `BeeAgent/QwenPaw` 并列，`manage.sh` 会自动识别。推荐新部署直接使用仓库内 `local/`。
