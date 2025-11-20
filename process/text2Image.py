import os
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials

def generate_image_from_text(prompt):
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
        number_of_images=1,     # Số lượng ảnh (tối đa 4)
        aspect_ratio="1:1"      # Tỉ lệ ảnh, ví dụ 1:1, 16:9, 9:16
        
    )
    # Lấy ảnh đầu tiên
    image_bytes = result.images[0]._image_bytes  # hoặc result.images[0].image_bytes nếu phiên bản API hỗ trợ

    return image_bytes