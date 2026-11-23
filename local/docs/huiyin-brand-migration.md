# 汇银品牌迁入 BeeAgent / QwenPaw Console

> 状态：Phase 1 已实施（主色 / logo / 关键文案）；欢迎区 + 侧栏默认头像已切 HY；Phase 2 登录整页皮肤待定  

> 对照源：`huiyin_fe/apps/custom`（线上汇银咨询 / 小蜜蜂）  
> 目标壳：`QwenPaw/console`（Hub 实际服务 `src/qwenpaw/console`）

---

## 1. 结论摘要

| 问题 | 结论 |
|------|------|
| 有没有合适迁移方案？ | **有**：抽「品牌包」覆盖 token / 静态资源 / 文案，而不是整页移植 Vue 业务 |
| 要不要 AI 生图补素材？ | **现阶段不需要**。汇银现有 logo、登录背景、能力图标已够 Phase 1–2；缺的主要是定名、SVG 双色 logo、暗色规范与构建同步流程 |
| 不建议做什么？ | 不把 `huiyin-admin` / `custom` 业务页整仓搬进 React Console |

---

## 2. 两边现状

### 2.1 汇银线上（`huiyin_fe/apps/custom`）

| 维度 | 内容 |
|------|------|
| 产品 | 汇银咨询 · 小蜜蜂 / 金融声誉智护平台 |
| 技术 | Vue + Tailwind；主题写在 `src/assets/css/main.css` |
| 主色 | 品牌蓝 `#1668DC`；强调橙 `#F2830A`；标题深蓝 `#123B7A` |
| 登录视觉 | 《汇银咨询_小蜜蜂登录页视觉资产包》：蓝渐变底 + 白字 logo + 橙点缀 |

### 2.2 BeeAgent 壳（`QwenPaw/console`）

| 维度 | 内容 |
|------|------|
| 产品 | 全程 QwenPaw 文案与虎头形象 |
| 技术 | React + Ant Design + `src/styles/tokens.css`（`--app-*`） |
| 主色 | `--app-accent: #ff7f16`（偏橙，与汇银「蓝主色 + 橙强调」不一致） |
| Hub 静态目录 | 运行时吃的是 `src/qwenpaw/console`，不是仅 `console/dist` |

---

## 3. 推荐方案：品牌包换肤（三阶段）

### Phase 1 — 品牌包（必做，低风险）

1. 在仓库建品牌目录，例如：

   ```text
   local/brand/huiyin/
     README.md
     colors.json          # 主色 / 强调色 / 暗色映射
     images/
       logo.png           # 来自 custom/public/images/logo.png
       logo-mark.png      # logo-1.png（小蜜蜂主视觉）
       hy-logo-white.png  # 登录/深色底
       favicon.ico
       icon.png
     login/               # Phase 2 再用
       bg.svg
       bg.png
       icons/*.svg
   ```

2. 覆盖 / 映射到 Console：

   | 汇银资产 | QwenPaw 落点 |
   |----------|--------------|
   | `logo.png` / `logo-1.png` | `console/public/qwenpaw.png`、聊天默认头像、Hub/侧栏品牌图 |
   | `hy-logo-white.png` | Login 顶栏、深色底 logo |
   | `favicon.ico` / `icon.png` | `index.html` favicon、`online.svg` 替补 |
   | `main.css` 品牌色 | `styles/tokens.css` 的 `--app-accent*` 族 |
   | 产品名文案 | `AppBrand`、Login、HubShell、`document.title`、相关 i18n |

3. **同步改 Ant Design**：仅改 CSS 变量不够，需在 `ConfigProvider` 的 `theme.token.colorPrimary` 对齐 `#1668DC`。

4. **构建后必须**把产物同步到 `QwenPaw/src/qwenpaw/console/`（Hub 实际托管目录），再重启 Hub。

### Phase 2 — 登录 / 欢迎皮肤（可选）

- 用汇银登录资产重做 QwenPaw `Login` **视觉**（蓝渐变背景、白字 logo、橙 CTA）。
- **保留**现有 Hub 账号密码表单与 `/api/auth/login` 等接口。
- **不要**直接移植 `Login.vue`（鉴权模型、路由、组件库均不同）。

### Phase 3 — 明确不做

- 不迁移舆情监测、简报编辑、渠道图标矩阵等业务页到 Console。
- 那些能力若要进 BeeAgent，应以 Skill / Agent 能力或独立嵌入页呈现，而不是搬 Vue 路由树。

---

## 4. 颜色映射建议

来源：`huiyin_fe/apps/custom/src/assets/css/main.css` 注释（登录页视觉资产包）。

| 语义 | 汇银 | 建议写入 QwenPaw |
|------|------|------------------|
| Primary / 主操作 | `#1668DC` | `--app-accent`、antd `colorPrimary` |
| Accent / CTA·警示 | `#F2830A` | 次强调 token（如 `--app-brand-accent`），勿与主色抢戏 |
| 标题字色（浅底） | `#123B7A` | 导航强调字 / Hub 标题 |
| 渐变蓝档 | `#0879F2` → `#013D9A` | 仅 Login 背景，不进全局 surface |
| 暗色主色 | 提亮蓝（约 `214 90% 62%`） | `html.dark-mode` 下 `--app-accent` |

原则：**蓝做主色，橙做强调**——与当前 QwenPaw「全局橙」调换角色，而不是简单换一张 logo。

---

## 5. 文案与定名（实施前必须拍板）

