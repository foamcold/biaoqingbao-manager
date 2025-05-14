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

## 使用 Docker 运行 (Running with Docker)

本项目支持使用 Docker 进行容器化部署和运行。

### 准备工作

1.  **确保 Docker 已安装**:
    *   访问 [Docker 官网](https://docs.docker.com/get-docker/) 获取适用于您操作系统的 Docker Desktop 或 Docker Engine。

2.  **关于 Docker Compose**:
    *   **Docker Compose V2 (推荐)**: 新版本的 Docker Desktop 通常集成了 Docker Compose V2，命令为 `docker compose` (带空格)。
    *   **Docker Compose V1 (旧版)**: 如果您单独安装了旧版的 Docker Compose，命令可能是 `docker-compose` (带连字符)。
    *   本文档将主要使用 `docker compose` 语法。如果此命令无效，请尝试使用 `docker-compose`。

3.  **配置环境变量 (`.env` 文件)**:
    *   与本地运行类似，复制 `.env.example` 为 `.env`：
        ```bash
        # Windows
        copy .env.example .env
        # macOS/Linux
        cp .env.example .env
        ```
    *   编辑 `.env` 文件，并至少设置 `ADMIN_PASSWORD` 和 `SECRET_KEY`。
    *   `EMOTICONS_FOLDER` 默认值为 `emoticons`。当使用 Docker 时，此路径将对应容器内的路径。卷映射会确保数据持久化到宿主机。
    *   对于 Docker 部署，建议在 `.env` 中设置 `FLASK_ENV=production` 和 `FLASK_DEBUG=0`。

### 方式一：使用 Docker Compose (推荐)

使用 `docker-compose.yml` 文件可以简化多容器应用的定义和运行。

1.  **构建并启动服务**:
    在项目根目录下运行：
    ```bash
    docker compose up --build
    ```
    *   `--build` 参数会强制重新构建 Docker 镜像（如果 `Dockerfile` 或相关文件有更改）。
    *   如果不想看实时日志，可以使用 `-d` 参数后台运行：`docker compose up --build -d`
    *   如果 `docker compose` 命令无效，请尝试 `docker-compose up --build`。

2.  **访问应用**:
    在浏览器中访问 `http://localhost:5000`。

3.  **停止服务**:
    *   如果前台运行，按 `Ctrl+C`。
    *   如果后台运行，使用：
        ```bash
        docker compose down
        ```
        (或 `docker-compose down`)

4.  **查看日志 (如果后台运行)**:
    ```bash
    docker compose logs -f web
    ```
    (或 `docker-compose logs -f web`。假设服务名为 `web`，如 `docker-compose.yml` 中所定义)

5.  **持久化存储**:
    `emoticons` 目录通过 `docker-compose.yml` 中的卷映射 (`./emoticons:/app/emoticons`) 进行持久化。只要宿主机上的 `./emoticons` 目录存在，即使容器被删除和重建，表情包数据也会保留。

### 方式二：使用普通 Docker 命令

如果您不使用 Docker Compose，也可以直接使用 `docker` 命令构建和运行。

1.  **构建 Docker 镜像**:
    在项目根目录下运行 (确保 `Dockerfile` 存在)：
    ```bash
    docker build -t biaoqingbao-manager .
    ```
    *   `-t biaoqingbao-manager` 为镜像指定一个名称 (tag)。您可以选择其他名称。

2.  **运行 Docker 容器**:
    ```bash
    docker run -d \
      -p 5000:5000 \
      --name bqb_manager_container \
      -v "$(pwd)/emoticons":/app/emoticons \
      --env-file .env \
      biaoqingbao-manager
    ```
    *   `-d`: 后台运行容器。
    *   `-p 5000:5000`: 将宿主机的 5000 端口映射到容器的 5000 端口。
    *   `--name bqb_manager_container`: 为容器指定一个名称，方便管理。
    *   `-v "$(pwd)/emoticons":/app/emoticons`: 卷映射。
        *   `$(pwd)/emoticons` (Linux/macOS) 或 `%cd%\emoticons` (Windows CMD) 或 `${PWD}/emoticons` (PowerShell) 表示宿主机当前目录下的 `emoticons` 文件夹。请确保此目录存在。
        *   `/app/emoticons` 是容器内应用期望的表情包路径 (基于 `Dockerfile` 中的 `WORKDIR /app` 和应用默认的 `emoticons` 文件夹)。
    *   `--env-file .env`: 从项目根目录的 `.env` 文件加载环境变量。
    *   `biaoqingbao-manager`: 您在 `docker build` 时为镜像设置的名称。

3.  **访问应用**:
    在浏览器中访问 `http://localhost:5000`。

4.  **查看容器日志**:
    ```bash
    docker logs -f bqb_manager_container
    ```

5.  **停止容器**:
    ```bash
    docker stop bqb_manager_container
    ```

6.  **移除容器 (如果不再需要)**:
    ```bash
    docker rm bqb_manager_container
    ```
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