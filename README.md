# 择时助手 V1

本项目是一个本地运行的股票择时提醒工具，支持：

- A股与美股监控
- 日内背离提醒
- 跨日背离提醒
- Telegram 消息通知
- Streamlit 本地网页界面
- Windows 登录自启动

## 已实现的核心能力

- 录入股票池和独立规则
- 买入提醒与卖出提醒分开配置
- A股正式交易时段监控
- 美股正式交易时段监控
- SQLite 本地保存规则、密钥和日志
- 后台监控进程与网页界面分离

## 你还需要自己准备

- Telegram 机器人 Token
- Telegram chat_id
- Finnhub API Key

## 本机启动

```powershell
.\start_app.ps1
```

启动后：

- 后台监控进程会运行
- 本地网页界面服务会启动在 `http://localhost:8501`

如果你的电脑双击 `.ps1` 会弹出“选择打开方式”，直接双击下面这两个文件即可：

- `启动择时助手.cmd`：启动后台监控和网页界面
- `打开择时助手界面.cmd`：只打开浏览器界面

如果只想打开界面：

```powershell
.\open_ui.ps1
```

## 配置 Windows 登录自启动

```powershell
.\register_startup_task.ps1
```

如果当前 Windows 环境不允许创建任务计划程序条目，脚本会自动回退为“启动文件夹快捷方式”方案，依然可以在登录后自启。

## 手动运行命令

启动网页：

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py --server.port 8501 --server.headless true
```

启动后台监控：

```powershell
.\.venv\Scripts\python.exe .\worker.py
```

## 目录说明

- `app.py`: Streamlit 界面
- `worker.py`: 后台监控与提醒
- `timing_assistant/`: 核心模块
- `data/timing_assistant.db`: 本地 SQLite 数据库

## 当前说明

- A股当前报价使用轻量化新浪行情接口，A股历史日线使用 AKShare。
- 美股当前与历史数据使用 Finnhub。
- 第一版不包含自动下单、回测和财报过滤。
