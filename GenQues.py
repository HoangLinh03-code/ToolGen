import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QFileDialog, QMessageBox, QSplitter, 
    QProgressBar, QSpinBox, QTextEdit, QShortcut
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont, QKeySequence
import mammoth
from dotenv import load_dotenv
from google.oauth2 import service_account
import glob
import time
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from github_updater_check import GitHubUpdateChecker
from process.response2docx import response2docx_improved

load_dotenv()

class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(list)
    batch_complete = pyqtSignal(int)  # Thông báo hoàn thành batch

    def __init__(self, root_folder, prompt_tracnghiem_path, prompt_dungaai_path, 
                 project_id, creds, batch_size=2):
        super().__init__()
        self.root_folder = root_folder
        self.prompt_tracnghiem_path = prompt_tracnghiem_path
        self.prompt_dungsai_path = prompt_dungaai_path
        self.project_id = project_id
        self.creds = creds
        self.batch_size = batch_size

    def run(self):
        generated_files = []
        
        try:
            # Đọc 2 prompt
            with open(self.prompt_tracnghiem_path, "r", encoding="utf-8") as f:
                prompt_tracnghiem = f.read()
            
            with open(self.prompt_dungsai_path, "r", encoding="utf-8") as f:
                prompt_dungsai = f.read()
            
            # Lấy danh sách các bài (folder con)
            bai_folders = [
                os.path.join(self.root_folder, name)
                for name in sorted(os.listdir(self.root_folder))
                if os.path.isdir(os.path.join(self.root_folder, name))
            ]
            
            total_bai = len(bai_folders)
            self.progress.emit(f"Tìm thấy {total_bai} bài cần xử lý")
            
            # Xử lý theo batch
            for batch_start in range(0, total_bai, self.batch_size):
                if self.isInterruptionRequested():
                    self.progress.emit("⏹ Đã hủy theo yêu cầu người dùng")
                    break
                batch_end = min(batch_start + self.batch_size, total_bai)
                batch_folders = bai_folders[batch_start:batch_end]
                
                self.progress.emit(f"\n=== XỬ LÝ BATCH {batch_start//self.batch_size + 1} ===")
                self.progress.emit(f"Xử lý batch {batch_start+1} đến {batch_end}")
                
                # Xử lý từng bài trong batch
                for idx, bai_folder in enumerate(batch_folders):
                    if self.isInterruptionRequested():
                        self.progress.emit("⏹ Dừng ở giữa batch theo yêu cầu người dùng")
                        break
                    bai_name = os.path.basename(bai_folder)
                    self.progress.emit(f"\n--- Đang xử lý {bai_name} ---")
                    
                    # Lấy tất cả PDF trong bài
                    pdf_files = glob.glob(os.path.join(bai_folder, "*.pdf"))
                    
                    if not pdf_files:
                        self.progress.emit(f"⚠️ Không tìm thấy PDF trong {bai_name}")
                        continue
                    
                    # Tạo output folder cho bài này
                    output_folder = os.path.join("output", bai_name)
                    os.makedirs(output_folder, exist_ok=True)
                    
                    self.progress.emit(f"  ➤ Sinh 80 câu trắc nghiệm và 40 câu đúng/sai (xử lý đồng thời)...")

                    try:
                        with ThreadPoolExecutor(max_workers=2) as ex:
                            fut_tn = ex.submit(
                                response2docx_improved,
                                pdf_files,
                                prompt_tracnghiem,
                                os.path.join(output_folder, f"{bai_name}_TracNghiem"),
                                self.project_id,
                                self.creds,
                                "gemini-2.5-pro",
                                "tracnghiem",
                            )
                            fut_ds = ex.submit(
                                response2docx_improved,
                                pdf_files,
                                prompt_dungsai,
                                os.path.join(output_folder, f"{bai_name}_DungSai"),
                                self.project_id,
                                self.creds,
                                "gemini-2.5-pro",
                                "dungsai",
                            )
                            for fut in as_completed([fut_tn, fut_ds]):
                                out = fut.result()
                                if out:
                                    generated_files.append(out)
                        self.progress.emit(f"  ✓ Hoàn thành bài {bai_name}")
                    except Exception as e:
                        self.progress.emit(f"  ✗ Lỗi xử lý {bai_name}: {str(e)}")
                
                # Hoàn thành batch - dọn dẹp bộ nhớ
                self.progress.emit(f"\n✓ Hoàn thành batch {batch_start//self.batch_size + 1}")
                self.progress.emit("Đang dọn dẹp bộ nhớ...")
                gc.collect()
                time.sleep(2)  # Nghỉ 2s giữa các batch
                
                percent = int((batch_end / total_bai) * 100) if total_bai else 100
                self.batch_complete.emit(percent)
        
        except Exception as e:
            self.error.emit(f"Lỗi trong quá trình xử lý: {str(e)}")
            return
        finally:
            # Đảm bảo executor được shutdown
            if self._executor:
                self._executor.shutdown(wait=False, cancel_futures=True)
        
        self.finished.emit(generated_files)
        
    def stop(self):
        """Dừng thread một cách an toàn"""
        self.requestInterruption()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)


