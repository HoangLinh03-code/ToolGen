import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QFileDialog, QMessageBox, QSplitter, QProgressBar,
    QCheckBox, QGroupBox, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont
import mammoth
from dotenv import load_dotenv
from google.oauth2 import service_account
import glob

from process.response2docx import response2docx_json, response2docx_dung_sai_json

load_dotenv()

if getattr(sys, 'frozen', False):
    # Chạy từ .exe
    # _MEIPASS dùng cho các file được đóng gói bằng --add-data (như .env, icon...)
    internal_path = sys._MEIPASS
    # sys.executable dùng cho các file nằm cạnh file exe (như output, prompt mặc định)
    external_path = os.path.dirname(sys.executable)
else:
    # Chạy local
    internal_path = os.path.dirname(__file__)
    external_path = os.path.dirname(__file__)

dotenv_path = os.path.join(internal_path, '.env')
load_dotenv(dotenv_path)

class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, pdf_files, pdf_folder, prompt_paths, app_key, app_id, project_id, creds):
        super().__init__()
        self.pdf_files = pdf_files
        self.pdf_folder = pdf_folder
        self.prompt_paths = prompt_paths  # Dict: {"trac_nghiem": path, "dung_sai": path}
        self.app_key = app_key
        self.app_id = app_id
        self.project_id = project_id
        self.creds = creds

    def run(self):
        generated_files = []
        try:
            # Xử lý theo folder hoặc files
            if self.pdf_folder:
                sub_folders = [
                    os.path.join(self.pdf_folder, name)
                    for name in os.listdir(self.pdf_folder)
                    if os.path.isdir(os.path.join(self.pdf_folder, name))
                ]

                if not sub_folders:
                    # Nếu không có subfolder, xử lý trực tiếp folder
                    pdf_files_in_folder = glob.glob(os.path.join(self.pdf_folder, "*.pdf"))
                    if pdf_files_in_folder:
                        self.process_pdf_set(
                            pdf_files_in_folder,
                            os.path.basename(self.pdf_folder),
                            generated_files
                        )
                else:
                    # Có subfolder
                    for folder in sub_folders:
                        pdf_files_in_subfolder = glob.glob(os.path.join(folder, "*.pdf"))
                        if pdf_files_in_subfolder:
                            output_filename = f"{os.path.basename(self.pdf_folder)}_{os.path.basename(folder)}"
                            self.process_pdf_set(
                                pdf_files_in_subfolder,
                                output_filename,
                                generated_files
                            )
                            
            elif self.pdf_files:
                # Xử lý danh sách files PDF
                output_filename = os.path.splitext(os.path.basename(self.pdf_files[0]))[0]
                self.process_pdf_set(self.pdf_files, output_filename, generated_files)

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
        self.setWindowTitle("Supreme Gen Ques v2.0")
        self.resize(1200, 750)
        self.generated_files = []
        
        # Prompt files mặc định
        self.default_prompt_tn = os.path.join(external_path, "testTN.txt")
        self.default_prompt_ds = os.path.join(external_path, "testDS.txt")
        
        if not os.path.exists(self.default_prompt_tn):
             self.default_prompt_tn = os.path.join(internal_path, "testTN.txt")
        if not os.path.exists(self.default_prompt_ds):
             self.default_prompt_ds = os.path.join(internal_path, "testDS.txt")
        
        self.init_ui()
        self.setup_credentials()
        self.pdf_files = []
        self.pdf_folder = None
        
    def setup_credentials(self):
        """Thiết lập thông tin xác thực Google Cloud từ biến môi trường."""
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

    def init_ui(self):
        font = QFont("Arial", 10)
        main_layout = QVBoxLayout()

        # ===== PHẦN 1: CHỌN FILE PDF =====
        pdf_group = QGroupBox("1. Chọn nguồn tài liệu PDF")
        pdf_group.setFont(QFont("Arial", 10, QFont.Bold))
        pdf_layout = QVBoxLayout()
        
        # Label hiển thị file đã chọn
        self.pdf_label = QLabel("Chưa chọn file PDF hoặc folder")
        self.pdf_label.setFont(font)
        self.pdf_label.setStyleSheet("border: 1px solid #ccc; padding: 8px; background: #f9f9f9; border-radius: 4px;")
        self.pdf_label.setWordWrap(True)
        self.pdf_label.setMinimumHeight(50)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.pdf_button = QPushButton("📄 Chọn File PDF")
        self.pdf_button.setFixedSize(150, 35)
        self.pdf_button.clicked.connect(self.select_pdf)
        
        self.folder_button = QPushButton("📁 Chọn Folder")
        self.folder_button.setFixedSize(150, 35)
        self.folder_button.clicked.connect(self.select_folder)
        
        self.clear_pdf_button = QPushButton("🗑️ Xóa")
        self.clear_pdf_button.setFixedSize(100, 35)
        self.clear_pdf_button.clicked.connect(self.clear_pdf_selection)
        
        btn_layout.addWidget(self.pdf_button)
        btn_layout.addWidget(self.folder_button)
        btn_layout.addWidget(self.clear_pdf_button)
        btn_layout.addStretch()
        
        pdf_layout.addWidget(self.pdf_label)
        pdf_layout.addLayout(btn_layout)
        pdf_group.setLayout(pdf_layout)
        main_layout.addWidget(pdf_group)

        # ===== PHẦN 2: CHỌN DẠNG ĐỀ =====
        type_group = QGroupBox("2. Chọn dạng đề cần sinh")
        type_group.setFont(QFont("Arial", 10, QFont.Bold))
        type_layout = QVBoxLayout()
        
        # Checkbox cho trắc nghiệm 4 đáp án
        tn_layout = QHBoxLayout()
        self.checkbox_tn = QCheckBox("Trắc nghiệm 4 đáp án (80 câu)")
        self.checkbox_tn.setFont(font)
        self.checkbox_tn.setChecked(True)
        self.checkbox_tn.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_tn_label = QLabel(self.default_prompt_tn if os.path.isfile(self.default_prompt_tn) else "Chưa chọn prompt")
        self.prompt_tn_label.setFont(QFont("Arial", 9))
        self.prompt_tn_label.setStyleSheet("color: #666; padding: 3px;")
        
        self.btn_select_prompt_tn = QPushButton("📝 Chọn Prompt")
        self.btn_select_prompt_tn.setFixedSize(120, 30)
        self.btn_select_prompt_tn.clicked.connect(lambda: self.select_prompt("trac_nghiem"))
        
        tn_layout.addWidget(self.checkbox_tn)
        tn_layout.addWidget(self.prompt_tn_label, 1)
        tn_layout.addWidget(self.btn_select_prompt_tn)
        
        # Checkbox cho đúng/sai
        ds_layout = QHBoxLayout()
        self.checkbox_ds = QCheckBox("Đúng/Sai (40 câu)")
        self.checkbox_ds.setFont(font)
        self.checkbox_ds.setChecked(True)
        self.checkbox_ds.stateChanged.connect(self.update_process_button_state)
        
        self.prompt_ds_label = QLabel(self.default_prompt_ds if os.path.isfile(self.default_prompt_ds) else "Chưa chọn prompt")
        self.prompt_ds_label.setFont(QFont("Arial", 9))
        self.prompt_ds_label.setStyleSheet("color: #666; padding: 3px;")
        
        self.btn_select_prompt_ds = QPushButton("📝 Chọn Prompt")
        self.btn_select_prompt_ds.setFixedSize(120, 30)
        self.btn_select_prompt_ds.clicked.connect(lambda: self.select_prompt("dung_sai"))
        
        ds_layout.addWidget(self.checkbox_ds)
        ds_layout.addWidget(self.prompt_ds_label, 1)
        ds_layout.addWidget(self.btn_select_prompt_ds)
        
        type_layout.addLayout(tn_layout)
        type_layout.addLayout(ds_layout)
        type_group.setLayout(type_layout)
        main_layout.addWidget(type_group)

        # ===== PHẦN 3: XỬ LÝ =====
        process_group = QGroupBox("3. Thực hiện")
        process_group.setFont(QFont("Arial", 10, QFont.Bold))
        process_layout = QVBoxLayout()
        
        self.process_button = QPushButton("🚀 BẮT ĐẦU XỬ LÝ")
        self.process_button.setFont(QFont("Arial", 11, QFont.Bold))
        self.process_button.setFixedHeight(45)
        self.process_button.clicked.connect(self.process_files)
        self.process_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setFont(font)
        self.status_label.setStyleSheet("color: #666; padding: 5px;")
        
        process_layout.addWidget(self.process_button)
        process_layout.addWidget(self.progress_bar)
        process_layout.addWidget(self.status_label)
        process_group.setLayout(process_layout)
        main_layout.addWidget(process_group)

        # ===== PHẦN 4: KẾT QUẢ =====
        result_group = QGroupBox("4. Kết quả")
        result_group.setFont(QFont("Arial", 10, QFont.Bold))
        result_layout = QVBoxLayout()
        
        self.docx_viewer = QWebEngineView()
        self.docx_viewer.setStyleSheet("border: 1px solid #ccc; border-radius: 4px;")
        
        self.docx_list = QListWidget()
        self.docx_list.setFont(font)
        self.docx_list.setFixedWidth(250)
        self.docx_list.itemClicked.connect(self.show_selected_docx)
        self.docx_list.setStyleSheet("border: 1px solid #ccc; border-radius: 4px;")
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.docx_viewer)
        splitter.addWidget(self.docx_list)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        result_layout.addWidget(splitter)
        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        
        self.setLayout(main_layout)
        self.update_process_button_state()

    def clear_pdf_selection(self):
        """Xóa lựa chọn PDF"""
        self.pdf_files = []
        self.pdf_folder = None
        self.pdf_label.setText("Chưa chọn file PDF hoặc folder")

    def select_pdf(self):
        """Chọn một hoặc nhiều file PDF"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file PDF", "", "PDF Files (*.pdf)"
        )
        if file_paths:
            self.pdf_files = file_paths
            self.pdf_folder = None
            
            if len(file_paths) == 1:
                text = f"📄 {os.path.basename(file_paths[0])}"
            else:
                text = f"📄 Đã chọn {len(file_paths)} file PDF"
            
            self.pdf_label.setText(text)
            self.pdf_label.setToolTip("\n".join(file_paths))

    def select_folder(self):
        """Chọn folder chứa PDF"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục PDF", ""
        )
        if folder_path:
            self.pdf_folder = folder_path
            self.pdf_files = []
            
            text = f"📁 {os.path.basename(folder_path)}"
            self.pdf_label.setText(text)
            self.pdf_label.setToolTip(folder_path)

    def select_prompt(self, prompt_type):
        """Chọn file prompt cho dạng đề"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Chọn file prompt cho {prompt_type}", "", "Text Files (*.txt)"
        )
        if file_path:
            if prompt_type == "trac_nghiem":
                self.prompt_tn_label.setText(file_path)
            else:
                self.prompt_ds_label.setText(file_path)

    def update_process_button_state(self):
        """Cập nhật trạng thái nút xử lý"""
        has_selection = self.checkbox_tn.isChecked() or self.checkbox_ds.isChecked()
        self.process_button.setEnabled(has_selection)
        
        if not has_selection:
            self.process_button.setText("⚠️ Vui lòng chọn ít nhất 1 dạng đề")
        else:
            self.process_button.setText("🚀 BẮT ĐẦU XỬ LÝ")

    def process_files(self):
        """Bắt đầu xử lý file"""
        # Kiểm tra đã chọn PDF chưa
        if not self.pdf_files and not self.pdf_folder:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn file PDF hoặc folder trước!")
            return
        
        # Kiểm tra đã chọn ít nhất 1 dạng đề
        if not self.checkbox_tn.isChecked() and not self.checkbox_ds.isChecked():
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn ít nhất một dạng đề!")
            return
        
        # Chuẩn bị prompt paths
        prompt_paths = {}
        
        if self.checkbox_tn.isChecked():
            prompt_tn = self.prompt_tn_label.text()
            if not os.path.isfile(prompt_tn):
                QMessageBox.warning(self, "Lỗi", "File prompt trắc nghiệm không tồn tại!")
                return
            prompt_paths["trac_nghiem"] = prompt_tn
        
        if self.checkbox_ds.isChecked():
            prompt_ds = self.prompt_ds_label.text()
            if not os.path.isfile(prompt_ds):
                QMessageBox.warning(self, "Lỗi", "File prompt đúng/sai không tồn tại!")
                return
            prompt_paths["dung_sai"] = prompt_ds
        
        # Hủy luồng cũ nếu có
        if hasattr(self, 'thread') and self.thread is not None:
            try:
                self.thread.quit()
                self.thread.wait()
            except Exception:
                pass
        
        # Vô hiệu hóa giao diện
        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Đang xử lý...")
        
        # Tạo thread mới
        self.thread = ProcessingThread(
            self.pdf_files if self.pdf_files else None,
            self.pdf_folder if self.pdf_folder else None,
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
        """Bật/tắt các thành phần UI"""
        self.process_button.setEnabled(enabled)
        self.pdf_button.setEnabled(enabled)
        self.folder_button.setEnabled(enabled)
        self.clear_pdf_button.setEnabled(enabled)
        self.checkbox_tn.setEnabled(enabled)
        self.checkbox_ds.setEnabled(enabled)
        self.btn_select_prompt_tn.setEnabled(enabled)
        self.btn_select_prompt_ds.setEnabled(enabled)

    def update_status(self, message):
        """Cập nhật trạng thái"""
        self.status_label.setText(message)
        current = self.progress_bar.value()
        self.progress_bar.setValue(min(current + 10, 90))

    def show_error(self, message):
        """Hiển thị lỗi"""
        QMessageBox.critical(self, "Lỗi", message)
        self.status_label.setText("Đã xảy ra lỗi")
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

    def processing_finished(self, generated_files):
        """Xử lý khi hoàn thành"""
        self.generated_files = [f for f in generated_files if f is not None]
        self.docx_list.clear()
        
        if not self.generated_files:
            QMessageBox.warning(self, "Cảnh báo", "Không có file nào được tạo ra.")
            self.status_label.setText("Không có file được tạo")
        else:
            for fname in self.generated_files:
                self.docx_list.addItem(os.path.basename(fname))
            self.status_label.setText(f"✓ Hoàn tất! Đã tạo {len(self.generated_files)} file")
            
            if self.generated_files:
                self.docx_list.setCurrentRow(0)
                self.show_selected_docx(self.docx_list.item(0))
        
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

    def show_selected_docx(self, item):
        """Hiển thị file DOCX đã chọn"""
        file_name = item.text()
        full_path = next((f for f in self.generated_files if os.path.basename(f) == file_name), None)
        
        if not full_path or not os.path.isfile(full_path):
            self.docx_viewer.setHtml(f"<h3>Lỗi:</h3><p>File không tồn tại: {file_name}</p>")
            return

        try:
            with open(full_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value.strip()
                if html:
                    styled_html = f"""
                    <html>
                    <head>
                        <style>
                            body {{ font-family: Arial, sans-serif; padding: 20px; line-height: 1.6; }}
                            p {{ margin: 10px 0; }}
                        </style>
                    </head>
                    <body>{html}</body>
                    </html>
                    """
                    self.docx_viewer.setHtml(styled_html)
                else:
                    self.docx_viewer.setHtml(f"<p>Không có nội dung trong {file_name}</p>")
        except Exception as e:
            self.docx_viewer.setHtml(f"<h3>Lỗi khi mở {file_name}</h3><p>{str(e)}</p>")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())