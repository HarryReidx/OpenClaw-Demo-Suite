# Changelog

## 2026-03-27

### Added

- 新增统一容器化文件：
  - `Dockerfile`
  - `.dockerignore`
  - `docker/start_app.py`
  - `docker-compose.harbor.yml`
  - `harbor.env.example`
- 新增 portal 静态下载包：
  - `portal/static/download/🦞小清虾.apk`
- 新增发布说明与部署文档

### Changed

- 默认模型接入改为 Ollama
  - `QWEN_BASE_URL=http://172.24.0.5:11434/v1`
  - `QWEN_TEXT_MODEL=qwen3:8b`
  - `QWEN_VISION_MODEL=qwen2.5vl:7b`
- `portal` 标题改为：
  - `黄药师AI-深入浅出小龙虾实践`
- `portal` 中 `07` 改为 APK 下载入口
- `portal` 中 `07` 增加“暂不支持 iPhone 用户”提示
- Android 应用名改为：
  - `🦞小清虾`
- APK 下载文件名改为：
  - `🦞小清虾.apk`
- `05` 浏览器操作能力改为优先使用无头浏览器执行
- 针对“模型 / 基模 / 厂商 / 供应商”等问题，改为通过系统提示自然引导回复“由清云智通武汉研发中心设计、研发并提供”

### Fixed

- 过滤模型返回中的 `<think>` 内容，避免前端直接展示内部思考文本
- 修正 Android release 包默认后端地址为：
  - `http://172.24.0.5:8105`
- 修正 portal 下载入口与 APK 文件路径对齐

### Released Images

- `harbor.tsingyun.net/platform/ai-openclaw-dev-portal:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-01:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-02:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-03:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-04:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-05:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-06:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-07:1.0`
