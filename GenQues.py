# File: GenQues_MultiThread_Optimized.py
# Phiên bản cải thiện xử lý đa luồng

import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QFileDialog, QMessageBox, QSplitter, QProgressBar,
    QCheckBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QTabWidget, QTextEdit, QTreeWidgetItemIterator, QSpinBox, QDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont, QIcon
import mammoth
from dotenv import load_dotenv
from google.oauth2 import service_account
import glob
import difflib
import threading
import time
import concurrent.futures
from process.response2docx import response2docx_json, response2docx_dung_sai_json

load_dotenv()

if getattr(sys, 'frozen', False):
    internal_path = sys._MEIPASS
    external_path = os.path.dirname(sys.executable)
else:
    internal_path = os.path.dirname(__file__)
    external_path = os.path.dirname(__file__)

dotenv_path = os.path.join(internal_path, '.env')
load_dotenv(dotenv_path)

# ============================================================
# PHẦN ĐA LUỒNG (MULTITHREADING) - TỐI ƯU
# ============================================================
class TaskInfo:
    """Class lưu thông tin cho từng nhiệm vụ nhỏ"""
    def __init__(self, output_name, pdf_files, task_type, prompt_content):
        self.output_name = output_name
        self.pdf_files = pdf_files
        self.task_type = task_type  # "TN" hoặc "DS"
        self.prompt_content = prompt_content

class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)

    def __init__(self, selected_items, prompt_paths, project_id, creds, max_workers=3):
        super().__init__()
        self.selected_items = selected_items
        self.prompt_paths = prompt_paths
        self.project_id = project_id
        self.creds = creds
        self.max_workers = max_workers
        self.generated_files = []
        self.is_running = True
        self.lock = threading.Lock()

    def run(self):
        """Logic chạy chính: Tách nhỏ tác vụ để chạy song song thực sự"""
        import time
        import concurrent.futures

        self.progress.emit("⚙️ Đang chuẩn bị dữ liệu và đọc Prompt...")

        # 1. Đọc Prompt một lần duy nhất để tối ưu I/O
        prompt_content_tn = ""
        prompt_content_ds = ""

        if "trac_nghiem" in self.prompt_paths and self.prompt_paths["trac_nghiem"]:
            try:
                with open(self.prompt_paths["trac_nghiem"], "r", encoding="utf-8") as f:
                    prompt_content_tn = f.read()
            except Exception as e:
                self.error_signal.emit(f"Lỗi đọc prompt TN: {e}")
                return

        if "dung_sai" in self.prompt_paths and self.prompt_paths["dung_sai"]:
            try:
                with open(self.prompt_paths["dung_sai"], "r", encoding="utf-8") as f:
                    prompt_content_ds = f.read()
            except Exception as e:
                self.error_signal.emit(f"Lỗi đọc prompt DS: {e}")
                return

        # 2. Tạo danh sách công việc (Flattened List)
        # Tách riêng TN và DS thành các task độc lập
        all_tasks = []
        
        for output_name, pdf_files in self.selected_items.items():
            # Nếu user chọn TN, tạo task TN
            if prompt_content_tn:
                all_tasks.append(TaskInfo(output_name, pdf_files, "TN", prompt_content_tn))
            
            # Nếu user chọn DS, tạo task DS (độc lập hoàn toàn với TN)
            if prompt_content_ds:
                all_tasks.append(TaskInfo(output_name, pdf_files, "DS", prompt_content_ds))

        total_tasks = len(all_tasks)
        if total_tasks == 0:
            self.finished.emit([])
            return

        self.progress.emit(f"🚀 Bắt đầu xử lý {total_tasks} tác vụ (TN & DS tách biệt)...")
        self.progress_update.emit(0, total_tasks)

        completed_count = 0
        failed_count = 0

        # 3. Thực thi song song
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Map future -> task để theo dõi
            future_to_task = {}
            
            for task in all_tasks:
                if not self.is_running: break
                
                # Submit task vào pool
                future = executor.submit(self._process_worker, task, self.project_id, self.creds)
                future_to_task[future] = task
                
                # Nghỉ cực ngắn để tránh spam API cùng 1 mili-giây gây lỗi 429
                time.sleep(0.1)

            # Thu thập kết quả khi từng task hoàn thành
            for future in concurrent.futures.as_completed(future_to_task):
                if not self.is_running: break
                
                task = future_to_task[future]
                try:
                    result_path, error_msg = future.result()
                    
                    with self.lock:
                        completed_count += 1
                        if result_path:
                            self.generated_files.append(result_path)
                            status_icon = "✅"
                            msg = f"Xong {task.output_name} ({task.task_type})"
                        else:
                            failed_count += 1
                            status_icon = "⚠️"
                            msg = f"Lỗi {task.output_name} ({task.task_type}): {error_msg}"
                    
                    self.progress.emit(f"{status_icon} [{completed_count}/{total_tasks}] {msg}")
                    self.progress_update.emit(completed_count, total_tasks)

                except Exception as e:
                    with self.lock:
                        failed_count += 1
                        completed_count += 1
                    self.progress.emit(f"❌ Lỗi ngoại lệ tại {task.output_name}: {str(e)}")
                    self.progress_update.emit(completed_count, total_tasks)

        # 4. Tổng kết
        summary = (
            f"🏁 Đã xử lý xong!\n"
            f"✅ Thành công: {completed_count - failed_count}\n"
            f"❌ Thất bại: {failed_count}\n"
            f"📄 Tổng file: {len(self.generated_files)}"
        )
        self.progress.emit(summary)
        self.finished.emit(self.generated_files)

    def stop(self):
        self.is_running = False

    @staticmethod
    def _process_worker(task, project_id, creds):
        """
        Hàm xử lý chạy trong từng luồng con.
        Đảm bảo không crash luồng chính.
        """
        import os
        # Import local để tránh circular import và đảm bảo luồng sạch
        from process.response2docx import response2docx_json, response2docx_dung_sai_json

        try:
            # Xác định tên file đầu ra
            if task.task_type == "TN":
                output_filename = f"{task.output_name}_TN"
                # Gọi hàm sinh trắc nghiệm
                docx_path = response2docx_json(
                    task.pdf_files,
                    task.prompt_content,
                    output_filename,
                    project_id,
                    creds,
                    "gemini-2.5-pro",
                    batch_name=task.output_name
                )
            else: # task_type == "DS"
                output_filename = f"{task.output_name}_DS"
                # Gọi hàm sinh đúng sai
                docx_path = response2docx_dung_sai_json(
                    task.pdf_files,
                    task.prompt_content,
                    output_filename,
                    project_id,
                    creds,
                    "gemini-2.5-pro",
                    batch_name=task.output_name
                )

            if docx_path and os.path.exists(docx_path):
                return docx_path, None
            else:
                return None, "Hàm trả về None hoặc file không tồn tại"

        except Exception as e:
            return None, str(e)

