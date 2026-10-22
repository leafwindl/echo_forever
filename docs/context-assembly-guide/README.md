# Echo 上下文拼接说明书

双击 `index.html`，直接在本地浏览器打开。最终 HTML 已内置说明数据、脚本、样式和 Dagre 布局引擎，不需要服务器或联网。

- 展示普通文字聊天的实际组装顺序，区分共享 Renderer、Context Builder 和 Agent。
- 可切换演示材料，查看 `messages` 角色、可选项以及独立的 `tools` 通道。
- 来源卡片说明人工编写、数据库读取、规则计算和模型抽取，附真实文件、函数、生成时行号与源码片段。
- 展示六类材料的当前落点、工具回填、校验范围与长度预算。
- 示例数据明确标为虚构；不读取 `.env`、实际用户数据库或调用模型。

在项目根目录运行：

```powershell
python -B docs/context-assembly-guide/build_page.py
node docs/context-assembly-guide/verify_page.cjs
```

`build_page.py` 读取实际代码核对引用并生成 `index.html` 和 `diagrams.json`。更新说明结构或交互，修改 `template.html`；修改材料说明及引用，修改构建脚本。固定提示长度数据沿用 `docs/persona-prompt-review/current-prompt-metrics.json`，若提示正文变化先重新运行该目录的审计脚本。

图表 JSON 只有节点、边、分组与布局意图；SVG 几何由内置布局引擎运行时生成。Dagre 引擎复用 `../chat-flow-page/vendor/dagre.min.js`，许可证见同目录 `DAGRE-LICENSE.txt`。

验证脚本在 Node VM 内检查渲染与交互，不替代真实浏览器的视觉检查。页面说明是源码快照，不是实时追踪器；单独复制 HTML 仍可离线阅读，仓库源码和许可证链接需要保留相对目录。
