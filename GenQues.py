import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QFileDialog, QMessageBox, QSplitter, QProgressBar,
    QCheckBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QTabWidget, QTextEdit, QTreeWidgetItemIterator
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont, QIcon
import mammoth
from dotenv import load_dotenv
from google.oauth2 import service_account
import glob
import difflib
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

class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, selected_items, prompt_paths, app_key, app_id, project_id, creds):
        super().__init__()
        self.selected_items = selected_items  # Dict với key là tên output, value là list PDF files
        self.prompt_paths = prompt_paths  # Dict với đường dẫn file prompt
        self.app_key = app_key
        self.app_id = app_id
        self.project_id = project_id
        self.creds = creds

    def run(self):
        generated_files = []
        try:
            for output_name, pdf_files in self.selected_items.items():
                if pdf_files:
                    self.process_pdf_set(pdf_files, output_name, generated_files)
        except Exception as e:
            self.error.emit(f"Lỗi trong quá trình xử lý: {str(e)}")
            return

        self.finished.emit(generated_files)

    def process_pdf_set(self, pdf_files, base_filename, generated_files):
        """Xử lý một bộ PDF với các dạng đề đã chọn"""
        
        # Xử lý đề trắc nghiệm 4 đáp án
        if "trac_nghiem" in self.prompt_paths and self.prompt_paths["trac_nghiem"]:
            self.progress.emit(f"Đang tạo đề trắc nghiệm 4 đáp án cho {base_filename}...")
            try:
                # Đọc nội dung từ file prompt
                with open(self.prompt_paths["trac_nghiem"], "r", encoding="utf-8") as f:
                    prompt_tn = f.read()
                
                output_filename = f"{base_filename}_TN"
                docx_path = response2docx_json(
                    pdf_files,
                    prompt_tn,
                    output_filename,
                    self.project_id,
                    self.creds,
                    "gemini-2.5-pro"
                )
                
                if docx_path:
                    generated_files.append(docx_path)
                    self.progress.emit(f"✓ Hoàn tất đề trắc nghiệm: {base_filename}")
            except Exception as e:
                self.error.emit(f"Lỗi khi tạo đề trắc nghiệm cho {base_filename}: {str(e)}")
        
        # Xử lý đề đúng/sai
        if "dung_sai" in self.prompt_paths and self.prompt_paths["dung_sai"]:
            self.progress.emit(f"Đang tạo đề đúng/sai cho {base_filename}...")
            try:
                # Đọc nội dung từ file prompt
                with open(self.prompt_paths["dung_sai"], "r", encoding="utf-8") as f:
                    prompt_ds = f.read()
                
                output_filename = f"{base_filename}_DS"
                docx_path = response2docx_dung_sai_json(
                    pdf_files,
                    prompt_ds,
                    output_filename,
                    self.project_id,
                    self.creds,
                    "gemini-2.5-pro"
                )
                
                if docx_path:
                    generated_files.append(docx_path)
                    self.progress.emit(f"✓ Hoàn tất đề đúng/sai: {base_filename}")
            except Exception as e:
                self.error.emit(f"Lỗi khi tạo đề đúng/sai cho {base_filename}: {str(e)}")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gen Ques v2.1")
        self.resize(1400, 850) # Tăng kích thước một chút cho thoáng
        self.generated_files = []
        
        # Prompt files mặc định
        self.default_prompt_tn = os.path.join(external_path, "testTN.txt")
        self.default_prompt_ds = os.path.join(external_path, "testDS.txt")
        
        if not os.path.exists(self.default_prompt_tn):
             self.default_prompt_tn = os.path.join(internal_path, "testTN.txt")
        if not os.path.exists(self.default_prompt_ds):
             self.default_prompt_ds = os.path.join(internal_path, "testDS.txt")
        
        # Load prompt content
        self.load_default_prompts()
        
        # [NEW] Thiết lập giao diện hiện đại
        self.setup_modern_theme()
        self.init_ui()
        self.setup_credentials()

    def setup_modern_theme(self):
        """Thiết lập CSS toàn cục cho ứng dụng đẹp hơn (Đã fix lỗi mất chữ ở Tab)"""
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #333;
                background-color: #f5f7fa;
            }
            
            /* --- TABS FIX --- */
            QTabWidget::pane { 
                border: 1px solid #dcdcdc; 
                background: white; 
                border-radius: 5px;
                top: -1px; /* Kết nối liền mạch với tab */
            }
            
            QTabBar::tab {
                background: #e1e4e8;
                color: #555;
                /* Fix lỗi mất chữ: Giảm padding dọc, tăng min-width */
                padding: 10px 20px; 
                min-width: 180px; /* Đảm bảo tab đủ rộng để chứa text dài */
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                border: 1px solid transparent; /* Placeholder cho border */
            }
            
            QTabBar::tab:selected {
                background: white;
                color: #1976D2; /* Blue highlight */
                border: 1px solid #dcdcdc;
                border-bottom: 2px solid white; /* Che border của pane để tạo cảm giác liền mạch */
                margin-bottom: -1px; /* Đẩy tab xuống đè lên border pane */
            }
            
            QTabBar::tab:!selected:hover {
                background: #d0d4d8;
                color: #333;
            }
            
            /* --- GROUP BOX (CARD STYLE) --- */
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
            
            /* --- BUTTONS --- */
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
            QPushButton:pressed {
                background-color: #e3f2fd;
            }
            
            /* Primary Button (Start Process) */
            QPushButton#ProcessBtn {
                background-color: #2e7d32; /* Green */
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

            /* --- TREE & LIST --- */
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

            /* --- PROGRESS BAR --- */
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
        main_layout.setContentsMargins(15, 15, 15, 15) # Lề ngoài
        main_layout.setSpacing(15)

        # Tạo TabWidget
        self.tab_widget = QTabWidget()
        
        # ================= TAB 1: PROCESSING =================
        processing_tab = QWidget()
        # Dùng GridLayout hoặc VBox nhưng chia tỉ lệ
        processing_layout = QVBoxLayout()
        processing_layout.setSpacing(20)
        processing_layout.setContentsMargins(15, 15, 15, 15)
        
        # --- SECTION 1: NGUỒN TÀI LIỆU (Chiếm không gian lớn nhất) ---
        pdf_group = QGroupBox("1. Nguồn Tài Liệu PDF")
        pdf_layout = QVBoxLayout()
        
        # Toolbar cho file
        file_toolbar = QHBoxLayout()
        
        self.add_files_button = QPushButton("📄 Thêm File")
        self.add_files_button.setIcon(QIcon()) # Có thể thêm icon thật ở đây
        self.add_files_button.setCursor(Qt.PointingHandCursor)
        self.add_files_button.clicked.connect(self.add_pdf_files)
        
        self.add_folder_button = QPushButton("📁 Thêm Folder")
        self.add_folder_button.setCursor(Qt.PointingHandCursor)
        self.add_folder_button.clicked.connect(self.add_folder)
        
        self.select_all_button = QPushButton("☑️ Chọn hết")
        self.select_all_button.clicked.connect(self.select_all_items)
        
        self.deselect_all_button = QPushButton("☐ Bỏ chọn")
        self.deselect_all_button.clicked.connect(self.deselect_all_items)
        
        self.btn_remove_selected = QPushButton("❌ Xóa mục chọn")
        self.btn_remove_selected.setStyleSheet("color: #c62828; border-color: #ffcdd2;")
        self.btn_remove_selected.setToolTip("Xóa các dòng đang được bôi đen (Phím tắt: Delete)")
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
        
        # TreeView
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Tên Tài Liệu", "Đường Dẫn Chi Tiết"])
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setAnimated(True)
        self.file_tree.setIndentation(20)
        self.file_tree.itemChanged.connect(self.handle_item_check_changed)
        
        # Header config
        header = self.file_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Cột tên tự co giãn
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Cột đường dẫn giãn hết cỡ
        header.setStretchLastSection(False) 
        self.file_tree.setColumnWidth(0, 400)

        # Status label
        self.file_count_label = QLabel("<i>Chưa có tài liệu nào được chọn</i>")
        self.file_count_label.setStyleSheet("color: #666; margin-top: 5px;")
        self.file_count_label.setAlignment(Qt.AlignRight)
        
        pdf_layout.addLayout(file_toolbar)
        pdf_layout.addWidget(self.file_tree)
        pdf_layout.addWidget(self.file_count_label)
        pdf_group.setLayout(pdf_layout)
        
        # --- SECTION 2: CẤU HÌNH (Dạng Đề & Prompt) ---
        # Sử dụng QHBoxLayout để chia đôi màn hình nếu màn hình rộng, hoặc giữ QVBoxLayout
        config_group = QGroupBox("2. Cấu Hình Tạo Đề")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(15)
        
        # Dòng 1: Trắc nghiệm
        tn_container = QWidget()
        tn_container.setStyleSheet("background: #f9f9f9; border-radius: 6px; padding: 5px;")
        tn_layout = QHBoxLayout(tn_container)
        
        self.checkbox_tn = QCheckBox("Trắc nghiệm 4 đáp án (80 câu)")
        self.checkbox_tn.setChecked(True)
        self.checkbox_tn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.checkbox_tn.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_tn_label = QLabel(os.path.basename(self.default_prompt_tn))
        self.prompt_tn_label.setStyleSheet("color: #1565C0; font-style: italic;")
        
        self.btn_select_prompt_tn = QPushButton("📁 Chọn Prompt")
        self.btn_select_prompt_tn.clicked.connect(lambda: self.select_prompt_file("trac_nghiem"))
        
        self.btn_edit_prompt_tn = QPushButton("✏️ Sửa")
        self.btn_edit_prompt_tn.clicked.connect(lambda: self.edit_prompt("trac_nghiem"))
        
        tn_layout.addWidget(self.checkbox_tn, 2)
        tn_layout.addWidget(QLabel("Prompt:"), 0)
        tn_layout.addWidget(self.prompt_tn_label, 3)
        tn_layout.addWidget(self.btn_select_prompt_tn)
        tn_layout.addWidget(self.btn_edit_prompt_tn)
        
        # Dòng 2: Đúng/Sai
        ds_container = QWidget()
        ds_container.setStyleSheet("background: #f9f9f9; border-radius: 6px; padding: 5px;")
        ds_layout = QHBoxLayout(ds_container)
        
        self.checkbox_ds = QCheckBox("Đúng/Sai (40 câu)")
        self.checkbox_ds.setChecked(True)
        self.checkbox_ds.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.checkbox_ds.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_ds_label = QLabel(os.path.basename(self.default_prompt_ds))
        self.prompt_ds_label.setStyleSheet("color: #1565C0; font-style: italic;")
        
        self.btn_select_prompt_ds = QPushButton("📁 Chọn Prompt")
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

        # --- SECTION 3: ACTION ---
        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(0, 10, 0, 0)
        
        self.process_button = QPushButton("🚀 BẮT ĐẦU XỬ LÝ NGAY")
        self.process_button.setObjectName("ProcessBtn") # Dùng ID để style riêng
        self.process_button.setCursor(Qt.PointingHandCursor)
        self.process_button.setMinimumHeight(50)
        self.process_button.clicked.connect(self.process_files)
        
        # Progress info
        status_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v")
        
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: #555;")
        
        action_layout.addWidget(self.process_button)
        action_layout.addWidget(self.status_label)
        action_layout.addWidget(self.progress_bar)

        # Add to Main Tab Layout
        processing_layout.addWidget(pdf_group, 6) # Chiếm 6 phần
        processing_layout.addWidget(config_group, 3) # Chiếm 3 phần
        processing_layout.addLayout(action_layout, 1) # Chiếm 1 phần
        
        processing_tab.setLayout(processing_layout)
        
        # ================= TAB 2: KẾT QUẢ =================
        result_tab = QWidget()
        result_layout = QHBoxLayout() # Đổi thành HBox để full màn hình
        result_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("QSplitter::handle { background-color: #e0e0e0; }")
        
        # -- LEFT: LIST FILE --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        
        lbl_result = QLabel("📂 Danh sách đã tạo")
        lbl_result.setStyleSheet("font-weight: bold; color: #2E7D32; padding: 5px;")
        
        self.docx_list = QListWidget()
        self.docx_list.setCursor(Qt.PointingHandCursor)
        self.docx_list.itemClicked.connect(self.show_selected_docx)
        
        left_layout.addWidget(lbl_result)
        left_layout.addWidget(self.docx_list)
        
        # -- RIGHT: PREVIEW --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        # Header preview
        preview_header = QHBoxLayout()
        lbl_preview = QLabel("📋 Xem trước tài liệu")
        lbl_preview.setStyleSheet("font-weight: bold; color: #1565C0; padding: 5px;")
        
        self.btn_open_external = QPushButton("↗️ Mở bằng Word/WPS")
        self.btn_open_external.setIcon(QIcon())
        self.btn_open_external.setFixedSize(180, 35)
        self.btn_open_external.setCursor(Qt.PointingHandCursor)
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
        self.docx_viewer.setStyleSheet("border: 1px solid #ccc;")
        
        right_layout.addLayout(preview_header)
        right_layout.addWidget(self.docx_viewer)
        
        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 9)
        
        result_layout.addWidget(splitter)
        result_tab.setLayout(result_layout)
        
        # Add Tabs
        self.tab_widget.addTab(processing_tab, "⚙️ CẤU HÌNH & XỬ LÝ")
        self.tab_widget.addTab(result_tab, "📄 KẾT QUẢ ĐẦU RA")
        
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
        self.update_process_button_state()

    # ============================================================
    # PHẦN LOGIC BÊN DƯỚI GIỮ NGUYÊN 100% NHƯ CŨ
    # (Copy toàn bộ logic từ code cũ của bạn vào đây)
    # ============================================================

    def remove_selected_items(self):
        """
        Phiên bản sửa lỗi: Xóa tất cả các mục ĐÃ ĐƯỢC TICK (CHECKED).
        Khắc phục lỗi chỉ xóa file đang bôi đen.
        """
        # 1. Tìm tất cả các item đang được TICK (Checked)
        checked_items = []
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            # Chỉ lấy item nào có trạng thái là Checked (V)
            if item.checkState(0) == Qt.Checked:
                checked_items.append(item)
            iterator += 1
            
        if not checked_items:
            QMessageBox.information(self, "Thông báo", "Vui lòng tick chọn (V) vào các mục cần xóa!")
            return

        # Xác nhận
        confirm = QMessageBox.question(
            self, "Xác nhận", 
            f"Bạn có chắc muốn xóa {len(checked_items)} mục đã chọn?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return

        # 2. LOGIC XÓA AN TOÀN (Lọc danh sách)
        # Nguyên tắc: Nếu Folder cha đã nằm trong danh sách xóa, thì KHÔNG cần lệnh xóa Folder con nữa.
        # (Vì xóa cha là con tự mất. Cố xóa con sẽ gây lỗi).
        
        items_to_delete = []
        for item in checked_items:
            parent = item.parent()
            
            # Logic: Item này sẽ được xóa NẾU:
            # - Nó không có cha (nằm ngay root)
            # - HOẶC Cha của nó KHÔNG nằm trong trạng thái Checked (tức là chỉ muốn xóa con, giữ lại cha)
            if parent is None or parent.checkState(0) != Qt.Checked:
                items_to_delete.append(item)

        # 3. Thực hiện xóa
        root = self.file_tree.invisibleRootItem()
        for item in items_to_delete:
            # Lấy cha của item đó để ra lệnh xóa con
            (item.parent() or root).removeChild(item)

        # 4. Cập nhật lại số lượng
        self.update_file_count()
    
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

    def open_current_docx(self):
        
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
        """
        Xử lý sự kiện khi user tick vào checkbox.
        Sử dụng cơ chế blockSignals + try/finally để đảm bảo an toàn tuyệt đối, 
        tránh trường hợp giao diện bị đơ không bấm được.
        """
        if column != 0: return

        # 1. Chặn tín hiệu tạm thời để code xử lý không kích hoạt lại sự kiện này (tránh vòng lặp vô tận)
        self.file_tree.blockSignals(True)
        
        try:
            # 2. Lấy trạng thái mới
            check_state = item.checkState(0)
            
            # 3. Cập nhật đồng bộ cho con và cha
            self.update_children_check_state(item, check_state)
            self.update_parent_check_state(item)
            
            # 4. Cập nhật số lượng file
            self.update_file_count()
            
        except Exception as e:
            # Nếu có lỗi ngầm, in ra console để debug chứ không làm crash giao diện
            print(f"Error in handle_item_check_changed: {e}")
            
        finally:
            # 5. QUAN TRỌNG NHẤT: Luôn luôn mở lại tín hiệu dù có lỗi hay không
            self.file_tree.blockSignals(False)

    def update_children_check_state(self, parent_item, check_state):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, check_state)
            if child.childCount() > 0:
                self.update_children_check_state(child, check_state)

    def update_parent_check_state(self, item):
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
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            if item.text(1) == file_path: return True
            iterator += 1
        return False

    def clear_all_items(self):
        self.file_tree.clear()
        self.update_file_count()

    def select_all_items(self):
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            item.setCheckState(0, Qt.Checked)
            iterator += 1

    def deselect_all_items(self):
        
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            item.setCheckState(0, Qt.Unchecked)
            iterator += 1

    def update_file_count(self):
        
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
        
        dialog = QMessageBox()
        dialog.setWindowTitle(f"Sửa Prompt - {'Trắc nghiệm' if prompt_type == 'trac_nghiem' else 'Đúng/Sai'}")
        dialog.setIcon(QMessageBox.NoIcon)
        widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("📝 Chỉnh sửa nội dung prompt:")
        label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(label)
        text_edit = QTextEdit()
        text_edit.setFont(QFont("Consolas", 10))
        text_edit.setMinimumSize(700, 500)
        if prompt_type == "trac_nghiem": text_edit.setPlainText(self.prompt_tn_content)
        else: text_edit.setPlainText(self.prompt_ds_content)
        layout.addWidget(text_edit)
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
        layout.addLayout(btn_layout)
        widget.setLayout(layout)
        from PyQt5.QtWidgets import QDialog, QVBoxLayout as QVBox
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle(f"Sửa Prompt - {'Trắc nghiệm' if prompt_type == 'trac_nghiem' else 'Đúng/Sai'}")
        edit_dialog.setModal(True)
        dialog_layout = QVBox()
        dialog_layout.addWidget(widget)
        edit_dialog.setLayout(dialog_layout)
        edit_dialog.resize(750, 600)
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
        
        has_selection = self.checkbox_tn.isChecked() or self.checkbox_ds.isChecked()
        self.process_button.setEnabled(has_selection)
        if not has_selection: self.process_button.setText("⚠️ Vui lòng chọn ít nhất 1 dạng đề")
        else: self.process_button.setText("🚀 BẮT ĐẦU XỬ LÝ NGAY")

    def get_selected_items(self):
        """
        Xử lý thông minh v7.0:
        1. Folder: Quét file -> Phân cụm bằng thuật toán Tỷ lệ tương đồng.
           - Nếu tất cả file có tỷ lệ giống nhau cao -> Gộp thành 1 file (Tên Folder/Tên Chung).
           - Nếu khác nhau -> Tách nhóm.
        2. File lẻ: Gom nhóm bằng thuật toán tương tự.
        """
        selected_items = {}
        loose_files_paths = [] 

        def traverse(item):
            if item.checkState(0) == Qt.Unchecked: return

            item_type = item.data(0, Qt.UserRole)

            # --- XỬ LÝ FOLDER ---
            if item_type == "folder" and item.checkState(0) == Qt.Checked:
                folder_name = item.text(0).replace("📁 ", "").strip()
                pdf_list = []
                self._collect_checked_pdfs_recursive(item, pdf_list)
                
                if not pdf_list: return

                # CHẠY CLUSTERING
                clustered_groups = self._smart_group_files(pdf_list)
                
                # LOGIC QUYẾT ĐỊNH
                if len(clustered_groups) == 1:
                    # Nếu chỉ ra 1 nhóm -> Folder này đồng nhất
                    # Ưu tiên lấy tên Folder làm key cho đẹp
                    final_list = list(clustered_groups.values())[0]
                    final_list.sort()
                    selected_items[folder_name] = final_list
                else:
                    # Folder lộn xộn -> Dùng kết quả phân tách
                    print(f"ℹ️ Folder '{folder_name}' được tách thành {len(clustered_groups)} nhóm.")
                    selected_items.update(clustered_groups)
                return 

            # --- DUYỆT TIẾP ---
            if item_type == "folder": 
                for i in range(item.childCount()):
                    traverse(item.child(i))
                return

            # --- FILE LẺ ---
            if item_type == "file" and item.checkState(0) == Qt.Checked:
                loose_files_paths.append(item.text(1))

        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            traverse(root.child(i))

        # Xử lý file lẻ
        if loose_files_paths:
            smart_groups = self._smart_group_files(loose_files_paths)
            selected_items.update(smart_groups)

        return selected_items

    def _smart_group_files(self, file_paths):
        """
        Thuật toán Clustering dựa trên Longest Common Substring (LCS) & Tỷ lệ.
        Thay vì fix cứng số ký tự, ta dùng % giống nhau.
        """
        import difflib
        groups = {}
        
        # Copy danh sách để không ảnh hưởng list gốc
        pending_files = file_paths.copy()
        
        while pending_files:
            # Lấy file đầu tiên làm "Hạt giống" (Seed) cho nhóm mới
            seed_file = pending_files.pop(0)
            seed_name = os.path.splitext(os.path.basename(seed_file))[0]
            
            current_group = [seed_file]
            current_common_str = seed_name # Chuỗi chung khởi tạo là tên file đầu
            
            # Duyệt ngược để có thể remove an toàn
            for i in range(len(pending_files) - 1, -1, -1):
                candidate_file = pending_files[i]
                candidate_name = os.path.splitext(os.path.basename(candidate_file))[0]
                
                # Tìm chuỗi chung dài nhất giữa (Lõi nhóm hiện tại) và (Ứng viên)
                matcher = difflib.SequenceMatcher(None, current_common_str, candidate_name)
                match = matcher.find_longest_match(0, len(current_common_str), 0, len(candidate_name))
                
                # Lấy ra chuỗi chung
                lcs = current_common_str[match.a : match.a + match.size].strip()
                
                # === CÔNG THỨC QUYẾT ĐỊNH GOM NHÓM (QUAN TRỌNG) ===
                # Tính tỷ lệ: Độ dài chuỗi chung / Độ dài ngắn nhất trong 2 chuỗi
                # Ví dụ: "Bai1" (4) và "Bai2" (4) -> Chung "Bai" (3) -> Tỷ lệ 3/4 = 0.75 (75%) -> GOM
                min_len = min(len(current_common_str), len(candidate_name))
                if min_len == 0: ratio = 0
                else: ratio = len(lcs) / min_len
                
                # CONFIG: NGƯỠNG TƯƠNG ĐỒNG (THRESHOLD)
                # 0.4 nghĩa là chỉ cần giống nhau 40% cấu trúc tên là gom.
                # Kết hợp điều kiện: Chuỗi chung phải có ít nhất 3 ký tự có nghĩa.
                clean_lcs = lcs.replace("-", "").replace("_", "").replace(".", "").strip()
                
                if ratio >= 0.4 and len(clean_lcs) >= 3:
                    # GOM VÀO NHÓM
                    current_group.append(candidate_file)
                    
                    # Cập nhật lại chuỗi chung của nhóm (Intersection)
                    # Nhóm càng đông, tên chung càng ngắn lại (nhưng chính xác hơn)
                    current_common_str = lcs
                    
                    # Xóa khỏi danh sách chờ để không xét lại
                    pending_files.pop(i)
            
            # Xử lý tên Output cho nhóm này
            final_name = current_common_str.strip(" -_.")
            
            # Fallback: Nếu tên chung bị co lại còn quá ngắn hoặc rỗng
            if len(final_name) < 3: 
                final_name = seed_name # Dùng tên file hạt giống
            
            current_group.sort()
            
            # Merge vào kết quả (xử lý trùng key)
            if final_name in groups:
                groups[final_name].extend(current_group)
                groups[final_name] = sorted(list(set(groups[final_name])))
            else:
                groups[final_name] = current_group
                
        return groups
    def _collect_checked_pdfs_recursive(self, parent_item, pdf_list):
        """Hàm đệ quy hỗ trợ get_selected_items"""
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
        
        if hasattr(self, 'thread') and self.thread is not None:
            try:
                self.thread.quit()
                self.thread.wait()
            except Exception: pass
        
        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Đang kết nối AI và xử lý...")
        
        self.thread = ProcessingThread(
            selected_items,
            prompt_paths,
            self.app_key,
            self.app_id,
            self.project_id,
            self.credentials
        )
        self.thread.progress.connect(self.update_status)
        self.thread.error.connect(self.show_error)
        self.thread.finished.connect(self.processing_finished)
        self.thread.start()

    def set_ui_enabled(self, enabled):
        
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

    def update_status(self, message):
        
        self.status_label.setText(message)
        current = self.progress_bar.value()
        self.progress_bar.setValue(min(current + 10, 90))

    def show_error(self, message):
        
        QMessageBox.critical(self, "Lỗi", message)
        self.status_label.setText("Đã xảy ra lỗi")
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

    def processing_finished(self, generated_files):
        
        self.generated_files = [f for f in generated_files if f is not None]
        self.docx_list.clear()
        if not self.generated_files:
            QMessageBox.warning(self, "Cảnh báo", "Không có file nào được tạo ra.")
            self.status_label.setText("Không có file được tạo")
        else:
            for fname in self.generated_files:
                self.docx_list.addItem(os.path.basename(fname))
            self.status_label.setText(f"✓ Hoàn tất! Đã tạo {len(self.generated_files)} file")
            self.tab_widget.setCurrentIndex(1)
            if self.generated_files:
                self.docx_list.setCurrentRow(0)
                self.show_selected_docx(self.docx_list.item(0))
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

    def show_selected_docx(self, item):
        # ... (Giữ nguyên code logic v2.0 - check 10MB) ...
        file_name = item.text()
        full_path = next((f for f in self.generated_files if os.path.basename(f) == file_name), None)
        self.btn_open_external.setEnabled(True)
        if not full_path or not os.path.isfile(full_path):
            self.docx_viewer.setHtml(f"<h3>Lỗi:</h3><p>File không tồn tại: {file_name}</p>")
            self.btn_open_external.setEnabled(False)
            return
        file_size_mb = os.path.getsize(full_path) / (1024 * 1024)
        limit_mb = 10.0 
        if file_size_mb > limit_mb:
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
                            img {{ max-width: 100%; height: auto; border: 1px solid #ddd; box-shadow: 2px 2px 5px #eee; }}
                            table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                            th, td {{ border: 1px solid #ddd; padding: 8px; }}
                        </style></head><body>{html}</body></html>"""
                    self.docx_viewer.setHtml(styled_html)
                else:
                    self.docx_viewer.setHtml(f"<p>File {file_name} không có nội dung văn bản/ảnh đọc được.</p>")
        except Exception as e:
            self.docx_viewer.setHtml(f"<h3>Lỗi khi đọc file</h3><p>{str(e)}</p>")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())