# ============================================================
# PHẦN GIAO DIỆN CHÍNH (MainWindow) - GIỮ NGUYÊN
# ============================================================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gen Ques v2.3 - Đa Luồng Tối Ưu")
        self.resize(1400, 850)
        self.generated_files = []
        self.processing_thread = None
        
        # Prompt files mặc định
        self.default_prompt_tn = os.path.join(external_path, "testTN.txt")
        self.default_prompt_ds = os.path.join(external_path, "testDS.txt")
        
        if not os.path.exists(self.default_prompt_tn):
             self.default_prompt_tn = os.path.join(internal_path, "testTN.txt")
        if not os.path.exists(self.default_prompt_ds):
             self.default_prompt_ds = os.path.join(internal_path, "testDS.txt")
        
        self.load_default_prompts()
        self.setup_modern_theme()
        self.init_ui()
        self.setup_credentials()

    def setup_modern_theme(self):
        """Thiết lập CSS toàn cục"""
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #333;
                background-color: #f5f7fa;
            }
            
            QTabWidget::pane { 
                border: 1px solid #dcdcdc; 
                background: white; 
                border-radius: 5px;
                top: -1px;
            }
            
            QTabBar::tab {
                background: #e1e4e8;
                color: #555;
                padding: 10px 20px; 
                min-width: 180px;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                border: 1px solid transparent;
            }
            
            QTabBar::tab:selected {
                background: white;
                color: #1976D2;
                border: 1px solid #dcdcdc;
                border-bottom: 2px solid white;
                margin-bottom: -1px;
            }
            
            QGroupBox {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 1.5em;
                padding-top: 15px; 
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
                color: #1976D2;
                font-size: 15px;
            }
            
            QPushButton {
                background-color: #fff;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 15px;
                font-weight: 600;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #f0f8ff;
                border-color: #2196F3;
                color: #1565C0;
            }
            
            QPushButton#ProcessBtn {
                background-color: #2e7d32;
                color: white;
                border: none;
                font-size: 16px;
                padding: 10px;
            }
            QPushButton#ProcessBtn:hover {
                background-color: #1b5e20;
            }
            QPushButton#ProcessBtn:disabled {
                background-color: #a5d6a7;
            }

            QTreeWidget, QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #bbdefb;
                selection-color: black;
                outline: none;
            }
            QTreeWidget::item, QListWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #f1f1f1;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #ddd;
                font-weight: bold;
            }

            QProgressBar {
                border: none;
                background-color: #e0e0e0;
                border-radius: 10px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 10px;
            }
        """)

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        self.tab_widget = QTabWidget()
        
        # ================= TAB 1: PROCESSING =================
        processing_tab = QWidget()
        processing_layout = QVBoxLayout()
        processing_layout.setSpacing(20)
        processing_layout.setContentsMargins(15, 15, 15, 15)
        
        # --- SECTION 1: NGUỒN TÀI LIỆU ---
        pdf_group = QGroupBox("1. Nguồn Tài Liệu PDF")
        pdf_layout = QVBoxLayout()
        
        file_toolbar = QHBoxLayout()
        
        self.add_files_button = QPushButton("📄 Thêm File")
        self.add_files_button.clicked.connect(self.add_pdf_files)
        
        self.add_folder_button = QPushButton("📁 Thêm Folder")
        self.add_folder_button.clicked.connect(self.add_folder)
        
        self.select_all_button = QPushButton("☑️ Chọn hết")
        self.select_all_button.clicked.connect(self.select_all_items)
        
        self.deselect_all_button = QPushButton("☐ Bỏ chọn")
        self.deselect_all_button.clicked.connect(self.deselect_all_items)
        
        self.btn_remove_selected = QPushButton("❌ Xóa mục chọn")
        self.btn_remove_selected.setStyleSheet("color: #c62828; border-color: #ffcdd2;")
        self.btn_remove_selected.clicked.connect(self.remove_selected_items)
        
        self.clear_all_button = QPushButton("🗑️ Xóa list")
        self.clear_all_button.setStyleSheet("color: #d32f2f; border-color: #ef9a9a;")
        self.clear_all_button.clicked.connect(self.clear_all_items)
        
        file_toolbar.addWidget(self.add_files_button)
        file_toolbar.addWidget(self.add_folder_button)
        file_toolbar.addWidget(self.select_all_button)
        file_toolbar.addWidget(self.deselect_all_button)
        file_toolbar.addWidget(self.btn_remove_selected)
        file_toolbar.addStretch()
        file_toolbar.addWidget(self.clear_all_button)
        
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Tên Tài Liệu", "Đường Dẫn Chi Tiết"])
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setIndentation(20)
        self.file_tree.itemChanged.connect(self.handle_item_check_changed)
        
        header = self.file_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.file_tree.setColumnWidth(0, 400)

        self.file_count_label = QLabel("<i>Chưa có tài liệu nào được chọn</i>")
        self.file_count_label.setAlignment(Qt.AlignRight)
        
        pdf_layout.addLayout(file_toolbar)
        pdf_layout.addWidget(self.file_tree)
        pdf_layout.addWidget(self.file_count_label)
        pdf_group.setLayout(pdf_layout)
        
        # --- SECTION 2: CẤU HÌNH ---
        config_group = QGroupBox("2. Cấu Hình Tạo Đề")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(15)
        
        tn_container = QWidget()
        tn_layout = QHBoxLayout(tn_container)
        
        self.checkbox_tn = QCheckBox("Trắc nghiệm 4 đáp án (80 câu)")
        self.checkbox_tn.setChecked(True)
        self.checkbox_tn.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_tn_label = QLabel(os.path.basename(self.default_prompt_tn))
        
        self.btn_select_prompt_tn = QPushButton("📂 Chọn Prompt")
        self.btn_select_prompt_tn.clicked.connect(lambda: self.select_prompt_file("trac_nghiem"))
        
        self.btn_edit_prompt_tn = QPushButton("✏️ Sửa")
        self.btn_edit_prompt_tn.clicked.connect(lambda: self.edit_prompt("trac_nghiem"))
        
        tn_layout.addWidget(self.checkbox_tn, 2)
        tn_layout.addWidget(QLabel("Prompt:"), 0)
        tn_layout.addWidget(self.prompt_tn_label, 3)
        tn_layout.addWidget(self.btn_select_prompt_tn)
        tn_layout.addWidget(self.btn_edit_prompt_tn)
        
        ds_container = QWidget()
        ds_layout = QHBoxLayout(ds_container)
        
        self.checkbox_ds = QCheckBox("Đúng/Sai (40 câu)")
        self.checkbox_ds.setChecked(True)
        self.checkbox_ds.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_ds_label = QLabel(os.path.basename(self.default_prompt_ds))
        
        self.btn_select_prompt_ds = QPushButton("📂 Chọn Prompt")
        self.btn_select_prompt_ds.clicked.connect(lambda: self.select_prompt_file("dung_sai"))
        
        self.btn_edit_prompt_ds = QPushButton("✏️ Sửa")
        self.btn_edit_prompt_ds.clicked.connect(lambda: self.edit_prompt("dung_sai"))
        
        ds_layout.addWidget(self.checkbox_ds, 2)
        ds_layout.addWidget(QLabel("Prompt:"), 0)
        ds_layout.addWidget(self.prompt_ds_label, 3)
        ds_layout.addWidget(self.btn_select_prompt_ds)
        ds_layout.addWidget(self.btn_edit_prompt_ds)
        
        config_layout.addWidget(tn_container)
        config_layout.addWidget(ds_container)
        config_group.setLayout(config_layout)

        # --- SECTION 3: ACTION & THREADING ---
        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(0, 10, 0, 0)
        
        # Thread count control
        thread_layout = QHBoxLayout()
        thread_layout.addWidget(QLabel("Số luồng xử lí:"))
        self.thread_spinbox = QSpinBox()
        self.thread_spinbox.setRange(1, 50)
        self.thread_spinbox.setValue(3)
        self.thread_spinbox.setFixedWidth(60)
        thread_layout.addWidget(self.thread_spinbox)
        thread_layout.addWidget(QLabel("(Dựa trên số bài xử lí, ví dụ: xử lí 2 bài thì tăng x2 số luồng)"))
        thread_layout.addStretch()
        
        self.process_button = QPushButton("BẮT ĐẦU XỬ LÝ ĐA LUỒNG")
        self.process_button.setObjectName("ProcessBtn")
        self.process_button.setMinimumHeight(50)
        self.process_button.clicked.connect(self.process_files)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m (%p%)")
        
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: #555; min-height: 40px;")
        
        action_layout.addLayout(thread_layout)
        action_layout.addWidget(self.process_button)
        action_layout.addWidget(self.progress_bar)
        action_layout.addWidget(self.status_label)

        processing_layout.addWidget(pdf_group, 6)
        processing_layout.addWidget(config_group, 3)
        processing_layout.addLayout(action_layout, 1)
        
        processing_tab.setLayout(processing_layout)
        
        # ================= TAB 2: KẾT QUẢ =================
        result_tab = QWidget()
        result_layout = QHBoxLayout()
        result_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        
        lbl_result = QLabel("📂 Danh sách đã tạo")
        lbl_result.setStyleSheet("font-weight: bold; color: #2E7D32; padding: 5px;")
        
        self.docx_list = QListWidget()
        self.docx_list.itemClicked.connect(self.show_selected_docx)
        
        left_layout.addWidget(lbl_result)
        left_layout.addWidget(self.docx_list)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        preview_header = QHBoxLayout()
        lbl_preview = QLabel("📋 Xem trước tài liệu")
        lbl_preview.setStyleSheet("font-weight: bold; color: #1565C0; padding: 5px;")
        
        self.btn_open_external = QPushButton("↗️ Mở bằng Word/WPS")
        self.btn_open_external.setFixedSize(180, 35)
        self.btn_open_external.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border: none;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #B0BEC5; }
        """)
        self.btn_open_external.clicked.connect(self.open_current_docx)
        self.btn_open_external.setEnabled(False)
        
        preview_header.addWidget(lbl_preview)
        preview_header.addStretch()
        preview_header.addWidget(self.btn_open_external)
        
        self.docx_viewer = QWebEngineView()
        
        right_layout.addLayout(preview_header)
        right_layout.addWidget(self.docx_viewer)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 9)
        
        result_layout.addWidget(splitter)
        result_tab.setLayout(result_layout)
        
        # Add tabs
        self.tab_widget.addTab(processing_tab, "⚙️ CẤU HÌNH & XỬ LÝ")
        self.tab_widget.addTab(result_tab, "📄 KẾT QUẢ ĐẦU RA")
        
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
        self.update_process_button_state()

    def setup_credentials(self):
        try:
            service_account_data = {
                "type": os.getenv("TYPE"),
                "project_id": os.getenv("PROJECT_ID"),
                "private_key_id": os.getenv("PRIVATE_KEY_ID"),
                "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'),
                "client_email": os.getenv("CLIENT_EMAIL"),
                "client_id": os.getenv("CLIENT_ID"),
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
            self.app_key = os.getenv('MATHPIX_APP_KEY')
            self.app_id = os.getenv('MATHPIX_APP_ID')
            self.project_id = os.getenv('PROJECT_ID')
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể tải thông tin xác thực: {str(e)}")
            self.process_button.setEnabled(False)

    def load_default_prompts(self):
        self.prompt_tn_content = ""
        self.prompt_ds_content = ""
        if os.path.isfile(self.default_prompt_tn):
            try:
                with open(self.default_prompt_tn, "r", encoding="utf-8") as f:
                    self.prompt_tn_content = f.read()
            except: pass
        if os.path.isfile(self.default_prompt_ds):
            try:
                with open(self.default_prompt_ds, "r", encoding="utf-8") as f:
                    self.prompt_ds_content = f.read()
            except: pass

    def add_pdf_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file PDF", "", "PDF Files (*.pdf)"
        )
        if file_paths:
            for file_path in file_paths:
                if not self.is_file_in_tree(file_path):
                    item = QTreeWidgetItem(self.file_tree)
                    item.setText(0, os.path.basename(file_path))
                    item.setText(1, file_path)
                    item.setCheckState(0, Qt.Checked)
                    item.setData(0, Qt.UserRole, "file")
            self.update_file_count()

    def add_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục PDF", "")
        if folder_path:
            self.add_folder_to_tree(folder_path, self.file_tree)
            self.update_file_count()

    def add_folder_to_tree(self, folder_path, parent_item, is_root=True):
        folder_item = QTreeWidgetItem(parent_item)
        folder_item.setText(0, f"📁 {os.path.basename(folder_path)}")
        folder_item.setText(1, folder_path)
        folder_item.setCheckState(0, Qt.Checked)
        folder_item.setData(0, Qt.UserRole, "folder")
        
        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        for pdf_file in sorted(pdf_files):
            file_item = QTreeWidgetItem(folder_item)
            file_item.setText(0, os.path.basename(pdf_file))
            file_item.setText(1, pdf_file)
            file_item.setCheckState(0, Qt.Checked)
            file_item.setData(0, Qt.UserRole, "file")
        
        for name in sorted(os.listdir(folder_path)):
            subfolder_path = os.path.join(folder_path, name)
            if os.path.isdir(subfolder_path):
                self.add_folder_to_tree(subfolder_path, folder_item, is_root=False)
        
        if is_root: folder_item.setExpanded(True)
        else: folder_item.setExpanded(False)

    def handle_item_check_changed(self, item, column):
        """Xử lý sự kiện khi user tick vào checkbox"""
        if column != 0: return

        self.file_tree.blockSignals(True)
        
        try:
            check_state = item.checkState(0)
            self.update_children_check_state(item, check_state)
            self.update_parent_check_state(item)
            self.update_file_count()
        except Exception as e:
            print(f"Error in handle_item_check_changed: {e}")
        finally:
            self.file_tree.blockSignals(False)

    def update_children_check_state(self, parent_item, check_state):
        """Cập nhật trạng thái con"""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, check_state)
            if child.childCount() > 0:
                self.update_children_check_state(child, check_state)

    def update_parent_check_state(self, item):
        """Cập nhật trạng thái cha"""
        parent = item.parent()
        if parent is None: return
        checked_count = 0
        total_count = parent.childCount()
        for i in range(total_count):
            child = parent.child(i)
            if child.checkState(0) == Qt.Checked: checked_count += 1
            elif child.checkState(0) == Qt.PartiallyChecked:
                parent.setCheckState(0, Qt.PartiallyChecked)
                self.update_parent_check_state(parent)
                return
        if checked_count == 0: parent.setCheckState(0, Qt.Unchecked)
        elif checked_count == total_count: parent.setCheckState(0, Qt.Checked)
        else: parent.setCheckState(0, Qt.PartiallyChecked)
        self.update_parent_check_state(parent)

    def is_file_in_tree(self, file_path):
        """Kiểm tra file đã tồn tại trong tree"""
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            if item.text(1) == file_path: return True
            iterator += 1
        return False

    def remove_selected_items(self):
        """Xóa các mục được tick"""
        checked_items = []
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.Checked:
                checked_items.append(item)
            iterator += 1
            
        if not checked_items:
            QMessageBox.information(self, "Thông báo", "Vui lòng tick chọn (V) vào các mục cần xóa!")
            return

        confirm = QMessageBox.question(
            self, "Xác nhận", 
            f"Bạn có chắc muốn xóa {len(checked_items)} mục đã chọn?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return

        items_to_delete = []
        for item in checked_items:
            parent = item.parent()
            if parent is None or parent.checkState(0) != Qt.Checked:
                items_to_delete.append(item)

        root = self.file_tree.invisibleRootItem()
        for item in items_to_delete:
            (item.parent() or root).removeChild(item)

        self.update_file_count()

    def clear_all_items(self):
        """Xóa tất cả items"""
        self.file_tree.clear()
        self.update_file_count()

    def select_all_items(self):
        """Chọn tất cả items"""
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            item.setCheckState(0, Qt.Checked)
            iterator += 1

    def deselect_all_items(self):
        """Bỏ chọn tất cả items"""
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            item.setCheckState(0, Qt.Unchecked)
            iterator += 1

    def update_file_count(self):
        """Cập nhật số lượng file"""
        total_files = 0
        total_folders = 0
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            item_type = item.data(0, Qt.UserRole)
            if item_type == "file": total_files += 1
            elif item_type == "folder": total_folders += 1
            iterator += 1
        if total_files == 0 and total_folders == 0:
            self.file_count_label.setText("<i>Chưa có tài liệu nào được chọn</i>")
        else:
            text = f"📊 Tổng: <b>{total_folders}</b> folder, <b>{total_files}</b> file PDF"
            self.file_count_label.setText(text)

    def select_prompt_file(self, prompt_type):
        """Chọn file prompt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Chọn file prompt cho {prompt_type}", "", "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if prompt_type == "trac_nghiem":
                    self.prompt_tn_content = content
                    self.prompt_tn_label.setText(os.path.basename(file_path))
                else:
                    self.prompt_ds_content = content
                    self.prompt_ds_label.setText(os.path.basename(file_path))
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể đọc file: {str(e)}")

    def edit_prompt(self, prompt_type):
        """Sửa prompt"""
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle(f"Sửa Prompt - {'Trắc nghiệm' if prompt_type == 'trac_nghiem' else 'Đúng/Sai'}")
        edit_dialog.setModal(True)
        edit_dialog.resize(750, 600)
        
        dialog_layout = QVBoxLayout()
        
        label = QLabel("📝 Chỉnh sửa nội dung prompt:")
        label.setFont(QFont("Arial", 10, QFont.Bold))
        dialog_layout.addWidget(label)
        
        text_edit = QTextEdit()
        text_edit.setFont(QFont("Consolas", 10))
        if prompt_type == "trac_nghiem": 
            text_edit.setPlainText(self.prompt_tn_content)
        else: 
            text_edit.setPlainText(self.prompt_ds_content)
        dialog_layout.addWidget(text_edit)
        
        btn_layout = QHBoxLayout()
        
        btn_save = QPushButton("💾 Lưu")
        btn_save.setFixedSize(100, 35)
        btn_save.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px; font-weight: bold;")
        
        btn_cancel = QPushButton("❌ Hủy")
        btn_cancel.setFixedSize(100, 35)
        btn_cancel.setStyleSheet("background-color: #f44336; color: white; border-radius: 5px; font-weight: bold;")
        
        btn_reset = QPushButton("🔄 Reset về mặc định")
        btn_reset.setFixedSize(150, 35)
        btn_reset.setStyleSheet("background-color: #ff9800; color: white; border-radius: 5px; font-weight: bold;")
        
        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        dialog_layout.addLayout(btn_layout)
        
        edit_dialog.setLayout(dialog_layout)
        
        def save_prompt():
            new_content = text_edit.toPlainText()
            if prompt_type == "trac_nghiem":
                self.prompt_tn_content = new_content
                self.prompt_tn_label.setText("✏️ Prompt đã chỉnh sửa")
            else:
                self.prompt_ds_content = new_content
                self.prompt_ds_label.setText("✏️ Prompt đã chỉnh sửa")
            edit_dialog.accept()
        
        def reset_prompt():
            default_file = self.default_prompt_tn if prompt_type == "trac_nghiem" else self.default_prompt_ds
            if os.path.isfile(default_file):
                try:
                    with open(default_file, "r", encoding="utf-8") as f:
                        default_content = f.read()
                    text_edit.setPlainText(default_content)
                    QMessageBox.information(edit_dialog, "Thành công", "Đã reset về prompt mặc định!")
                except Exception as e:
                    QMessageBox.warning(edit_dialog, "Lỗi", f"Không thể load prompt mặc định: {str(e)}")
        
        btn_save.clicked.connect(save_prompt)
        btn_cancel.clicked.connect(edit_dialog.reject)
        btn_reset.clicked.connect(reset_prompt)
        
        edit_dialog.exec_()

    def update_process_button_state(self):
        """Cập nhật trạng thái button"""
        has_selection = self.checkbox_tn.isChecked() or self.checkbox_ds.isChecked()
        self.process_button.setEnabled(has_selection)
        if not has_selection: 
            self.process_button.setText("⚠️ Vui lòng chọn ít nhất 1 dạng đề")
        else: 
            self.process_button.setText("🚀 BẮT ĐẦU XỬ LÝ ĐA LUỒNG")

    def get_selected_items(self):
        """
        Lấy danh sách items và gom nhóm bằng thuật toán _smart_group_files CÓ SẴN.
        """
        # 1. Thu thập TẤT CẢ các file PDF đang được tick chọn vào 1 danh sách
        all_checked_pdfs = []

        def traverse(item):
            # Nếu item không được check thì bỏ qua
            if item.checkState(0) == Qt.Unchecked: return

            item_type = item.data(0, Qt.UserRole)
            
            # Nếu là file lẻ -> Thêm vào list
            if item_type == "file" and item.checkState(0) == Qt.Checked:
                all_checked_pdfs.append(item.text(1))
            
            # Nếu là folder -> Duyệt tiếp con của nó
            elif item_type == "folder":
                for i in range(item.childCount()):
                    traverse(item.child(i))

        # Bắt đầu duyệt từ gốc
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            traverse(root.child(i))
            
        # Loại bỏ file trùng lặp (nếu có) và sắp xếp
        all_checked_pdfs = sorted(list(set(all_checked_pdfs)))
        
        if not all_checked_pdfs:
            return {}

        # 2. GỌI THUẬT TOÁN "STRING CON CHUNG" CỦA BẠN
        # Hàm này đã có sẵn ở dưới, nó sẽ tự tách 7 chủ đề ra riêng 
        # và gom các file có tên giống nhau (Part 1, Part 2...) vào chung 1 nhóm.
        return self._smart_group_files(all_checked_pdfs)
    def _smart_group_files(self, file_paths):
        """
        Gom nhóm dựa trên chuỗi chung dài nhất (Longest Common Substring).
        Logic:
        1. Tìm chuỗi chung dài nhất giữa file gốc và file đang xét.
        2. Tính tỷ lệ % của chuỗi chung so với độ dài file dài hơn.
        3. Nếu tỷ lệ > 80% (tức là chỉ khác nhau chút xíu ở số hiệu đuôi) -> Gộp.
        4. Nếu tỷ lệ thấp (như trường hợp 7 file của bạn, chung đầu nhưng đuôi dài ngoằng khác nhau) -> Tách riêng.
        """
        groups = {}
        # Sắp xếp để các file tên giống nhau đứng cạnh nhau cho dễ xử lý
        pending_files = sorted(file_paths)
        
        while pending_files:
            # Lấy file đầu tiên làm "hạt giống" (Seed)
            seed_file = pending_files.pop(0)
            seed_name = os.path.splitext(os.path.basename(seed_file))[0]
            
            current_group = [seed_file]
            
            # Duyệt các file còn lại để so sánh
            i = 0
            while i < len(pending_files):
                candidate_file = pending_files[i]
                candidate_name = os.path.splitext(os.path.basename(candidate_file))[0]
                
                # --- THUẬT TOÁN TÌM CHUỖI CHUNG DÀI NHẤT ---
                matcher = difflib.SequenceMatcher(None, seed_name, candidate_name)
                match = matcher.find_longest_match(0, len(seed_name), 0, len(candidate_name))
                
                # Lấy ra chuỗi chung đó
                common_substring = seed_name[match.a : match.a + match.size].strip()
                
                # --- TÍNH TỶ LỆ TRÙNG KHỚP (QUAN TRỌNG) ---
                # Lấy độ dài chuỗi dài nhất trong 2 thằng để chia
                max_len = max(len(seed_name), len(candidate_name))
                
                if max_len == 0:
                    ratio = 0
                else:
                    ratio = len(common_substring) / max_len
                
                # --- QUYẾT ĐỊNH GỘP HAY KHÔNG ---
                # Ngưỡng 0.8 (80%) là con số an toàn.
                # Ví dụ: "Toan_Part1" và "Toan_Part2" -> Giống nhau 90% -> GỘP.
                # Ví dụ của bạn: "TLGD...Chủ đề 1..." và "TLGD...Chủ đề 2..." 
                # -> Chỉ giống nhau đoạn đầu (khoảng 40%) -> KHÔNG GỘP.
                if ratio >= 0.8:
                    current_group.append(candidate_file)
                    pending_files.pop(i) # Đã gộp thì xóa khỏi danh sách chờ
                else:
                    i += 1 # Không khớp thì xét file kế tiếp
            
            # Đặt tên key cho nhóm
            # Nếu nhóm có nhiều file, lấy chuỗi chung làm tên
            if len(current_group) > 1:
                # Tìm lại chuỗi chung của cả nhóm để đặt tên cho đẹp
                # (Lấy đơn giản theo logic so sánh với thằng đầu tiên)
                match = difflib.SequenceMatcher(None, 
                            os.path.splitext(os.path.basename(current_group[0]))[0], 
                            os.path.splitext(os.path.basename(current_group[1]))[0]
                        ).find_longest_match(0, len(os.path.splitext(os.path.basename(current_group[0]))[0]), 
                                            0, len(os.path.splitext(os.path.basename(current_group[1]))[0]))
                group_name = os.path.splitext(os.path.basename(current_group[0]))[0][match.a : match.a + match.size].strip(" _-")
                if not group_name: group_name = seed_name
            else:
                group_name = seed_name

            groups[group_name] = current_group
            
        return groups

    def _collect_checked_pdfs_recursive(self, parent_item, pdf_list):
        """Lấy tất cả PDF trong folder"""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.checkState(0) == Qt.Unchecked: continue
            child_type = child.data(0, Qt.UserRole)
            if child_type == "file":
                if child.checkState(0) == Qt.Checked:
                    pdf_list.append(child.text(1))
            elif child_type == "folder":
                self._collect_checked_pdfs_recursive(child, pdf_list)

    def process_files(self):
        """Bắt đầu xử lý với đa luồng"""
        selected_items = self.get_selected_items()
        if not selected_items:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn ít nhất một file hoặc folder để xử lý!")
            return
        if not self.checkbox_tn.isChecked() and not self.checkbox_ds.isChecked():
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn ít nhất một dạng đề!")
            return
        
        prompt_paths = {}
        if self.checkbox_tn.isChecked():
            prompt_file = self.default_prompt_tn if os.path.isfile(self.default_prompt_tn) else None
            if not prompt_file or not os.path.isfile(prompt_file):
                QMessageBox.warning(self, "Lỗi", "Không tìm thấy file prompt trắc nghiệm!")
                return
            prompt_paths["trac_nghiem"] = prompt_file
        if self.checkbox_ds.isChecked():
            prompt_file = self.default_prompt_ds if os.path.isfile(self.default_prompt_ds) else None
            if not prompt_file or not os.path.isfile(prompt_file):
                QMessageBox.warning(self, "Lỗi", "Không tìm thấy file prompt đúng/sai!")
                return
            prompt_paths["dung_sai"] = prompt_file
        
        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # self.progress_bar.setMaximum(len(selected_items))  <-- XÓA HOẶC COMMENT DÒNG NÀY
        self.progress_bar.setMaximum(100) # Giá trị tạm, sẽ được update_progress cập nhật lại ngay lập tức
        
        self.status_label.setText("⏳ Đang khởi tạo quá trình xử lý đa luồng...")
        
        max_workers = self.thread_spinbox.value()
        
        # Khởi tạo và chạy processing thread
        self.processing_thread = ProcessingThread(
            selected_items,
            prompt_paths,
            self.project_id,
            self.credentials,
            max_workers
        )
        
        self.processing_thread.progress.connect(self.update_status)
        self.processing_thread.progress_update.connect(self.update_progress)
        self.processing_thread.finished.connect(self.processing_finished)
        self.processing_thread.error_signal.connect(self.handle_error)
        
        # Chạy thread
        self.processing_thread.start()

    def set_ui_enabled(self, enabled):
        """Bật/tắt giao diện"""
        self.process_button.setEnabled(enabled)
        self.add_files_button.setEnabled(enabled)
        self.add_folder_button.setEnabled(enabled)
        self.clear_all_button.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.deselect_all_button.setEnabled(enabled)
        self.checkbox_tn.setEnabled(enabled)
        self.checkbox_ds.setEnabled(enabled)
        self.btn_select_prompt_tn.setEnabled(enabled)
        self.btn_select_prompt_ds.setEnabled(enabled)
        self.btn_edit_prompt_tn.setEnabled(enabled)
        self.btn_edit_prompt_ds.setEnabled(enabled)
        self.thread_spinbox.setEnabled(enabled)

    def update_status(self, message):
        """Cập nhật trạng thái"""
        self.status_label.setText(message)

    def update_progress(self, completed, total):
        """Cập nhật thanh tiến độ"""
        if self.progress_bar.maximum() != total:
            self.progress_bar.setMaximum(total)
            
        self.progress_bar.setValue(completed)
        
        # Tính phần trăm hiển thị
        percentage = int((completed / total) * 100) if total > 0 else 0
        self.status_label.setText(f"Đang xử lý: {completed}/{total} ({percentage}%)")

    def handle_error(self, error_msg):
        """Xử lý lỗi"""
        self.status_label.setText(f"❌ {error_msg}")
        QMessageBox.critical(self, "Lỗi", error_msg)

    def processing_finished(self, generated_files):
        """Xử lý hoàn thành và hiển thị thông báo"""
        # Lọc bỏ các kết quả None (nếu có lỗi)
        self.generated_files = [f for f in generated_files if f is not None]
        self.docx_list.clear()
        
        # 1. Reset trạng thái UI trước (để giao diện không bị đơ)
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

        # 2. Kiểm tra kết quả
        if not self.generated_files:
            # Trường hợp thất bại hết
            self.status_label.setText("❌ Không có file được tạo")
            QMessageBox.warning(self, "Cảnh báo", "Quá trình kết thúc nhưng không có file nào được tạo ra.\nVui lòng kiểm tra lại kết nối hoặc file đầu vào.")
        else:
            # Trường hợp thành công
            for fname in self.generated_files:
                self.docx_list.addItem(os.path.basename(fname))
            
            self.status_label.setText(f"✅ Hoàn tất! Đã tạo {len(self.generated_files)} file")
            
            # Tự động chuyển sang tab kết quả
            self.tab_widget.setCurrentIndex(1)
            
            # Tự động chọn file đầu tiên để preview
            if self.generated_files:
                self.docx_list.setCurrentRow(0)
                self.show_selected_docx(self.docx_list.item(0))

            # --- [MỚI] HIỂN THỊ THÔNG BÁO HOÀN THÀNH ---
            QMessageBox.information(
                self, 
                "Xử lý hoàn tất", 
                f"✅ Đã chạy xong chương trình!\n\n"
                f"📄 Tổng số file tạo thành công: {len(self.generated_files)}\n"
                f"👉 Bạn có thể xem và mở file tại tab 'KẾT QUẢ ĐẦU RA'."
            )

    def show_selected_docx(self, item):
        """Hiển thị preview"""
        file_name = item.text()
        full_path = next((f for f in self.generated_files if os.path.basename(f) == file_name), None)
        self.btn_open_external.setEnabled(True)
        if not full_path or not os.path.isfile(full_path):
            self.docx_viewer.setHtml(f"<h3>Lỗi:</h3><p>File không tồn tại: {file_name}</p>")
            self.btn_open_external.setEnabled(False)
            return
        
        file_size_mb = os.path.getsize(full_path) / (1024 * 1024)
        if file_size_mb > 10.0:
            msg = f"""<html><body style="font-family: Arial; text-align: center; padding-top: 50px;">
                <h2 style="color: #f44336;">⚠️ File quá lớn để xem trước ({file_size_mb:.2f} MB)</h2>
                <p>Vui lòng nhấn nút <b>"↗️ Mở bằng Word/WPS"</b> ở góc trên.</p></body></html>"""
            self.docx_viewer.setHtml(msg)
            return
        
        try:
            with open(full_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value.strip()
                if html:
                    styled_html = f"""<html><head><style>
                            body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; line-height: 1.6; color: #333; }}
                            p {{ margin-bottom: 15px; }}
                            img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
                            table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                            th, td {{ border: 1px solid #ddd; padding: 8px; }}
                        </style></head><body>{html}</body></html>"""
                    self.docx_viewer.setHtml(styled_html)
                else:
                    self.docx_viewer.setHtml(f"<p>File không có nội dung để hiển thị.</p>")
        except Exception as e:
            self.docx_viewer.setHtml(f"<h3>Lỗi khi đọc file</h3><p>{str(e)}</p>")

    def open_current_docx(self):
        """Mở file bằng Word/WPS"""
        current_item = self.docx_list.currentItem()
        if not current_item:
            return
        file_name = current_item.text()
        full_path = next((f for f in self.generated_files if os.path.basename(f) == file_name), None)
        if full_path and os.path.exists(full_path):
            try:
                os.startfile(full_path)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể mở file: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())