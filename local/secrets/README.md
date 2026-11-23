# Secrets（本机配置，勿提交真实密钥）

从 example 复制后填写：

```bash
cp local/secrets/deepseek.env.example local/secrets/deepseek.env
cp local/secrets/ark.env.example local/secrets/ark.env
cp local/secrets/hub.env.example local/secrets/hub.env
cp local/secrets/hub-admin.txt.example local/secrets/hub-admin.txt
cp hub.yaml.example hub.yaml   # 仓库根目录
```

`manage.sh` 会自动加载 `deepseek.env` / `hub.env`。
