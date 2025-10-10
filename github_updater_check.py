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


# ===== FIX UNICODE ERROR =====
if sys.platform == "win32":
    import io
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except AttributeError:
            pass

os.environ['PYTHONIOENCODING'] = 'utf-8'

load_dotenv()
VERSION_FILE = "version.json"

# ✅ FIX: In đúng path của VERSION_FILE
print(f"[DEBUG] VERSION_FILE path: {os.path.abspath(VERSION_FILE)}")

def load_current_version():
    """Đọc version hiện tại từ version.json"""
    try:
        if not os.path.exists(VERSION_FILE):
            print(f"[DEBUG] Không tìm thấy {VERSION_FILE}, tạo mới với version 1.0.0")
            save_current_version("1.0.0")
            return "1.0.0"
            
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            version_str = data.get("version", "1.0.0")
            print(f"[DEBUG] ✅ Đã đọc version hiện tại từ {VERSION_FILE}: {version_str}")
            return version_str
    except json.JSONDecodeError as e:
        print(f"[DEBUG] ❌ Lỗi JSON trong {VERSION_FILE}: {e}")
        print(f"[DEBUG] Tạo lại file với version 1.0.0")
        save_current_version("1.0.0")
        return "1.0.0"
    except Exception as e:
        print(f"[DEBUG] ❌ Lỗi khi đọc {VERSION_FILE}: {e}")
        return "1.0.0"

def save_current_version(new_version):
    """Ghi version mới vào version.json"""
    try:
        data = {"version": new_version}
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[DEBUG] ✅ Đã ghi version mới vào {VERSION_FILE}: {new_version}")
        
        # Verify ghi thành công
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            verify_data = json.load(f)
            print(f"[DEBUG] 🔍 Verify: {verify_data}")
            
    except Exception as e:
        print(f"[DEBUG] ❌ Lỗi khi ghi {VERSION_FILE}: {e}")

