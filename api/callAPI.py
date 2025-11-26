import os
import sys
from dotenv import load_dotenv
from google.oauth2 import service_account
from google import genai
from google.genai import types

# ============================================================
# 1. CẤU HÌNH LOAD .ENV (Logic chuẩn từ test_connect.py)
# ============================================================
def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        # Lùi lại 1 cấp từ thư mục api để về root project
        current_file_path = os.path.abspath(__file__)
        current_dir = os.path.dirname(current_file_path) # folder api
        return os.path.dirname(current_dir) # folder root

base_path = get_base_path()
dotenv_path = os.path.join(base_path, '.env')


print(f"[API] Đang tìm .env ....")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)
    print(f"✅ [API] Đã load cấu hình từ")
else:
    # Fallback tìm ở CWD nếu chạy debug
    cwd_env = os.path.join(os.getcwd(), '.env')
    if os.path.exists(cwd_env):
        load_dotenv(cwd_env, override=True)

# ============================================================
# 2. HÀM TẠO CREDENTIALS (PUBLIC HELPER)
# ============================================================
def get_vertex_ai_credentials():
    """
    Hàm helper để lấy credentials, dùng chung cho cả callAPI và text2Image.
    """
    try:
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key:
            print("❌ [API] Lỗi: Không tìm thấy PRIVATE_KEY trong .env")
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
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_data,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return creds
    except Exception as e:
        print(f"❌ [API] Lỗi khi tạo credentials: {e}")
        return None

# ============================================================
# 3. CLASS VERTEX CLIENT (CHO TEXT GENERATION)
# ============================================================

class VertexClient:
    def __init__(self, project_id, creds, model_name, region="us-central1"):
        """
        Khởi tạo Client sử dụng google.genai SDK mới
        """
        self.model_name = model_name
        if not creds:
            print("❌ Lỗi: Credentials bị None.")
            return

        try:
            # Khởi tạo Client theo chuẩn mới
            self.client = genai.Client(
                vertexai=True,
                project=project_id,
                location=region,
                credentials=creds
            )
            print(f"✅ Init GenAI Client thành công với model: {self.model_name}")
        except Exception as e:
            print(f"Lỗi init GenAI Client: {e}")
            self.client = None

    def send_data_to_AI(self, prompt, file_paths=None, temperature=0.4, top_p=0.8):
        if not self.client:
            return "❌ Lỗi: Client chưa được khởi tạo."

        contents = []

        # 1. Xử lý File PDF (Sử dụng types.Part.from_bytes)
        if file_paths:
            # Nếu file_paths là string đơn, chuyển thành list
            if isinstance(file_paths, str):
                file_paths = [file_paths]
                
            for file_path in file_paths:
                try:
                    with open(file_path, "rb") as f:
                        pdf_bytes = f.read()
                    
                    # SDK mới dùng from_bytes thay vì from_data cũ
                    pdf_part = types.Part.from_bytes(
                        data=pdf_bytes, 
                        mime_type="application/pdf"
                    )
                    contents.append(types.Content(role="user", parts=[pdf_part]))
                    print(f"📄 Đã load PDF: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"❌ Lỗi đọc file {file_path}: {e}")
                    raise e

        # 2. Xử lý Prompt text
        text_part = types.Part.from_text(text=prompt)
        contents.append(types.Content(role="user", parts=[text_part]))

        # 3. Cấu hình sinh nội dung
        generate_config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p
        )

        try:
            # Gọi API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=generate_config
            )
            
            # Trả về text
            if response.text:
                return response.text
            else:
                return "⚠️ API trả về rỗng (Có thể do Safety Filter chặn)."
                
        except Exception as e:
            print(f"❌ Lỗi khi gọi AI generate_content: {e}")
            raise e
    
    def send_data_to_check(self, prompt, temperature=0.45, top_p=0.8):
        # Hàm check nhanh chỉ dùng text
        if not self.client:
             return "ERROR_NO_CREDS"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=top_p
                )
            )
            return response.text if response.text else "EMPTY_RESPONSE"
        except Exception as e:
            print(f"❌ Lỗi khi check data: {e}")
            return str(e)