import requests
import json
import os
import sys
import subprocess
import tempfile
import shutil
from packaging import version
import tkinter as tk
from tkinter import messagebox, ttk
import threading
from dotenv import load_dotenv
load_dotenv()

class pGitHubUpdateChecker:
    def __init__(self, current_version, github_repo):
        """
        current_version: 1.0.0
        github_repo: "HoangLinh03-code/ToolGen"
        """
        self.current_version = current_version

        self.github_repo = github_repo

        self.api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
        
    def check_for_updates(self):
        """Kiểm tra phiên bản mới nhất từ GitHub Releases"""
        try:
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': f'Bearer {os.getenv("GITHUB_TOKEN")}',
                'User-Agent': 'Python-Update-Checker'
            }
            print(f"[DEBUG] Kiểm tra cập nhật từ {headers}")

            print(f"[DEBUG] Gửi yêu cầu tới {self.api_url}")
            
            response = requests.get(self.api_url, headers=headers, timeout=10)

            print(f"Repo status: {response.status_code}")
            print(response.json())

            response.raise_for_status()
            
            release_data = response.json()
            
            # Lấy thông tin version
            remote_version = release_data['tag_name'].lstrip('v')
            
            # So sánh version
            if version.parse(remote_version) > version.parse(self.current_version):
                # Tìm file .exe trong assets
                exe_asset = None
                version_asset = None
                
                for asset in release_data['assets']:
                    if asset['name'].endswith('.exe'):
                        exe_asset = asset
                    elif asset['name'] == 'version.json':
                        version_asset = asset
                
                update_info = {
                    'version': remote_version,
                    'download_url': exe_asset['browser_download_url'] if exe_asset else None,
                    'size': exe_asset['size'] if exe_asset else 0,
                    'changelog': release_data['body'],
                    'release_date': release_data['published_at'],
                    'release_name': release_data['name']
                }
                
                return True, update_info
            
            return False, None
            
        except requests.exceptions.RequestException as e:
            print(f"Lỗi kết nối: {e}")
            return False, None
        except Exception as e:
            print(f"Lỗi khi kiểm tra cập nhật: {e}")
            return False, None
    
    def download_update_with_progress(self, download_url, save_path, progress_callback=None):
        """Tải xuống với progress bar"""
        try:
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress, downloaded, total_size)
            
            return True
            
        except Exception as e:
            print(f"Lỗi khi tải xuống: {e}")
            return False
    
    def install_update(self, installer_path):
        """Cài đặt bản cập nhật"""
        try:
            current_exe = sys.executable
            
            # Tạo script batch để thay thế file exe
            batch_script = f"""@echo off
echo Đang cập nhật...
timeout /t 2 /nobreak > NUL
taskkill /F /IM "{os.path.basename(current_exe)}" > NUL 2>&1
timeout /t 1 /nobreak > NUL
copy /Y "{installer_path}" "{current_exe}"
del "{installer_path}"
start "" "{current_exe}"
del "%~f0"
"""
            
            batch_path = os.path.join(tempfile.gettempdir(), "updater.bat")
            with open(batch_path, 'w', encoding='utf-8') as f:
                f.write(batch_script)
            
            # Chạy updater và thoát
            subprocess.Popen(batch_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            sys.exit(0)
            
        except Exception as e:
            print(f"Lỗi khi cài đặt: {e}")
            return False
    
    def show_update_dialog(self, update_info):
        """Hiển thị dialog cập nhật với progress bar"""
        root = tk.Tk()
        root.title("Cập nhật có sẵn")
        root.geometry("500x400")
        root.resizable(False, False)
        
        # Frame chính
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Tiêu đề
        title_label = tk.Label(
            main_frame, 
            text=f"Phiên bản mới: {update_info['version']}", 
            font=('Arial', 14, 'bold')
        )
        title_label.pack(pady=(0, 10))
        
        # Thông tin
        info_text = f"Phiên bản hiện tại: {self.current_version}\n"
        info_text += f"Kích thước: {update_info['size'] / 1024 / 1024:.2f} MB"
        
        info_label = tk.Label(main_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(pady=(0, 10))
        
        # Changelog
        changelog_label = tk.Label(main_frame, text="Thay đổi:", font=('Arial', 10, 'bold'))
        changelog_label.pack(anchor=tk.W)
        
        changelog_frame = tk.Frame(main_frame, relief=tk.SUNKEN, borderwidth=1)
        changelog_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        changelog_text = tk.Text(changelog_frame, wrap=tk.WORD, height=10)
        changelog_scroll = tk.Scrollbar(changelog_frame, command=changelog_text.yview)
        changelog_text.configure(yscrollcommand=changelog_scroll.set)
        
        changelog_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        changelog_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        changelog_text.insert('1.0', update_info['changelog'] or "Không có thông tin")
        changelog_text.config(state=tk.DISABLED)
        
        # Progress bar (ẩn ban đầu)
        progress_frame = tk.Frame(main_frame)
        progress_label = tk.Label(progress_frame, text="")
        progress_bar = ttk.Progressbar(progress_frame, length=400, mode='determinate')
        
        # Buttons
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=(10, 0))
        
        result = {'update': False}
        
        def on_update():
            result['update'] = True
            update_btn.config(state=tk.DISABLED)
            skip_btn.config(state=tk.DISABLED)
            
            # Hiện progress
            progress_frame.pack(fill=tk.X, pady=(10, 0))
            progress_label.pack()
            progress_bar.pack(pady=(5, 0))
            
            def progress_callback(percent, downloaded, total):
                progress_bar['value'] = percent
                downloaded_mb = downloaded / 1024 / 1024
                total_mb = total / 1024 / 1024
                progress_label.config(text=f"Đang tải: {downloaded_mb:.1f} / {total_mb:.1f} MB ({percent:.1f}%)")
                root.update_idletasks()
            
            def download_thread():
                temp_installer = os.path.join(tempfile.gettempdir(), "update_installer.exe")
                if self.download_update_with_progress(update_info['download_url'], temp_installer, progress_callback):
                    progress_label.config(text="Đang cài đặt...")
                    root.update_idletasks()
                    root.after(1000, lambda: self.install_update(temp_installer))
                else:
                    messagebox.showerror("Lỗi", "Không thể tải xuống bản cập nhật")
                    root.destroy()
            
            threading.Thread(target=download_thread, daemon=True).start()
        
        def on_skip():
            root.destroy()
        
        update_btn = tk.Button(button_frame, text="Cập nhật ngay", command=on_update, 
                               bg='#4CAF50', fg='white', padx=20, pady=5, font=('Arial', 10, 'bold'))
        update_btn.pack(side=tk.LEFT, padx=5)
        
        skip_btn = tk.Button(button_frame, text="Để sau", command=on_skip, 
                            padx=20, pady=5)
        skip_btn.pack(side=tk.LEFT, padx=5)
        
        root.mainloop()
        return result['update']


# ===== SỬ DỤNG TRONG APP =====
