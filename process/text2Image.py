# import os
# import vertexai
# from vertexai.preview.vision_models import ImageGenerationModel
# from api.callAPI import get_vertex_ai_credentials
# import io

# def generate_image_from_text(prompt):
#     # Khởi tạo Vertex AI với credentials từ .env
#     credentials = get_vertex_ai_credentials()
#     vertexai.init(
#         project=os.getenv("PROJECT_ID"),
#         location=os.getenv("LOCATION", "us-central1"),
#         credentials=credentials
#     )

#     # Tải model Imagen
#     model = ImageGenerationModel.from_pretrained("imagen-4.0-generate-preview-06-06")

#     # Sinh ảnh
#     result = model.generate_images(
#         prompt=prompt,
#         number_of_images=1,     # Số lượng ảnh (tối đa 4)
#         aspect_ratio="1:1"      # Tỉ lệ ảnh, ví dụ 1:1, 16:9, 9:16
#     )
#     # Lấy ảnh đầu tiên
#     image_bytes = result.images[0]._image_bytes  # hoặc result.images[0].image_bytes nếu phiên bản API hỗ trợ

#     return image_bytes

import os
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import config  # chứa GEMINI_API_KEYS

def generate_image_from_text(prompt, file_path=None):
    """
    Sinh ảnh từ prompt:
    - Ưu tiên dùng Imagen 4.0 (Vertex AI).
    - Nếu lỗi, fallback sang Gemini API (với danh sách nhiều API keys).
    - Trả về image_bytes.
    """

    # --- Cách 1: Vertex AI Imagen ---
    try:
        credentials = get_vertex_ai_credentials()
        vertexai.init(
            project=os.getenv("PROJECT_ID"),
            location=os.getenv("LOCATION", "us-central1"),
            credentials=credentials
        )

        model = ImageGenerationModel.from_pretrained("imagen-4.0-generate-preview-06-06")

        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="1:1"
        )

        image_bytes = result.images[0]._image_bytes
        print("Thành công với Vertex AI (Imagen 4.0)")
        return image_bytes

    except Exception as e:
        print(f"Lỗi Vertex AI: {e}, thử fallback sang Gemini API...")

    # --- Cách 2: Gemini API fallback ---
    if file_path is None:
        print("Gemini API yêu cầu file_path để upload (tham chiếu ảnh).")
        return None

    for api_key in config.GEMINI_API_KEYS:
        try:
            print(f"Thử với Gemini API Key: {api_key}")
            client = genai.Client(api_key=api_key)

            # Upload file (ảnh tham chiếu)
            myfile = client.files.upload(file=file_path)

            prompt1 = "Yêu cầu trả về duy nhất hình ảnh\n" + prompt
            contents = (prompt1, myfile)

            response = client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE']
                )
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image = Image.open(BytesIO(part.inline_data.data))

                    # Convert PIL.Image → image_bytes
                    output_buffer = BytesIO()
                    image.save(output_buffer, format="PNG")
                    image_bytes = output_buffer.getvalue()

                    print("Thành công với Gemini API")
                    return image_bytes

        except Exception as e:
            print(f"API Key lỗi: {api_key}, lỗi: {e}")

    print("Tất cả phương án đều thất bại.")
    return None