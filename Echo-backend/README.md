# Echo Backend (AI伴侣微信小程序后端)

这是一个基于 FastAPI 开发的微信小程序 AI 伴侣“Echo”的后端 Demo。主要功能包括与 OpenAI 兼容的大模型 API 对接、内网穿透以及基础的纯文本对话管理。

## 1. 环境准备

推荐使用 Conda 创建虚拟环境。

```bash
# 创建虚拟环境
conda create -n echo python=3.9 -y

# 激活虚拟环境
conda activate echo

# 安装依赖
pip install -r requirements.txt
```

## 2. 配置环境变量

复制 `.env.example` 文件作为本地配置文件 `.env`：

```bash
cp .env.example .env
```
然后在 `.env` 文件中填入真实的信息，例如：
```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
WECHAT_APPID=your_actual_wechat_appid
WECHAT_SECRET=your_actual_wechat_secret
```

## 3. 启动后端服务

使用 uvicorn 启动后端：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
服务将在本地 `http://localhost:8000` 运行。

## 4. 内网穿透到微信小程序

为使微信小程序能够访问本地开发机，请使用 [ngrok](https://ngrok.com/) 进行内网穿透：

```bash
# 执行内网穿透，映射本地的 8000 端口
ngrok http 8000
```

`ngrok` 运行后会提供一个 `https://<xxxxx>.ngrok-free.app` 格式的外网地址。
将其复制，配置到小程序的代码中（用于向该后端发起 API 请求）。

如果你有自定义需求，请参考代码中的内联注释及配置项。
