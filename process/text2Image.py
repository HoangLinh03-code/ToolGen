import os
import mimetypes
from google import genai
from google.genai import types
# Import hàm lấy credentials đã được chuẩn hóa bên callAPI
from api.callAPI import get_vertex_ai_credentials 

def generate_image_from_text(prompt, aspect_ratio="1:1", number_of_images=1):
    """
    Sinh ảnh sử dụng Gemini 3.0 Image Preview (Google GenAI SDK)
    Thay thế cho Imagen 4.0 cũ.
    """
    try:
        # 1. Lấy Credentials từ hàm chung
        credentials = get_vertex_ai_credentials()
        project_id = os.getenv("PROJECT_ID")
        
        # Lưu ý: Image Generation thường yêu cầu us-central1
        location = "global"  # Hoặc "us-central1"

        if not credentials or not project_id:
            print("❌ Lỗi: Thiếu Credentials hoặc Project ID")
            return None

        # 2. Khởi tạo Client (SDK Mới)
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            credentials=credentials
        )

        # 3. Cấu hình Model & Tham số
        # Model ID theo yêu cầu: gemini-3-pro-image-preview
        model_name = "gemini-3-pro-image-preview" 

        # print(f"🎨 Đang sinh ảnh với model {model_name} (Ratio: {aspect_ratio})...")
        
        # 4. Gọi API sinh ảnh (Dùng generate_content với image_config)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"], # Buộc trả về ảnh (tuỳ chọn)
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    # image_size="4K" # Có thể bật nếu muốn ảnh chất lượng cao
                ),
            )
        )

        # 5. Xử lý kết quả trả về
        # Duyệt qua các parts để tìm ảnh (Inline Data)
        if response.parts:
            for part in response.parts:
                if part.inline_data and part.inline_data.data:
                    # print("✅ Sinh ảnh thành công!")
                    return part.inline_data.data # Trả về bytes của ảnh đầu tiên tìm thấy
        
        print("❌ API không trả về dữ liệu ảnh (Có thể do Safety Filter).")
        return None
            
    except Exception as e:
        print(f"❌ Lỗi ngoại lệ khi sinh ảnh: {str(e)}")
        return None


def get_image_size_for_aspect_ratio(aspect_ratio, base_width_inches=3.0):
    """
    Tính toán kích thước ảnh (width, height) để hiển thị trong Word.
    Giữ nguyên logic cũ.
    """
    try:
        w, h = map(float, aspect_ratio.split(":"))
        ratio = h / w
        
        width = base_width_inches
        height = base_width_inches * ratio
        
        return width, height
    except:
        return base_width_inches, base_width_inches