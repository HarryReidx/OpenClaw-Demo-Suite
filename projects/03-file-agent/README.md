# 03. File Agent

这个子工程用于演示 Agent 的核心跃迁：从“只会回答”变成“会调用工具去完成任务”。

## 入口

- 默认端口：`8103`
- 局域网访问：`http://你的电脑IP:8103/`

## 能力

- 调用 Qwen 生成文案
- 使用工具把文案写入本地文件
- 严格限制写入范围到 `demo_outputs/file-agent/`

## 运行方式

推荐直接在仓库根目录运行：

```powershell
.\launch_all.ps1
```

