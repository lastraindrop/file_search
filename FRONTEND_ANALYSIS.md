# FileCortex v6.3.0 前端深度分析报告

> **分析日期**: 2026-05-09
> **分析范围**: `templates/index.html`, `static/css/style.css`, `static/js/{state,api,ui,main}.js`
> **后端参考**: `routers/`, `file_cortex_core/config.py`, `web_app.py`

---

## 目录

1. [UI 是否体现了最新架构、功能与设计？](#1-ui-是否体现了最新架构功能与设计)
2. [硬编码现象与灵活性分析](#2-硬编码现象与灵活性分析)
3. [界面直观度与用户体验](#3-界面直观度与用户体验)
4. [重要 BUG 清单与修复方案](#4-重要-bug-清单与修复方案)
5. [布局合理性问题](#5-布局合理性问题)

---

## 1. UI 是否体现了最新架构、功能与设计？

### 1.1 架构对齐度：**B+ (85/100)**

**已体现的后端能力：**

| 后端功能 | 前端覆盖 | 位置 |
|----------|----------|------|
| 项目打开/树浏览 | ✅ | `main.js:165-216` |
| 4 模式搜索 (smart/exact/regex/content) | ✅ | `index.html:52-57` |
| WebSocket 实时搜索 | ✅ | `main.js:523-566` |
| 文件预览 + 编辑 | ✅ | `main.js:275-313`, `773-796` |
| Staging 管理 + 后端同步 | ✅ | `main.js:663-681` |
| Favorites 分组 | ✅ | `main.js:683-703` |
| 自定义工具执行 (WebSocket) | ✅ | `main.js:580-653` |
| 快速分类 | ✅ | `main.js:568-578` |
| Context 生成 (Markdown/XML) | ✅ | `main.js:746-771` |
| 路径收集与格式化 | ✅ | `main.js:900-934` |
| 批量操作 (重命名/删除/移动) | ✅ | `main.js:473-880` |
| 全局设置 | ✅ | `main.js:241-273` |
| 项目设置持久化 | ✅ | `main.js:224-239` |
| 工作区 Pin/Recent | ✅ | `main.js:156-163` |

**未充分体现的后端能力：**

| 缺失功能 | 影响 | 建议 |
|----------|------|------|
| **文件创建** (`POST /api/fs/create`) | 用户无法通过 Web UI 创建新文件或文件夹 | 在中心面板添加 "+" 按钮 |
| **标签管理** (`POST /api/project/tag`) | UI 无法给文件添加/移除标签，但 `updateFileMetaUI()` 尝试显示标签 | 添加标签输入 UI |
| **会话保存** (`POST /api/project/session`) | 无法保存/恢复 UI 会话状态 | 未来添加 |
| **项目排除规则编辑** | 只能通过搜索栏的 Skip 输入间接修改，缺少专门 UI | 添加项目设置面板 |
| **自定义工具在线配置** | 工具只能在桌面端 `file_search.py` 中配置，Web 端无法增删 | 添加工具管理模态框 |
| **快速分类在线配置** | 同上，分类按钮配置依赖后端预设 | 添加分类管理 UI |
| **Prompt 模板在线编辑** | 只能选择已有模板，无法创建或编辑 | 添加模板编辑器 |
| **Collection Profiles 在线编辑** | 只能选择已有配置文件 | 添加配置文件管理 |
| **API Token 认证 (HTTP Header)** | 后端 `web_app.py:49` 检查 `X-API-Token` header，但前端 `_fetch()` 从未发送该 header | **BUG** — 见第4节 |

### 1.2 设计理念一致性

- ✅ 单页应用 (SPA) 架构与后端 FastAPI + Jinja2 模板配合良好
- ✅ ES Modules 模块化 (`state → api → ui → main`) 与后端微内核架构呼应
- ⚠️ `window.App` 全局暴露模式是为了兼容 HTML 中的 `onclick` 内联处理器，这是技术债务
- ⚠️ CDN 依赖无 SRI hash，存在供应链攻击风险

---

## 2. 硬编码现象与灵活性分析

### 2.1 严重硬编码问题

#### **HC-1: API 端点字符串散布** (`api.js`)
```javascript
// api.js 中有 18 个硬编码的 API 路径字符串
'/api/project/config?path=...'  // line 37
'/api/global/settings'           // line 53, 58
'/api/fs/children'               // line 66
'/api/content?path=...'          // line 75
// ... 等 14 个
```
而 `state.js:23-27` 中 `config.endpoints` 只集中管理了 3 个端点。**不一致**：应全部集中在 `config.endpoints`。

#### **HC-2: CSS 魔术值** (`style.css`)
```css
--bg-dark: #020617;          /* line 4  - 无法切换主题 */
--accent: #38bdf8;           /* line 6  - 无可访问性对比度调整 */
max-width: 450px;            /* line 109 - 写死的输入框宽度 */
max-width: 300px;            /* line 118 - 写死的搜索框宽度 */
max-width: 250px;            /* line 119 - 写死的排除框宽度 */
max-width: 110px;            /* line 120 - 写死的模式下拉宽度 */
```
**问题**: 无亮色主题支持，所有尺寸/颜色写死在 CSS 中，无 `prefers-color-scheme` 媒体查询。

#### **HC-3: 版本号双重硬编码** (`index.html:8,25`)
```html
<title>FileCortex v6.3.0 Production | Workspace Orchestrator</title>
<span class="badge ...">v6.3.0 Production</span>
```
版本号写死在 HTML 中，未从后端注入。与 `pyproject.toml`/`file_search.py`/`web_app.py` 中的版本号需手动同步。

#### **HC-4: Token 阈值与默认值** (`state.js:18-21`)
```javascript
defaults: {
    archiveName: 'context_backup.zip',   // 硬编码
    tokenThreshold: 128000,               // 与后端 config.py:89 的 100000 不一致！
    tokenRatio: 4                         // 后端无对应配置
}
```
**BUG**: 前端默认 token 阈值 (128000) 与后端 `ProjectConfig.token_threshold` 默认值 (100000) 不一致。

#### **HC-5: 文件图标硬编码为文字** (`ui.js:320`)
```javascript
const icon = node.type === 'dir' ? 'Folder' : 'File';
```
使用英文字符串 "Folder"/"File" 作为图标而非 SVG/图标库。缺乏视觉区分度。

#### **HC-6: Sidebar 宽度硬编码** (`index.html:102`)
```html
<aside ... style="width: 60px; transition: width 0.3s;">
```
内联样式与 `state.js:13-16` 的配置重复。HTML 内联样式优先级最高，可能覆盖 CSS 主题。

#### **HC-7: 搜索结果数量限制未暴露** (`main.js`)
后端 `search.py:23` 有 `MAX_SEARCH_RESULTS = 5000`，但前端无法配置此限制，也无法显示"结果已截断"提示。

### 2.2 灵活性评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 主题/外观 | 2/10 | 仅暗色主题，无 `prefers-color-scheme`，无用户自定义 |
| 布局响应性 | 5/10 | 有基本移动端断点但功能受限 |
| API 路由管理 | 3/10 | 大量硬编码端点字符串 |
| 配置与默认值 | 4/10 | 部分集中化但前后端不一致 |
| 可扩展性 | 3/10 | 无插件/扩展点设计 |

---

## 3. 界面直观度与用户体验

### 3.1 信息架构问题

#### **UX-1: 功能层级混乱 — Staging 与导出耦合**
当前布局将 **Staging（暂存列表）**、**Quick Categorize（分类按钮）**、**Custom Tools（工具按钮）**、**Export Format（格式选择）**、**Prompt Template（模板选择）**、**Include Blueprint（开关）**、**Archive（归档）**、**Copy Paths（路径收集）**、**Generate Context（生成上下文）** 全部塞在右侧 `col-md-2` 面板中。

**问题**: 这 9 个功能分属 3 个不同的工作流：
1. **Staging 工作流**: 添加文件 → 查看列表 → 编辑列表
2. **操作工作流**: 分类 / 工具执行 / 归档
3. **导出工作流**: 选择格式 → 选择模板 → 生成 → 复制

将它们全部放在一个狭窄的 2/12 列中，用户无法建立清晰的心理模型。

#### **UX-2: 工作流断裂 — 搜索结果到 Staging**
搜索结果 (左面板 "Results" 标签) 中的文件需要通过复选框选中 → 切换到 "Files" 标签或使用 Bulk Actions → Stage 才能添加到暂存。没有直接的 "Stage from search" 操作。

#### **UX-3: 缺少拖拽支持**
虽然 CSS 中有 `.drag-over` 样式 (`style.css:369-372`)，但实际 JS 代码中 **没有实现任何拖拽逻辑**。用户期望可以拖拽文件到 Staging 面板。

#### **UX-4: 键盘导航不完整**
帮助模态框 (`index.html:240-244`) 只列出了 5 个快捷键，但缺少：
- 搜索结果导航 (上下箭头)
- 文件树导航
- Enter 打开文件
- Staging 面板中的快捷删除

#### **UX-5: 无加载状态指示器**
`openProject()` 在加载过程中只显示 "Loading workspace tree..." 文字。搜索显示 "Searching..." 文字。缺少骨架屏 (skeleton) 或进度条。

#### **UX-6: 模态框堆叠问题**
批量重命名 (`main.js:473-521`) 使用了两层嵌套模态框 (先预览再确认)，但 Bootstrap 模态框不原生支持堆叠，可能导致 z-index 冲突或底层模态框滚动泄漏。

### 3.2 可用性细节问题

| 问题 | 位置 | 影响 |
|------|------|------|
| 文件树中目录点击即展开，无法仅选中目录 | `ui.js:362-365` | 用户想对目录操作时被迫展开 |
| 编辑器无语法高亮 | `main.js:780` | 编辑时只是纯文本 textarea |
| Note 覆盖层可能遮挡文件内容 | `index.html:157` | `position-absolute` + `translate-middle-y` 定位不可靠 |
| 长路径在 Staging 中只显示文件名 | `ui.js:94` | 无法区分同名文件 |
| 搜索无停止按钮 | `main.js:523-566` | 大项目搜索可能持续很久，无法中途取消 |
| 工具执行后 `confirm("Clear staging?")` | `main.js:607-611` | 使用原生 `confirm()` 不符合 UI 风格 |

### 3.3 体验评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 首次使用可理解性 | 5/10 | 界面元素密集，无 onboarding/引导 |
| 工作流连贯性 | 5/10 | 搜索→暂存→导出流程有断裂 |
| 视觉一致性 | 8/10 | Glassmorphism 风格统一，CSS 变量管理良好 |
| 反馈及时性 | 6/10 | Toast 通知好，但缺少加载/空状态/进度 |
| 键盘可访问性 | 4/10 | 基本快捷键存在但不够全面 |

---

## 4. 重要 BUG 清单与修复方案

### BUG-1: API Token 从未在 HTTP 请求中发送 [严重]

**位置**: `api.js:3-16` (`_fetch` 函数)
**症状**: 后端 `web_app.py:43-63` 的中间件检查 `X-API-Token` header，但前端的 `_fetch()` 从未附加此 header。如果设置了 `FCTX_API_TOKEN` 环境变量，**所有 HTTP API 请求将返回 401**。
**WebSocket** 的 token 传递 (通过 query parameter) 是正确的 (`main.js:537`)。

```javascript
// 当前代码 (api.js:3-16)
export async function _fetch(url, options = {}) {
    const res = await fetch(url, options);
    // ❌ 从未添加 X-API-Token header
    ...
}
```

**修复**:
```javascript
export async function _fetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = state.globalSettings.api_token || "";
    if (token) headers['X-API-Token'] = token;
    const res = await fetch(url, { ...options, headers });
    ...
}
```

但需要先解决 **BUG-2**。

---

### BUG-2: `api_token` 不在全局设置中 [严重]

**位置**: `main.js:536`, `config.py:109-118`
**症状**: `main.js:536` 读取 `App.state.globalSettings.api_token`，但：
1. 后端 `GlobalSettingsRequest` 模型 (`schemas.py:109-118`) 中 **没有 `api_token` 字段**
2. 前端 Settings 模态框 (`index.html:322-357`) 中 **没有 api_token 输入框**
3. 即便修复了 BUG-1 的 header 发送，token 值也永远为空字符串

**根因**: Token 配置设计为环境变量 (`FCTX_API_TOKEN`)，前端不可能通过 API 获取它（否则就是安全漏洞）。正确的做法是前端通过非受保护的端点或页面模板注入获取 token 的存在状态，而非 token 值本身。

**修复方案**: 
- 方案 A (推荐): 后端在渲染 `index.html` 时通过 Jinja2 模板注入 `window.__FCTX_TOKEN__`，前端在 `_fetch` 中使用
- 方案 B: 前端在 Settings 模态框中添加 API Token 输入框，存入 `localStorage`

---

### BUG-3: Token 阈值前后端不一致

**位置**: `state.js:20` vs `config.py:89`
**症状**: 前端默认 `tokenThreshold: 128000`，后端默认 `token_threshold: 100000`。当全局设置未保存时，前端使用 128000 的阈值显示警告，但后端使用 100000。

**修复**: 统一为后端值 `100000`，或从后端 `/api/global/settings` 获取默认值。

---

### BUG-4: `fetchContent` 的 `limitMb` 参数被忽略

**位置**: `api.js:74`
```javascript
export async function fetchContent(path, limitMb = 1) {
    const res = await _fetch(`/api/content?path=${encodeURIComponent(path)}`);
    // ❌ limitMb 参数从未使用，也未传给后端
```

**修复**: 后端 `/api/content` 端点已从 `global_settings.preview_limit_mb` 读取限制，此参数可删除，或添加到 query string 中作为用户覆盖。

---

### BUG-5: Favorites 组选择器只增不删

**位置**: `ui.js:124-131`
```javascript
groups.forEach((g) => {
    if (!currentOptions.includes(g)) {
        const opt = document.createElement('option');
        opt.value = g; opt.innerText = g;
        select.appendChild(opt);
    }
});
// ❌ 从不删除已不存在的 option
// ❌ 从不清理旧 option（可能导致重复）
```

**症状**: 当后端的 groups 改变后（如删除了一个组），下拉菜单中的旧选项仍然存在。

**修复**: 每次 `renderFavorites()` 时重建整个 select 的 options。

---

### BUG-6: `showFileNote` 的 Note 匹配逻辑有误

**位置**: `main.js:331-338`
```javascript
let note = notes[App.state.currentFile] || "";
if (!note) {
    const fileName = App.state.currentFile.split(/[\\\/]/).pop();
    Object.entries(notes).forEach(([key, val]) => {
        if (key.endsWith(fileName)) note = val;  // ❌ 粗糙的后缀匹配
    });
}
```

**问题**: 
1. 使用文件名后缀匹配可能匹配到错误的文件（如 `/src/utils.js` 和 `/test/utils.js`）
2. 应该使用精确路径匹配（后端已通过 `PathValidator.norm_path` 保证路径一致性）

**修复**: 删除 fallback 逻辑，只使用精确路径匹配。

---

### BUG-7: `updateFileMetaUI` 标签匹配逻辑同样有误

**位置**: `ui.js:62-69`
```javascript
if (matchedTags.length === 0) {
    Object.entries(tags).forEach(([key, val]) => {
        if (path && key && path.endsWith(key.split('/').pop())) {  // ❌ 同样的粗糙匹配
            matchedTags.push(...val);
        }
    });
}
```

同 BUG-6 的根因。**修复**: 使用精确路径匹配。

---

### BUG-8: 搜索 WebSocket 无取消/停止机制

**位置**: `main.js:523-566`
**症状**: 用户点击搜索后无法停止。虽然后端有 `stop_event` 支持 (`ws_routes.py:68`)，但前端没有发送停止消息的 UI 或逻辑。关闭搜索结果的 tab 不会关闭 WebSocket 连接。

**修复**: 添加 "Stop" 按钮，发送停止消息到 WebSocket，或关闭连接。

---

### BUG-9: `stageAll` 不传递搜索排除规则和模式

**位置**: `main.js:891-898`
```javascript
const data = await api.stageAll(App.state.projectPath);
// ❌ 未传递 mode 和 apply_excludes 参数
```

**修复**: 传递当前搜索设置：
```javascript
const data = await api.stageAll(App.state.projectPath, 'files', true);
```

---

### BUG-10: 右键菜单搜索结果的 `showPathCollector` 语义错误

**位置**: `ui.js:279-282`
```javascript
item.oncontextmenu = (e) => {
    e.preventDefault();
    window.App.showPathCollector([data.path]);  // 单个路径用 Path Collector？
};
```

右键搜索结果应该显示 **上下文菜单** (Stage/Fav/Copy/Delete)，而不是打开路径收集器。

**修复**: 改为 `window.App.showContextMenu(e, data.path)`。

---

### BUG-11: 响应式布局中 summary-bar CSS 冲突

**位置**: `style.css:393-400`
```css
.summary-bar,
.summary-primary,
.summary-metrics,
.search-option-grid {
    grid-template-columns: 1fr;    /* ❌ summary-bar 不是 grid */
    flex-direction: column;         /* ❌ 对非 flex 元素无效 */
    align-items: stretch;
}
```

`.summary-bar` 使用 `display: flex`，但媒体查询中将 `grid-template-columns` 应用到它上面，无效且混乱。

---

### BUG-12: 内联 `style="display:none !important"` 无法被 JS 正确切换

**位置**: `index.html:88`
```html
<div id="bulkActions" ... style="display:none !important;">
```

`!important` 使得 `main.js:819` 的 `setProperty('display', 'flex', 'important')` 必须使用 `!important` 才能覆盖。虽然代码中已这样做了，但这是脆弱的。应在 CSS 类中控制显示状态。

---

## 5. 布局合理性问题

### 5.1 核心问题：4 列布局中右侧面板过载

当前布局：`Sidebar(60px) | Left(md-3) | Center(md-7) | Right(md-2)`

**右侧 `col-md-2` 面板承载了过多职责：**

```
┌─────────────────────┐
│ Staging 标题 + 按钮  │  ← 列表管理
│ ┌─ stagingList ────┐ │
│ │ file1.txt    ×   │ │
│ │ file2.py     ×   │ │
│ └──────────────────┘ │
│ ─────────────────── │
│ Quick Categorize    │  ← 操作区
│ [Scripts] [Docs]    │
│ Custom Tools        │
│ [Summary] [Lint]    │
│ ─────────────────── │
│ Export Format  [▼]  │  ← 导出配置
│ Prompt Template [▼] │
│ [✓] Include Blueprint│
│ [  Archive Selection ]│ ← 操作按钮
│ [  Copy Paths       ]│
│ [══ Copy Context ══]│  ← 主要 CTA
└─────────────────────┘
```

**问题**:
1. 在 1920px 屏幕上，右侧面板仅 ~320px 宽，文件名经常截断
2. 在 1366px 屏幕上，右侧面板仅 ~227px 宽，几乎不可用
3. Staging 列表和导出配置混在一起，用户需要滚动才能看到 Generate Context 按钮
4. "Custom Tools" 和 "Quick Categorize" 是**项目级配置**的产物，但与 Staging 列表共享同一空间

### 5.2 建议布局重构

#### 方案 A：三面板 + 底部操作栏（推荐）

```
┌──────────────────────────────────────────────────────────────┐
│ Navbar: [项目路径] [Open] [Pin] [Settings] [Refresh]         │
├──────────────────────────────────────────────────────────────┤
│ Filter: [Find ___] [Skip ___] [Mode▼] [☑Dirs][☑Case] Search│
├──────────────────────────────────────────────────────────────┤
│ Summary: Workspace: my-project | 5 staged | 3 favorites     │
├────────┬─────────────────────────────┬───────────────────────┤
│Pinned  │ [Files] [Results] [Favs]    │  Staging (5)    [×]   │
│Recent  │ ┌─────────────────────────┐ │  ├ file1.txt         │
│        │ │  📂 src                 │ │  ├ file2.py          │
│ [Proj1]│ │    📄 main.py           │ │  ├ file3.js          │
│ [Proj2]│ │    📄 utils.py          │ │  └────────────────── │
│        │ │  📂 tests               │ │  Quick Actions       │
│        │ │    📄 test_main.py      │ │  [Scripts] [Docs]    │
│        │ └─────────────────────────┘ │  [Summary] [Lint]    │
│        │                             │  ──────────────────── │
│        │ ┌─────────────────────────┐ │  Export: [MD ▼]      │
│        │ │  // File Preview        │ │  Template: [None ▼]  │
│        │ │  def main():            │ │  [✓] Blueprint       │
│        │ │      pass               │ │  [Archive] [Paths]   │
│        │ │                         │ │  [═══ Context ═══]   │
│        │ └─────────────────────────┘ │                       │
│        │ [Stage][Fav][Notes][Copy]   │                       │
├────────┴─────────────────────────────┴───────────────────────┤
│ [☑] 2 selected | [Move] [Rename] [Delete] [Stage]           │
└──────────────────────────────────────────────────────────────┘
```

**关键改变**:
1. 左侧边栏保持在最左边 (60-210px)，包含 Pinned + Recent
2. 中间面板合并了 Files/Results/Favs (左) + Preview (右)
3. 右侧面板专注 Staging + 导出
4. Bulk Actions 移到底部固定栏
5. 文件操作按钮 (Stage/Fav/Notes/Copy) 紧跟在 Preview 下方

#### 方案 B：标签页分离 Staging 和 Tools

将右侧面板改为标签页：
- **Stage 标签**: Staging 列表 + 导出配置 + Generate Context
- **Tools 标签**: Quick Categorize + Custom Tools + Archive

这样至少解决了 "所有东西塞在一起" 的问题，但仍然受限于 `col-md-2` 的宽度。

### 5.3 其他布局问题

#### **L-1: 左面板 Tabs 语义不当**

"Files" / "Results" / "Favorites" 是三个**不同功能**，但共享同一个 `col-md-3` 空间：
- **Files**: 项目文件浏览器 — 这是**全局导航**
- **Results**: 搜索结果 — 这是**临时内容**
- **Favorites**: 收藏文件 — 这是**快捷访问**

将临时内容 (搜索结果) 和持久结构 (文件树) 放在同一位置意味着用户搜索后**失去文件树上下文**，回到文件树又**失去搜索结果**。

**建议**: 搜索结果应覆盖或叠加在文件树上，而非切换 tab。或者使用分割视图。

#### **L-2: Settings 模态框只包含全局设置**

`index.html:322-357` 的 Settings 模态框只管理全局设置 (Preview Limit, Token Threshold 等)。**项目级设置** (excludes, search_settings, prompt_templates, custom_tools, categories) 散落在不同的 UI 位置：
- excludes → 搜索栏 Skip 输入
- search_settings → 搜索栏选项
- prompt_templates → 右侧面板下拉
- custom_tools → 右侧面板按钮 (只读)
- categories → 右侧面板按钮 (只读)

**建议**: 添加 **项目设置模态框**，集中管理所有项目级配置。

#### **L-3: "Generate Context" 按钮的重要性与其位置不匹配**

"Copy Context" 是 FileCortex 的**核心价值操作**（生成 LLM 上下文），但它被放在右侧面板的最底部，需要滚动才能看到。而且 `pulse-accent` 动画在 `col-md-2` 的狭窄空间中不够醒目。

**建议**: 将 Generate Context 按钮提升到更显著的位置，如 Summary Bar 或底部操作栏。

---

## 修复优先级总结

### P0 (必须修复 — 功能性 BUG)

| ID | 问题 | 影响 |
|----|------|------|
| BUG-1 | API Token 从未在 HTTP 请求中发送 | 设置 token 后 Web UI 完全不可用 |
| BUG-2 | `api_token` 不在全局设置中 | Token 认证体系在前端不完整 |
| BUG-9 | `stageAll` 不传递排除规则 | Stage All 忽略排除设置 |
| BUG-10 | 搜索结果右键打开路径收集器 | 语义错误，用户困惑 |

### P1 (应修复 — 数据正确性)

| ID | 问题 | 影响 |
|----|------|------|
| BUG-3 | Token 阈值前后端不一致 | 警告阈值显示错误 |
| BUG-5 | Favorites 组选择器只增不删 | 删除组后 UI 残留 |
| BUG-6 | Note 匹配逻辑粗糙 | 可能显示错误文件的 Note |
| BUG-7 | Tag 匹配逻辑粗糙 | 可能显示错误文件的 Tag |

### P2 (可修复 — 体验问题)

| ID | 问题 | 影响 |
|----|------|------|
| BUG-4 | `fetchContent` 参数被忽略 | 死代码 |
| BUG-8 | 搜索无停止按钮 | 大项目搜索无法取消 |
| BUG-11 | 响应式 CSS 冲突 | 移动端布局可能异常 |
| BUG-12 | `!important` 显示控制 | 代码脆弱 |
| HC-3 | 版本号硬编码 | 需手动同步 |
| HC-4 | 默认值不一致 | 首次使用行为不一致 |
| UX-1 | 右侧面板过载 | 信息架构混乱 |
| UX-3 | 拖拽未实现 | CSS 有样式但无功能 |
| L-1 | 搜索/文件树 Tab 冲突 | 工作流断裂 |
| L-3 | Generate Context 位置不佳 | 核心功能不可见 |

### P3 (可改进 — 架构优化)

| ID | 问题 | 建议 |
|----|------|------|
| HC-1 | API 端点散布 | 集中到 `config.endpoints` |
| HC-2 | CSS 魔术值 | 引入亮色主题 |
| HC-5 | 文件图标为文字 | 使用图标库 (Lucide/Heroicons) |
| HC-6 | 内联样式覆盖 | 移到 CSS 类 |
| UX-2 | 搜索→Staging 流程断裂 | 添加直接 Stage 操作 |
| UX-4 | 键盘导航不完整 | 扩展快捷键 |
| UX-5 | 无加载状态指示器 | 添加骨架屏 |
| L-2 | 项目设置散落 | 添加项目设置模态框 |

---

## 行动计划

### Phase 1: BUG 修复 (优先)
1. 修复 BUG-1 + BUG-2: 在 `_fetch` 中注入 API Token
2. 修复 BUG-3: 统一 token 阈值默认值
3. 修复 BUG-5: 重写 favorites select 渲染逻辑
4. 修复 BUG-6 + BUG-7: 使用精确路径匹配
5. 修复 BUG-9: 传递 stageAll 参数
6. 修复 BUG-10: 搜索结果右键改为上下文菜单

### Phase 2: 布局优化
1. 实施方案 A（三面板 + 底部操作栏）
2. 将 Generate Context 提升到 Summary Bar
3. 添加项目设置模态框

### Phase 3: 体验提升
1. 搜索结果叠加在文件树上
2. 添加搜索停止按钮
3. 实现拖拽到 Staging
4. 使用图标库替换文字图标
5. 添加亮色主题支持
6. 版本号从后端注入
