import os
import hashlib
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials
import time
from typing import Optional
import traceback

# Init Vertex once
print("🔧 Initializing Vertex AI...")
_credentials = get_vertex_ai_credentials()

if _credentials is None:
    print("❌ CRITICAL: Không thể load credentials!")
    raise Exception("Missing credentials")

vertexai.init(
    project=os.getenv("PROJECT_ID"),
    location=os.getenv("LOCATION", "us-central1"),
    credentials=_credentials
)
print("✅ Vertex AI initialized")

# Sử dụng model nhanh và ổn định nhất
_MODEL_NAME = os.getenv("IMAGEN_MODEL", "imagen-3.0-fast-generate-001")
print(f"🎨 Loading model: {_MODEL_NAME}")

try:
    _MODEL = ImageGenerationModel.from_pretrained(_MODEL_NAME)
    print(f"✅ Model loaded: {_MODEL_NAME}")
except Exception as e:
    print(f"❌ CRITICAL: Không thể load model {_MODEL_NAME}: {e}")
    print(f"Traceback: {traceback.format_exc()}")
    raise

# Cache ảnh đã sinh
_IMAGE_CACHE = {}

# Cấu hình retry
MAX_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "5"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY_SECONDS", "3"))
GENERATION_TIMEOUT = int(os.getenv("IMAGE_GENERATION_TIMEOUT", "90"))

print(f"⚙️  Config: MAX_RETRIES={MAX_RETRIES}, RETRY_DELAY={RETRY_DELAY}s, TIMEOUT={GENERATION_TIMEOUT}s")

