# FileCortex 前端分析报告

> **版本**: 6.3.3 | **评估日期**: 2026-05-16

---

## 1. 技术栈

| 层 | 技术 |
|----|------|
| UI 框架 | Bootstrap 5.3.0 (CDN) |
| 代码高亮 | highlight.js 11.9.0 (CDN) |
| Markdown | marked.js (CDN) |
| 图表 | mermaid.js (CDN) |
| 模块化 | ES6 Modules (`type="module"`) |
| 模板 | Jinja2 (FastAPI) |

## 2. JS 模块架构

```
static/js/
├── state.js    (76行) — 全局状态 + 配置常量 + XSS防护
├── api.js      (201行) — HTTP/WebSocket 请求封装
├── ui.js       (386行) — UI 渲染驱动
└── main.js    (1177行) — 流程控制 + 事件绑定
```

### 2.1 数据流
```
用户操作 → main.js (App) → api.js → FastAPI → DataManager
                                      ↓
           main.js ← ui.js ← HTTP/WS 响应
```

### 2.2 API Token 传输
```
window.__FCTX_API_TOKEN__  ← index.html:430 Jinja2 注入 ← web_app.py
         ↓
state.js → _getApiToken() → X-API-Token header (HTTP) / token query (WS)
```

---

## 3. 前端契约评估

| 契约项 | 状态 |
|--------|------|
| 端点集中在 `config.endpoints` | ✅ 完成 |
| API Token HTTP + WS 双通道 | ✅ |
| XSS 防护 (`escapeHtml`) | ✅ |
| 全局设置动态加载 | ✅ |
| 搜索 UI 状态持久化 (localStorage) | ✅ |

---

## 4. 性能分析

| 问题 | 严重度 | 说明 |
|------|--------|------|
| CDN 无 SRI hash | 中 | 潜在的供应链风险 |
| 无虚拟滚动 | 中 | 大目录 (>5000 文件) 可能导致卡顿 |
| `innerHTML` 渲染 | 低 | 适合当前规模，但需注意 XSS |

---

## 5. 待修复项

| 编号 | 问题 | 位置 |
|------|------|------|
| HC-2 | CSS 魔术值 → CSS 变量 + 亮色主题 | `static/css/style.css` |
| BUG-5 | Favorites 组选择器选项清理 | `main.js` |
| BUG-11 | 响应式 CSS grid 冲突 | `index.html` |

---

> *本报告基于对 FileCortex v6.3.3 前端代码的完整审查生成。*
