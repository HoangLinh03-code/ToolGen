import os
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials

def generate_image_from_text(prompt, aspect_ratio="1:1", number_of_images=1):
    try:
        # Khởi tạo Vertex AI với credentials từ .env
        credentials = get_vertex_ai_credentials()
        vertexai.init(
            project=os.getenv("PROJECT_ID"),
            location=os.getenv("LOCATION", "us-central1"),
            credentials=credentials
        )

        # Tải model Imagen
        model = ImageGenerationModel.from_pretrained("imagen-4.0-generate-preview-06-06")

        # Sinh ảnh
        result = model.generate_images(
            prompt=prompt,
            number_of_images=number_of_images,
            aspect_ratio=aspect_ratio
        )
        
        # Lấy ảnh đầu tiên
        if result.images and len(result.images) > 0:
            image_bytes = result.images[0]._image_bytes
            return image_bytes
        else:
            print("❌ Không có ảnh nào được sinh ra")
            return None
            
    except Exception as e:
        print(f"❌ Lỗi khi sinh ảnh: {e}")
        return None


def get_image_size_for_aspect_ratio(aspect_ratio, base_width_inches=3.0):
    try:
        w, h = map(float, aspect_ratio.split(":"))
        ratio = h / w
        
        width = base_width_inches
        height = base_width_inches * ratio
        
        return width, height
    except:
        # Default to square if parsing fails
        return base_width_inches, base_width_inches