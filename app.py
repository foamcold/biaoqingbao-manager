import os
import time
import random
import datetime
import json
from flask import Flask, request, redirect, url_for, render_template, send_from_directory, session, flash, abort, jsonify, Response
from werkzeug.utils import secure_filename
import functools
import shutil
import requests
from urllib.parse import urlparse, urlunparse
import mimetypes
import math
from dotenv import load_dotenv
import uuid # For unique ID generation

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_dev')
app.config['EMOTICONS_FOLDER'] = os.environ.get('EMOTICONS_FOLDER', 'emoticons')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_PER_PAGE = [50, 100, 150, 200, 250, 300]
ADMIN_ALLOWED_PER_PAGE = [10, 20, 30, 40, 50]

# Global store for URL processing tasks (for simplicity in this example)
# WARNING: This in-memory dict is not suitable for multi-worker Gunicorn setups in production.
# Consider Redis or another shared store for production.
url_processing_tasks = {}

if not os.path.exists(app.config['EMOTICONS_FOLDER']):
    os.makedirs(app.config['EMOTICONS_FOLDER'])

# --- Helper Functions for External Links ---
def generate_unique_id():
    """Generates a unique ID string."""
    return str(uuid.uuid4())

def get_external_links_path(category_name):
    """Gets the full path to the external_links.json file for a category."""
    # The category_name received here should already be validated by the route
    # For path construction, we use the original category_name as it's used for directory names
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    return os.path.join(category_path, 'external_links.json')

def load_external_links(category_name):
    """Loads external links for a given category from its JSON file."""
    links_file_path = get_external_links_path(category_name)

    if not os.path.exists(links_file_path):
        return []
    try:
        with open(links_file_path, 'r', encoding='utf-8') as f:
            links = json.load(f)
        # Ensure all links have 'added_at' and 'type' for consistency
        for link in links:
            if 'added_at' not in link:
                # Fallback for potentially old data, though new data will always have it
                link['added_at'] = datetime.datetime.min.isoformat() + "Z"
            if 'type' not in link:
                link['type'] = 'external' # Assume it's external if type is missing
        return links
    except (json.JSONDecodeError, IOError) as e:
        app.logger.error(f"Error loading external links for {category_name}: {e}")
        return []

