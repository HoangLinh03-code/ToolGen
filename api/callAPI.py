import vertexai, os
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv
from google.oauth2 import service_account

load_dotenv()
class VertexClient:
    def __init__(self, project_id, creds, model, region="us-central1"):
        vertexai.init(
            project=project_id,
            location=region,
            credentials=creds
        )
        self.model = GenerativeModel(model)

    def send_data_to_AI(self, prompt, file_paths=None, temperature=0.7, top_p=0.8):
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
            temperature=0.7,
            top_p=top_p,
            max_output_tokens=8192,  # THÊM DÒNG NÀY
            candidate_count=1
        )
        
        response = self.model.generate_content(
            parts, generation_config=generation_config
        )
        return response.text
        
    def send_data_to_check(self, prompt, temperature=0.6, top_p=0.8):
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
        return response.text

def get_vertex_ai_credentials():
    """Láº¥y Ä‘á»‘i tÆ°á»£ng credentials cho Vertex AI tá»« .env."""
    try:
        service_account_data = {
            "type": os.getenv("TYPE"),
            "project_id": os.getenv("PROJECT_ID"),
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'), # Quan trá»ng: Thay tháº¿ chuá»—i \n
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
    