def _key(prompt: str) -> str:
    """Tạo key cho cache"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

def _optimize_prompt(prompt: str) -> str:
    """
    Tối ưu prompt để tăng tỷ lệ sinh ảnh thành công
    """
    # Làm sạch prompt
    prompt = prompt.strip()
    
    # Thêm prefix cho educational content
    if not prompt.lower().startswith(("educational", "simple", "diagram", "chart", "illustration")):
        optimized = f"Simple educational illustration: {prompt}"
    else:
        optimized = prompt
    
    # Giới hạn độ dài (Imagen works better with concise prompts)
    if len(optimized) > 250:
        optimized = optimized[:247] + "..."
    
    return optimized

def generate_image_from_text(prompt: str, max_retries: int = None) -> Optional[bytes]:
    """
    Sinh ảnh từ prompt với cache, retry và timeout
    
    Args:
        prompt: Mô tả ảnh cần sinh
        max_retries: Số lần retry tối đa (None = dùng global MAX_RETRIES)
        
    Returns:
        bytes: Image data hoặc None nếu thất bại
    """
    if max_retries is None:
        max_retries = MAX_RETRIES
    
    print(f"\n{'='*70}")
    print(f"🎨 GENERATE IMAGE REQUEST")
    print(f"{'='*70}")
    print(f"📝 Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    
    # Check cache trước
    k = _key(prompt)
    if k in _IMAGE_CACHE:
        print(f"✅ Cache HIT - trả về ảnh từ cache")
        print(f"{'='*70}\n")
        return _IMAGE_CACHE[k]
    
    print(f"❌ Cache MISS - cần sinh ảnh mới")
    
    # Tối ưu prompt
    optimized_prompt = _optimize_prompt(prompt)
    print(f"🔧 Optimized: {optimized_prompt[:100]}{'...' if len(optimized_prompt) > 100 else ''}")
    
    # Retry logic
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n{'─'*70}")
            print(f"🔄 Attempt {attempt}/{max_retries}")
            print(f"{'─'*70}")
            
            start_time = time.time()
            
            print(f"⏳ Calling Imagen API...")
            result = _MODEL.generate_images(
                prompt=optimized_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )
            
            generation_time = time.time() - start_time
            print(f"✅ API call completed in {generation_time:.2f}s")
            
            # Kiểm tra timeout
            if generation_time > GENERATION_TIMEOUT:
                print(f"⏱️  WARNING: Timeout ({generation_time:.1f}s > {GENERATION_TIMEOUT}s)")
                if attempt < max_retries:
                    print(f"🔄 Retrying after {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    print(f"❌ Max retries reached, giving up")
                    return None
            
            # Lấy ảnh
            if not result or not hasattr(result, 'images') or not result.images or len(result.images) == 0:
                raise Exception("API returned empty result")
            
            image = result.images[0]
            
            # Kiểm tra xem có _image_bytes không
            if not hasattr(image, '_image_bytes'):
                # Thử các thuộc tính khác
                if hasattr(image, 'image_bytes'):
                    image_bytes = image.image_bytes
                elif hasattr(image, '_pil_image'):
                    from io import BytesIO
                    buffer = BytesIO()
                    image._pil_image.save(buffer, format='PNG')
                    image_bytes = buffer.getvalue()
                else:
                    raise Exception(f"Cannot extract image bytes. Available attributes: {dir(image)}")
            else:
                image_bytes = image._image_bytes
            
            if not image_bytes or len(image_bytes) == 0:
                raise Exception("Image bytes is empty")
            
            # Cache lại
            _IMAGE_CACHE[k] = image_bytes
            
            print(f"✅ SUCCESS - Generated {len(image_bytes)} bytes in {generation_time:.2f}s")
            print(f"{'='*70}\n")
            
            return image_bytes
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ ERROR on attempt {attempt}:")
            print(f"   Type: {type(e).__name__}")
            print(f"   Message: {error_msg}")
            
            # Debug: Print full traceback cho attempt đầu tiên
            if attempt == 1:
                print(f"   Traceback:\n{traceback.format_exc()}")
            
            # Phân tích lỗi
            if "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                print(f"⚠️  Safety filter blocked this image")
                if attempt < max_retries:
                    optimized_prompt = f"Simple diagram: {prompt[:80]}"
                    print(f"🔧 Trying with simpler prompt...")
                    time.sleep(RETRY_DELAY)
                    continue
            
            elif "quota" in error_msg.lower() or "rate" in error_msg.lower() or "limit" in error_msg.lower():
                print(f"⏳ Rate limit or quota exceeded")
                if attempt < max_retries:
                    wait_time = RETRY_DELAY * attempt  # Tăng dần thời gian chờ
                    print(f"⏰ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
            
            elif "timeout" in error_msg.lower():
                print(f"⏱️  API timeout")
                if attempt < max_retries:
                    time.sleep(RETRY_DELAY)
                    continue
            
            elif "permission" in error_msg.lower() or "auth" in error_msg.lower():
                print(f"🔐 Authentication/Permission error - cannot retry")
                return None
            
            # Lỗi khác
            if attempt >= max_retries:
                print(f"💔 Failed after {max_retries} attempts")
                print(f"{'='*70}\n")
                return None
            
            # Retry
            print(f"🔄 Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
    
    print(f"❌ FAILED - All retries exhausted")
    print(f"{'='*70}\n")
    return None


class ImageGenerationTracker:
    """Class theo dõi việc sinh ảnh"""
    
    def __init__(self, target_count: int):
        self.target_count = target_count
        self.generated_count = 0
        self.placeholder_count = 0
        self.failed_count = 0
        self.cache_hits = 0
        self.total_generation_time = 0.0
        self.attempts_log = []  # Log mọi lần thử
        
        print(f"\n📊 ImageGenerationTracker initialized: target={target_count}")
    
    def should_generate(self, question_num: int, total_questions: int) -> bool:
        """
        Quyết định có nên sinh ảnh cho câu này không
        """
        # LUÔN sinh nếu chưa đủ số lượng target
        should = self.generated_count < self.target_count
        
        print(f"   🤔 should_generate(q={question_num}, total={total_questions})")
        print(f"      Current: {self.generated_count}/{self.target_count}")
        print(f"      Decision: {'✅ YES' if should else '❌ NO (enough images)'}")
        
        return should
    
    def record_success(self, generation_time: float = 0.0):
        """Ghi nhận sinh ảnh thành công"""
        self.generated_count += 1
        self.total_generation_time += generation_time
        self.attempts_log.append(("success", generation_time))
        print(f"   ✅ Recorded SUCCESS (total: {self.generated_count}/{self.target_count})")
    
    def record_placeholder(self):
        """Ghi nhận thêm placeholder"""
        self.placeholder_count += 1
        self.attempts_log.append(("placeholder", 0))
        print(f"   📝 Recorded PLACEHOLDER (total: {self.placeholder_count})")
    
    def record_failed(self):
        """Ghi nhận sinh ảnh thất bại"""
        self.failed_count += 1
        self.attempts_log.append(("failed", 0))
        print(f"   ❌ Recorded FAILED (total: {self.failed_count})")
    
    def record_cache_hit(self):
        """Ghi nhận sử dụng cache"""
        self.cache_hits += 1
        self.attempts_log.append(("cache", 0))
        print(f"   📦 Recorded CACHE HIT (total: {self.cache_hits})")
    
    def get_summary(self) -> str:
        """Lấy thông tin tổng kết"""
        total_images = self.generated_count + self.placeholder_count
        avg_time = self.total_generation_time / max(1, self.generated_count) if self.generated_count > 0 else 0.0
        
        summary = f"""
