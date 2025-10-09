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
    # Chỉ set nếu chưa được set (tránh conflict với GenQues.py)
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except AttributeError:
            # Nếu stdout/stderr không có buffer (đã được redirect), bỏ qua
            pass

os.environ['PYTHONIOENCODING'] = 'utf-8'

load_dotenv()
VERSION_FILE = "version.json"

print(f"[DEBUG] sys.executable: {VERSION_FILE}")

def load_current_version():
    """Đọc version hiện tại từ version.json (hoặc trả về mặc định nếu chưa có)."""
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            version_str = data.get("version", "1.0.0")
            print(f"[DEBUG] Đã đọc version hiện tại: {version_str}")
            return version_str
    except FileNotFoundError:
        print("[DEBUG] Không tìm thấy version.json, dùng mặc định 1.0.0")
        return "1.0.0"
    except Exception as e:
        print(f"[DEBUG] Lỗi khi đọc version.json: {e}")
        return "1.0.0"

def save_current_version(new_version):
    """Ghi version mới vào version.json sau khi update thành công."""
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": new_version}, f, indent=4, ensure_ascii=False)
        print(f"[DEBUG] Đã ghi version mới vào {VERSION_FILE}: {new_version}")
    except Exception as e:
        print(f"[DEBUG] Lỗi khi ghi version.json: {e}")