对外需要统一一套称呼，避免混用：

| 候选 | 适用场景 |
|------|----------|
| 汇银咨询 | 公司 / 登录顶栏 |
| 小蜜蜂 | 产品主名 / 欢迎语 |
| BeeAgent | 工程 / 仓库 / 对内 |

建议在 `local/brand/huiyin/brand.json` 固定：

```json
{
  "company": "汇银咨询",
  "product": "小蜜蜂",
  "product_full": "小蜜蜂 · 金融声誉智护平台",
  "engineering": "BeeAgent",
  "tagline": "AI赋能风控，数智守护声誉"
}
```

---

## 6. 关键替换清单（Phase 1 代码触点）

实施时按此勾选（路径相对 `QwenPaw/console`）：

- [ ] `public/` 静态资源替换
- [ ] `src/styles/tokens.css`（含 dark）
- [ ] Ant Design `ConfigProvider` 主题
- [ ] `src/layouts/AppBrand.tsx`
- [ ] `src/pages/Login/index.tsx`
- [ ] `src/pages/Hub/components/HubShell.tsx`（品牌字、返回文案）
- [ ] `src/os/MenuBar.tsx` / `DesktopOS.tsx` / Tauri 加载页（若启用桌面）
- [ ] `index.html` title / favicon
- [ ] i18n：`hub.*`、欢迎相关字符串；聊天默认头像
- [ ] 构建脚本：`dist` → `src/qwenpaw/console` 同步（写入 `local/scripts` 或文档化）

---

## 7. 还缺什么

| 缺口 | 影响 | 建议 |
|------|------|------|
| 产品定名未统一 | 文案混乱 | 先定 `brand.json` |
| 浅/深底矢量 logo | Console 登录现用 `logo-light/dark.svg` | 设计导出 SVG；过渡期可用 PNG |
| 暗色模式完整规范 | 仅有 custom Tailwind dark 片段 | Phase 1 写死暗色 `--app-accent` 映射即可 |
| Ant Design 主题联动 | 部分按钮/链接仍偏旧主色 | 与 token 同步改 |
| Hub 静态同步流程 | 改了 dist 页面不更新 | 文档 + `manage.sh` 或构建钩子 |
| 版权页脚 | 对外演示缺公司信息 | 登录页补「融汇银通…」与商务邮箱（按需） |
| Tauri 图标 | 桌面端仍显示 QwenPaw | 有桌面发布再换 `src-tauri/icons` |
| 欢迎语 / 默认 Agent 展示名 | 仍偏「智能助手 / QwenPaw」 | 对齐 `local/official_default` 与品牌话术 |

---

## 8. 关于「是否需要生图能力」

**结论：Phase 1–2 不依赖 AI 生图。**

| 素材 | 是否已有 | 是否建议 AI 生成 |
|------|----------|------------------|
| 汇银 / 小蜜蜂 logo | 有（PNG） | **否** — 品牌标识应以设计稿/商标文件为准，AI 易变形、侵权与不一致 |
| 登录背景 | 有 `bg.svg` / `bg.png` | **否** |
| 能力卡图标 | 有 3 个 SVG | **否** |
| 浅/深 SVG logo | 缺 | **优先设计导出**；若仅作内部占位可用 PNG，不建议 AI「仿标」 |
| 装饰插画 / 空状态图 | 非必须 | 可选；若要统一风格再考虑生图，且需人工验收 |

若后续需要生图，适用场景仅限：

- 非商标类装饰插画、空状态、Skill 卡片配图；
- 明确标注「占位 / 非正式品牌资产」；
- 正式对外前仍用设计确认过的文件替换。

**当前仓库已具备迁品牌所需的核心视觉资产**，缺的是工程化接入与产品定名，不是缺图。

---

## 9. 建议落地顺序

1. 确认对外名称与 `brand.json`  
2. 建立 `local/brand/huiyin/` 并拷贝现有资产（不改源文件语义）  
3. Phase 1：tokens + antd + logo + 文案  
4. 构建 → 同步 `src/qwenpaw/console` → 重启 Hub 验收  
5. （可选）Phase 2 登录皮肤  
6. （可选）版权页脚、桌面图标  

---

## 10. 验收清单

- [ ] 登录页 / 侧栏 / Hub 不再出现 QwenPaw 主品牌字样（或仅工程调试可见）  
- [ ] 主按钮、选中态为品牌蓝，而非橙 `#ff7f16`  
- [ ] Favicon 与浏览器标题为汇银 / 小蜜蜂  
- [ ] `lutianhao` 与 `admin` 强制刷新后一致  
- [ ] 暗色模式下对比度可读  
- [ ] 重启 Hub 后仍为新资源（证明已写入 package console）  

---

## 11. 相关路径速查

```text
huiyin_fe/apps/custom/src/assets/css/main.css
huiyin_fe/apps/custom/public/images/
huiyin_fe/apps/custom/public/images/login/
huiyin_fe/apps/custom/src/views/Login.vue

QwenPaw/console/src/styles/tokens.css
QwenPaw/console/src/layouts/AppBrand.tsx
QwenPaw/console/src/pages/Login/index.tsx
QwenPaw/console/public/
QwenPaw/src/qwenpaw/console/          # Hub 实际静态资源
```

手工同步示例（实施阶段）：

```bash
# 构建 Console 后同步到 Hub 托管目录
rsync -a --delete QwenPaw/console/dist/ QwenPaw/src/qwenpaw/console/
./local/scripts/manage.sh restart
```
