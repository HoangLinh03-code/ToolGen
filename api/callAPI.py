import vertexai, os
import sys
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account

# ============================================================
# CẤU HÌNH LOAD .ENV (SỬA LỖI KHÔNG NHẬN BIẾN MỚI)
# ============================================================

# 1. Xác định đường dẫn gốc (nơi chứa file .py này hoặc file exe)
if getattr(sys, 'frozen', False):
    # Nếu chạy từ file .exe (PyInstaller)
    base_path = os.path.dirname(sys.executable)
else:
    # Nếu chạy từ code Python thường (lấy thư mục chứa file hiện tại)
    base_path = os.path.dirname(os.path.abspath(__file__))

# Lưu ý: Nếu file này nằm trong thư mục con (ví dụ /api/), 
# mà file .env nằm ở thư mục gốc project, bạn cần lùi lại 1 cấp:
# base_path = os.path.dirname(base_path) # Bỏ comment dòng này nếu file .py nằm trong thư mục con

# 2. Đường dẫn tuyệt đối đến .env
dotenv_path = os.path.join(base_path, '.env')

# 3. Load .env với quyền GHI ĐÈ (override=True)
if os.path.exists(dotenv_path):
    # override=True: Bắt buộc lấy giá trị mới trong file, bỏ qua cache cũ
    load_dotenv(dotenv_path, override=True) 
    print(f"✅ Đã load (và ghi đè) cấu hình từ: {dotenv_path}")
else:
    # Thử tìm ở thư mục làm việc hiện tại (Current Working Directory) nếu không thấy ở base_path
    cwd_env = os.path.join(os.getcwd(), '.env')
    if os.path.exists(cwd_env):
        load_dotenv(cwd_env, override=True)
        print(f"✅ Đã load (và ghi đè) cấu hình từ CWD: {cwd_env}")
    else:
        print(f"⚠️ CẢNH BÁO: Không tìm thấy file .env tại {dotenv_path} hoặc {cwd_env}")

# ============================================================

class VertexClient:
    # ... (Giữ nguyên code class VertexClient của bạn ở đây) ...
    def __init__(self, project_id, creds, model, region="us-central1"):
        vertexai.init(
            project=project_id,
            location=region,
            credentials=creds
        )
        self.model = GenerativeModel(model)

    def send_data_to_AI(self, prompt, file_paths=None, temperature=0.5, top_p=0.8):
        parts = []

        # Nếu có nhiều file PDF
        if file_paths:
            for file_path in file_paths:
                with open(file_path, "rb") as f:
                    pdf_bytes = f.read()
                parts.append(
                    Part.from_data(data=pdf_bytes, mime_type="application/pdf")
                )
            print("Load xong pdf")

        # Thêm prompt dạng text
        parts.append(Part.from_text(prompt))

        # Config sinh nội dung
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p
        )

        response = self.model.generate_content(
            parts, generation_config=generation_config
        )
        return response.text
    
    def send_data_to_check(self, prompt, temperature=0.5, top_p=0.8):
        parts = []
        # Thêm prompt dạng text
        parts.append(Part.from_text(prompt))

        # Config sinh nội dung
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p
        )

        response = self.model.generate_content(
            parts, generation_config=generation_config
        )
        return response.text

def get_vertex_ai_credentials():
    """Lấy đối tượng credentials cho Vertex AI từ .env."""
    try:
        # Kiểm tra xem biến môi trường có giá trị không
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key:
            print("❌ Lỗi: Không tìm thấy PRIVATE_KEY trong biến môi trường")
            return None

        service_account_data = {
            "type": os.getenv("TYPE"),
            "project_id": os.getenv("PROJECT_ID"),
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": private_key.replace('\\n', '\n'),
            "client_email": os.getenv("CLIENT_EMAIL"),
            "client_id": os.getenv("CLIENT_ID"),
            "auth_uri": os.getenv("AUTH_URI"),
            "token_uri": os.getenv("TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
            "universe_domain": os.getenv("UNIVERSE_DOMAIN")
        }
        credentials = service_account.Credentials.from_service_account_info(
            service_account_data,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return credentials
    except Exception as e:
        print(f"❌ Lỗi khi tạo credentials từ service account: {e}")
        return None