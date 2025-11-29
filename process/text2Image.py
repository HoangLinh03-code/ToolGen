import os
from google import genai
from google.genai import types
from api.callAPI import get_vertex_ai_credentials 

def generate_image_from_text(prompt, aspect_ratio="1:1"):
    try:
        credentials = get_vertex_ai_credentials()
        project_id = os.getenv("PROJECT_ID")
        location = "global" 

        if not credentials or not project_id:
            print("❌ Lỗi: Thiếu Credentials/Project ID")
            return None

        client = genai.Client(vertexai=True, project=project_id, location=location, credentials=credentials)
        model_name = "gemini-3-pro-image-preview" 

        print(f"🎨 Đang sinh ảnh: {prompt[:30]}...")
        
        # Gọi API với timeout=60s (Đủ cho 1 ảnh)
        response = client.models.generate_content(
            model=model_name,
            contents=f"Vẽ hình ảnh minh họa chính xác cho mô tả sau: {prompt}",
            config=types.GenerateContentConfig(
                # tools=[{"google_search": {}}],
                response_modalities=["IMAGE"],
                candidate_count=1, # Yêu cầu rõ ràng chỉ sinh 1 ảnh
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            )
        )
        for part in response.parts:
            if part.inline_data and part.inline_data.data:
                print(f"✅ Sinh ảnh thành công ({len(part.inline_data.data)} bytes)")
                return part.inline_data.data

        print("❌ API không trả về dữ liệu ảnh.")
        return None
            
    except Exception as e:
        print(f"❌ Lỗi sinh ảnh: {str(e)}")
        return None

# Hàm phụ trợ giữ nguyên
def get_image_size_for_aspect_ratio(aspect_ratio, base_width_inches=3.0):
    try:
        w, h = map(float, aspect_ratio.split(":"))
        return base_width_inches, base_width_inches * (h / w)
    except:
        return base_width_inches, base_width_inches