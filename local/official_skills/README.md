# BeeAgent 官方 Skills

声誉管理专项能力以 **Skill** 形式挂在 **默认通用智能体** 上，不再拆成多个专家 Agent。

来源：`local/coze智能体提示词/`，已去掉 Coze `LibraryBlock` / `web_pilot` / 外部知识库，改为 QwenPaw 的 `web_search`、`web_fetch` 与工作区文件。

## 同步到全部 Hub 用户

```bash
./local/scripts/manage.sh sync-skills --force
```

`manage.sh start` 成功后也会自动同步一次。

## 当前包含

| Skill | 能力 |
|-------|------|
| koujing-xiezhuan | 口径撰写 |
| wangping-huashu | 网评话术 |
| shensu-chegao | 申诉撤稿函 |
| yuqing-yanpan | 舆情研判 |
| yuan-xiezhuan | 预案撰写 |
| shiqian-pinggu | 事前评估 |
| paicha-fangan | 排查方案 |
| weike-wenan | 微课文案 |
| yanlian-jiaoben | 演练脚本 |
| shuju-chuli | 数据处理（Excel 打标回填并交付） |
| yuqing-baogao | 报告生成（周报/月报/季度报/年报 Word，年报模板做减法） |

用户在默认对话里直接提需求即可；Agent 会按 description 匹配并加载对应 Skill。
