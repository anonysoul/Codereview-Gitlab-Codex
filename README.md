# GitLab Codex Review

仅支持 GitLab Merge Request 的自动审查服务。

主链路是：GitLab `merge_request` webhook -> 拉取或复用本地仓库缓存 -> checkout 到 webhook 的 `last_commit.id` -> 执行 `codex review --base origin/<target_branch>` -> 将结果作为单条 MR note 回帖 -> 写入审查日志。

## 当前范围

- 只支持 GitLab，不支持其他代码托管平台。
- 只处理 Merge Request，不处理 Push。
- 审查执行器只使用本机 `codex` CLI，不再接入第三方 LLM SDK。
- Dashboard 只展示 Merge Request 审查日志。

## 运行要求

- Python 3.10+
- 本机已安装 `git`
- 本机已安装 `codex`，并且服务进程可直接调用

## 关键配置

复制配置模板：

```bash
cp conf/.env.dist conf/.env
```

至少需要确认这些配置：

```bash
GITLAB_ACCESS_TOKEN=your_gitlab_token
CODEREVIEW_CACHE_DIR=~/.cache/codereview
MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED=0
# CODEX_REVIEW_PROMPT=请用中文输出适合直接回复到 GitLab MR 的审查结论，聚焦 bug、风险、回归和缺失测试。
```

说明：

- `GITLAB_ACCESS_TOKEN` 优先从 `conf/.env` 读取；未配置时可使用 webhook 的 `Secret Token`
- `CODEREVIEW_CACHE_DIR` 默认是 `~/.cache/codereview`
- `CODEX_REVIEW_PROMPT` 可选，用于覆盖默认中文审查提示词

## 启动

安装依赖：

```bash
pip install -r requirements.txt
```

启动 API：

```bash
python api.py
```

启动 Dashboard：

```bash
streamlit run ui.py --server.port=5002 --server.address=0.0.0.0
```

## GitLab Webhook

在 GitLab 项目设置中配置：

- URL: `http://your-server-ip:5001/review/webhook`
- Trigger Events: 只勾选 `Merge request events`
- Secret Token: 可选；如果未在 `conf/.env` 中配置 `GITLAB_ACCESS_TOKEN`，可使用这里的 token

## Docker

项目内提供了基础 `Dockerfile` 和 `docker-compose.yml`。镜像已经包含 `git`，但仍要求运行环境里存在可用的 `codex` CLI；如果你用容器部署，需要自行保证容器内能执行 `codex`。

## 其他文档

- [FAQ](doc/faq.md)
- [Pro 版说明](doc/pro.md)
