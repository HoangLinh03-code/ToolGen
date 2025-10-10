import sys
import os
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QFileDialog, QMessageBox, QSplitter, 
    QProgressBar, QSpinBox, QTextEdit, QTabWidget, QGroupBox,
    QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor
import mammoth
from dotenv import load_dotenv
from google.oauth2 import service_account
import glob
import time
import gc
import io

from concurrent.futures import ThreadPoolExecutor, as_completed
from github_updater_check import GitHubUpdateChecker, load_current_version
from process.response2docx import response2docx_improved

load_dotenv()


# ==================== CONSOLE REDIRECT ====================
class ConsoleRedirect(QObject):
    """Redirect stdout/stderr to QTextEdit"""
    output_written = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.buffer = io.StringIO()
    
    def write(self, text):
        if text.strip():  # Bỏ qua dòng trống
            self.output_written.emit(text)
        # Vẫn ghi vào terminal gốc
        sys.__stdout__.write(text)
    
    def flush(self):
        pass

# ==================== PROGRESS MANAGER ====================
class ProgressManager:
    """Quản lý tiến trình xử lý - lưu và load trạng thái"""
    
    def __init__(self, progress_file="processing_progress.json"):
        self.progress_file = progress_file
        self.data = self.load()
    
    def load(self):
        """Load tiến trình từ file"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"processed": {}, "last_update": None}
        return {"processed": {}, "last_update": None}
    
    def save(self):
        """Lưu tiến trình vào file"""
        self.data["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def is_completed(self, bai_name, output_folder):
        """Kiểm tra bài đã xử lý xong chưa (có đủ 2 file docx)"""
        tracnghiem_file = os.path.join(output_folder, f"{bai_name}_TracNghiem.docx")
        dungsai_file = os.path.join(output_folder, f"{bai_name}_DungSai.docx")
        
        return (os.path.exists(tracnghiem_file) and 
                os.path.exists(dungsai_file) and
                os.path.getsize(tracnghiem_file) > 0 and
                os.path.getsize(dungsai_file) > 0)
    
    def mark_completed(self, bai_name):
        """Đánh dấu bài đã hoàn thành"""
        self.data["processed"][bai_name] = {
            "status": "completed",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save()
    
    def get_completed_list(self):
        """Lấy danh sách bài đã hoàn thành"""
        return [k for k, v in self.data["processed"].items() if v["status"] == "completed"]
    
    def reset(self):
        """Reset toàn bộ tiến trình"""
        self.data = {"processed": {}, "last_update": None}
        self.save()


# ==================== API CHECKER ====================
class APIChecker(QThread):
    """Thread kiểm tra API Gemini"""
    result = pyqtSignal(dict)
    
    def __init__(self, project_id, creds):
        super().__init__()
        self.project_id = project_id
        self.creds = creds
    
    def run(self):
        try:
            # Import vertexai thay vì google.generativeai
            import vertexai
            from vertexai.generative_models import GenerativeModel
            
            # Khởi tạo với credentials
            vertexai.init(
                project=self.project_id, 
                credentials=self.creds
            )
            
            # Test model
            model = GenerativeModel("gemini-2.0-flash-exp")
            
            result = {
                "status": "OK",
                "message": "✅ API Gemini hoạt động bình thường",
                "project_id": self.project_id,
                "quota_info": "Kiểm tra quota tại Google Cloud Console"
            }
        except Exception as e:
            result = {
                "status": "ERROR",
                "message": f"❌ Lỗi: {str(e)[:100]}",
                "project_id": self.project_id
            }
        
        self.result.emit(result)


# ==================== PROCESSING THREAD ====================
class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(list)
    batch_complete = pyqtSignal(int, int)  # (completed, total)
    image_progress = pyqtSignal(str)  # Log xử lý ảnh
    console_output = pyqtSignal(str)  # Output từ console
    
    def __init__(self, root_folder, prompt_tracnghiem_path, prompt_dungsai_path, 
                 project_id, creds, batch_size=2, max_lessons=None, resume=False):
        super().__init__()
        self.root_folder = root_folder
        self.prompt_tracnghiem_path = prompt_tracnghiem_path
        self.prompt_dungsai_path = prompt_dungsai_path
        self.project_id = project_id
        self.creds = creds
        self.batch_size = batch_size
        self.max_lessons = max_lessons
        self.resume = resume
        self.progress_manager = ProgressManager()
        self.stop_requested = False
    
    def stop(self):
        """Dừng xử lý"""
        self.stop_requested = True
    
    def run(self):
        generated_files = []
        
        try:
            # Đọc prompts
            with open(self.prompt_tracnghiem_path, "r", encoding="utf-8") as f:
                prompt_tracnghiem = f.read()
            
            with open(self.prompt_dungsai_path, "r", encoding="utf-8") as f:
                prompt_dungsai = f.read()
            
            # Lấy danh sách bài
            bai_folders = [
                os.path.join(self.root_folder, name)
                for name in sorted(os.listdir(self.root_folder))
                if os.path.isdir(os.path.join(self.root_folder, name))
            ]
            
            # Lọc bài chưa hoàn thành
            if self.resume:
                pending_folders = []
                for bf in bai_folders:
                    bai_name = os.path.basename(bf)
                    output_folder = os.path.join("output", bai_name)
                    if not self.progress_manager.is_completed(bai_name, output_folder):
                        pending_folders.append(bf)
                    else:
                        self.progress.emit(f"⏭️ Bỏ qua {bai_name} (đã hoàn thành)")
                bai_folders = pending_folders
            
            total_bai = len(bai_folders)
            
            # Giới hạn số bài xử lý
            if self.max_lessons and self.max_lessons < total_bai:
                bai_folders = bai_folders[:self.max_lessons]
                total_bai = self.max_lessons
            
            self.progress.emit(f"📊 Tổng số bài cần xử lý: {total_bai}")
            
            processed_count = 0
            
            # Xử lý theo batch
            for batch_start in range(0, total_bai, self.batch_size):
                if self.stop_requested:
                    self.progress.emit("⏸️ Đã dừng xử lý theo yêu cầu")
                    break
                
                batch_end = min(batch_start + self.batch_size, total_bai)
                batch_folders = bai_folders[batch_start:batch_end]
                
                self.progress.emit(f"\n{'='*50}")
                self.progress.emit(f"📦 BATCH {batch_start//self.batch_size + 1}")
                self.progress.emit(f"{'='*50}")
                
                for bai_folder in batch_folders:
                    if self.stop_requested:
                        break
                    
                    bai_name = os.path.basename(bai_folder)
                    self.progress.emit(f"\n🎯 Đang xử lý: {bai_name}")
                    
                    # Kiểm tra PDF
                    pdf_files = glob.glob(os.path.join(bai_folder, "*.pdf"))
                    
                    if not pdf_files:
                        self.progress.emit(f"⚠️ Không tìm thấy PDF trong {bai_name}")
                        continue
                    
                    self.progress.emit(f"📄 Tìm thấy {len(pdf_files)} file PDF")
                    
                    # Tạo output folder
                    output_folder = os.path.join("output", bai_name)
                    os.makedirs(output_folder, exist_ok=True)
                    
                    # Kiểm tra đã hoàn thành chưa
                    if self.progress_manager.is_completed(bai_name, output_folder):
                        self.progress.emit(f"✅ {bai_name} đã hoàn thành trước đó")
                        processed_count += 1
                        continue
                    
                    # 1. Xử lý trắc nghiệm
                    self.progress.emit(f"📝 Đang sinh 80 câu trắc nghiệm...")
                    self.image_progress.emit(f"[TracNghiem-{bai_name}] Bắt đầu xử lý")
                    
                    try:
                        docx_tracnghiem = response2docx_improved(
                            pdf_files,
                            prompt_tracnghiem,
                            os.path.join(output_folder, f"{bai_name}_TracNghiem"),
                            self.project_id,
                            self.creds,
                            "gemini-2.5-pro",
                            question_type="tracnghiem"
                        )
                        if docx_tracnghiem:
                            generated_files.append(docx_tracnghiem)
                            self.progress.emit(f"✅ Hoàn thành trắc nghiệm")
                            self.image_progress.emit(f"[TracNghiem-{bai_name}] Hoàn thành")
                    except Exception as e:
                        self.progress.emit(f"❌ Lỗi trắc nghiệm: {str(e)}")
                        self.image_progress.emit(f"[TracNghiem-{bai_name}] Lỗi: {str(e)}")
                    
                    # 2. Xử lý đúng/sai
                    self.progress.emit(f"📝 Đang sinh 40 câu đúng/sai...")
                    self.image_progress.emit(f"[DungSai-{bai_name}] Bắt đầu xử lý")
                    
                    try:
                        docx_dungsai = response2docx_improved(
                            pdf_files,
                            prompt_dungsai,
                            os.path.join(output_folder, f"{bai_name}_DungSai"),
                            self.project_id,
                            self.creds,
                            "gemini-2.5-pro",
                            question_type="dungsai"
                        )
                        if docx_dungsai:
                            generated_files.append(docx_dungsai)
                            self.progress.emit(f"✅ Hoàn thành đúng/sai")
                            self.image_progress.emit(f"[DungSai-{bai_name}] Hoàn thành")
                    except Exception as e:
                        self.progress.emit(f"❌ Lỗi đúng/sai: {str(e)}")
                        self.image_progress.emit(f"[DungSai-{bai_name}] Lỗi: {str(e)}")
                    
                    # Đánh dấu hoàn thành nếu có đủ 2 file
                    if self.progress_manager.is_completed(bai_name, output_folder):
                        self.progress_manager.mark_completed(bai_name)
                        processed_count += 1
                        self.progress.emit(f"🎉 Hoàn thành {bai_name} ({processed_count}/{total_bai})")
                
                # Hoàn thành batch
                self.batch_complete.emit(processed_count, total_bai)
                self.progress.emit(f"\n✅ Hoàn thành batch - Tiến độ: {processed_count}/{total_bai}")
                self.progress.emit("🧹 Đang dọn dẹp bộ nhớ...")
                gc.collect()
                time.sleep(2)
        
        except Exception as e:
            self.error.emit(f"Lỗi nghiêm trọng: {str(e)}")
            return
        
        self.finished.emit(generated_files)


# ==================== PROMPT EDITOR DIALOG ====================
class PromptEditorDialog(QDialog):
    """Dialog chỉnh sửa prompt"""
    
    def __init__(self, prompt_path, parent=None):
        super().__init__(parent)
        self.prompt_path = prompt_path
        self.setWindowTitle(f"Chỉnh sửa Prompt: {os.path.basename(prompt_path)}")
        self.resize(800, 600)
        self.init_ui()
        self.load_prompt()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.save_prompt)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(QLabel(f"File: {self.prompt_path}"))
        layout.addWidget(self.editor)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def load_prompt(self):
        try:
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể đọc file: {str(e)}")
    
    def save_prompt(self):
        try:
            with open(self.prompt_path, 'w', encoding='utf-8') as f:
                f.write(self.editor.toPlainText())
            QMessageBox.information(self, "Thành công", "Đã lưu prompt!")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể lưu file: {str(e)}")


# ==================== MAIN WINDOW ====================
class MainWindow(QWidget):
    CURRENT_VERSION = "1.0.0"  # Thay đổi mỗi khi release
    GITHUB_REPO = "HoangLinh03-code/ToolGen"  # Thay bằng repo của bạn
    
    # Kiểm tra cập nhật
    print("Đang kiểm tra cập nhật phiên bản")
    # checker = GitHubUpdateChecker(CURRENT_VERSION, GITHUB_REPO)
    # checker = GitHubUpdateChecker("1.0.0", "HoangLinh03-code/ToolGen")
    checker = GitHubUpdateChecker(load_current_version(), GITHUB_REPO)
    
    has_update, update_info = checker.check_for_updates()
    
    if has_update:
        print(f"✓ Tìm thấy phiên bản mới: {update_info['version']}")
        checker.show_update_dialog(update_info)
    else:
        print("✓ Bạn đang sử dụng phiên bản mới nhất")
    
    # Tiếp tục chạy app
    print("\n=== APP ĐANG CHẠY ===")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Supreme Gen Ques Pro - Advanced Edition")
        self.resize(1400, 900)
        
        # Khởi tạo các biến TRƯỚC khi gọi init_ui()
        self.generated_files = []
        self.progress_manager = ProgressManager()
        self.root_folder = None
        self.processing_thread = None
        
        # Console redirect
        self.console_redirect = ConsoleRedirect()
        self.console_redirect.output_written.connect(self.append_console_output)
        sys.stdout = self.console_redirect
        sys.stderr = self.console_redirect
        
        # Default paths
        self.default_prompt_tracnghiem = os.path.join(
            os.path.dirname(__file__), "prompt_Gen.txt"
        )
        self.default_prompt_dungsai = os.path.join(
            os.path.dirname(__file__), "promptDSCongNghe10.txt"
        )
        
        self.setup_style()
        self.setup_credentials()
        self.init_ui()
        
        # Auto check API
        QTimer.singleShot(1000, self.check_api_status)
    
    def setup_style(self):
        """Thiết lập giao diện đẹp"""
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', Arial;
                font-size: 10pt;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #3498db;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                padding: 5px;
            }
            QProgressBar {
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
            }
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
            }
            QTabBar::tab {
                background: #ecf0f1;
                padding: 8px 15px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
        """)
    
    def setup_credentials(self):
        try:
            service_account_data = {
                "type": os.getenv("TYPE"),
                "project_id": os.getenv("PROJECT_ID"),
                "private_key_id": os.getenv("PRIVATE_KEY_ID"),
                "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'),
                "client_email": os.getenv("CLIENT_EMAIL"),
                "client_id": os.getenv("CLIENT_ID", ""),
                "auth_uri": os.getenv("AUTH_URI"),
                "token_uri": os.getenv("TOKEN_URI"),
                "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
                "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
                "universe_domain": os.getenv("UNIVERSE_DOMAIN")
            }
            self.credentials = service_account.Credentials.from_service_account_info(
                service_account_data,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self.project_id = os.getenv('PROJECT_ID')
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể tải credentials: {str(e)}")
    
    def init_ui(self):
        main_layout = QHBoxLayout()
        
        # === LEFT PANEL: Cấu hình ===
        left_panel = QVBoxLayout()
        
        # 1. API Status
        api_group = QGroupBox("🔌 Trạng thái API")
        api_layout = QVBoxLayout()
        self.api_status_label = QLabel("⏳ Đang kiểm tra...")
        self.api_status_label.setWordWrap(True)
        self.api_status_label.setMinimumHeight(60)
        self.api_check_btn = QPushButton("🔄 Kiểm tra lại")
        self.api_check_btn.clicked.connect(self.check_api_status)
        api_layout.addWidget(self.api_status_label)
        api_layout.addWidget(self.api_check_btn)
        api_group.setLayout(api_layout)
        
        # 2. Folder Management
        folder_group = QGroupBox("📁 Quản lý Folder")
        folder_layout = QVBoxLayout()
        
        self.folder_label = QLineEdit("Chưa chọn folder")
        self.folder_label.setReadOnly(True)
        folder_btn_layout = QHBoxLayout()
        self.folder_button = QPushButton("Chọn Folder")
        self.folder_button.clicked.connect(self.select_root_folder)
        self.scan_button = QPushButton("Scan Folder")
        self.scan_button.clicked.connect(self.scan_folder)
        folder_btn_layout.addWidget(self.folder_button)
        folder_btn_layout.addWidget(self.scan_button)
        
        folder_layout.addWidget(QLabel("Folder gốc:"))
        folder_layout.addWidget(self.folder_label)
        folder_layout.addLayout(folder_btn_layout)
        folder_group.setLayout(folder_layout)
        
        # 3. Prompt Settings
        prompt_group = QGroupBox("📝 Cấu hình Prompt")
        prompt_layout = QVBoxLayout()
        
        # Prompt trắc nghiệm
        tn_layout = QHBoxLayout()
        self.prompt_tn_label = QLineEdit(self.default_prompt_tracnghiem)
        self.prompt_tn_label.setReadOnly(True)
        self.prompt_tn_btn = QPushButton("Chọn")
        self.prompt_tn_btn.clicked.connect(lambda: self.select_prompt("tracnghiem"))
        self.prompt_tn_edit_btn = QPushButton("Sửa")
        self.prompt_tn_edit_btn.clicked.connect(lambda: self.edit_prompt("tracnghiem"))
        tn_layout.addWidget(self.prompt_tn_label)
        tn_layout.addWidget(self.prompt_tn_btn)
        tn_layout.addWidget(self.prompt_tn_edit_btn)
        
        # Prompt đúng/sai
        ds_layout = QHBoxLayout()
        self.prompt_ds_label = QLineEdit(self.default_prompt_dungsai)
        self.prompt_ds_label.setReadOnly(True)
        self.prompt_ds_btn = QPushButton("Chọn")
        self.prompt_ds_btn.clicked.connect(lambda: self.select_prompt("dungsai"))
        self.prompt_ds_edit_btn = QPushButton("Sửa")
        self.prompt_ds_edit_btn.clicked.connect(lambda: self.edit_prompt("dungsai"))
        ds_layout.addWidget(self.prompt_ds_label)
        ds_layout.addWidget(self.prompt_ds_btn)
        ds_layout.addWidget(self.prompt_ds_edit_btn)
        
        prompt_layout.addWidget(QLabel("Prompt 80 câu TN:"))
        prompt_layout.addLayout(tn_layout)
        prompt_layout.addWidget(QLabel("Prompt 40 câu Đ/S:"))
        prompt_layout.addLayout(ds_layout)
        prompt_group.setLayout(prompt_layout)
        
        # 4. Processing Settings
        process_group = QGroupBox("⚙️ Cài đặt xử lý")
        process_layout = QVBoxLayout()
        
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("Batch size:"))
        self.batch_spinbox = QSpinBox()
        self.batch_spinbox.setRange(1, 5)
        self.batch_spinbox.setValue(2)
        batch_layout.addWidget(self.batch_spinbox)
        batch_layout.addStretch()
        
        max_layout = QHBoxLayout()
        self.max_lessons_checkbox = QCheckBox("Giới hạn số bài:")
        self.max_lessons_spinbox = QSpinBox()
        self.max_lessons_spinbox.setRange(1, 100)
        self.max_lessons_spinbox.setValue(10)
        self.max_lessons_spinbox.setEnabled(False)
        self.max_lessons_checkbox.toggled.connect(self.max_lessons_spinbox.setEnabled)
        max_layout.addWidget(self.max_lessons_checkbox)
        max_layout.addWidget(self.max_lessons_spinbox)
        max_layout.addStretch()
        
        self.resume_checkbox = QCheckBox("Tiếp tục tiến trình cũ (Resume)")
        self.resume_checkbox.setChecked(True)
        
        process_layout.addLayout(batch_layout)
        process_layout.addLayout(max_layout)
        process_layout.addWidget(self.resume_checkbox)
        process_group.setLayout(process_layout)
        
        # 5. Control Buttons & Progress
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("▶️ Bắt đầu")
        self.start_button.clicked.connect(self.start_processing)
        self.start_button.setStyleSheet("background-color: #27ae60; font-size: 12pt;")
        
        self.stop_button = QPushButton("⏸️ Dừng")
        self.stop_button.clicked.connect(self.stop_processing)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("background-color: #e74c3c;")
        
        self.reset_button = QPushButton("🔄 Reset")
        self.reset_button.clicked.connect(self.reset_progress)
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.reset_button)
        
        # Progress bar - TO HƠN VÀ RÕ RÀNG HƠN
        progress_group = QGroupBox("📊 Tiến trình xử lý")
        progress_layout = QVBoxLayout()
        
        self.progress_label = QLabel("Chưa bắt đầu")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: #2c3e50;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(35)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498db;
                border-radius: 8px;
                text-align: center;
                font-size: 14pt;
                font-weight: bold;
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2ecc71);
                border-radius: 6px;
            }
        """)
        self.progress_bar.setFormat("%p% - %v/%m bài")
        
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_group.setLayout(progress_layout)
        
        # Add to left panel
        left_panel.addWidget(api_group)
        left_panel.addWidget(folder_group)
        left_panel.addWidget(prompt_group)
        left_panel.addWidget(process_group)
        left_panel.addLayout(control_layout)
        left_panel.addWidget(progress_group)
        left_panel.addStretch()
        
        # === RIGHT PANEL: Logs & Preview ===
        right_panel = QVBoxLayout()
        
        # Tabs
        tabs = QTabWidget()
        
        # Tab 0: Hướng dẫn sử dụng
        guide_widget = QWidget()
        guide_layout = QVBoxLayout()
        
        guide_content = QTextEdit()
        guide_content.setReadOnly(True)
        guide_content.setHtml("""
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', Arial; padding: 20px; line-height: 1.8; }
                h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
                h2 { color: #34495e; margin-top: 25px; }
                .step { background: #ecf0f1; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #3498db; }
                .note { background: #fff3cd; padding: 10px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #ffc107; }
                .warning { background: #f8d7da; padding: 10px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #dc3545; }
                ul { margin-left: 20px; }
                li { margin: 8px 0; }
                code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', monospace; }
            </style>
        </head>
        <body>
            <h1>📖 Hướng dẫn sử dụng Supreme Gen Ques Pro</h1>
            
            <h2>🎯 Mục đích</h2>
            <p>Công cụ tự động sinh câu hỏi trắc nghiệm và đúng/sai từ tài liệu PDF sử dụng AI Gemini.</p>
            
            <h2>📋 Cấu trúc thư mục yêu cầu</h2>
            <div class="step">
                <strong>Folder gốc</strong> (VD: Lớp 10)<br>
                ├── Bài 1<br>
                │   ├── file1.pdf<br>
                │   └── file2.pdf<br>
                ├── Bài 2<br>
                │   └── file.pdf<br>
                └── Bài 3<br>
                    └── file.pdf
            </div>
            
            <h2>🚀 Các bước thực hiện:</h2>
            
            <div class="step">
                <strong>Bước 1: Kiểm tra API</strong><br>
                • Chương trình tự động kiểm tra kết nối Gemini API khi khởi động<br>
                • Nếu lỗi, nhấn <code>🔄 Kiểm tra lại</code> hoặc kiểm tra file .env
            </div>
            
            <div class="step">
                <strong>Bước 2: Chọn Folder gốc</strong><br>
                • Nhấn <code>Chọn Folder</code> → Chọn folder chứa các bài (VD: Lớp 10)<br>
                • Nhấn <code>Scan Folder</code> để xem cấu trúc và số PDF
            </div>
            
            <div class="step">
                <strong>Bước 3: Cấu hình Prompt</strong><br>
                • <strong>Prompt 80 câu TN:</strong> File prompt sinh câu trắc nghiệm<br>
                • <strong>Prompt 40 câu Đ/S:</strong> File prompt sinh câu đúng/sai<br>
                • Nhấn <code>Chọn</code> để đổi file hoặc <code>Sửa</code> để chỉnh sửa
            </div>
            
            <div class="step">
                <strong>Bước 4: Cài đặt xử lý</strong><br>
                • <strong>Batch size:</strong> Số bài xử lý cùng lúc (1-5, khuyến nghị: 2)<br>
                • <strong>Giới hạn số bài:</strong> Tick để chỉ xử lý N bài đầu tiên<br>
                • <strong>Resume:</strong> Tick để bỏ qua bài đã hoàn thành
            </div>
            
            <div class="step">
                <strong>Bước 5: Bắt đầu xử lý</strong><br>
                • Nhấn <code>▶️ Bắt đầu</code> → Theo dõi tiến trình trong các tab<br>
                • Nhấn <code>⏸️ Dừng</code> nếu muốn tạm dừng (tiến trình được lưu)
            </div>
            
            <h2>📊 Các Tab theo dõi</h2>
            <ul>
                <li><strong>📋 Log Chính:</strong> Theo dõi tiến trình xử lý tổng thể</li>
                <li><strong>🖼️ Log Ảnh:</strong> Chi tiết xử lý ảnh từng câu hỏi</li>
                <li><strong>📊 Tiến độ:</strong> Bảng trạng thái tất cả bài học</li>
                <li><strong>📄 Xem File:</strong> Preview file docx đã tạo</li>
            </ul>
            
            <h2>💡 Tính năng Resume (Tiếp tục)</h2>
            <div class="note">
                <strong>Khi nào dùng Resume?</strong><br>
                • Xử lý bị gián đoạn và muốn tiếp tục<br>
                • Muốn thêm bài mới vào folder đã xử lý<br>
                • Chỉ xử lý từng đợt (VD: 10 bài/lần)<br><br>
                <strong>Cách hoạt động:</strong><br>
                • Chương trình kiểm tra từng bài đã có đủ 2 file docx chưa<br>
                • Bỏ qua bài đã hoàn thành, chỉ xử lý bài mới
            </div>
            
            <h2>🔄 Reset tiến trình</h2>
            <div class="warning">
                <strong>⚠️ Cảnh báo:</strong> Nhấn <code>🔄 Reset</code> sẽ XÓA toàn bộ lịch sử xử lý!<br>
                Chương trình sẽ coi tất cả bài là chưa xử lý.<br>
                <strong>Lưu ý:</strong> File docx đã tạo KHÔNG bị xóa, chỉ xóa trạng thái theo dõi.
            </div>
            
            <h2>📁 Kết quả</h2>
            <p>File docx được lưu trong: <code>output/[Tên bài]/</code></p>
            <ul>
                <li>[Tên bài]_TracNghiem.docx - 80 câu trắc nghiệm</li>
                <li>[Tên bài]_DungSai.docx - 40 câu đúng/sai</li>
            </ul>
            
            <h2>❓ Xử lý sự cố</h2>
            <div class="step">
                <strong>Lỗi API:</strong> Kiểm tra file .env, đảm bảo credentials đúng<br>
                <strong>Lỗi xử lý bài:</strong> Xem Log Chính, có thể do PDF lỗi hoặc hết quota<br>
                <strong>File không đủ:</strong> Resume sẽ tự động xử lý lại bài thiếu
            </div>
            
            <p style="margin-top: 30px; text-align: center; color: #7f8c8d; font-style: italic;">
                💡 Mẹo: Để tối ưu tốc độ, nên chạy batch size = 2 và giới hạn 10-20 bài/lần
            </p>
        </body>
        </html>
        """)
        
        guide_layout.addWidget(guide_content)
        guide_widget.setLayout(guide_layout)
        
        # Tab 1: Processing Log
        log_widget = QWidget()
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(QLabel("📋 Log xử lý:"))
        log_layout.addWidget(self.log_text)
        log_widget.setLayout(log_layout)
        
        # Tab 2: Image Processing Log
        img_log_widget = QWidget()
        img_log_layout = QVBoxLayout()
        self.img_log_text = QTextEdit()
        self.img_log_text.setReadOnly(True)
        self.img_log_text.setFont(QFont("Consolas", 9))
        img_log_layout.addWidget(QLabel("🖼️ Log xử lý ảnh:"))
        img_log_layout.addWidget(self.img_log_text)
        img_log_widget.setLayout(img_log_layout)
        
        # Tab 3: Console Output (Terminal)
        console_widget = QWidget()
        console_layout = QVBoxLayout()
        
        console_toolbar = QHBoxLayout()
        clear_console_btn = QPushButton("🗑️ Xóa")
        clear_console_btn.clicked.connect(self.clear_console)
        clear_console_btn.setMaximumWidth(100)
        
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self.auto_scroll_checkbox.setChecked(True)
        
        console_toolbar.addWidget(QLabel("💻 Console Output (Terminal):"))
        console_toolbar.addStretch()
        console_toolbar.addWidget(self.auto_scroll_checkbox)
        console_toolbar.addWidget(clear_console_btn)
        
        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setFont(QFont("Consolas", 9))
        self.console_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
            }
        """)
        
        console_layout.addLayout(console_toolbar)
        console_layout.addWidget(self.console_text)
        console_widget.setLayout(console_layout)
        
        # Tab 4: Progress Table
        progress_widget = QWidget()
        progress_layout = QVBoxLayout()
        self.progress_table = QTableWidget()
        self.progress_table.setColumnCount(3)
        self.progress_table.setHorizontalHeaderLabels(["Bài", "Trạng thái", "Thời gian"])
        self.progress_table.horizontalHeader().setStretchLastSection(True)
        progress_layout.addWidget(QLabel("📊 Bảng tiến độ:"))
        progress_layout.addWidget(self.progress_table)
        progress_widget.setLayout(progress_layout)
        
        # Tab 5: Document Viewer
        viewer_widget = QWidget()
        viewer_layout = QHBoxLayout()
        self.docx_viewer = QWebEngineView()
        self.docx_list = QListWidget()
        self.docx_list.setMaximumWidth(200)
        self.docx_list.itemClicked.connect(self.show_selected_docx)
        viewer_layout.addWidget(self.docx_viewer)
        viewer_layout.addWidget(self.docx_list)
        viewer_widget.setLayout(viewer_layout)
        
        # Add tabs - HƯỚNG DẪN LÀ TAB ĐẦU TIÊN
        tabs.addTab(guide_widget, "📖 Hướng dẫn")
        tabs.addTab(log_widget, "📋 Log Chính")
        tabs.addTab(img_log_widget, "🖼️ Log Ảnh")
        tabs.addTab(console_widget, "💻 Console")
        tabs.addTab(progress_widget, "📊 Tiến độ")
        tabs.addTab(viewer_widget, "📄 Xem File")
        
        right_panel.addWidget(tabs)
        
        # === MAIN LAYOUT ===
        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setMaximumWidth(500)
        
        right_container = QWidget()
        right_container.setLayout(right_panel)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
        
        # Load progress table
        self.update_progress_table()
    
    # ==================== API METHODS ====================
    def check_api_status(self):
        """Kiểm tra trạng thái API"""
        self.api_status_label.setText("⏳ Đang kiểm tra...")
        self.api_check_btn.setEnabled(False)
        
        self.api_checker = APIChecker(self.project_id, self.credentials)
        self.api_checker.result.connect(self.on_api_check_result)
        self.api_checker.start()
    
    def on_api_check_result(self, result):
        """Xử lý kết quả kiểm tra API"""
        self.api_check_btn.setEnabled(True)
        
        if result["status"] == "OK":
            status_text = f"{result['message']}\n"
            status_text += f"📦 Project: {result['project_id']}\n"
            status_text += f"📊 {result['quota_info']}"
            self.api_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            status_text = f"{result['message']}\n"
            status_text += f"📦 Project: {result['project_id']}"
            self.api_status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        
        self.api_status_label.setText(status_text)
        self.log_text.append(f"\n[API CHECK] {status_text}\n")
    
    # ==================== FOLDER METHODS ====================
    def select_root_folder(self):
        """Chọn folder gốc"""
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder gốc")
        if folder:
            self.root_folder = folder
            self.folder_label.setText(folder)
            self.log_text.append(f"\n📁 Đã chọn folder: {folder}")
            self.scan_folder()
    
    def scan_folder(self):
        """Scan và hiển thị cấu trúc folder"""
        if not self.root_folder or not os.path.isdir(self.root_folder):
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn folder hợp lệ!")
            return
        
        self.log_text.append("\n🔍 Đang scan folder...")
        
        bai_folders = [
            name for name in sorted(os.listdir(self.root_folder))
            if os.path.isdir(os.path.join(self.root_folder, name))
        ]
        
        self.log_text.append(f"📊 Tìm thấy {len(bai_folders)} bài:")
        
        for bai_name in bai_folders:
            bai_path = os.path.join(self.root_folder, bai_name)
            pdf_count = len(glob.glob(os.path.join(bai_path, "*.pdf")))
            output_folder = os.path.join("output", bai_name)
            
            is_completed = self.progress_manager.is_completed(bai_name, output_folder)
            status = "✅" if is_completed else "⏳"
            
            self.log_text.append(f"  {status} {bai_name} - {pdf_count} PDF")
        
        self.update_progress_table()
    
    # ==================== PROMPT METHODS ====================
    def select_prompt(self, prompt_type):
        """Chọn file prompt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file prompt", "", "Text Files (*.txt)"
        )
        if file_path:
            if prompt_type == "tracnghiem":
                self.prompt_tn_label.setText(file_path)
            else:
                self.prompt_ds_label.setText(file_path)
            self.log_text.append(f"📝 Đã chọn prompt {prompt_type}: {os.path.basename(file_path)}")
    
    def edit_prompt(self, prompt_type):
        """Mở dialog chỉnh sửa prompt"""
        prompt_path = (self.prompt_tn_label.text() if prompt_type == "tracnghiem" 
                      else self.prompt_ds_label.text())
        
        if not os.path.isfile(prompt_path):
            QMessageBox.warning(self, "Lỗi", "File prompt không tồn tại!")
            return
        
        dialog = PromptEditorDialog(prompt_path, self)
        if dialog.exec_() == QDialog.Accepted:
            self.log_text.append(f"✅ Đã lưu prompt {prompt_type}")
    
    # ==================== PROCESSING METHODS ====================
    def start_processing(self):
        """Bắt đầu xử lý"""
        # Validation
        if not self.root_folder or not os.path.isdir(self.root_folder):
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn folder gốc hợp lệ!")
            return
        
        prompt_tn = self.prompt_tn_label.text()
        prompt_ds = self.prompt_ds_label.text()
        
        if not os.path.isfile(prompt_tn) or not os.path.isfile(prompt_ds):
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn cả 2 file prompt!")
            return
        
        # Disable UI
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Đang khởi động...")
        self.log_text.clear()
        self.img_log_text.clear()
        
        # Get settings
        max_lessons = (self.max_lessons_spinbox.value() 
                      if self.max_lessons_checkbox.isChecked() else None)
        resume = self.resume_checkbox.isChecked()
        
        self.log_text.append("="*60)
        self.log_text.append("🚀 BẮT ĐẦU XỬ LÝ")
        self.log_text.append("="*60)
        self.log_text.append(f"📁 Folder: {self.root_folder}")
        self.log_text.append(f"📦 Batch size: {self.batch_spinbox.value()}")
        self.log_text.append(f"📊 Giới hạn: {max_lessons if max_lessons else 'Không'}")
        self.log_text.append(f"🔄 Resume: {'Có' if resume else 'Không'}")
        self.log_text.append("="*60 + "\n")
        
        # Create thread
        self.processing_thread = ProcessingThread(
            self.root_folder,
            prompt_tn,
            prompt_ds,
            self.project_id,
            self.credentials,
            self.batch_spinbox.value(),
            max_lessons,
            resume
        )
        
        self.processing_thread.progress.connect(self.update_log)
        self.processing_thread.image_progress.connect(self.update_image_log)
        self.processing_thread.error.connect(self.show_error)
        self.processing_thread.finished.connect(self.processing_finished)
        self.processing_thread.batch_complete.connect(self.update_progress_bar)
        self.processing_thread.start()
    
    def stop_processing(self):
        """Dừng xử lý"""
        if self.processing_thread and self.processing_thread.isRunning():
            reply = QMessageBox.question(
                self, "Xác nhận",
                "Bạn có chắc muốn dừng xử lý?\nTiến trình đã hoàn thành sẽ được lưu lại.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.processing_thread.stop()
                self.log_text.append("\n⏸️ Đang dừng xử lý...")
    
    def reset_progress(self):
        """Reset tiến trình"""
        reply = QMessageBox.question(
            self, "Xác nhận",
            "⚠️ Bạn có chắc muốn xóa toàn bộ tiến trình?\nHành động này KHÔNG THỂ hoàn tác!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.progress_manager.reset()
            self.log_text.append("\n🔄 Đã reset toàn bộ tiến trình!")
            self.update_progress_table()
            QMessageBox.information(self, "Thành công", "Đã xóa tiến trình!")
    
    # ==================== UPDATE METHODS ====================
    def update_log(self, message):
        """Cập nhật log chính"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def update_image_log(self, message):
        """Cập nhật log xử lý ảnh"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.img_log_text.append(f"[{timestamp}] {message}")
        self.img_log_text.verticalScrollBar().setValue(
            self.img_log_text.verticalScrollBar().maximum()
        )
    
    def append_console_output(self, text):
        """Thêm output vào console tab"""
        self.console_text.insertPlainText(text)
        if self.auto_scroll_checkbox.isChecked():
            self.console_text.verticalScrollBar().setValue(
                self.console_text.verticalScrollBar().maximum()
            )
    
    def clear_console(self):
        """Xóa console output"""
        self.console_text.clear()
    
    def update_progress_bar(self, completed, total):
        """Cập nhật progress bar"""
        progress = int((completed / total) * 100) if total > 0 else 0
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(completed)
        self.progress_label.setText(f"Đã hoàn thành: {completed}/{total} bài ({progress}%)")
        self.update_progress_table()
    
    def update_progress_table(self):
        """Cập nhật bảng tiến độ"""
        if not self.root_folder or not os.path.isdir(self.root_folder):
            return
        
        bai_folders = [
            name for name in sorted(os.listdir(self.root_folder))
            if os.path.isdir(os.path.join(self.root_folder, name))
        ]
        
        self.progress_table.setRowCount(len(bai_folders))
        
        for idx, bai_name in enumerate(bai_folders):
            output_folder = os.path.join("output", bai_name)
            is_completed = self.progress_manager.is_completed(bai_name, output_folder)
            
            # Tên bài
            name_item = QTableWidgetItem(bai_name)
            
            # Trạng thái
            status_text = "✅ Hoàn thành" if is_completed else "⏳ Chưa xử lý"
            status_item = QTableWidgetItem(status_text)
            if is_completed:
                status_item.setBackground(QColor(46, 204, 113, 50))
            
            # Thời gian
            timestamp = ""
            if bai_name in self.progress_manager.data["processed"]:
                timestamp = self.progress_manager.data["processed"][bai_name].get("timestamp", "")
            time_item = QTableWidgetItem(timestamp)
            
            self.progress_table.setItem(idx, 0, name_item)
            self.progress_table.setItem(idx, 1, status_item)
            self.progress_table.setItem(idx, 2, time_item)
        
        self.progress_table.resizeColumnsToContents()
    
    def show_error(self, message):
        """Hiển thị lỗi"""
        QMessageBox.critical(self, "Lỗi", message)
        self.enable_ui()
    
    def processing_finished(self, generated_files):
        """Xử lý khi hoàn thành"""
        self.generated_files = [f for f in generated_files if f is not None]
        self.docx_list.clear()
        
        self.log_text.append("\n" + "="*60)
        self.log_text.append("🎉 HOÀN THÀNH XỬ LÝ")
        self.log_text.append("="*60)
        
        if not self.generated_files:
            self.log_text.append("⚠️ Không có file mới được tạo")
            QMessageBox.information(self, "Hoàn thành", "Không có file mới được tạo!")
        else:
            self.log_text.append(f"✅ Đã tạo {len(self.generated_files)} file thành công!")
            
            for fname in self.generated_files:
                self.docx_list.addItem(os.path.basename(fname))
            
            self.docx_list.setCurrentRow(0)
            self.show_selected_docx(self.docx_list.item(0))
            
            QMessageBox.information(
                self, "Hoàn thành", 
                f"🎉 Đã tạo {len(self.generated_files)} file thành công!\n\n"
                "Bạn có thể xem file trong tab 'Xem File'"
            )
        
        self.progress_bar.setValue(100)
        self.enable_ui()
        self.update_progress_table()
    
    def enable_ui(self):
        """Bật lại UI"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def refresh_docx_list(self):
        """Làm mới danh sách file docx từ output folder"""
        self.docx_list.clear()
        self.generated_files = []
        
        if not os.path.exists("output"):
            self.log_text.append("⚠️ Thư mục output chưa tồn tại")
            self.docx_viewer.setHtml(
                "<h3>📁 Thư mục output trống</h3>"
                "<p>Chưa có file nào được tạo. Hãy bắt đầu xử lý để tạo file.</p>"
            )
            return
        
        # Scan tất cả file .docx trong output
        docx_files = []
        for root, dirs, files in os.walk("output"):
            for file in files:
                if file.endswith(".docx") and not file.startswith("~$"):  # Bỏ qua file temp
                    full_path = os.path.join(root, file)
                    docx_files.append(full_path)
        
        if not docx_files:
            self.log_text.append("⚠️ Không tìm thấy file .docx nào trong output")
            self.docx_viewer.setHtml(
                "<h3>📄 Chưa có file</h3>"
                "<p>Thư mục output chưa có file .docx nào.</p>"
            )
            return
        
        # Sắp xếp theo tên
        docx_files.sort()
        
        # Thêm vào list
        for file_path in docx_files:
            self.docx_list.addItem(os.path.basename(file_path))
            self.generated_files.append(file_path)
        
        self.log_text.append(f"✅ Đã tải {len(docx_files)} file docx")
        
        # Auto select first file
        if self.docx_list.count() > 0:
            self.docx_list.setCurrentRow(0)
            self.show_selected_docx(self.docx_list.item(0))
    
    def open_output_folder(self):
        """Mở thư mục output trong file explorer"""
        output_path = os.path.abspath("output")
        
        if not os.path.exists(output_path):
            QMessageBox.warning(self, "Lỗi", "Thư mục output chưa tồn tại!")
            return
        
        # Mở folder tùy theo hệ điều hành
        import platform
        system = platform.system()
        
        try:
            if system == "Windows":
                os.startfile(output_path)
            elif system == "Darwin":  # macOS
                os.system(f'open "{output_path}"')
            else:  # Linux
                os.system(f'xdg-open "{output_path}"')
            
            self.log_text.append(f"📁 Đã mở thư mục: {output_path}")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể mở thư mục: {str(e)}")
    
    def on_tab_changed(self, index, tabs):
        """Xử lý khi chuyển tab"""
        tab_name = tabs.tabText(index)
        
        # Nếu chuyển sang tab "Xem File", tự động load danh sách
        if "Xem File" in tab_name:
            if self.docx_list.count() == 0:  # Chỉ load nếu list trống
                self.refresh_docx_list()    
    def show_selected_docx(self, item):
        """Hiển thị file docx được chọn"""
        if not item:
            return
        
        file_name = item.text()
        
        # Tìm file trong generated_files hoặc scan từ output folder
        full_path = None
        
        # Tìm trong generated_files trước
        for f in self.generated_files:
            if os.path.basename(f) == file_name:
                full_path = f
                break
        
        # Nếu không tìm thấy, scan toàn bộ output folder
        if not full_path and os.path.exists("output"):
            for root, dirs, files in os.walk("output"):
                if file_name in files:
                    full_path = os.path.join(root, file_name)
                    break
        
        if not full_path or not os.path.isfile(full_path):
            self.docx_viewer.setHtml(
                f"<h3 style='color: #e74c3c;'>❌ Lỗi</h3>"
                f"<p>File không tồn tại: {file_name}</p>"
                f"<p>Đường dẫn tìm kiếm: {full_path or 'Không tìm thấy'}</p>"
            )
            return
        
        # Hiển thị loading
        self.docx_viewer.setHtml(
            "<h3>⏳ Đang tải nội dung...</h3>"
            f"<p>File: {file_name}</p>"
        )
        
        try:
            with open(full_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value.strip()
                
                if html:
                    styled_html = f"""
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <style>
                            body {{
                                font-family: 'Segoe UI', Arial, sans-serif;
                                padding: 20px;
                                line-height: 1.8;
                                background-color: #f8f9fa;
                            }}
                            h1, h2, h3 {{ 
                                color: #2c3e50; 
                                margin-top: 20px;
                            }}
                            p {{ 
                                margin: 10px 0;
                                text-align: justify;
                            }}
                            table {{ 
                                border-collapse: collapse; 
                                width: 100%; 
                                margin: 15px 0;
                                background: white;
                            }}
                            td, th {{ 
                                border: 1px solid #ddd; 
                                padding: 10px;
                                text-align: left;
                            }}
                            th {{ 
                                background-color: #3498db; 
                                color: white;
                                font-weight: bold;
                            }}
                            img {{
                                max-width: 100%;
                                height: auto;
                                margin: 15px 0;
                                border: 1px solid #ddd;
                                border-radius: 5px;
                            }}
                            .file-info {{
                                background: #e3f2fd;
                                padding: 15px;
                                border-radius: 5px;
                                margin-bottom: 20px;
                                border-left: 4px solid #2196f3;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="file-info">
                            <h2>📄 {file_name}</h2>
                            <p><strong>Đường dẫn:</strong> {full_path}</p>
                            <p><strong>Kích thước:</strong> {os.path.getsize(full_path) / 1024:.2f} KB</p>
                        </div>
                        <hr>
                        <div class="content">
                            {html}
                        </div>
                    </body>
                    </html>
                    """
                    self.docx_viewer.setHtml(styled_html)
                    self.log_text.append(f"✅ Đã tải file: {file_name}")
                else:
                    self.docx_viewer.setHtml(
                        f"<h3>⚠️ Cảnh báo</h3>"
                        f"<p>Không có nội dung trong {file_name}</p>"
                        f"<p>File có thể bị lỗi hoặc trống.</p>"
                    )
        except Exception as e:
            error_html = f"""
            <html>
            <body style='font-family: Arial; padding: 20px;'>
                <h3 style='color: #e74c3c;'>❌ Lỗi khi mở {file_name}</h3>
                <p><strong>Chi tiết lỗi:</strong></p>
                <pre style='background: #f8f9fa; padding: 15px; border-radius: 5px;'>{str(e)}</pre>
                <p><strong>Đường dẫn:</strong> {full_path}</p>
                <p><strong>Gợi ý:</strong> File có thể bị hỏng hoặc không đúng định dạng DOCX.</p>
            </body>
            </html>
            """
            self.docx_viewer.setHtml(error_html)
            self.log_text.append(f"❌ Lỗi khi tải {file_name}: {str(e)}")


# ==================== MAIN ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set app-wide style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    # Restore stdout/stderr on exit
    def cleanup():
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    
    app.aboutToQuit.connect(cleanup)
    
    sys.exit(app.exec_())