📊 THỐNG KÊ SINH ẢNH:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Ảnh sinh thành công: {self.generated_count}/{self.target_count} ({self.generated_count*100//max(1,self.target_count)}%)
📦 Ảnh từ cache: {self.cache_hits}
📝 Ảnh placeholder: {self.placeholder_count}
❌ Lỗi sinh ảnh: {self.failed_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📷 Tổng số ảnh: {total_images}/{self.target_count}
⏱️  Thời gian TB/ảnh: {avg_time:.1f}s
⏱️  Tổng thời gian: {self.total_generation_time:.1f}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Thêm warning nếu có vấn đề
        if self.generated_count == 0 and self.placeholder_count > 0:
            summary += "\n⚠️  WARNING: Không có ảnh nào được sinh thành công!"
            summary += "\n   Kiểm tra: credentials, model name, API quota"
        
        if self.failed_count > self.generated_count:
            summary += f"\n⚠️  WARNING: Tỷ lệ thất bại cao ({self.failed_count} failed vs {self.generated_count} success)"
        
        return summary


def calculate_optimal_image_count(required_count: int, target_percentage: float = 0.2) -> int:
    """Tính số lượng ảnh tối ưu"""
    return max(1, int(required_count * target_percentage))


def clear_cache():
    """Xóa cache ảnh"""
    global _IMAGE_CACHE
    cache_size = len(_IMAGE_CACHE)
    _IMAGE_CACHE.clear()
    print(f"🧹 Đã xóa {cache_size} ảnh từ cache")


def get_cache_stats() -> dict:
    """Lấy thống kê cache"""
    total_size = sum(len(img) for img in _IMAGE_CACHE.values())
    return {
        "cached_images": len(_IMAGE_CACHE),
        "cache_size_mb": total_size / (1024 * 1024),
        "cache_size_bytes": total_size
    }


# Test function để verify setup
def test_image_generation():
    """Test function để kiểm tra xem sinh ảnh có hoạt động không"""
    print("\n" + "="*70)
    print("🧪 TESTING IMAGE GENERATION")
    print("="*70 + "\n")
    
    test_prompt = "Simple diagram showing a circle and a square"
    print(f"Test prompt: {test_prompt}\n")
    
    result = generate_image_from_text(test_prompt, max_retries=2)
    
    if result:
        print(f"\n✅ TEST PASSED - Generated {len(result)} bytes")
        return True
    else:
        print(f"\n❌ TEST FAILED - Could not generate image")
        return False