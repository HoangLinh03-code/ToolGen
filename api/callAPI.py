import vertexai, os, time
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account

load_dotenv()
CHUNK_SIZE = 3 * 1024 * 1024  # 5MB
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
            total_chunks = 0
            total_pdf_size = 0

            if file_paths:
                for file_path in file_paths:
                    if not os.path.isfile(file_path):
                        print(f"[DEBUG] File không tồn tại: {file_path}")
                        continue
                    file_size = os.path.getsize(file_path)
                    total_pdf_size += file_size
                    print(f"[DEBUG] Đang đọc file: {file_path}, kích thước: {file_size/1024/1024:.2f} MB")
                    start_read = time.time()
                    try:
                        with open(file_path, "rb") as f:
                            chunk_idx = 0
                            while True:
                                chunk = f.read(CHUNK_SIZE)
                                if not chunk:
                                    break
                                parts.append(
                                    Part.from_data(data=chunk, mime_type="application/pdf")
                                )
                                chunk_idx += 1
                            total_chunks += chunk_idx
                            print(f"[DEBUG] Số chunk của file {file_path}: {chunk_idx}")
                    except Exception as e:
                        print(f"[DEBUG] Lỗi khi đọc file {file_path}: {e}")
                    print(f"[DEBUG] Thời gian đọc file: {time.time() - start_read:.2f}s")

            print(f"[DEBUG] Tổng số chunk PDF: {total_chunks}, tổng kích thước: {total_pdf_size/1024/1024:.2f} MB")

            parts.append(Part.from_text(prompt))

            generation_config = GenerationConfig(
                temperature=temperature,
                top_p=top_p
            )

            start_send = time.time()
            response = self.model.generate_content(
                parts, generation_config=generation_config
            )
            print(f"[DEBUG] Thời gian gửi dữ liệu lên AI: {time.time() - start_send:.2f}s")
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