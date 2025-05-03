# 表情包管理器 (Biaoqingbao Manager)

一个简单的基于 Flask 的 Web 应用，用于管理和分享您的表情包收藏。

A simple Flask-based web application for managing and sharing your emoticon/meme collection.

## 主要功能 (Features)

*   **管理员后台**: 通过密码保护的后台界面进行管理操作。
*   **分类管理**: 创建和删除表情包分类（文件夹）。
*   **上传功能**:
    *   支持从本地上传单个或多个图片文件。
    *   支持通过 URL 批量下载并保存图片。
    *   上传时自动添加时间戳后缀以避免文件名冲突。
    *   实时上传/下载进度显示。
*   **随机访问**: 通过 `/分类名` URL 随机获取该分类下的一个表情包图片。
*   **分类预览**:
    *   分页浏览指定分类下的所有表情包。
    *   网格布局，自适应列数。
    *   支持单图预览、下载、重命名、删除。
    *   支持批量选择和批量删除。
*   **中文支持**: 支持中文分类名。
*   **响应式设计**: 基于 Bootstrap，适配不同屏幕尺寸。

## 技术栈 (Technology Stack)

*   **后端 (Backend)**: Python, Flask
*   **前端 (Frontend)**: HTML, CSS, JavaScript, Bootstrap 5
*   **依赖管理 (Dependency Management)**: pip, requirements.txt
*   **配置 (Configuration)**: python-dotenv (.env file)

## 安装与设置 (Installation and Setup)

1.  **克隆仓库 (Clone the repository)**:
    ```bash
    git clone https://github.com/FoamCold/biaoqingbao-manager.git
    cd biaoqingbao-manager
    ```

2.  **创建并激活虚拟环境 (Create and activate a virtual environment)** (推荐):
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **安装依赖 (Install dependencies)**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **配置环境变量 (Configure environment variables)**:
    *   复制 `.env.example` 文件为 `.env`:
        ```bash
        # Windows
        copy .env.example .env

        # macOS/Linux
        cp .env.example .env
        ```
    *   编辑 `.env` 文件，设置至少以下两个变量：
        *   `ADMIN_PASSWORD`: 设置一个强密码用于管理员登录。
        *   `SECRET_KEY`: 设置一个随机的长字符串作为 Flask 的密钥 (用于 session 加密等)。可以使用以下命令生成：
            ```bash
            python -c "import secrets; print(secrets.token_hex(32))"
            ```
        *   （可选）`EMOTICONS_FOLDER`: 表情包存储目录，默认为 `emoticons`。
        *   （可选）`FLASK_ENV`: 开发环境设为 `development`，生产环境设为 `production`。
        *   （可选）`FLASK_DEBUG`: 开发环境设为 `1`，生产环境设为 `0`。

## 本地运行 (Running Locally)

1.  确保虚拟环境已激活并且 `.env` 文件已配置好。
2.  运行 Flask 开发服务器：
    ```bash
    flask run
    ```
3.  在浏览器中访问 `http://127.0.0.1:5000` (或 Flask 启动时显示的地址)。
4.  访问 `/login` 并使用您在 `.env` 中设置的 `ADMIN_PASSWORD` 登录管理员后台。

## 部署 (Deployment)

对于生产环境部署，请遵循以下建议：

1.  **环境变量**: 确保在生产服务器上设置了必要的环境变量 (`ADMIN_PASSWORD`, `SECRET_KEY`, `EMOTICONS_FOLDER`, `FLASK_ENV=production`, `FLASK_DEBUG=0`)。不要将 `.env` 文件直接用于生产，应使用系统环境变量或部署工具管理敏感信息。
2.  **WSGI 服务器**: 不要使用 Flask 内建的开发服务器 (`flask run`)。请使用生产级的 WSGI 服务器，例如 Gunicorn 或 Waitress。
    *   **Gunicorn (Linux/macOS)**:
        ```bash
        # 示例：运行4个工作进程，监听 0.0.0.0:8000
        gunicorn -w 4 -b 0.0.0.0:8000 app:app
        ```
    *   **Waitress (Windows/Linux/macOS)**:
        ```bash
        # 示例：监听所有接口的 8000 端口
        waitress-serve --host 0.0.0.0 --port 8000 app:app
        ```
3.  **反向代理 (Reverse Proxy)**: 建议在 WSGI 服务器前部署一个反向代理服务器，如 Nginx 或 Apache。反向代理可以处理：
    *   HTTPS (SSL/TLS) 加密
    *   静态文件服务 (提高性能)
    *   负载均衡 (如果需要)
    *   请求缓冲和安全防护
4.  **文件权限**: 确保运行 WSGI 服务器的用户对 `EMOTICONS_FOLDER` 指定的目录具有读写权限。
5.  **日志**: 配置合适的日志记录，以便监控应用状态和排查问题。

## 使用说明 (Usage)

*   **管理员**: 访问 `/login` 登录。登录后会自动跳转到 `/admin` 页面，可以进行分类管理和表情包上传。点击分类卡片或导航栏进入分类详情页进行图片管理。
*   **普通用户**: 访问 `/分类名称` (例如 `/funny`) 会随机显示该分类下的一个表情包图片。

## 项目结构 (Project Structure)

```
.
├── .env.example        # 环境变量示例文件
├── .gitignore          # Git 忽略配置
├── app.py              # Flask 应用主文件
├── requirements.txt    # Python 依赖列表
├── README.md           # 项目说明 (本文件)
├── emoticons/          # 存储表情包的根目录 (默认)
│   └── category1/      # 示例分类目录
│       └── image1.jpg
│   └── category2/
│       └── image2.png
└── templates/          # HTML 模板目录
    ├── admin.html          # 管理员主页模板
    ├── category_view.html  # 分类详情页模板
    └── login.html          # 登录页面模板
``` 