import vertexai, os
import sys
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account

# ============================================================
# CẤU HÌNH LOAD .ENV (SỬA LỖI PYINSTALLER _MEIPASS)
# ============================================================

def get_base_path():
    """
    Hàm xác định đường dẫn gốc chứa file .env
    - Nếu chạy EXE: Trả về thư mục tạm sys._MEIPASS
    - Nếu chạy Code: Trả về thư mục gốc của project (lùi ra khỏi folder api)
    """
    if getattr(sys, 'frozen', False):
        # 1. TRƯỜNG HỢP CHẠY FILE EXE (PyInstaller)
        # File .env được bundle vào root của thư mục tạm thông qua --add-data ".env;."
        # Nên ta lấy đường dẫn từ sys._MEIPASS
        return sys._MEIPASS
    else:
        # 2. TRƯỜNG HỢP CHẠY CODE PYTHON THƯỜNG
        # File này đang nằm ở: Project/api/callAPI.py
        # File .env nằm ở:     Project/.env
        # Nên cần lấy thư mục cha của thư mục chứa file này
        current_file_path = os.path.abspath(__file__) # .../api/callAPI.py
        current_dir = os.path.dirname(current_file_path) # .../api
        return os.path.dirname(current_dir) # .../Project (Thư mục gốc)

# 1. Lấy đường dẫn gốc chuẩn
base_path = get_base_path()

# 2. Đường dẫn tuyệt đối đến .env
dotenv_path = os.path.join(base_path, '.env')

# 3. Load .env với quyền GHI ĐÈ
print(f"📂 Đang tìm .env ...") # In ra để debug xem đúng đường dẫn chưa

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True) 
    print(f"✅ Đã load cấu hình")
else:
    # Fallback: Nếu không thấy trong _MEIPASS (hiếm khi xảy ra nếu build đúng), 
    # thử tìm cạnh file exe (sys.executable) phòng trường hợp user để file .env bên ngoài
    if getattr(sys, 'frozen', False):
        exe_path = os.path.dirname(sys.executable)
        external_env = os.path.join(exe_path, '.env')
        if os.path.exists(external_env):
            load_dotenv(external_env, override=True)
            print(f"✅ Đã load cấu hình từ file bên ngoài EXE")
        else:
            print(f"⚠️ CẢNH BÁO: Không tìm thấy file .env ở trong Temp lẫn cạnh file EXE!")
    else:
        print(f"⚠️ CẢNH BÁO: Không tìm thấy file .env")

# ============================================================

class VertexClient:
    def __init__(self, project_id, creds, model, region="us-central1"):
        # Xử lý trường hợp creds bị None để tránh crash app ngay lập tức
        if not creds:
            print("❌ Lỗi: Credentials bị None, không thể init Vertex AI.")
            return

        try:
            vertexai.init(
                project=project_id,
                location=region,
                credentials=creds
            )
            self.model = GenerativeModel(model)
        except Exception as e:
            print(f"❌ Lỗi init Vertex AI: {e}")

    def send_data_to_AI(self, prompt, file_paths=None, temperature=0.45, top_p=0.8):
        # Nếu model chưa được khởi tạo (do lỗi creds), trả về lỗi giả lập hoặc raise
        if not hasattr(self, 'model'):
            return "❌ Lỗi: Kết nối AI chưa được khởi tạo (Thiếu Credentials)."

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

        try:
            response = self.model.generate_content(
                parts, generation_config=generation_config
            )
            return response.text
        except Exception as e:
            print(f"❌ Lỗi khi gọi AI generate_content: {e}")
            raise e # Ném lỗi ra để bên ngoài bắt được
    
    def send_data_to_check(self, prompt, temperature=0.45, top_p=0.8):
        if not hasattr(self, 'model'):
             return "ERROR_NO_CREDS"

        parts = []
        parts.append(Part.from_text(prompt))

        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p
        )

        try:
            response = self.model.generate_content(
                parts, generation_config=generation_config
            )
            return response.text
        except Exception as e:
            print(f"❌ Lỗi khi check data: {e}")
            return str(e)

def get_vertex_ai_credentials():
    """Lấy đối tượng credentials cho Vertex AI từ .env."""
    try:
        # Kiểm tra xem biến môi trường có giá trị không
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key:
            print("❌ Lỗi: Không tìm thấy PRIVATE_KEY trong biến môi trường (File .env có thể chưa load đúng)")
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