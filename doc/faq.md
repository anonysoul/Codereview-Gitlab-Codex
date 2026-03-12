## 常见问题

### Docker 容器部署时，更新 .env 文件后不生效

**可能原因**

Docker 的文件映射机制是将宿主机的文件复制到容器内，因此宿主机文件的更新不会自动同步到容器内。

**解决方案**

- 删除现有容器：

```
docker rm -f <container_name>
```

重新创建并启动容器：

```
docker-compose up -d
```

或参考说明文档启动容器。

### GitLab 配置 Webhooks 时提示 "Invalid url given"

**可能原因**

GitLab 默认禁止 Webhooks 访问本地网络地址。

**解决方案**

- 进入 GitLab 管理区域：Admin Area → Settings → Network。
- 在 Outbound requests 部分，勾选 Allow requests to the local network from webhooks and integrations。
- 保存。

### docker 容器部署时，连接Ollama失败

**可能原因**

配置127.0.0.1:11434连接Ollama。由于docker容器的网络模式为bridge，容器内的127.0.0.1并不是宿主机的127.0.0.1，所以连接失败。

**解决方案**

在.env文件中修改OLLAMA_API_BASE_URL为宿主机的IP地址或外网IP地址。同时要配置Ollama服务绑定到宿主机的IP地址（或0.0.0.0）。

```
OLLAMA_API_BASE_URL=http://127.0.0.1:11434  # 错误
OLLAMA_API_BASE_URL=http://{宿主机/外网IP地址}:11434  # 正确
```

### 是否支持对 GitHub 代码库的 Review？

是的，支持。 需完成以下配置：

**1.配置Github Webhook**

- 进入你的 GitHub 仓库 → Settings → Webhooks → Add webhook。
    - Payload URL: http://your-server-ip:5001/review/webhook（替换为你的服务器地址）
    - Content type选择application/json
    - 在 Which events would you like to trigger this webhook? 中选择 Just the push event（或按需勾选其他事件）
    - 点击 Add webhook 完成配置。

**2.生成 GitHub Personal Access Token**

- 进入 GitHub 个人设置 → Developer settings → Personal access tokens → Generate new token。
- 选择 Fine-grained tokens 或 tokens (classic) 都可以
- 点击 Create new token
- Repository access根据需要选择
- Permissions需要选择Commit statuses、Contents、Discussions、Issues、Metadata和Pull requests
- 点击 Generate token 完成配置。

**3.配置.env文件**

- 在.env文件中，配置GITHUB_ACCESS_TOKEN：
  ```
  GITHUB_ACCESS_TOKEN=your-access-token  #替换为你的Access Token
  ```