class MainWindow(QWidget):
    CURRENT_VERSION = "1.0.0"  # Thay đổi mỗi khi release
    GITHUB_REPO = "HoangLinh03-code/ToolGen"  # Thay bằng repo của bạn
    
    # Kiểm tra cập nhật
    print("Đang kiểm tra cập nhật phiên bản")
    checker = GitHubUpdateChecker(CURRENT_VERSION, GITHUB_REPO)
    
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
        self.setWindowTitle("Supreme Gen Ques - Improved")
        self.resize(1200, 800)
        self.generated_files = []
        
        # Default prompt files
        self.default_prompt_tracnghiem = os.path.join(
            os.path.dirname(__file__), "prompt_Gen.txt"
        )
        self.default_prompt_dungsai = os.path.join(
            os.path.dirname(__file__), "promptDSCongNghe10.txt"
        )
        
        self.init_ui()
        self.setup_credentials()
        self.root_folder = None

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
            QMessageBox.critical(self, "Lỗi", f"Không thể tải thông tin xác thực: {str(e)}")
            self.process_button.setEnabled(False)

    def init_ui(self):
        font = QFont("Arial", 10)
        main_layout = QVBoxLayout()
        
        # 1. Chọn folder gốc (Tin học/Lớp 10)
        self.folder_label = QLabel("Chưa chọn folder gốc")
        self.folder_label.setFont(font)
        self.folder_label.setFixedHeight(30)
        self.folder_label.setStyleSheet("border: 1px solid black; padding: 3px;")
        self.folder_button = QPushButton("Chọn Folder Gốc")
        self.folder_button.setFixedSize(150, 30)
        self.folder_button.clicked.connect(self.select_root_folder)
        
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_button)
        
        # 2. Chọn prompt trắc nghiệm
        self.prompt_tn_label = QLabel(self.default_prompt_tracnghiem)
        self.prompt_tn_label.setFont(font)
        self.prompt_tn_label.setFixedHeight(30)
        self.prompt_tn_label.setStyleSheet("border: 1px solid black; padding: 3px;")
        self.prompt_tn_button = QPushButton("Prompt 80 câu")
        self.prompt_tn_button.setFixedSize(150, 30)
        self.prompt_tn_button.clicked.connect(lambda: self.select_prompt("tracnghiem"))
        
        prompt_tn_layout = QHBoxLayout()
        prompt_tn_layout.addWidget(self.prompt_tn_label)
        prompt_tn_layout.addWidget(self.prompt_tn_button)
        
        # 3. Chọn prompt đúng/sai
        self.prompt_ds_label = QLabel(self.default_prompt_dungsai)
        self.prompt_ds_label.setFont(font)
        self.prompt_ds_label.setFixedHeight(30)
        self.prompt_ds_label.setStyleSheet("border: 1px solid black; padding: 3px;")
        self.prompt_ds_button = QPushButton("Prompt 40 câu")
        self.prompt_ds_button.setFixedSize(150, 30)
        self.prompt_ds_button.clicked.connect(lambda: self.select_prompt("dungsai"))
        
        prompt_ds_layout = QHBoxLayout()
        prompt_ds_layout.addWidget(self.prompt_ds_label)
        prompt_ds_layout.addWidget(self.prompt_ds_button)
        
        # 4. Batch size
        batch_layout = QHBoxLayout()
        batch_label = QLabel("Số bài xử lý cùng lúc:")
        self.batch_spinbox = QSpinBox()
        self.batch_spinbox.setMinimum(1)
        self.batch_spinbox.setMaximum(5)
        self.batch_spinbox.setValue(2)
        self.batch_spinbox.setFixedWidth(60)
        batch_layout.addWidget(batch_label)
        batch_layout.addWidget(self.batch_spinbox)
        batch_layout.addStretch()
        
        # 5. Nút xử lý / trợ giúp / thoát
        self.process_button = QPushButton("Bắt đầu xử lý")
        self.process_button.setFont(font)
        self.process_button.setFixedHeight(40)
        self.process_button.clicked.connect(self.process_files)
        self.help_button = QPushButton("Hướng dẫn")
        self.help_button.setFixedHeight(32)
        self.help_button.clicked.connect(self.show_help)
        self.exit_button = QPushButton("Thoát")
        self.exit_button.setFixedHeight(32)
        self.exit_button.clicked.connect(self.request_exit)
        
        # 6. Progress bar và log
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        self.log_text.setMaximumHeight(200)
        
        # 7. Viewer
        self.docx_viewer = QWebEngineView()
        self.docx_list = QListWidget()
        self.docx_list.setFixedWidth(250)
        self.docx_list.itemClicked.connect(self.show_selected_docx)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.docx_viewer)
        splitter.addWidget(self.docx_list)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        # Layout chính
        main_layout.addLayout(folder_layout)
        main_layout.addLayout(prompt_tn_layout)
        main_layout.addLayout(prompt_ds_layout)
        main_layout.addLayout(batch_layout)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.process_button)
        btn_row.addWidget(self.help_button)
        btn_row.addWidget(self.exit_button)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("Log xử lý:"))
        main_layout.addWidget(self.log_text)
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)
        # Phím tắt Ctrl+Q để thoát nhanh
        self.shortcut_quit = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut_quit.activated.connect(self.request_exit)

    def select_root_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder gốc (vd: Lớp 10)")
        if folder:
            self.root_folder = folder
            self.folder_label.setText(folder)
            self.folder_label.setToolTip(folder)

    def select_prompt(self, prompt_type):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file prompt", "", "Text Files (*.txt)"
        )
        if file_path:
            if prompt_type == "tracnghiem":
                self.prompt_tn_label.setText(file_path)
            else:
                self.prompt_ds_label.setText(file_path)

    def process_files(self):
        if not self.root_folder or not os.path.isdir(self.root_folder):
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn folder gốc hợp lệ")
            return
        
        prompt_tn = self.prompt_tn_label.text()
        prompt_ds = self.prompt_ds_label.text()
        
        if not os.path.isfile(prompt_tn) or not os.path.isfile(prompt_ds):
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn cả 2 file prompt")
            return
        
        # Disable UI
        self.process_button.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.prompt_tn_button.setEnabled(False)
        self.prompt_ds_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        # Tạo thread
        self.thread = ProcessingThread(
            self.root_folder,
            prompt_tn,
            prompt_ds,
            self.project_id,
            self.credentials,
            self.batch_spinbox.value()
        )
        
        self.thread.progress.connect(self.update_log)
        self.thread.error.connect(self.show_error)
        self.thread.finished.connect(self.processing_finished)
        self.thread.batch_complete.connect(self.update_progress)
        self.thread.start()

    def update_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def update_progress(self, percent):
        self.progress_bar.setValue(percent)

    def show_error(self, message):
        QMessageBox.critical(self, "Lỗi", message)
        self.enable_ui()

    def processing_finished(self, generated_files):
        self.generated_files = [f for f in generated_files if f is not None]
        self.docx_list.clear()
        
        if not self.generated_files:
            QMessageBox.warning(self, "Cảnh báo", "Không có file nào được tạo")
        else:
            for fname in self.generated_files:
                self.docx_list.addItem(os.path.basename(fname))
            self.docx_list.setCurrentRow(0)
            self.show_selected_docx(self.docx_list.item(0))
            QMessageBox.information(
                self, "Hoàn thành", 
                f"Đã tạo {len(self.generated_files)} file thành công!"
            )
        
        self.progress_bar.setValue(100)
        self.enable_ui()

    def enable_ui(self):
        self.process_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.prompt_tn_button.setEnabled(True)
        self.prompt_ds_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    # def request_exit(self):
    #     if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
    #         reply = QMessageBox.question(
    #             self, "Thoát",
    #             "Đang xử lý. Bạn có muốn dừng và thoát ứng dụng không?",
    #             QMessageBox.Yes | QMessageBox.No, QMessageBox.No
    #         )
    #         if reply == QMessageBox.Yes:
    #             try:
    #                 self.thread.requestInterruption()
    #                 self.thread.wait(3000)
    #             except Exception:
    #                 pass
    #             QApplication.quit()
    #         return
    #     QApplication.quit()

    def request_exit(self):
        """Xử lý yêu cầu thoát ứng dụng"""
        if self.thread and self.thread.isRunning():
            reply = QMessageBox.question(
                self, "Xác nhận thoát",
                "Đang có tiến trình xử lý. Bạn có chắc muốn dừng và thoát?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.log_text.append("\n⏹ Đang dừng tiến trình...")
                QApplication.processEvents()  # Cập nhật UI
                
                # Gọi stop() để dừng executor
                self.thread.stop()
                
                # Đợi thread kết thúc (tăng timeout lên 5s)
                if not self.thread.wait(5000):
                    self.log_text.append("⚠️ Thread không dừng sau 5s, buộc thoát...")
                    self.thread.terminate()  # Force terminate nếu cần
                    self.thread.wait(1000)
                
                self.log_text.append("✓ Đã dừng tiến trình")
                QApplication.processEvents()
                
                QApplication.quit()
        else:
            QApplication.quit()

    def show_help(self):
        QMessageBox.information(
            self,
            "Hướng dẫn sử dụng",
            (
                "1) Chọn folder gốc (Theo Lớp).\n"
                "2) Chọn 2 file prompt (80 câu trắc nghiệm, 40 câu đúng sai).\n"
                "3) Chọn số bài xử lý đồng thời (mặc định 2).\n"
                "4) Nhấn 'Bắt đầu xử lý'.\n\n"
                "Gợi ý: Nhấn Ctrl+Q hoặc nút 'Thoát' để rời ứng dụng."
            )
        )

    # def closeEvent(self, event):
    #     if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
    #         reply = QMessageBox.question(
    #             self, "Thoát",
    #             "Đang xử lý. Bạn có muốn dừng và thoát ứng dụng không?",
    #             QMessageBox.Yes | QMessageBox.No, QMessageBox.No
    #         )
    #         if reply == QMessageBox.Yes:
    #             try:
    #                 self.thread.requestInterruption()
    #                 self.thread.wait(3000)
    #             except Exception:
    #                 pass
    #             event.accept()
    #         else:
    #             event.ignore()
    #     else:
    #         event.accept()
    def closeEvent(self, event):
        """Xử lý sự kiện đóng cửa sổ"""
        if self.thread and self.thread.isRunning():
            reply = QMessageBox.question(
                self, "Xác nhận thoát",
                "Đang có tiến trình xử lý. Bạn có chắc muốn dừng và thoát?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Dừng thread
                self.thread.stop()
                
                if not self.thread.wait(5000):
                    self.thread.terminate()
                    self.thread.wait(1000)
                
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def show_selected_docx(self, item):
        if not item:
            return
        file_name = item.text()
        full_path = next(
            (f for f in self.generated_files if os.path.basename(f) == file_name), 
            None
        )
        if not full_path or not os.path.isfile(full_path):
            self.docx_viewer.setHtml(f"<h3>Lỗi:</h3><p>File không tồn tại: {file_name}</p>")
            return
        
        try:
            with open(full_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value.strip()
                if html:
                    self.docx_viewer.setHtml(html)
                else:
                    self.docx_viewer.setHtml(f"<p>Không có nội dung trong {file_name}</p>")
        except Exception as e:
            self.docx_viewer.setHtml(f"<h3>Lỗi khi mở {file_name}</h3><p>{str(e)}</p>")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())