def save_external_links(category_name, links_data):
    """Saves external links for a given category to its JSON file."""
    links_file_path = get_external_links_path(category_name)

    category_dir = os.path.dirname(links_file_path)
    # Category directory should exist if the category itself exists.
    if not os.path.exists(category_dir):
        try:
            # This case should ideally not be hit if category management is correct
            os.makedirs(category_dir)
            app.logger.info(f"Created missing directory for external links: {category_dir}")
        except OSError as e:
            app.logger.error(f"Error creating directory {category_dir} for external links: {e}")
            return False

    try:
        with open(links_file_path, 'w', encoding='utf-8') as f:
            json.dump(links_data, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        app.logger.error(f"Error saving external links for {category_name}: {e}")
        return False

# --- End Helper Functions for External Links ---

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'logged_in' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(status='error', message='需要登录'), 401
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def is_valid_category_name(name):
    """Basic check for category name validity."""
    if not name:
        return False
    # Disallow path separators and relative paths
    if '/' in name or '\\' in name or name == '.' or name == '..':
        return False
    # Optional: You might want to disallow other specific characters
    # forbidden_chars = ":*?\"<>|"
    # if any(c in name for c in forbidden_chars):
    #    return False
    return True

@app.route('/')
def index():
    """主页，显示项目信息和分类列表。"""
    base_url = request.host_url
    categories = []
    if os.path.exists(app.config['EMOTICONS_FOLDER']):
        try:
            # 只列出目录
            categories = sorted([d for d in os.listdir(app.config['EMOTICONS_FOLDER'])
                                 if os.path.isdir(os.path.join(app.config['EMOTICONS_FOLDER'], d))])
        except OSError as e:
            flash(f"无法读取表情包目录: {e}", "danger")
            categories = [] # 出错时返回空列表

    # 检查登录状态
    logged_in = 'logged_in' in session

    return render_template('index.html',
                           base_url=base_url,
                           categories=categories,
                           logged_in=logged_in)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == app.config['ADMIN_PASSWORD']:
            session['logged_in'] = True
            flash('登录成功!', 'success')
            return redirect(url_for('index'))
        else:
            flash('密码错误!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """处理用户登出。"""
    session.pop('logged_in', None)
    session.pop('last_shown', None) # Clear last shown for all categories on logout
    flash('您已成功登出。', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    # --- Pagination Logic for Categories ---
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    if page < 1: page = 1

    try:
        # Use the new constant and default for admin page
        per_page = int(request.args.get('per_page', 10)) # Default 10 for admin
    except ValueError:
        per_page = 10
    if per_page not in ADMIN_ALLOWED_PER_PAGE: # Use admin specific list
        per_page = 10 # Fallback to admin default

    all_categories_list = []
    emoticons_path = app.config['EMOTICONS_FOLDER']
    if os.path.exists(emoticons_path):
        try:
            all_categories_list = sorted([d for d in os.listdir(emoticons_path) if os.path.isdir(os.path.join(emoticons_path, d))])
        except OSError as e:
            flash(f'无法读取表情包目录: {e}', 'danger')
    
    total_categories = len(all_categories_list)
    total_pages = math.ceil(total_categories / per_page) if per_page > 0 else 1
    if page > total_pages and total_pages > 0:
        page = total_pages

    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    categories_on_page = all_categories_list[start_index:end_index]
    # --- End Pagination Logic ---

    return render_template('admin.html', 
                           categories=categories_on_page, # Pass only current page categories
                           config=app.config, 
                           # Pagination context
                           page=page,
                           per_page=per_page,
                           total_categories=total_categories,
                           total_pages=total_pages,
                           allowed_per_page_values=ADMIN_ALLOWED_PER_PAGE)

@app.route('/admin/create_category', methods=['POST'])
@login_required
def create_category():
    category_name_raw = request.form.get('category_name', '')
    category_name = category_name_raw.strip()

    # Use the new validation function
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。名称不能为空，且不能包含 / 或 \\', 'warning')
        return redirect(url_for('admin'))

    # Use the original (but validated) name for the path
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)

    if os.path.exists(category_path):
        flash(f'分类 "{category_name}" 已存在。', 'warning') # Use original name in message
    else:
        try:
            os.makedirs(category_path)
            flash(f'分类 "{category_name}" 创建成功。', 'success') # Use original name in message
        except OSError as e:
            flash(f'创建分类时出错: {e}', 'danger')

    return redirect(url_for('admin'))

@app.route('/admin/delete_category/<path:category_name>', methods=['POST'])
@login_required
def delete_category(category_name):
    # Validate the raw category name directly
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    # Use the validated name for path operations
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)

    if not os.path.isdir(category_path):
        flash(f'分类 "{category_name}" 不存在或不是一个目录。', 'warning') # Use original name
    else:
        try:
            shutil.rmtree(category_path)
            flash(f'分类 "{category_name}" 已成功删除。', 'success') # Use original name
            last_shown = session.get('last_shown', {})
            if category_name in last_shown: # Use original name
                del last_shown[category_name]
                session['last_shown'] = last_shown
                session.modified = True
        except OSError as e:
            flash(f'删除分类时出错: {e}', 'danger')

    return redirect(url_for('admin'))

@app.route('/admin/category/<path:category_name>')
@login_required
def view_category(category_name):
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    if not os.path.isdir(category_path):
        flash(f'分类 "{category_name}" 不存在。', 'warning')
        return redirect(url_for('admin'))

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    if page < 1: page = 1

    try:
        per_page = int(request.args.get('per_page', 100))
    except ValueError:
        per_page = 100
    if per_page not in ALLOWED_PER_PAGE:
        per_page = 100

    all_items = []

    # 1. Load local images
    try:
        local_image_files = [f for f in os.listdir(category_path)
                             if os.path.isfile(os.path.join(category_path, f)) and allowed_file(f)]
        for filename in local_image_files:
            file_path = os.path.join(category_path, filename)
            try:
                modified_time = os.path.getmtime(file_path)
                added_at_iso = datetime.datetime.fromtimestamp(modified_time, datetime.timezone.utc).isoformat()
            except OSError:
                # Fallback if cannot get modification time
                added_at_iso = datetime.datetime.min.isoformat() + "Z"
            
            all_items.append({
                'id': filename, # Use filename as ID for local files
                'name': filename,
                'type': 'local',
                'view_url': url_for('serve_emoticon_file', category_name=category_name, filename=filename),
                'download_url': url_for('download_emoticon', category_name=category_name, filename=filename),
                'added_at': added_at_iso
            })
    except OSError as e:
        flash(f'无法读取分类 "{category_name}" 的本地图片内容: {e}', 'danger')

    # 2. Load external links
    external_links = load_external_links(category_name)
    for link in external_links:
        all_items.append({
            'id': link['id'], # Use the ID from external_links.json
            'name': link['url'], # Display URL as name
            'type': 'external',
            'view_url': link['url'], # For direct linking
            'added_at': link.get('added_at', datetime.datetime.min.isoformat() + "Z") # Ensure added_at exists
            # 'download_url' is not applicable for external links in the same way
        })

    # 3. Sort all items by 'added_at' in descending order (newest first)
    all_items.sort(key=lambda x: x['added_at'], reverse=True)

    # 4. Pagination
    total_items_count = len(all_items)
    total_pages = math.ceil(total_items_count / per_page) if per_page > 0 else 1
    if page > total_pages and total_pages > 0:
        page = total_pages

    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    items_on_page = all_items[start_index:end_index]

    # 5. Get all category names for dropdown
    all_categories_list = []
    emoticons_dir = app.config['EMOTICONS_FOLDER']
    try:
        all_categories_list = sorted([d for d in os.listdir(emoticons_dir) if os.path.isdir(os.path.join(emoticons_dir, d))])
    except OSError as e:
        app.logger.warning(f'Could not list directories in {emoticons_dir}: {e}')

    return render_template('category_view.html',
                           category_name=category_name,
                           items=items_on_page, # Changed from 'images' to 'items'
                           all_categories=all_categories_list,
                           page=page,
                           per_page=per_page,
                           total_items=total_items_count, # Changed from 'total_images'
                           total_pages=total_pages,
                           allowed_per_page_values=ALLOWED_PER_PAGE)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/admin/upload', methods=['POST'])
@login_required
def upload_file():
    category_name_raw = request.form.get('category', '')
    file = request.files.get('file')
    original_full_filename = file.filename if file else ''

    # Validate the category name from the form
    if not is_valid_category_name(category_name_raw):
        return jsonify(status='error', message='无效的分类名称', filename=original_full_filename), 400

    if not file or original_full_filename == '':
        return jsonify(status='error', message='缺少文件', filename=original_full_filename), 400

    # Use the validated name directly for path construction
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name_raw)
    if not os.path.isdir(category_path):
        # Use original name in error message
        return jsonify(status='error', message=f'分类 "{category_name_raw}" 不存在', filename=original_full_filename), 400

    if not allowed_file(original_full_filename):
        return jsonify(status='error', message='不允许的文件类型', filename=original_full_filename), 400

    try:
        filename_base, file_extension = os.path.splitext(original_full_filename)
        safe_filename_base = secure_filename(filename_base)
        if not safe_filename_base:
            safe_filename_base = "file"

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
        safe_extension = file_extension.lower()
        if not safe_extension.startswith('.'):
             safe_extension = '.' + safe_extension.split('.')[-1] if '.' in safe_extension else '.' + safe_extension

        if safe_extension.lstrip('.') not in ALLOWED_EXTENSIONS:
             return jsonify(status='error', message=f'不允许的扩展名 ({safe_extension})', filename=original_full_filename), 400

        new_filename = f"{safe_filename_base}_{timestamp}{safe_extension}"
        save_path = os.path.join(category_path, new_filename)
        file.save(save_path)

        return jsonify(
            status='success',
            message=f"文件 '{original_full_filename}' 成功上传为 '{new_filename}'",
            original_filename=original_full_filename,
            new_filename=new_filename
        )

    except Exception as e:
        app.logger.error(f"Error saving file {original_full_filename}: {e}")
        return jsonify(status='error', message=f'保存文件时出错: {e}', filename=original_full_filename), 500

