# FileCortex v6.3.1 前端深度分析报告

> **分析日期**: 2026-05-10 (审计更新)
> **分析范围**: `templates/index.html`, `static/css/style.css`, `static/js/{state,api,ui,main}.js`
> **后端参考**: `routers/`, `file_cortex_core/config.py`, `web_app.py`

---

## 1. UI 是否体现了最新架构、功能与设计？

### 1.1 架构对齐度：**A- (88/100)** — v6.3.1 评估

**已体现的后端能力：**

| 后端功能 | 前端覆盖 | 位置 |
|----------|----------|------|
| 项目打开/树浏览 | ✅ | `main.js:175-225` |
| 4 模式搜索 (smart/exact/regex/content) | ✅ | `index.html:52-57` |
| WebSocket 实时搜索 | ✅ | `main.js:614-665` |
| 搜索停止按钮 | ✅ | `main.js:623,667-677` |
| 文件预览 + 编辑 | ✅ | `main.js:372-410,893-916` |
| Staging 管理 + 后端同步 | ✅ | `main.js:783-800` |
| Favorites 分组 | ✅ | `main.js:803-823` |
| 自定义工具执行 (WebSocket) | ✅ | `main.js:700-773` |
| 快速分类 | ✅ | `main.js:688-698` |
| Context 生成 (Markdown/XML) | ✅ | `main.js:866-891` |
| API Token 认证 (HTTP + WS) | ✅ | `api.js:3-12`, `main.js:632` |
| 全局设置 (preview_limit/token_threshold/allowed_extensions) | ✅ | `main.js:257-283` |
| 项目设置持久化 | ✅ | `main.js:234-248,341-370` |

**v6.3.1 已修复的前端问题：**

| 问题 | 修复 |
|------|------|
| `allowed_extensions` 前后端不一致 | `GlobalSettings` 新增字段 |
| `tokenThreshold` 前端 100000 vs 后端 128000 | 统一为 128000 |
| `bootstrap.Modal.getInstance` 空值崩溃 (3处) | null guard added |
| API Token 未在 HTTP 请求中发送 | `_fetch` 注入 `X-API-Token` header |

---

## 2. 硬编码现象与灵活性分析

### 2.1 已修复的硬编码问题

| 问题 | 位置 | 修复 |
|------|------|------|
| **HC-1: API 端点散布** | `api.js` 18个硬编码端点字符串 | 已集中于 `state.js:config.endpoints` (47行) |
| **HC-3: 版本号双重硬编码** | `index.html:8,25` | 已改为 `{{ version }}` Jinja2 注入 |
| **HC-4: Token 阈值不一致** | `state.js:20` 128000 vs 后端 100000 | 统一为 **128000** |

### 2.2 仍存在的硬编码

| 问题 | 影响 | 建议 |
|------|------|------|
| CSS 魔术值 (颜色/尺寸) | 无亮色主题 | P2: 引入 CSS 变量 + `prefers-color-scheme` |
| 内联样式 (sidebar width) | 覆盖 CSS | 移到 CSS 类 |
| 文件图标为文字 "Folder"/"File" | 缺乏视觉区分 | 使用图标库 |

---

## 3. 重要 BUG 修复清单 (v6.3.1)

| ID | 问题 | 位置 | 状态 |
|----|------|------|------|
| BUG-1 | API Token HTTP 请求未发送 | `api.js:3-16` | ✅ Fixed |
| BUG-2 | `api_token` 不在全局设置中 | `main.js:536`, `config.py` | ✅ Fixed (design: `window.__FCTX_API_TOKEN__` via template) |
| BUG-3 | Token 阈值前后端不一致 | `state.js:20` vs `config.py:89` | ✅ Fixed (统一 128000) |
| BUG-5 | Favorites 组选择器只增不删 | `ui.js:124-131` | 待验证 |
| BUG-9 | `stageAll` 不传递排除规则 | `main.js:891-898` | ✅ 已修复 (当前代码传递 `applyExcludes=true`) |
| BUG-10 | 搜索结果右键打开路径收集器 | `ui.js:279-282` | 待验证 |
| BUG-11 | 响应式 CSS grid-template-columns 冲突 | `style.css:393-400` | 待修复 |

---

## 4. 布局合理性问题

### 4.1 当前布局：Sidebar(60px) | Left(md-3) | Center(md-7) | Right(md-2)

右侧 `col-md-2` 面板仍承载 Staging + Quick Categorize + Custom Tools + Export + Archive + Copy Paths + Generate Context，在 1366px 屏幕上过窄。

### 4.2 建议 (v7.0)

- 方案 A: 三面板 + 底部操作栏 (推荐，详见原报告)
- 方案 B: 标签页分离 Staging 和 Tools
- L-3: Generate Context 按钮提升到 Summary Bar

---

## 5. 修复优先级 (v6.3.x → v7.0)

### P0 (已完成 — v6.3.1)
- [x] API Token HTTP header 注入
- [x] `allowed_extensions` 前后端对齐
- [x] `tokenThreshold` 默认值统一
- [x] `bootstrap.Modal.getInstance` null guard
- [x] 版本号从 Jinja2 模板注入

### P2 (未来)
- [ ] BUG-5: Favorites 组选择器选项清理
- [ ] BUG-10: 搜索结果右键 → 上下文菜单
- [ ] BUG-11: 响应式 CSS grid 冲突
- [ ] HC-2: CSS 魔术值 → CSS 变量 + 亮色主题
- [ ] HC-5: 文字图标 → SVG/图标库
- [ ] 拖拽到 Staging (CSS 样式已有，JS 待实现)
