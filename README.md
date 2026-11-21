# ReproLab AI · 研途复现官

[打开线上演示](https://cy642.github.io/reprolab-ai/)

ReproLab AI 用论文证据、可编辑的复现方案、数据审计和实验分析支持科研复现准备。公开演示提供预置的合成数据和定稿报告。选择「解锁实时演示」可进入独立的操作空间，访问码由演示负责人管理。公开访客无需登录即可浏览。

## 三分钟演示

1. 打开工作流，查看场景 A 的论文、方案、审计、洞察和人工审批。
2. 在数据审计中查看 P002 跨 Train/Test，对应 CSV 第 3、9 行。审批后报告仍保存两条高风险。
3. 在报告中心查看来源、风险和结论限制，并导出 JSON 或 Markdown。
4. 切到场景 B，查看缺少实验记录时失败的节点。再查看实验洞察中模拟的 0.62、0.73 与 11.0 个百分点差值。

## 运行与部署

- `frontend/` 提供 React / Vite 界面。GitHub Pages 版本使用 `npm run build -- --mode pages --base /reprolab-ai/`，构建时为 `VITE_API_BASE_URL` 设置演示后端 HTTPS 地址。
- `backend/` 提供 FastAPI / SQLite API、规则计算、模型接口、测试以及合成演示夹具。
- `scripts/start-phase7-demo.ps1` 在 Windows 的隔离目录启动本地确定性演示。先在 `backend` 创建 `.venv` 并安装 `requirements-dev.txt`，再在 `frontend` 执行 `npm ci`。
- 线上部署采用两份独立的 SQLite 数据目录。公开后端仅供浏览，操作后端由访问码保护。OpenAI 密钥保存在虚拟机上的私有网关，前端构建只包含 HTTPS 地址。
- [产品与技术说明](docs/competition/product_overview.md)

演示不执行真实训练。公开示例的指标与患者编号为模拟数据。流程完成后仍需核对原文的语义支持、数据切分风险和统计限制。
