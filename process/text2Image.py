import os
import hashlib
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from api.callAPI import get_vertex_ai_credentials
import time
from typing import Optional
import traceback
import re
from io import BytesIO
from PIL import Image
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
_MODEL_NAME = os.getenv("IMAGEN_MODEL")
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
MAX_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY_SECONDS", "2"))
GENERATION_TIMEOUT = int(os.getenv("IMAGE_GENERATION_TIMEOUT", "90"))

print(f"⚙️  Config: MAX_RETRIES={MAX_RETRIES}, RETRY_DELAY={RETRY_DELAY}s, TIMEOUT={GENERATION_TIMEOUT}s")

def _key(prompt: str) -> str:
    """Tạo key cho cache"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

def _optimize_prompt(prompt: str) -> str:
    """
    Tối ưu prompt để ngắn gọn nhưng vẫn đủ ý
    Imagen 4 hoạt động tốt với prompt ngắn, cụ thể
    """
    prompt = prompt.strip()
    
    # 🔥 BƯỚC 1: Rút gọn prompt dài
    # Loại bỏ các từ thừa, chỉ giữ keywords quan trọng
    prompt = re.sub(r'\b(một|các|những|này|kia|đó)\b', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r'\s+', ' ', prompt).strip()
    
    # 🔥 BƯỚC 2: Chuyển sang English (Imagen 4 hoạt động tốt hơn với tiếng Anh)
    # Tạo mapping keywords tiếng Việt -> tiếng Anh
    vn_to_en = {
        'sơ đồ': 'diagram',
        'biểu đồ': 'chart',
        'hình vẽ': 'illustration',
        'hình ảnh': 'image',
        'máy tính': 'computer',
        'mạch điện': 'circuit',
        'công thức': 'formula',
        'bảng': 'table',
        'đồ thị': 'graph',
        'minh họa': 'illustration',
        'thiết kế': 'design',
        'giao diện': 'interface',
        'logo': 'logo',
        'màu sắc': 'colors',
        'hình chữ nhật': 'rectangle',
        'hình tròn': 'circle',
        'mũi tên': 'arrow',
        'kết nối': 'connection',
        'luồng': 'flow',
        'quy trình': 'process',
    }
    
    # Replace keywords
    for vn, en in vn_to_en.items():
        prompt = prompt.replace(vn, en)
    
    # 🔥 BƯỚC 3: Thêm prefix cho educational content
    if not any(word in prompt.lower() for word in ['diagram', 'chart', 'illustration', 'simple']):
        prompt = f"Simple educational {prompt}"
    
    # 🔥 BƯỚC 4: Giới hạn độ dài (Imagen 4 optimal: 50-80 chars)
    if len(prompt) > 100:
        # Lấy các từ khóa quan trọng nhất
        words = prompt.split()
        important_words = [w for w in words[:15]]  # Chỉ lấy 15 từ đầu
        prompt = ' '.join(important_words)
    
    return prompt.strip()

def generate_image_from_text(prompt: str, max_retries: int = None) -> Optional[bytes]:
    """
    Sinh ảnh từ prompt với kích thước tối ưu
    """
    if max_retries is None:
        max_retries = MAX_RETRIES
    
    print(f"\n{'='*70}")
    print(f"🎨 GENERATE IMAGE REQUEST")
    print(f"{'='*70}")
    print(f"📝 Original prompt: {prompt[:80]}...")
    
    # Check cache
    k = _key(prompt)
    if k in _IMAGE_CACHE:
        print(f"✅ Cache HIT")
        print(f"{'='*70}\n")
        return _IMAGE_CACHE[k]
    
    print(f"❌ Cache MISS - generating new image")
    
    # Optimize prompt
    optimized_prompt = _optimize_prompt(prompt)
    print(f"🔧 Optimized prompt: {optimized_prompt}")
    print(f"📏 Length: {len(prompt)} → {len(optimized_prompt)} chars")
    
    # Retry logic
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n{'─'*70}")
            print(f"🔄 Attempt {attempt}/{max_retries}")
            print(f"{'─'*70}")
            
            start_time = time.time()
            
            print(f"⏳ Calling Imagen API...")
            
            # 🔥 TỐI ƯU: Dùng aspect_ratio nhỏ hơn để giảm dung lượng
            result = _MODEL.generate_images(
                prompt=optimized_prompt,
                number_of_images=1,
                aspect_ratio="1:1",  # Giữ 1:1 cho educational diagrams
                # 🔥 THÊM OUTPUT FORMAT ĐỂ KIỂM SOÁT DUG LƯỢNG
                # add_watermark=False,  # Bỏ watermark nếu có
            )
            
            generation_time = time.time() - start_time
            print(f"✅ API call completed in {generation_time:.2f}s")
            
            # Check timeout
            if generation_time > GENERATION_TIMEOUT:
                print(f"⏱️ WARNING: Timeout ({generation_time:.1f}s > {GENERATION_TIMEOUT}s)")
                if attempt < max_retries:
                    time.sleep(RETRY_DELAY)
                    continue
            
            # Get images
            if not result or not hasattr(result, 'images') or not result.images:
                raise Exception("API returned empty result")
            
            image = result.images[0]
            
            # Extract bytes
            image_bytes = None
            
            # Try different attributes
            for attr_name in ['_image_bytes', 'image_bytes', '_pil_image']:
                if hasattr(image, attr_name):
                    attr_value = getattr(image, attr_name)
                    
                    if attr_name == '_pil_image' and attr_value:
                        
                        
                        buffer = BytesIO()
                        
                        # Resize nếu quá lớn
                        if attr_value.size[0] > 1024 or attr_value.size[1] > 1024:
                            attr_value = attr_value.resize((1024, 1024), Image.LANCZOS)
                        
                        # Save với optimize và quality thấp hơn
                        attr_value.save(
                            buffer, 
                            format='PNG',
                            optimize=True,  # Tối ưu dung lượng
                            # quality=85  # Không dùng cho PNG
                        )
                        image_bytes = buffer.getvalue()
                        print(f"   → Converted & optimized PIL to bytes: {len(image_bytes)} bytes")
                        break
                    
                    elif isinstance(attr_value, bytes) and len(attr_value) > 0:
                        # 🔥 TỐI ƯU: Nén ảnh bytes nếu quá lớn
                        if len(attr_value) > 500_000:  # Lớn hơn 500KB
                            print(f"   → Image too large ({len(attr_value)} bytes), compressing...")
                            
                            # Load từ bytes
                            img = Image.open(BytesIO(attr_value))
                            
                            # Resize
                            if img.size[0] > 1024 or img.size[1] > 1024:
                                img = img.resize((1024, 1024), Image.LANCZOS)
                            
                            # Re-save với nén
                            buffer = BytesIO()
                            img.save(buffer, format='PNG', optimize=True)
                            image_bytes = buffer.getvalue()
                            
                            print(f"   → Compressed: {len(attr_value)} → {len(image_bytes)} bytes")
                        else:
                            image_bytes = attr_value
                            print(f"   → Got bytes directly: {len(image_bytes)} bytes")
                        break
            
            if not image_bytes:
                raise Exception("Cannot extract image bytes")
            
            # Validate
            if len(image_bytes) < 100:
                raise Exception(f"Image too small: {len(image_bytes)} bytes")
            
            # Cache
            _IMAGE_CACHE[k] = image_bytes
            
            # Stats
            size_kb = len(image_bytes) / 1024
            print(f"\n✅ SUCCESS!")
            print(f"   Size: {len(image_bytes)} bytes ({size_kb:.1f} KB)")
            print(f"   Time: {generation_time:.2f}s")
            print(f"{'='*70}\n")
            
            return image_bytes
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ ERROR on attempt {attempt}:")
            print(f"   {type(e).__name__}: {error_msg}")
            
            if attempt == 1:
                print(f"\n   Full traceback:")
                print(traceback.format_exc())
            
            # Handle specific errors
            if "empty" in error_msg.lower():
                if attempt < max_retries:
                    # Try even simpler prompt
                    optimized_prompt = "simple diagram"
                    print(f"   🔧 Trying ultra-simple prompt: {optimized_prompt}")
                    time.sleep(RETRY_DELAY)
                    continue
            
            elif "safety" in error_msg.lower():
                if attempt < max_retries:
                    optimized_prompt = "educational geometric shapes"
                    print(f"   🔧 Trying safe prompt: {optimized_prompt}")
                    time.sleep(RETRY_DELAY)
                    continue
            
            elif any(word in error_msg.lower() for word in ["quota", "rate", "limit"]):
                if attempt < max_retries:
                    wait_time = RETRY_DELAY * attempt * 2  # Tăng dần
                    print(f"   ⏰ Rate limit - waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            
            # Max retries reached
            if attempt >= max_retries:
                print(f"   💔 Failed after {max_retries} attempts")
                print(f"{'='*70}\n")
                return None
            
            print(f"   🔄 Retrying in {RETRY_DELAY}s...")
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