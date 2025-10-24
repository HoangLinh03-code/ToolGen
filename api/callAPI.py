import vertexai, os
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account
import sys
import traceback
load_dotenv()
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)
 
dotenv_path = os.path.join(base_path, '.env')
load_dotenv(dotenv_path)
class VertexClient:
    def __init__(self, project_id, creds, model, region="us-central1"):
        vertexai.init(
            project=project_id,
            location=region,
            credentials=creds
        )
        self.model = GenerativeModel(model)
    
    def _safe_extract_text(self, response):
        """Xử lý response an toàn, tránh lỗi multiple content parts"""
        try:
            # Thử lấy text trực tiếp trước
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            
            # Nếu không có text, thử lấy từ candidates
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        # Ghép tất cả text parts lại
                        text_parts = []
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_parts.append(part.text.strip())
                        if text_parts:
                            return '\n'.join(text_parts)
            
            # Nếu vẫn không có text, thử lấy từ finish_reason
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    return f"Response finished with reason: {candidate.finish_reason}"
            
            return "Không thể lấy được nội dung từ AI response"
            
        except Exception as e:
            print(f"Lỗi xử lý response: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return f"Lỗi xử lý response: {str(e)}"

    def send_data_to_AI(self, prompt, file_paths=None, temperature=0.5, top_p=0.8):
        parts = []
        
        if file_paths:
            for file_path in file_paths:
                with open(file_path, "rb") as f:
                    pdf_bytes = f.read()
                parts.append(
                    Part.from_data(data=pdf_bytes, mime_type="application/pdf")
                )
            print("Load xong pdf\n")
        
        parts.append(Part.from_text(prompt))
        
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=8192,  # THÊM DÒNG NÀY
            candidate_count=1
        )
        
        response = self.model.generate_content(
            parts, generation_config=generation_config
        )
        
        return self._safe_extract_text(response)
        
    def send_data_to_check(self, prompt, temperature=0.5, top_p=0.8):
        parts = []
        # ThÃªm prompt dáº¡ng text
        parts.append(Part.from_text(prompt))

        # Config sinh ná»™i dung
        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p
        )

        response = self.model.generate_content(
            parts, generation_config=generation_config
        )
        
        return self._safe_extract_text(response)

def get_vertex_ai_credentials():
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
        credentials = service_account.Credentials.from_service_account_info(
            service_account_data,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return credentials
    except Exception as e:
        print(f"Lỗi khi tạo credentials trên service account: {e}")
        return None