class GitHubUpdateChecker:
    def __init__(self, current_version, github_repo):
        self.current_version = current_version
        self.github_repo = github_repo
        self.api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
        
    def check_for_updates(self):
        """Kiểm tra phiên bản mới nhất từ GitHub Releases"""
        try:
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Python-Update-Checker'
            }
            
            self._safe_print(f"[DEBUG] Kiểm tra cập nhật từ {self.api_url}")
            self._safe_print(f"[DEBUG] Phiên bản hiện tại: {self.current_version}")
            
            response = requests.get(self.api_url, headers=headers, timeout=10)
            self._safe_print(f"[DEBUG] Repo status: {response.status_code}")
            
            response.raise_for_status()
            release_data = response.json()
            
            # Lấy thông tin version
            remote_version = release_data['tag_name'].lstrip('v')
            self._safe_print(f"[DEBUG] Phiên bản mới nhất: {remote_version}")
            
            # So sánh version
            if version.parse(remote_version) > version.parse(self.current_version):
                exe_asset = None
                
                for asset in release_data['assets']:
                    if asset['name'].endswith('.exe'):
                        exe_asset = asset
                        break
                
                update_info = {
                    'version': remote_version,
                    'download_url': exe_asset['browser_download_url'] if exe_asset else None,
                    'size': exe_asset['size'] if exe_asset else 0,
                    'changelog': release_data['body'],
                    'release_date': release_data['published_at'],
                    'release_name': release_data['name']
                }
                
                self._safe_print(f"[DEBUG] Download URL: {update_info['download_url']}")
                return True, update_info
            
            self._safe_print(f"[DEBUG] ✅ Đã dùng phiên bản mới nhất")
            return False, None
            
        except requests.exceptions.RequestException as e:
            self._safe_print(f"❌ Lỗi kết nối: {e}")
            return False, None
        except Exception as e:
            self._safe_print(f"❌ Lỗi khi kiểm tra cập nhật: {e}")
            return False, None
    
    def _safe_print(self, text):
        """In ra console an toàn"""
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode('ascii', errors='ignore').decode('ascii'))
    
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
            
            print(f"[DEBUG] ✅ Đã tải xuống: {save_path} ({os.path.getsize(save_path)} bytes)")
            return True
            
        except Exception as e:
            self._safe_print(f"❌ Lỗi khi tải xuống: {e}")
            return False
    
    def _show_error(self, message, title="Lỗi cập nhật"):
        """Hiển thị lỗi trong dialog"""
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, message)
            root.destroy()
        except Exception as e:
            self._safe_print(f"❌ Lỗi khi hiển thị dialog: {e}")
            self._safe_print(message)

    def install_update(self, installer_path, new_version):
        """
        ✅ CẢI THIỆN: Thêm tham số new_version để ghi vào version.json sau khi update
        """
        try:
            # Kiểm tra chạy dưới dạng .exe
            if not getattr(sys, 'frozen', False):
                print("⚠️ CẢNH BÁO: Không thể tự cập nhật khi đang chạy bằng Python script")
                self._show_error(
                    "Không thể tự cập nhật khi đang chạy bằng Python script (.py)\n"
                    "Vui lòng build thành .exe trước."
                )
                return False

            # Lấy đường dẫn file exe hiện tại
            current_exe = os.path.abspath(sys.executable)
            print(f"[DEBUG] Đường dẫn file hiện tại: {current_exe}")
            
            # Kiểm tra an toàn
            exe_name = os.path.basename(current_exe).lower()
            if exe_name in ['python.exe', 'pythonw.exe', 'python3.exe']:
                print("❌ LỖI: Phát hiện đường dẫn là Python interpreter!")
                self._show_error(f"Phát hiện đường dẫn là Python interpreter!\n{current_exe}")
                return False
            
            exe_dir = os.path.dirname(current_exe).lower()
            dangerous_paths = ['python', 'scripts', 'lib', 'site-packages']
            if any(danger in exe_dir for danger in dangerous_paths):
                print("❌ LỖI: File exe nằm trong thư mục Python!")
                self._show_error(f"File exe nằm trong thư mục hệ thống Python:\n{current_exe}")
                return False

            # Kiểm tra file cập nhật
            if not os.path.exists(installer_path):
                print(f"❌ Không tìm thấy file cập nhật: {installer_path}")
                self._show_error(f"Không tìm thấy file cập nhật:\n{installer_path}")
                return False
            
            if not installer_path.lower().endswith('.exe'):
                print(f"❌ File cập nhật không hợp lệ: {installer_path}")
                self._show_error(f"File cập nhật không hợp lệ (phải là .exe)")
                return False
            
            if os.path.abspath(installer_path) == current_exe:
                print("❌ File cập nhật trùng với file hiện tại!")
                self._show_error("File cập nhật trùng với file hiện tại!")
                return False

            # In thông tin
            print("\n" + "="*60)
            print("📄 THÔNG TIN CẬP NHẬT:")
            print(f"   File hiện tại: {current_exe}")
            print(f"   File cập nhật:  {installer_path}")
            print(f"   Phiên bản mới: {new_version}")
            print(f"   Kích thước: {os.path.getsize(installer_path) / 1024 / 1024:.2f} MB")
            print("="*60 + "\n")

            # ✅ GHI VERSION MỚI VÀO version.json TRƯỚC KHI CẬP NHẬT
            # Lý do: Nếu cập nhật thành công, app mới sẽ đọc version đúng
            version_file_path = os.path.join(os.path.dirname(current_exe), VERSION_FILE)
            print(f"[DEBUG] Ghi version mới vào: {version_file_path}")
            
            try:
                with open(version_file_path, "w", encoding="utf-8") as f:
                    json.dump({"version": new_version}, f, indent=4, ensure_ascii=False)
                print(f"[DEBUG] ✅ Đã ghi version {new_version} vào {version_file_path}")
            except Exception as e:
                print(f"[DEBUG] ⚠️ Không thể ghi version.json: {e}")
                # Tiếp tục cập nhật, không fail

            # Tạo batch script
            batch_script = f"""@echo off
chcp 65001 >nul
echo ====================================
echo    DANG CAP NHAT UNG DUNG...
echo ====================================
echo.

REM Đợi ứng dụng cũ đóng hoàn toàn
echo [1/4] Cho ung dung cu dong...
timeout /t 2 /nobreak > NUL

REM Xóa file exe cũ
echo [2/4] Xoa file cu...
del "{current_exe}" > NUL 2>&1
if errorlevel 1 (
    echo LOI: Khong the xoa file cu!
    pause
    exit /b 1
)

timeout /t 1 /nobreak > NUL

REM Di chuyển file mới vào vị trí
echo [3/4] Cai dat phien ban moi...
move /Y "{installer_path}" "{current_exe}" > NUL 2>&1
if errorlevel 1 (
    echo LOI: Khong the cai dat file moi!
    pause
    exit /b 1
)

REM Chạy ứng dụng mới
echo [4/4] Khoi dong ung dung...
timeout /t 1 /nobreak > NUL
start "" "{current_exe}"

REM Tự xóa batch script
del "%~f0"
exit
"""
            
            # Lưu batch script
            batch_path = os.path.join(tempfile.gettempdir(), "app_updater.bat")
            print(f"[DEBUG] Tạo batch script tại: {batch_path}")
            
            with open(batch_path, 'w', encoding='utf-8-sig') as f:
                f.write(batch_script)
            
            print(f"✅ Đã tạo script cập nhật: {batch_path}")

            # Chạy batch script và thoát
            print("🚀 Bắt đầu cập nhật...")
            print("   Ứng dụng sẽ tự động khởi động lại sau khi cập nhật\n")
            
            subprocess.Popen(
                batch_path, 
                shell=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            import time
            time.sleep(0.5)
            sys.exit(0)

        except PermissionError as e:
            print(f"❌ Lỗi quyền truy cập: {e}")
            self._show_error("Vui lòng chạy ứng dụng với quyền Administrator")
            return False
        
        except Exception as e:
            print(f"💥 Lỗi khi cài đặt cập nhật: {e}")
            import traceback
            traceback.print_exc()
            self._show_error(f"Lỗi khi cài đặt cập nhật:\n{e}")
            return False
    
    def show_update_dialog(self, update_info):
        """Hiển thị dialog cập nhật với progress bar"""
        root = tk.Tk()
        root.title("Cập nhật có sẵn")
        root.geometry("500x400")
        root.resizable(False, False)
        
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
        info_text += f"Dung lượng: {update_info['size'] / 1024 / 1024:.2f} MB"
        
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
        
        # Progress bar
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
                temp_installer = None
                try:
                    temp_installer = os.path.join(tempfile.gettempdir(), "update_installer.exe")
                    
                    # Tải file
                    if self.download_update_with_progress(update_info['download_url'], temp_installer, progress_callback):
                        progress_label.config(text="Đang chuẩn bị cài đặt...")
                        progress_bar['value'] = 100
                        root.update_idletasks()
                        
                        # ✅ TRUYỀN new_version VÀO install_update
                        success = self.install_update(temp_installer, update_info['version'])
                        
                        if success:
                            # ✅ Nếu thành công (batch script đã chạy), hiển thị thông báo
                            root.after(0, show_success_dialog)
                        else:
                            # ❌ Nếu thất bại, hiển thị lỗi và reset UI
                            root.after(0, lambda: show_error_dialog("Không thể cài đặt bản cập nhật."))
                            
                            if temp_installer and os.path.exists(temp_installer):
                                try:
                                    os.remove(temp_installer)
                                except Exception:
                                    pass
                    else:
                        # ❌ Download thất bại
                        root.after(0, lambda: show_error_dialog("Không thể tải xuống bản cập nhật."))
                
                except Exception as e:
                    # ❌ Lỗi nghiêm trọng
                    import traceback
                    traceback.print_exc()
                    root.after(0, lambda: show_error_dialog(f"Đã xảy ra lỗi:\n{e}"))
            
            def show_success_dialog():
                """Hiển thị dialog thành công với nút Restart"""
                # Ẩn progress
                progress_frame.pack_forget()
                
                # Ẩn changelog
                changelog_label.pack_forget()
                changelog_frame.pack_forget()
                
                # Hiển thị thông báo thành công
                success_frame = tk.Frame(main_frame, bg='#E8F5E9', relief=tk.SOLID, borderwidth=1)
                success_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
                
                success_icon = tk.Label(success_frame, text="✅", font=('Arial', 48), bg='#E8F5E9')
                success_icon.pack(pady=(20, 10))
                
                success_label = tk.Label(
                    success_frame, 
                    text="Cập nhật thành công!", 
                    font=('Arial', 14, 'bold'),
                    bg='#E8F5E9',
                    fg='#2E7D32'
                )
                success_label.pack(pady=(0, 10))
                
                success_msg = tk.Label(
                    success_frame,
                    text=f"Đã cập nhật lên phiên bản {update_info['version']}\nỨng dụng sẽ khởi động lại tự động.",
                    font=('Arial', 10),
                    bg='#E8F5E9',
                    justify=tk.CENTER
                )
                success_msg.pack(pady=(0, 20))
                
                # Clear button frame cũ
                for widget in button_frame.winfo_children():
                    widget.destroy()
                
                # Nút Restart ngay
                restart_btn = tk.Button(
                    button_frame, 
                    text="🔄 Khởi động lại ngay", 
                    command=lambda: restart_app(),
                    bg='#4CAF50', 
                    fg='white', 
                    padx=20, 
                    pady=8, 
                    font=('Arial', 11, 'bold'),
                    cursor='hand2'
                )
                restart_btn.pack(side=tk.LEFT, padx=5)
                
                # Nút Đóng
                close_btn = tk.Button(
                    button_frame, 
                    text="Đóng", 
                    command=root.destroy,
                    padx=20, 
                    pady=8,
                    font=('Arial', 10)
                )
                close_btn.pack(side=tk.LEFT, padx=5)
                
                # Auto close sau 10 giây và restart
                countdown = [10]
                countdown_label = tk.Label(
                    success_frame,
                    text=f"Tự động khởi động lại sau {countdown[0]} giây...",
                    font=('Arial', 9),
                    bg='#E8F5E9',
                    fg='#666'
                )
                countdown_label.pack(pady=(0, 10))
                
                def update_countdown():
                    countdown[0] -= 1
                    if countdown[0] > 0:
                        countdown_label.config(text=f"Tự động khởi động lại sau {countdown[0]} giây...")
                        root.after(1000, update_countdown)
                    else:
                        restart_app()
                
                root.after(1000, update_countdown)
            
            def show_error_dialog(error_message):
                """Hiển thị dialog lỗi và reset UI"""
                messagebox.showerror("Lỗi cập nhật", error_message)
                
                progress_label.config(text="Cập nhật thất bại")
                progress_bar['value'] = 0
                update_btn.config(state=tk.NORMAL)
                skip_btn.config(state=tk.NORMAL)
            
            def restart_app():
                """Khởi động lại ứng dụng"""
                try:
                    current_exe = os.path.abspath(sys.executable)
                    subprocess.Popen([current_exe], shell=False)
                    root.destroy()
                    sys.exit(0)
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không thể khởi động lại:\n{e}")
            
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