import os
import hashlib
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials

# Init Vertex once
_credentials = get_vertex_ai_credentials()
vertexai.init(
    project=os.getenv("PROJECT_ID"),
    location=os.getenv("LOCATION", "us-central1"),
    credentials=_credentials
)

# Singleton model + in-memory cache

_MODEL = ImageGenerationModel.from_pretrained("imagen-4.0-generate-001")

_IMAGE_CACHE = {}

def _key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

def generate_image_from_text(prompt: str) -> bytes:
    """Sinh ảnh từ prompt với cache theo prompt."""
    k = _key(prompt)
    if k in _IMAGE_CACHE:
        return _IMAGE_CACHE[k]
    result = _MODEL.generate_images(
        prompt=prompt,
        number_of_images=1,
        aspect_ratio="1:1"
    )
    image_bytes = result.images[0]._image_bytes  # hoặc .image_bytes tùy SDK
    _IMAGE_CACHE[k] = image_bytes
    return image_bytes

class ImageGenerationTracker:
    """Class theo dõi việc sinh ảnh"""
    
    def __init__(self, target_count: int):
        self.target_count = target_count
        self.generated_count = 0
        self.placeholder_count = 0
        self.failed_count = 0
    
    def should_generate(self, question_num: int, total_questions: int) -> bool:
        """
        Quyết định có nên sinh ảnh cho câu này không
        
        Logic: Phân bố đều ảnh trong toàn bộ đề
        """
        if self.generated_count >= self.target_count:
            return False
        
        # Tính khoảng cách giữa các ảnh
        interval = max(1, total_questions // max(1, self.target_count))
        
        # Sinh ảnh ở các câu cách đều nhau
        return (question_num - 1) % interval == 0
    
    def record_success(self):
        """Ghi nhận sinh ảnh thành công"""
        self.generated_count += 1
    
    def record_placeholder(self):
        """Ghi nhận thêm placeholder"""
        self.placeholder_count += 1
    
    def record_failed(self):
        """Ghi nhận sinh ảnh thất bại"""
        self.failed_count += 1
    
    def get_summary(self) -> str:
        """Lấy thông tin tổng kết"""
        total_images = self.generated_count + self.placeholder_count
        return f"""
Ảnh sinh thành công: {self.generated_count}
Ảnh placeholder: {self.placeholder_count}
Tổng số ảnh: {total_images}/{self.target_count}
Lỗi sinh ảnh: {self.failed_count}
"""


def calculate_optimal_image_count(required_count: int, target_percentage: float = 0.2) -> int:
    """
    Tính số lượng ảnh tối ưu (giảm từ 20% xuống 15%)
    
    Args:
        required_count: Tổng số câu hỏi
        target_percentage: Tỷ lệ mục tiêu (mặc định 15%)
    
    Returns:
        Số lượng ảnh cần sinh
    """
    return int(required_count * target_percentage)

def should_generate_image(question_num: int, total_questions: int, 
                         images_generated: int, target_image_count: int) -> bool:
    """
    Quyết định có nên sinh ảnh cho câu này không
    
    Logic: Phân bố đều ảnh trong toàn bộ đề
    """
    if images_generated >= target_image_count:
        return False
    
    # Tính khoảng cách giữa các ảnh
    interval = total_questions // target_image_count
    
    # Sinh ảnh ở các câu cách đều nhau
    return (question_num - 1) % interval == 0
