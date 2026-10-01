# 微电子专业 AI 学习助手

当前项目由 Expo / React Native 手机 App 和 FastAPI 后端组成。手机端支持 iOS、Android；DeepSeek API Key 留在后端，学习资料、聊天记录、错题和进度存入 SQLite。Streamlit 旧版已移除。

## 本地启动后端

使用 Python 3.11 或更新版本。在 PowerShell 中：

```powershell
cd C:\Users\pc\AI-Study-Agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

打开 `backend\.env`，设置 DeepSeek Key 和两个登录字段。`JWT_SECRET` 应设为至少 32 个随机字符。接着启动服务：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
$env:APP_USERNAME = "你的登录账号"
$env:APP_PASSWORD = "请改成足够长的个人密码"
$env:JWT_SECRET = "请填写至少 32 个随机字符"
$env:DATABASE_PATH = "./data/study_agent.sqlite3"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

也可以从 `backend` 目录启动：

```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

第一次启动会建立本地 SQLite 数据库。不要把 `.env` 或数据库文件提交到 Git。

如果原 Streamlit 版曾生成 `study_agent_data.json`，可在启动后端前把文件保留在仓库根目录，并导入旧资料、对话、错题与进度：

```powershell
python backend\import_local_data.py study_agent_data.json
```

## 本地启动手机端

安装 Node.js 22.13 或更新版本、npm 和 Expo Go。先在 `mobile` 目录安装依赖：

```powershell
cd C:\Users\pc\AI-Study-Agent\mobile
npm install
Copy-Item .env.example .env
```

编辑 `.env`：Android 模拟器可用 `http://10.0.2.2:8000`；实体手机应填电脑的局域网 IP，例如 `http://192.168.1.25:8000`。手机和电脑须连接同一局域网。正式部署时请使用 HTTPS 后端地址。再启动：

```powershell
npx expo start
```

用 Expo Go 扫描终端显示的 QR 码。登录账号、密码就是后端设置的 `APP_USERNAME` 和 `APP_PASSWORD`。

## 云端部署（Railway）

手机离开电脑后继续使用，需要把 API 部署到云端，并为 SQLite 数据库挂载持久化卷。Railway 会提供 HTTPS 域名；无需自己购买服务器或配置 Caddy。Railway 资源按套餐和用量计费，开始部署前请先在 Railway 页面查看当前费用。

### 1. 推送代码到 GitHub

Railway 从 GitHub 读取项目。在项目 PowerShell 中确认 `.env`、API Key 和学习数据没有加入 Git，再推送代码：

```powershell
git status --short
git push origin main
```

### 2. 在 Railway 部署 API

在 Railway 新建项目并选择 GitHub 仓库 `AI-Study-Agent`，然后为 API 服务设置 **Root Directory** 为 `/backend`。该目录中的 Dockerfile 会自动构建 FastAPI 后端。

在服务的 **Variables** 中添加以下变量。请在 Railway 的安全输入框内填写密钥，不要把密钥发到聊天里：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
APP_USERNAME=你自己的登录账号
APP_PASSWORD=较长且唯一的密码
JWT_SECRET=至少 32 个随机字符
DATABASE_PATH=/data/study_agent.sqlite3
```

在服务的 **Volumes** 中添加持久化卷，挂载路径设置为 `/data`。否则服务重新部署时，学习资料、进度和错题数据库可能丢失。再到 **Settings → Networking** 为服务生成域名并部署。后端健康检查路径已在 `backend/railway.json` 中设为 `/health`。

部署完成后，在浏览器打开 `https://你的 Railway 域名/health`；出现 `{"ok":true}` 表示后端可用。Railway 的配置步骤见[官方部署文档](https://docs.railway.com/guides/docker-compose)、[持久化卷说明](https://docs.railway.com/volumes)和[变量说明](https://docs.railway.com/variables)。

如果以前的 Streamlit 版本里有 `study_agent_data.json`，不要将它提交到 Git。需要迁移时，先私下将文件上传到后端容器，再运行 `python import_local_data.py /安全路径/study_agent_data.json`。迁移前先备份现有数据。

## 私人 Android 手机安装

### 3. 构建 Android APK 并安装

在自己的电脑打开 PowerShell：

```powershell
cd C:\Users\pc\AI-Study-Agent\mobile
npm install
npx eas-cli@latest login
npx eas-cli@latest build:configure
npx eas-cli@latest env:set --name EXPO_PUBLIC_API_URL --value https://你的实际域名 --environment preview --visibility plaintext
npx eas-cli@latest build --platform android --profile preview
```

构建完成后，EAS 会显示 APK 安装链接。把链接发到自己的 Android 手机并打开，下载 APK 后按系统提示允许安装即可。EAS 的内部预览构建会生成可直接安装的 APK，不经过应用商店。[Expo 内部分发说明](https://docs.expo.dev/build/internal-distribution/)

登录 App 时输入 Railway Variables 里的 `APP_USERNAME` 和 `APP_PASSWORD`。以后更新手机 App：在电脑提交并推送代码，再运行 `npx eas-cli@latest build --platform android --profile preview`，下载并安装新 APK。Railway 连接 GitHub 分支后会自动部署后端更新。

### 个人账号模式

当前 API 使用服务端配置的单一个人账号和密码，适合你自己的设备登录。你的手机通过 HTTPS 连接后端；后端需持续运行，SQLite 文件必须放在持久化磁盘上。登录信息请只自己保管。