@app.route('/admin/initiate_url_download_task', methods=['POST'])
@login_required
def initiate_url_download_task():
    try:
        data = request.get_json()
        if not data:
            app.logger.error("Initiate task: No JSON body received.")
            return jsonify(status='error', message='请求体必须是JSON格式。'), 400
        
        category_name_raw = data.get('category')
        urls = data.get('urls')

        if not is_valid_category_name(category_name_raw):
            app.logger.warning(f"Initiate task: Invalid category name '{category_name_raw}'.")
            return jsonify(status='error', message='无效的分类名称。'), 400
        
        if not urls or not isinstance(urls, list) or not all(isinstance(url, str) and url.strip() for url in urls):
            app.logger.warning(f"Initiate task: Invalid URLs list for category '{category_name_raw}'.")
            return jsonify(status='error', message='URL列表必须是一个包含有效URL字符串的非空数组。'), 400

        category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name_raw)
        if not os.path.isdir(category_path):
            app.logger.warning(f"Initiate task: Category '{category_name_raw}' not found at path '{category_path}'.")
            return jsonify(status='error', message=f'分类 "{category_name_raw}" 不存在。'), 404

        task_id = str(uuid.uuid4())
        url_processing_tasks[task_id] = {
            'category': category_name_raw,
            'urls': [url.strip() for url in urls], # Store cleaned URLs
            'status': 'pending',
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        app.logger.info(f"Task {task_id} initiated for category '{category_name_raw}' with {len(urls)} URLs.")
        return jsonify({'task_id': task_id, 'status': 'Task initiated successfully'}), 202
    except Exception as e:
        app.logger.error(f"Error in initiate_url_download_task: {e}", exc_info=True)
        return jsonify(status='error', message=f'启动任务时发生内部服务器错误。'), 500

@app.route('/admin/stream_url_download_progress') # New route name
@login_required
def stream_url_download_progress(): # New function name
    task_id = request.args.get('task_id')
    if not task_id:
        app.logger.error("SSE stream: task_id missing.")
        def error_stream_no_task_id():
            yield f"event: error\ndata: {json.dumps({'message': '错误：缺少任务ID。'})}\n\n"
        return Response(error_stream_no_task_id(), mimetype='text/event-stream')

    task_data = url_processing_tasks.get(task_id)
    if not task_data:
        app.logger.error(f"SSE stream: Task ID '{task_id}' not found or expired.")
        def error_stream_invalid_task_id():
            yield f"event: error\ndata: {json.dumps({'message': '错误：无效或已过期的任务ID。'})}\n\n"
        return Response(error_stream_invalid_task_id(), mimetype='text/event-stream')

    category_name_raw = task_data['category']
    image_urls = task_data['urls']
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name_raw)

    def generate_events_for_task(): # Renamed the inner generator
        app.logger.info(f"SSE stream starting for task_id: {task_id} (Category: {category_name_raw}, URLs: {len(image_urls)})")
        yield f"event: message\ndata: {json.dumps({'type': 'info', 'message': f'开始处理任务 {task_id}，共 {len(image_urls)} 个 URL...'})}\n\n"
        
        processed_count = 0
        for index, image_url in enumerate(image_urls):
            progress_item_id = f"task-{task_id}-item-{index}"
            app.logger.info(f"[Task {task_id} - Item {progress_item_id}] 处理 URL: {image_url}")
            yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': '准备中', 'progress': 0})}\n\n"
            
            MAX_RETRIES = 3
            CONNECT_TIMEOUT = 5 # seconds
            READ_TIMEOUT = 15   # seconds for reading chunks (per chunk, effectively)

            success = False
            last_exception_message = "未知错误"
            # Fixed timestamp for this item's processing to ensure consistent filename if retries save successfully
            item_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")

            for attempt in range(MAX_RETRIES):
                try:
                    app.logger.info(f"[Task {task_id} - Item {progress_item_id}] Attempt {attempt + 1}/{MAX_RETRIES} for URL: {image_url}")
                    
                    parsed_url = urlparse(image_url)
                    if not all([parsed_url.scheme, parsed_url.netloc]) or parsed_url.scheme not in ('http', 'https'):
                        raise ValueError("无效的 URL 格式或协议")
                    clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, parsed_url.query, ''))
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

                    response = requests.get(clean_url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), headers=headers)
                    response.raise_for_status()
                    
                    content_type = response.headers.get('content-type')
                    content_type_main = content_type.split(';')[0].strip().lower() if content_type else ''
                    if content_type_main not in ('image/jpeg', 'image/png', 'image/gif'):
                        raise ValueError(f'不支持的内容类型: {content_type_main or "未知"}')

                    file_extension = mimetypes.guess_extension(content_type_main)
                    if not file_extension or file_extension.lstrip('.').lower() not in ALLOWED_EXTENSIONS:
                        _, ext_from_url = os.path.splitext(os.path.basename(parsed_url.path))
                        if ext_from_url and ext_from_url.lstrip('.').lower() in ALLOWED_EXTENSIONS:
                            file_extension = ext_from_url
                        else:
                            raise ValueError('无法确定有效扩展名')
                    
                    original_filename = os.path.basename(parsed_url.path) or "image"
                    filename_base, _ = os.path.splitext(original_filename)
                    safe_filename_base = secure_filename(filename_base)
                    if not safe_filename_base: safe_filename_base = "image"
                    
                    safe_extension = file_extension.lower()
                    if not safe_extension.startswith('.'): safe_extension = '.' + safe_extension
                    new_filename = f"{safe_filename_base}_{item_timestamp}{safe_extension}" # Use item_timestamp
                    save_path = os.path.join(category_path, new_filename)
                    
                    total_size_str = response.headers.get('content-length')
                    total_size = int(total_size_str) if total_size_str and total_size_str.isdigit() else None
                    
                    downloaded_size = 0
                    last_yield_time = datetime.datetime.now()

                    yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': f'下载中 (尝试 {attempt + 1})', 'progress': 0, 'downloaded': 0, 'total': total_size})}\n\n"

                    with open(save_path, 'wb') as f: # Overwrites or creates file for each attempt
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                now = datetime.datetime.now()
                                if (now - last_yield_time).total_seconds() > 0.2 or \
                                   (total_size is not None and downloaded_size == total_size) or \
                                   (total_size is None and (now - last_yield_time).total_seconds() > 1):
                                    progress_percent = -1
                                    if total_size is not None and total_size > 0:
                                        progress_percent = round((downloaded_size / total_size) * 100)
                                    
                                    yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': f'下载中 (尝试 {attempt + 1})', 'progress': progress_percent, 'downloaded': downloaded_size, 'total': total_size})}\n\n"
                                    last_yield_time = now
                    
                    app.logger.info(f"[Task {task_id} - Item {progress_item_id}] Attempt {attempt + 1} Succeeded. Saved as: {new_filename}")
                    yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': '完成', 'progress': 100, 'new_filename': new_filename, 'message': '上传成功'})}\n\n"
                    success = True
                    processed_count +=1
                    break

                except requests.exceptions.Timeout as e_timeout:
                    last_exception_message = f'下载超时 (尝试 {attempt + 1}/{MAX_RETRIES})'
                    app.logger.warning(f"[Task {task_id} - Item {progress_item_id}] {last_exception_message}: {e_timeout}")
                    if attempt < MAX_RETRIES - 1:
                        yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': f'超时，重试中... ({attempt + 2}/{MAX_RETRIES})', 'progress': 0, 'message': last_exception_message})}\n\n"
                        time.sleep(1)
                    # Error for last attempt handled by 'if not success' block
                
                except requests.exceptions.RequestException as e_req:
                    last_exception_message = f'网络错误 (尝试 {attempt + 1}/{MAX_RETRIES})'
                    app.logger.warning(f"[Task {task_id} - Item {progress_item_id}] {last_exception_message}: {e_req}")
                    if attempt < MAX_RETRIES - 1:
                         yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': f'网络错误，重试中... ({attempt + 2}/{MAX_RETRIES})', 'progress': 0, 'message': last_exception_message})}\n\n"
                         time.sleep(1)
                    # Error for last attempt handled by 'if not success' block

                except (IOError, ValueError, Exception) as e_proc:
                    last_exception_message = f'处理失败: {str(e_proc)}'
                    app.logger.warning(f"[Task {task_id} - Item {progress_item_id}] {last_exception_message}", exc_info=True)
                    success = False
                    break

            if not success:
                app.logger.error(f"[Task {task_id} - Item {progress_item_id}] URL {image_url} failed after {MAX_RETRIES} attempts or due to non-retryable error. Last error: {last_exception_message}")
                yield f"event: progress\ndata: {json.dumps({'id': progress_item_id, 'url': image_url, 'status': '错误', 'progress': 0, 'message': last_exception_message})}\n\n"
        
        app.logger.info(f"[Task {task_id}] 所有 URL 处理完毕. Processed: {processed_count}/{len(image_urls)}")
        yield f"event: end\ndata: {json.dumps({'message': f'任务 {task_id} 处理完毕。成功处理 {processed_count} / {len(image_urls)} 个 URL。'})}\n\n"
        
        if task_id in url_processing_tasks:
            del url_processing_tasks[task_id]
            app.logger.info(f"Task {task_id} data removed from memory.")
    
    return Response(generate_events_for_task(), mimetype='text/event-stream')