class GitHubUpdateChecker:
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
                # 'Authorization': f'Bearer {os.getenv("GITHUB_TOKEN")}',
                'User-Agent': 'Python-Update-Checker'
            }
            
            self._safe_print(f"[DEBUG] Kiểm tra cập nhật từ {self.api_url}")
            self._safe_print(f"[DEBUG] Phiên bản hiện tại: {self.current_version}")
            
            response = requests.get(self.api_url, headers=headers, timeout=10)

            self._safe_print(f"Repo status: {response.status_code}")
            
            response.raise_for_status()
            
            release_data = response.json()
            
            # Lấy thông tin version
            remote_version = release_data['tag_name'].lstrip('v')

            self._safe_print(f"[DEBUG] Phiên bản mới nhất: {remote_version}")
            
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

                print(f"[DEBUG] Download URL: {update_info}")
                
                return True, update_info
            
            return False, None
            
        except requests.exceptions.RequestException as e:
            self._safe_print(f"Lỗi kết nối: {e}")
            return False, None
        except Exception as e:
            self._safe_print(f"Lỗi khi kiểm tra cập nhật: {e}")
            return False, None
    
    def _safe_print(self, text):
        """In ra console an toàn, tránh lỗi encoding"""
        try:
            print(text)
        except UnicodeEncodeError:
            # Fallback: chỉ giữ ASCII
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
            
            return True
            
        except Exception as e:
            self._safe_print(f"Lỗi khi tải xuống: {e}")
            return False
    
    
    def _show_error(self, message, title="Lỗi cập nhật"):
        """Hiển thị lỗi trong dialog"""
        try:
            root = tk.Tk()
            root.withdraw()  # Ẩn cửa sổ chính
            messagebox.showerror("Lỗi", message)
            root.destroy()
        except Exception as e:
            self._safe_print(f"Lỗi khi hiển thị dialog lỗi: {e}")
            self._safe_print(message)

    def install_update(self, installer_path):
        """
        Cài đặt bản cập nhật một cách an toàn
        
        Args:
            installer_path: Đường dẫn đến file .exe mới đã tải về
        
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            # 1️⃣ KIỂM TRA BẮT BUỘC: Chỉ cho phép khi chạy dưới dạng .exe (PyInstaller)
            if not getattr(sys, 'frozen', False):
                print("⚠️ CẢNH BÁO: Không thể tự cập nhật khi đang chạy bằng Python script (.py)")
                print("   Vui lòng build thành .exe trước khi sử dụng tính năng tự động cập nhật")
                self._show_error(
                "Không thể tự cập nhật khi đang chạy bằng Python script (.py)\n"
                "Vui lòng build thành .exe trước khi sử dụng tính năng tự động cập nhật."
            )
                # return False

            # 2️⃣ LẤY ĐƯỜNG DẪN FILE EXE HIỆN TẠI (an toàn với PyInstaller)
            # current_exe = os.path.abspath(sys.executable)
            current_exe = r"D:\ToolGen\GenQues.exe"  # FOR TESTING ONLY

            print(f"[DEBUG] Đường dẫn file hiện tại: {current_exe}")
            
            # 🔒 KIỂM TRA AN TOÀN: Đảm bảo không phải python.exe
            exe_name = os.path.basename(current_exe).lower()
            if exe_name in ['python.exe', 'pythonw.exe', 'python3.exe']:
                print("❌ LỖI NGHIÊM TRỌNG: Phát hiện đường dẫn là Python interpreter!")
                print(f"   Đường dẫn: {current_exe}")
                print("   Từ chối cập nhật để bảo vệ hệ thống")
                self._show_error(
                f"Phát hiện đường dẫn là Python interpreter!\n\nĐường dẫn: {current_exe}\n\n"
                "Từ chối cập nhật để bảo vệ hệ thống."
               )
                return False
           
            
            # 🔒 KIỂM TRA THÊM: Đảm bảo file exe nằm trong thư mục ứng dụng
            # (không nằm trong thư mục Python hoặc Scripts)
            exe_dir = os.path.dirname(current_exe).lower()
            dangerous_paths = ['python', 'scripts', 'lib', 'site-packages']
            if any(danger in exe_dir for danger in dangerous_paths):
                print("❌ LỖI: File exe hiện tại nằm trong thư mục Python!")
                print(f"   Đường dẫn: {current_exe}")
                print("   Từ chối cập nhật để tránh ghi đè hệ thống")
                self._show_error(
                f"File exe hiện tại nằm trong thư mục hệ thống Python:\n{current_exe}\n\n"
                "Từ chối cập nhật để tránh ghi đè file hệ thống."
                )
                return False

            # 3️⃣ KIỂM TRA FILE CẬP NHẬT
            if not os.path.exists(installer_path):
                print(f"❌ Không tìm thấy file cập nhật: {installer_path}")
                self._show_error(f"Không tìm thấy file cập nhật:\n{installer_path}")
                return False
            
            # 🔒 KIỂM TRA: File cập nhật phải là .exe
            if not installer_path.lower().endswith('.exe'):
                print(f"❌ File cập nhật không hợp lệ (phải là .exe): {installer_path}")
                self._show_error(f"File cập nhật không hợp lệ (phải là .exe):\n{installer_path}")
                return False
            
            # 🔒 KIỂM TRA: File cập nhật phải khác với file hiện tại
            if os.path.abspath(installer_path) == current_exe:
                print("❌ File cập nhật trùng với file hiện tại!")
                self._show_error("File cập nhật trùng với file hiện tại!")
                return False

            # 📝 IN RA THÔNG TIN ĐỂ XÁC NHẬN
            print("\n" + "="*60)
            print("🔄 THÔNG TIN CẬP NHẬT:")
            print(f"   File hiện tại: {current_exe}")
            print(f"   File cập nhật:  {installer_path}")
            print(f"   Kích thước file cập nhật: {os.path.getsize(installer_path) / 1024 / 1024:.2f} MB")
            print("="*60 + "\n")

            # 4️⃣ TẠO BATCH SCRIPT TỰ ĐỘNG CẬP NHẬT
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

    REM Đợi một chút để đảm bảo file đã bị xóa
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
            print(f"[DEBUG] Batch script:\n{batch_script}")

            # 5️⃣ LƯU FILE BATCH TẠM THỜI
            batch_path = os.path.join(tempfile.gettempdir(), "app_updater.bat")
            print(f"[DEBUG] Tạo batch script tại: {batch_path}")
            
            # Ghi file với encoding UTF-8 (có BOM để Windows nhận diện đúng)
            with open(batch_path, 'w', encoding='utf-8-sig') as f:
                f.write(batch_script)
            
            print(f"✅ Đã tạo script cập nhật: {batch_path}")

            # 6️⃣ CHẠY BATCH SCRIPT VÀ THOÁT ỨNG DỤNG CŨ
            print("🚀 Bắt đầu cập nhật...")
            print("   Ứng dụng sẽ tự động khởi động lại sau khi cập nhật\n")
            
            # Chạy batch script ẩn (không hiện cửa sổ CMD)
            subprocess.Popen(
                batch_path, 
                shell=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            print("[TEST] Bỏ qua thực thi batch, chỉ in nội dung:")
            print(batch_script)
            
            # Đợi một chút để batch script bắt đầu
            import time
            time.sleep(0.5)
            
            # Thoát ứng dụng hiện tại
            sys.exit(0)

        except PermissionError as e:
            print(f"❌ Lỗi quyền truy cập: {e}")
            print("   Vui lòng chạy ứng dụng với quyền Administrator")
            return False
        
        except Exception as e:
            print(f"💥 Lỗi khi cài đặt cập nhật: {e}")
            import traceback
            tb = traceback.print_exc()
            self._show_error(f"Lỗi khi cài đặt cập nhật:\n{e}\n\nChi tiết:\n{tb}")
            return False
    def show_update_dialog(self, update_info):
        """Hiển thị dialog cập nhật với progress bar"""
        root = tk.Tk()

        root.title("Cập nhật có sẵn")  # Bỏ dấu để tránh lỗi trong title

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

        info_text += f"Dung lượng lưu trữ: {update_info['size'] / 1024 / 1024:.2f} MB"
        
        info_label = tk.Label(main_frame, text=info_text, justify=tk.LEFT)

        info_label.pack(pady=(0, 10))
        
        # Changelog
        changelog_label = tk.Label(main_frame, text="Thay doi:", font=('Arial', 10, 'bold'))

        changelog_label.pack(anchor=tk.W)
        
        changelog_frame = tk.Frame(main_frame, relief=tk.SUNKEN, borderwidth=1)

        changelog_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        changelog_text = tk.Text(changelog_frame, wrap=tk.WORD, height=10)
        changelog_scroll = tk.Scrollbar(changelog_frame, command=changelog_text.yview)
        changelog_text.configure(yscrollcommand=changelog_scroll.set)
        
        changelog_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        changelog_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        changelog_text.insert('1.0', update_info['changelog'] or "Khong co thong tin")
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

                progress_label.config(text=f"Dang tai: {downloaded_mb:.1f} / {total_mb:.1f} MB ({percent:.1f}%)")

                root.update_idletasks()
            
            def download_thread():
                try:
                    temp_installer = os.path.join(tempfile.gettempdir(), "update_installer.exe")

                    # Tải file cập nhật
                    if self.download_update_with_progress(update_info['download_url'], temp_installer, progress_callback):
                        progress_label.config(text="Đang cài đặt...")

                        root.update_idletasks()

                        # Thử cài đặt
                        success = self.install_update(temp_installer)
                        if not success:
                            # Nếu install_update trả False => báo lỗi
                            messagebox.showerror("Lỗi cài đặt", 
                                "Không thể cài đặt bản cập nhật. Ứng dụng sẽ tiếp tục chạy phiên bản hiện tại.")
                            
                            # Xóa file tải tạm nếu có
                            if os.path.exists(temp_installer):
                                try:
                                    os.remove(temp_installer)
                                except Exception:
                                    pass

                            # Rollback UI về trạng thái cũ
                            progress_label.config(text="Cài đặt thất bại. Giữ nguyên phiên bản hiện tại.")

                            progress_bar['value'] = 0

                            update_btn.config(state=tk.NORMAL)

                            skip_btn.config(state=tk.NORMAL)

                            return

                    else:
                        # Nếu tải thất bại
                        messagebox.showerror("Lỗi", "Không thể tải xuống bản cập nhật.")

                        root.destroy()

                except Exception as e:
                    # Nếu có lỗi bất ngờ (ngoại lệ trong luồng)
                    messagebox.showerror("Lỗi nghiêm trọng", f"Đã xảy ra lỗi khi cập nhật:\n{e}")
                    import traceback
                    traceback.print_exc()

                    # Dọn dẹp file tạm
                    if os.path.exists(temp_installer):
                        try:
                            os.remove(temp_installer)
                        except Exception:
                            pass

                    progress_label.config(text="Cập nhật thất bại. Giữ nguyên phiên bản hiện tại.")
                    progress_bar['value'] = 0
                    update_btn.config(state=tk.NORMAL)
                    skip_btn.config(state=tk.NORMAL)
            
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