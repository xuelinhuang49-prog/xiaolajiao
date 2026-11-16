# 小辣椒语音助手：Ollama 本地对话接入说明

本项目的网页通过本地 Python 服务的 `/api/chat` 接口请求 Ollama；Ollama 默认地址为 `http://127.0.0.1:11434`，默认角色模型为 `xiaolajiao`。前端不直接访问 Ollama，也不需要 DeepSeek API Key。原有语音识别、陕西话 `/tts`、秦腔、日常提醒、联系人和购物流程均保留。

## 首次配置

1. 安装并启动 Ollama。
2. 双击 `安装并创建小辣椒模型.bat`。脚本会下载基础模型 `qwen3:4b`（需要网络），再读取 `小辣椒/Modelfile.txt` 创建 `xiaolajiao` 角色模型。
3. 双击 `启动演示.bat`，浏览器打开 `http://localhost:8000`。
4. 访问 `http://localhost:8000/api/health` 检查服务状态。正常时会返回 `ok: true`。

## 如果你已安装其他模型

编辑 `小辣椒/Modelfile.txt` 第一行 `FROM qwen3:4b`，替换为 `ollama list` 中已有的模型名，再重新运行创建脚本。也可以先运行 `ollama pull qwen3:4b` 下载基础模型。

## 可选配置

默认使用 `xiaolajiao` 模型和 `http://127.0.0.1:11434` 地址。如需更改，可在启动 `server.py` 前设置环境变量 `OLLAMA_MODEL` 或 `OLLAMA_URL`。

## 说明

- 首次推理可能比较慢，前端请求超时时间已调整为 120 秒。
- 功能操作仍由现有 Python 模块/前端逻辑执行；模型只负责对话与工具意图，不应虚构任务执行成功。
- 本项目不要求配置 DeepSeek 密钥。