@app.route('/admin/category/<path:category_name>/add_external_links', methods=['POST'])
@login_required
def add_external_links(category_name):
    # Validate the raw category name directly
    if not is_valid_category_name(category_name):
        return jsonify(status='error', message='无效的分类名称'), 400

    # Use the validated name for path operations
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    if not os.path.isdir(category_path):
        # Use original name in error message
        return jsonify(status='error', message=f'分类 "{category_name}" 不存在'), 400

    urls_text = request.form.get('urls', '')
    if not urls_text.strip():
        return jsonify(status='error', message='未提供任何 URL'), 400

    image_urls = [url.strip() for url in urls_text.splitlines() if url.strip()]
    if not image_urls:
        # This case might be redundant if urls_text.strip() is empty, but good for clarity
        return jsonify(status='error', message='未提供任何有效的 URL'), 400

    external_links = load_external_links(category_name)
    new_links_added_count = 0
    processed_urls_messages = [] # To provide feedback for each URL

    for url_to_add in image_urls:
        try:
            parsed_url = urlparse(url_to_add)
            if not all([parsed_url.scheme, parsed_url.netloc]) or parsed_url.scheme not in ('http', 'https'):
                app.logger.warning(f"无效的 URL 格式或协议: {url_to_add} (分类: {category_name})")
                processed_urls_messages.append({'url': url_to_add, 'status': 'error', 'message': '无效的URL格式或协议'})
                continue 
        except ValueError: 
            app.logger.warning(f"解析URL时出错: {url_to_add} (分类: {category_name})")
            processed_urls_messages.append({'url': url_to_add, 'status': 'error', 'message': '解析URL时出错'})
            continue

        is_duplicate = False
        for existing_link in external_links:
            if existing_link.get('url') == url_to_add:
                is_duplicate = True
                app.logger.info(f"跳过重复的 URL: {url_to_add} (分类: {category_name})")
                processed_urls_messages.append({'url': url_to_add, 'status': 'skipped', 'message': '重复的URL'})
                break
        
        if is_duplicate:
            continue

        new_link = {
            'id': generate_unique_id(),
            'url': url_to_add,
            'type': 'external',
            'added_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        external_links.append(new_link)
        new_links_added_count += 1
        processed_urls_messages.append({'url': url_to_add, 'status': 'success', 'message': '添加成功'})
    
    if new_links_added_count > 0:
        if not save_external_links(category_name, external_links):
            return jsonify(status='error', message='保存外部链接时出错', details=processed_urls_messages), 500
        
        # Check if all processed URLs resulted in a successful addition
        all_successful_adds = True
        for detail in processed_urls_messages:
            if detail['url'] in image_urls and detail['status'] != 'success':
                 # This check is a bit complex because processed_urls_messages also contains skipped/error messages
                 # A simpler check might be if new_links_added_count == len(image_urls) (assuming no invalid format errors before duplicate check)
                 pass # For now, we rely on new_links_added_count vs image_urls length

        if new_links_added_count == len(image_urls): # Ideal case: all provided URLs were new and valid
             return jsonify(status='success', message=f'成功添加 {new_links_added_count} 个外部链接到分类 "{category_name}"。', details=processed_urls_messages)
        else: # Some were successful, some skipped/errored
             return jsonify(status='partial_success', message=f'操作完成。成功添加 {new_links_added_count} 个链接。部分URL可能被跳过或出错。', details=processed_urls_messages)

    elif not image_urls: # Should have been caught earlier
        return jsonify(status='error', message='未提供任何有效的 URL。', details=processed_urls_messages), 400
    else: # All provided URLs were invalid or duplicates
        return jsonify(status='warning', message='所有提供的 URL 均无效或已存在，未添加任何新链接。', details=processed_urls_messages), 400
    # Removed erroneous yield and Response(generate()) from here, as this is not an SSE endpoint.
    # The jsonify calls above are the correct way to return for this POST request.

@app.route('/emoticons/<path:category_name>/<path:filename>')
@login_required
def serve_emoticon_file(category_name, filename):
    # Validate category name, secure filename
    if not is_valid_category_name(category_name):
        app.logger.warning(f"Invalid category name requested: {category_name}")
        abort(404)
    
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        # Even if the original filename was valid UTF-8, if secure_filename changes it,
        # it might indicate potentially tricky characters. Abort for safety.
        app.logger.warning(f"Potentially unsafe filename requested: {filename} (secured: {safe_filename})")
        abort(404)
        
    # Use original validated category name, secured filename
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    file_path = os.path.join(category_path, safe_filename)

    if not os.path.isfile(file_path):
        app.logger.warning(f"Emoticon file not found: {file_path}")
        abort(404)
    
    return send_from_directory(category_path, safe_filename)

@app.route('/<path:category_name>')
def serve_random_emoticon(category_name):
    if not is_valid_category_name(category_name):
        abort(404)

    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    if not os.path.isdir(category_path):
        abort(404)

    all_available_items = []

    # 1. Load local images
    try:
        local_image_files = [f for f in os.listdir(category_path)
                             if os.path.isfile(os.path.join(category_path, f)) and allowed_file(f)]
        for filename in local_image_files:
            all_available_items.append({
                'id': filename, # Use filename as ID
                'type': 'local',
                'path': category_path, # Store path for send_from_directory
                'filename': filename
            })
    except OSError:
        # If error reading local files, we might still serve external links
        app.logger.error(f"Error reading local files for category {category_name} in serve_random_emoticon")


    # 2. Load external links
    external_links = load_external_links(category_name)
    for link in external_links:
        all_available_items.append({
            'id': link['id'], # Use the ID from external_links.json
            'type': 'external',
            'url': link['url']
        })

    if not all_available_items:
        abort(404) # No local images and no external links

    last_shown_map = session.get('last_shown_v2', {}) # Use a new session key to avoid conflict with old format
    last_shown_item_info = last_shown_map.get(category_name) # This will be a dict {'id': ..., 'type': ...} or None

    eligible_items = all_available_items
    if last_shown_item_info and len(all_available_items) > 1:
        # Filter out the last shown item based on its id and type
        possible_items = [
            item for item in all_available_items
            if not (item['id'] == last_shown_item_info['id'] and item['type'] == last_shown_item_info['type'])
        ]
        if possible_items:
            eligible_items = possible_items
    
    if not eligible_items: # Should only happen if all_available_items had only 1 item, and it was last_shown
        eligible_items = all_available_items # Fallback to serving any item if filtering left none

    chosen_item = random.choice(eligible_items)

    # Update session with the new last shown item's id and type
    last_shown_map[category_name] = {'id': chosen_item['id'], 'type': chosen_item['type']}
    session['last_shown_v2'] = last_shown_map
    session.modified = True

    if chosen_item['type'] == 'local':
        return send_from_directory(chosen_item['path'], chosen_item['filename'])
    elif chosen_item['type'] == 'external':
        # Before redirecting, ensure the URL is somewhat safe (already validated on input, but good practice)
        parsed_url = urlparse(chosen_item['url'])
        if parsed_url.scheme in ['http', 'https'] and parsed_url.netloc:
             return redirect(chosen_item['url'])
        else:
            app.logger.warning(f"Attempted to redirect to an invalid external URL: {chosen_item['url']}")
            # Fallback: if the chosen external URL is invalid, try to serve another random item
            # This is a simple fallback; a more robust solution might re-select or error differently.
            if len(all_available_items) > 1:
                # Try to pick another one, excluding the problematic one
                remaining_items = [item for item in all_available_items if item['id'] != chosen_item['id'] or item['type'] != chosen_item['type']]
                if remaining_items:
                    fallback_item = random.choice(remaining_items)
                    # Update session for the fallback item
                    last_shown_map[category_name] = {'id': fallback_item['id'], 'type': fallback_item['type']}
                    session['last_shown_v2'] = last_shown_map
                    session.modified = True
                    if fallback_item['type'] == 'local':
                        return send_from_directory(fallback_item['path'], fallback_item['filename'])
                    elif fallback_item['type'] == 'external' and urlparse(fallback_item['url']).scheme in ['http', 'https']:
                        return redirect(fallback_item['url'])
            # If all else fails or only one item which is bad
            abort(500) # Or a more specific error
    else:
        # Should not happen if types are only 'local' or 'external'
        app.logger.error(f"Unknown item type encountered: {chosen_item.get('type')}")
        abort(500)

@app.route('/admin/download/<path:category_name>/<path:filename>')
@login_required
def download_emoticon(category_name, filename):
    # Validate category name, secure filename
    if not is_valid_category_name(category_name):
        flash('无效的分类名称格式。', 'danger')
        return redirect(url_for('admin'))

    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        flash('无效的文件名格式。', 'danger')
        # Redirect back to the category view if possible
        redirect_url = url_for('view_category', category_name=category_name) if is_valid_category_name(category_name) else url_for('admin')
        return redirect(redirect_url)
        
    # Use original validated category name, secured filename
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    file_path = os.path.join(category_path, safe_filename)

    if not os.path.isfile(file_path):
        flash(f'文件 "{safe_filename}" 在分类 "{category_name}" 中未找到。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))
    
    try:
        return send_from_directory(category_path, safe_filename, as_attachment=True)
    except Exception as e:
        app.logger.error(f"Error sending file {file_path} for download: {e}")
        flash('下载文件时出错。', 'danger')
        return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/rename/<path:category_name>/<path:filename>', methods=['POST'])
@login_required
def rename_emoticon(category_name, filename):
    new_filename_raw = request.form.get('new_filename')

    # Validate category name, secure filename
    if not is_valid_category_name(category_name):
        flash('无效的分类名称格式。', 'danger')
        return redirect(url_for('admin'))

    safe_filename_old = secure_filename(filename)
    if not safe_filename_old or safe_filename_old != filename:
        flash('原始文件名无效。', 'danger')
        return redirect(url_for('view_category', category_name=category_name))

    if not new_filename_raw:
        flash('未提供新文件名。', 'danger')
        return redirect(url_for('view_category', category_name=category_name))
        
    # Use original validated category name for path
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    old_file_path = os.path.join(category_path, safe_filename_old)

    if not os.path.isfile(old_file_path):
        flash(f'原始文件 "{safe_filename_old}" 不存在。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    new_base_raw, new_ext_raw = os.path.splitext(new_filename_raw)
    _, old_ext = os.path.splitext(safe_filename_old)
    safe_new_base = secure_filename(new_base_raw)
    
    if not safe_new_base:
        flash('无效的新文件名基础部分。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    safe_filename_new = f"{safe_new_base}{old_ext.lower()}" 
    new_file_path = os.path.join(category_path, safe_filename_new)

    if safe_filename_new.lower() == safe_filename_old.lower():
         flash('新文件名与旧文件名相同。', 'info')
         return redirect(url_for('view_category', category_name=category_name))

    if os.path.exists(new_file_path):
        flash(f'目标文件名 "{safe_filename_new}" 已存在，请使用其他名称。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    try:
        os.rename(old_file_path, new_file_path)
        flash(f'文件已从 "{safe_filename_old}" 重命名为 "{safe_filename_new}".', 'success')
    except OSError as e:
        app.logger.error(f"Error renaming file {old_file_path} to {new_file_path}: {e}")
        flash(f'重命名文件时出错: {e}', 'danger')

    return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/delete_image/<path:category_name>/<path:filename>', methods=['POST'])
@login_required
def delete_emoticon(category_name, filename):
    # Validate category name, secure filename
    if not is_valid_category_name(category_name):
        flash('无效的分类名称格式。', 'danger')
        return redirect(url_for('admin'))
        
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        flash('无效的文件名格式。', 'danger')
        redirect_url = url_for('view_category', category_name=category_name) if is_valid_category_name(category_name) else url_for('admin')
        return redirect(redirect_url)
        
    # Use original validated category name, secured filename
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    file_path = os.path.join(category_path, safe_filename)

    if not os.path.isfile(file_path):
        flash(f'文件 "{safe_filename}" 在分类 "{category_name}" 中未找到。', 'warning') # Use original cat name
    else:
        try:
            os.remove(file_path)
            flash(f'文件 "{safe_filename}" 已成功删除。', 'success')
        except OSError as e:
            app.logger.error(f"Error deleting file {file_path}: {e}")
            flash(f'删除文件时出错: {e}', 'danger')

    return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/batch_delete/<path:category_name>', methods=['POST'])
@login_required
def batch_delete_emoticons(category_name):
    # Validate the raw category name directly
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    # Use the validated name for path operations
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    if not os.path.isdir(category_path):
        flash(f'分类 "{category_name}" 不存在。', 'warning') # Use original name
        return redirect(url_for('admin'))

    filenames_to_delete = request.form.getlist('filenames[]')
    
    if not filenames_to_delete:
        flash('没有选中任何文件进行删除。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    success_count = 0
    error_details = []

    for filename in filenames_to_delete:
        safe_filename = secure_filename(filename) 
        if not safe_filename or safe_filename != filename: 
            error_details.append(f"'{filename}': 无效的文件名格式")
            continue

        file_path = os.path.join(category_path, safe_filename)
        
        if not os.path.isfile(file_path):
            app.logger.warning(f"Attempted to batch delete non-existent file: {file_path}")
            continue
        else:
            try:
                os.remove(file_path)
                success_count += 1
            except OSError as e:
                app.logger.error(f"Error batch deleting file {file_path}: {e}")
                error_details.append(f"'{safe_filename}': 删除失败 ({e})")

    if success_count > 0:
        flash(f'成功删除了 {success_count} 个文件。', 'success')
    if error_details:
        flash(f'{len(error_details)} 个文件删除失败: {", ".join(error_details)}', 'danger')

    return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/category/<path:category_name>/external_link/<link_id>/edit', methods=['POST'])
@login_required
def edit_external_link(category_name, link_id):
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    new_url = request.form.get('new_url', '').strip()
    if not new_url:
        flash('新的 URL 不能为空。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    try:
        parsed_new_url = urlparse(new_url)
        if not all([parsed_new_url.scheme, parsed_new_url.netloc]) or parsed_new_url.scheme not in ('http', 'https'):
            flash('无效的新 URL 格式或协议。', 'warning')
            return redirect(url_for('view_category', category_name=category_name))
    except ValueError:
        flash('解析新 URL 时出错。', 'warning')
        return redirect(url_for('view_category', category_name=category_name))

    external_links = load_external_links(category_name)
    link_found = False
    for link_idx, link in enumerate(external_links):
        if link.get('id') == link_id:
            # Check if this new URL already exists (excluding the current link being edited)
            for other_idx, other_link in enumerate(external_links):
                if other_idx != link_idx and other_link.get('url') == new_url:
                    flash(f'新的 URL "{new_url}" 已在该分类中存在。', 'warning')
                    return redirect(url_for('view_category', category_name=category_name))
            
            link['url'] = new_url
            # Optionally update 'added_at' to reflect modification time, or keep original add time
            # link['added_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            link_found = True
            break
    
    if link_found:
        if save_external_links(category_name, external_links):
            flash('外部链接已成功更新。', 'success')
        else:
            flash('保存外部链接时出错。', 'danger')
    else:
        flash('未找到要编辑的外部链接。', 'warning')

    return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/category/<path:category_name>/external_link/<link_id>/delete', methods=['POST'])
@login_required
def delete_external_link(category_name, link_id):
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    external_links = load_external_links(category_name)
    original_length = len(external_links)
    
    # Filter out the link to be deleted
    external_links_updated = [link for link in external_links if link.get('id') != link_id]

    if len(external_links_updated) < original_length:
        if save_external_links(category_name, external_links_updated):
            flash('外部链接已成功删除。', 'success')
        else:
            flash('保存外部链接时出错（删除操作）。', 'danger')
    else:
        flash('未找到要删除的外部链接，或链接已被删除。', 'warning')
        
    return redirect(url_for('view_category', category_name=category_name))

@app.route('/admin/batch_delete_categories', methods=['POST'])
@login_required
def batch_delete_categories():
    category_names_to_delete = request.form.getlist('category_names[]') # Expecting this name from JS
    
    if not category_names_to_delete:
        flash('没有选中任何分类进行删除。', 'warning')
        return redirect(url_for('admin'))

    success_count = 0
    error_details = []
    emoticons_dir = app.config['EMOTICONS_FOLDER']

    for category_name in category_names_to_delete:
        if not is_valid_category_name(category_name):
            error_details.append(f"'{category_name}': 无效的名称格式")
            continue

        category_path = os.path.join(emoticons_dir, category_name)
        
        if not os.path.isdir(category_path):
            app.logger.warning(f"Attempted to batch delete non-existent category: {category_path}")
            # error_details.append(f"'{category_name}': 未找到") # Optionally report not found
            continue # Silently skip if not found
        else:
            try:
                shutil.rmtree(category_path)
                # Clear session cache for this category if needed
                last_shown = session.get('last_shown', {})
                if category_name in last_shown:
                    del last_shown[category_name]
                    session['last_shown'] = last_shown
                    session.modified = True
                success_count += 1
            except OSError as e:
                app.logger.error(f"Error batch deleting category {category_path}: {e}")
                error_details.append(f"'{category_name}': 删除失败 ({e})")

    if success_count > 0:
        flash(f'成功删除了 {success_count} 个分类。', 'success')
    if error_details:
        flash(f'{len(error_details)} 个分类删除失败: {", ".join(error_details)}', 'danger')

    # Redirect back to admin, potentially preserving page/per_page if desired (omitted for simplicity now)
    return redirect(url_for('admin'))
@app.route('/admin/batch_delete_items/<path:category_name>', methods=['POST'])
@login_required
def batch_delete_items(category_name):
    if not is_valid_category_name(category_name):
        return jsonify(status='error', message='无效的分类名称。'), 400

    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)
    if not os.path.isdir(category_path):
        return jsonify(status='error', message=f'分类 "{category_name}" 不存在。'), 404

    try:
        data = request.get_json()
        if not data or 'items_to_delete' not in data or not isinstance(data['items_to_delete'], list):
            return jsonify(status='error', message='请求体无效，缺少 "items_to_delete" 列表。'), 400
        items_to_delete = data['items_to_delete']
    except Exception as e:
        app.logger.error(f"Error parsing JSON for batch_delete_items: {e}")
        return jsonify(status='error', message='请求体JSON解析错误。'), 400

    results = []
    external_links_changed = False
    current_external_links = None # Load only once if needed

    for item in items_to_delete:
        item_id = item.get('id')
        item_type = item.get('type')
        item_name = item.get('name', item_id) # Fallback name to id if not provided

        if not item_id or not item_type:
            results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': '项目缺少 "id" 或 "type"'})
            continue

        if item_type == 'local':
            safe_filename = secure_filename(item_id)
            if not safe_filename or safe_filename != item_id:
                results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': '本地文件名无效。'})
                continue
            
            file_path = os.path.join(category_path, safe_filename)
            if not os.path.isfile(file_path):
                results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': '本地文件未找到。'})
            else:
                try:
                    os.remove(file_path)
                    results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'success', 'message': '本地文件已删除。'})
                except OSError as e:
                    app.logger.error(f"Error deleting local file {file_path}: {e}")
                    results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': f'删除本地文件时出错: {e}'})
        
        elif item_type == 'external':
            if current_external_links is None: # Load once
                current_external_links = load_external_links(category_name)
            
            original_link_count = len(current_external_links)
            current_external_links = [link for link in current_external_links if link.get('id') != item_id]
            
            if len(current_external_links) < original_link_count:
                external_links_changed = True
                results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'success', 'message': '外部链接已标记为删除。'})
            else:
                results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': '外部链接未找到或已被删除。'})
        
        else:
            results.append({'id': item_id, 'type': item_type, 'name': item_name, 'status': 'error', 'message': f'未知的项目类型: {item_type}'})

    if external_links_changed:
        if not save_external_links(category_name, current_external_links):
            # If saving fails, update status for all 'external' items that were 'success'
            for res in results:
                if res['type'] == 'external' and res['status'] == 'success':
                    res['status'] = 'error'
                    res['message'] = '外部链接已标记为删除，但保存更改失败。'
            # Optionally, add a general error message to the response
            # return jsonify(status='error', message='保存外部链接更改时出错。', results=results), 500
            app.logger.error(f"Failed to save external_links.json for category {category_name} after batch delete.")
            # The individual statuses will reflect the save failure for external links.

    return jsonify(results=results)

if __name__ == '__main__':
    @app.context_processor
    def inject_config():
        return dict(config=app.config)
    app.run(debug=True) 