import vertexai, os
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account
import sys

load_dotenv()
# ============ QUAN TRỌNG: Xử lý đường dẫn cho PyInstaller ============
if getattr(sys, 'frozen', False):
    # Chạy từ file .exe (PyInstaller)
    base_path = sys._MEIPASS  # Thư mục tạm của PyInstaller
else:
    # Chạy từ Python script thường
    base_path = os.path.dirname(__file__)

# Đường dẫn đến file .env
dotenv_path = os.path.join('.env')

# Load .env với explicit path
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"\nLoaded .env from: {dotenv_path}\n")
else:
    print(f"Warning: .env not found at {dotenv_path}\n")
    print(f"Base path: {base_path}\n")
    print(f"Files in base_path: {os.listdir(base_path) if os.path.exists(base_path) else 'N/A'}\n")
class VertexClient:
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
        service_account_data = {
            "type": os.getenv("TYPE"),
            "project_id": os.getenv("PROJECT_ID"),
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'), # Quan trọng: Thay thế chuỗi \n
            "client_email": os.getenv("CLIENT_EMAIL"),
            "client_id": os.getenv("CLIENT_ID", ""),
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
        print(f"Lỗi khi tạo credentials từ service account: {e}")
        return None