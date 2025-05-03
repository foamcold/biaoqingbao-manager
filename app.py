import os
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

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_dev')
app.config['EMOTICONS_FOLDER'] = os.environ.get('EMOTICONS_FOLDER', 'emoticons')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_PER_PAGE = [50, 100, 150, 200, 250, 300]
ADMIN_ALLOWED_PER_PAGE = [10, 20, 30, 40, 50]

if not os.path.exists(app.config['EMOTICONS_FOLDER']):
    os.makedirs(app.config['EMOTICONS_FOLDER'])

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
    # Validate the raw category name directly
    if not is_valid_category_name(category_name):
        flash('无效的分类名称。', 'danger')
        return redirect(url_for('admin'))

    # Use the validated category name directly for the path
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)

    if not os.path.isdir(category_path):
        flash(f'分类 "{category_name}" 不存在。', 'warning') # Use original name
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

    all_image_files = []
    try:
        all_image_files = sorted([f for f in os.listdir(category_path)
                                 if os.path.isfile(os.path.join(category_path, f)) and allowed_file(f)])
    except OSError as e:
        flash(f'无法读取分类 "{category_name}" 的内容: {e}', 'danger')

    total_images = len(all_image_files)
    total_pages = math.ceil(total_images / per_page) if per_page > 0 else 1
    if page > total_pages and total_pages > 0:
        page = total_pages

    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    image_files_on_page = all_image_files[start_index:end_index]

    images_list_for_template = []
    for img_filename in image_files_on_page:
        images_list_for_template.append({
            'filename': img_filename,
            'view_url': url_for('serve_emoticon_file', category_name=category_name, filename=img_filename),
            'download_url': url_for('download_emoticon', category_name=category_name, filename=img_filename)
        })

    all_categories = []
    emoticons_dir = app.config['EMOTICONS_FOLDER']
    try:
        all_categories = sorted([d for d in os.listdir(emoticons_dir) if os.path.isdir(os.path.join(emoticons_dir, d))])
    except OSError as e:
        app.logger.warning(f'Could not list directories in {emoticons_dir}: {e}')

    return render_template('category_view.html',
                           category_name=category_name,
                           images=images_list_for_template,
                           all_categories=all_categories,
                           page=page,
                           per_page=per_page,
                           total_images=total_images,
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

@app.route('/admin/upload_url_stream')
@login_required
def upload_url_stream():
    category_name_raw = request.args.get('category', '')
    urls_text = request.args.get('urls', '')
    image_urls = [url.strip() for url in urls_text.splitlines() if url.strip()]

    # Validate the category name from the query args
    if not is_valid_category_name(category_name_raw):
        # SSE requires a text/event-stream response, even for errors initially
        # We can send an error event or just close the stream with an HTTP error later.
        # For simplicity, let's log and return a 400 for now.
        app.logger.error(f"Invalid category name for URL upload: {category_name_raw}")
        return "Error: Invalid category name", 400

    if not image_urls:
        return "Error: No URLs provided", 400
    
    # Use the validated name directly for path construction
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name_raw)
    if not os.path.isdir(category_path):
         app.logger.error(f"Category not found for URL upload: {category_path}")
         # Use original name in error message
         return f"Error: Category '{category_name_raw}' not found", 400

    def generate():
        yield f"event: message\ndata: {json.dumps({'type': 'info', 'message': '开始处理 URL 列表...'})}\n\n"
        
        for index, image_url in enumerate(image_urls):
            safe_timestamp_id = str(datetime.datetime.now().timestamp()).replace('.', '_')
            url_id = f"url-{index}-{safe_timestamp_id}"
            app.logger.info(f"[SSE {url_id}] 处理 URL: {image_url}")
            yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '准备中', 'progress': 0})}\n\n"
            
            try:
                parsed_url = urlparse(image_url)
                if not all([parsed_url.scheme, parsed_url.netloc]) or parsed_url.scheme not in ('http', 'https'):
                    raise ValueError("无效的 URL 格式或协议")
                clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, parsed_url.query, ''))

                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
                response = requests.get(clean_url, stream=True, timeout=20, headers=headers)
                response.raise_for_status()
                app.logger.info(f"[SSE {url_id}] 响应头: {response.headers}")

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
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
                safe_extension = file_extension.lower()
                if not safe_extension.startswith('.'): safe_extension = '.' + safe_extension
                new_filename = f"{safe_filename_base}_{timestamp}{safe_extension}"
                save_path = os.path.join(category_path, new_filename)
                
                total_size_str = response.headers.get('content-length')
                app.logger.info(f"[SSE {url_id}] Content-Length: {total_size_str}")
                total_size = None
                if total_size_str:
                    try:
                        total_size = int(total_size_str)
                    except ValueError:
                        app.logger.warning(f"[SSE {url_id}] 无效的 Content-Length 值: {total_size_str}")
                        total_size = None
                
                downloaded_size = 0
                last_yield_time = datetime.datetime.now()

                yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '下载中', 'progress': 0})}\n\n"

                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        now = datetime.datetime.now()
                        if (now - last_yield_time).total_seconds() > 0.1 or (total_size is not None and downloaded_size == total_size):
                            progress_percent = -1
                            if total_size is not None and total_size > 0:
                                progress_percent = round((downloaded_size / total_size) * 100)
                            
                            app.logger.debug(f"[SSE {url_id}] Yielding progress: {progress_percent}%, DL: {downloaded_size}, Total: {total_size}")
                            yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '下载中', 'progress': progress_percent, 'downloaded': downloaded_size, 'total': total_size})}\n\n"
                            last_yield_time = now
                
                app.logger.info(f"[SSE {url_id}] 下载完成，保存为: {new_filename}")
                yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '完成', 'progress': 100, 'new_filename': new_filename, 'message': '上传成功'})}\n\n"

            except requests.exceptions.RequestException as e:
                app.logger.warning(f"[SSE {url_id}] Error downloading URL {image_url}: {e}")
                yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '错误', 'progress': 0, 'message': f'下载失败: {e}'})}\n\n"
            except (IOError, ValueError, Exception) as e:
                app.logger.warning(f"[SSE {url_id}] Error processing URL {image_url}: {e}")
                yield f"event: progress\ndata: {json.dumps({'id': url_id, 'url': image_url, 'status': '错误', 'progress': 0, 'message': f'处理失败: {e}'})}\n\n"
        
        app.logger.info("[SSE] 所有 URL 处理完毕")
        yield f"event: end\ndata: {json.dumps({'message': '所有 URL 处理完毕'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

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
    # Validate the raw category name directly
    if not is_valid_category_name(category_name):
        abort(404)

    # Use the validated category name directly for the path
    category_path = os.path.join(app.config['EMOTICONS_FOLDER'], category_name)

    if not os.path.isdir(category_path):
        abort(404)

    try:
        image_files = [f for f in os.listdir(category_path)
                       if os.path.isfile(os.path.join(category_path, f)) and allowed_file(f)]
    except OSError:
        abort(500)

    if not image_files:
        abort(404)

    last_shown_images = session.get('last_shown', {})
    last_shown_in_category = last_shown_images.get(category_name)

    eligible_images = image_files
    if last_shown_in_category and len(image_files) > 1:
        possible_images = [img for img in image_files if img != last_shown_in_category]
        if possible_images:
            eligible_images = possible_images

    chosen_image = random.choice(eligible_images)

    last_shown_images[category_name] = chosen_image
    session['last_shown'] = last_shown_images
    session.modified = True

    return send_from_directory(category_path, chosen_image)

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

if __name__ == '__main__':
    @app.context_processor
    def inject_config():
        return dict(config=app.config)
    app.run(debug=True) 