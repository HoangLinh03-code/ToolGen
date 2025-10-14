import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from api.callAPI import VertexClient

@dataclass
class QuestionValidation:
    """Class lưu kết quả kiểm tra một câu hỏi"""
    question_num: int
    has_title: bool = False
    has_content: bool = False
    has_image: bool = False
    answer_count: int = 0
    has_solution_header: bool = False
    has_correct_answer: bool = False
    has_separator: bool = False
    has_explanation: bool = False
    explanation_length: int = 0  # Số dòng giải thích tổng hoặc của block ngắn nhất

    @property
    def is_valid(self) -> bool:
        """Kiểm tra câu hỏi có hợp lệ không"""
        # Yêu cầu cơ bản cho mọi loại câu hỏi
        base_requirements = (
            self.has_title and
            self.has_content and
            self.answer_count == 4 and
            self.has_solution_header and
            self.has_correct_answer and
            self.has_separator and
            self.has_explanation
        )
        # Yêu cầu về độ dài giải thích sẽ được kiểm tra trong hàm validate
        return base_requirements

    @property
    def missing_parts(self) -> List[str]:
        """Liệt kê các phần bị thiếu"""
        missing = []
        if not self.has_title:
            missing.append("Tiêu đề câu hỏi (VD: **Câu X:**)")
        if not self.has_content:
            missing.append("Nội dung câu hỏi")
        if self.answer_count < 4:
            missing.append(f"Không đủ 4 đáp án (hiện có {self.answer_count})")
        if not self.has_solution_header:
            missing.append("Tiêu đề 'Lời giải:'")
        if not self.has_correct_answer:
            missing.append("Mã đáp án đúng (VD: 2 hoặc 1010)")
        if not self.has_separator:
            missing.append("Dấu phân cách ####")
        if not self.has_explanation:
            missing.append("Phần giải thích chi tiết")
        # Lỗi về độ dài sẽ được thêm vào trong hàm validate
        return missing


class QuestionValidator:
    """Class kiểm tra và bổ sung câu hỏi"""

    def __init__(self, question_type: str = "tracngem"):
        """
        Args:
            question_type: "tracnghiem" hoặc "dungsai"
        """
        self.question_type = question_type
        self.required_count = 80 if question_type == "tracnghiem" else 40

    def parse_questions(self, text: str) -> Dict[int, str]:
        """
        Tách text thành từng câu hỏi riêng biệt một cách chính xác hơn.
        """
        questions = {}
        # Pattern này tìm kiếm "**Câu X:**" và bao gồm tất cả nội dung cho đến khi gặp "**Câu Y:**" tiếp theo hoặc cuối chuỗi
        pattern = re.compile(r'(\*\*Câu\s+\d+[:.]?\*\*.*?(?=\*\*Câu\s+\d+[:.]?\*\*|\Z))', re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)

        for match in matches:
            num_match = re.search(r'\*\*Câu\s+(\d+)[:.]?\*\*', match, re.IGNORECASE)
            if num_match:
                q_num = int(num_match.group(1))
                questions[q_num] = match.strip()
        return questions

    def validate_single_question(self, question_text: str, question_num: int) -> Tuple[QuestionValidation, bool]:
        """
        Kiểm tra một câu hỏi có đầy đủ thành phần không, trả về cả trạng thái valid.
        """
        validation = QuestionValidation(question_num=question_num)
        lines = question_text.split("\n")
        
        in_explanation_section = False
        explanation_content = []

        # Vòng lặp đầu tiên: Thu thập thông tin cơ bản
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            if re.match(r'^\*?\*?Câu\s+\d+[:.]?\*?\*?', line, re.IGNORECASE):
                validation.has_title = True
            elif (not re.match(r'^[A-Da-d][.)]', line_stripped) and
                  not re.match(r'^\*?\*?Lời giải[:.]?\*?\*?', line, re.IGNORECASE) and
                  not re.match(r'^[1-4]$', line_stripped) and
                  not re.match(r'^[01]{4}$', line_stripped) and
                  line_stripped != "####" and not in_explanation_section and validation.has_title):
                validation.has_content = True
            if re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE):
                validation.has_image = True
            if re.match(r'^[A-Da-d][.)]', line_stripped):
                validation.answer_count += 1
            if re.match(r'^\*?\*?Lời giải[:.]?\*?\*?', line, re.IGNORECASE):
                validation.has_solution_header = True
            if (re.match(r'^[1-4]$', line_stripped) or re.match(r'^[01]{4}$', line_stripped)) and validation.has_solution_header:
                validation.has_correct_answer = True
            if line_stripped == "####":
                validation.has_separator = True
                in_explanation_section = True
                continue # Bỏ qua dòng #### để bắt đầu thu thập giải thích
            
            if in_explanation_section:
                explanation_content.append(line_stripped)

        validation.has_explanation = bool(explanation_content)

        # Vòng lặp thứ hai: Phân tích chuyên sâu phần giải thích
        is_valid = validation.is_valid
        
        if is_valid: # Chỉ kiểm tra độ dài nếu các phần cơ bản đã đủ
            if self.question_type == "tracnghiem":
                explanation_len = len([line for line in explanation_content if line])
                validation.explanation_length = explanation_len
                if explanation_len < 3:
                    is_valid = False
                    validation.missing_parts.append(f"Giải thích quá ngắn ({explanation_len} dòng, yêu cầu >= 3)")

            elif self.question_type == "dungsai":
                # Tách giải thích thành các khối cho từng phát biểu
                explanation_blocks = []
                current_block = []
                for line in explanation_content:
                    if re.match(r'^\s*-\s*\[', line) and current_block:
                        explanation_blocks.append(current_block)
                        current_block = [line]
                    else:
                        current_block.append(line)
                if current_block:
                    explanation_blocks.append(current_block)

                if len(explanation_blocks) < 4:
                    is_valid = False
                    validation.missing_parts.append(f"Không đủ 4 khối giải thích cho 4 phát biểu (hiện có {len(explanation_blocks)})")
                else:
                    min_len = float('inf')
                    all_blocks_valid = True
                    for i, block in enumerate(explanation_blocks):
                        block_len = len([line for line in block if line])
                        if block_len < 3:
                            all_blocks_valid = False
                            is_valid = False
                            validation.missing_parts.append(f"Khối giải thích {i+1} quá ngắn ({block_len} dòng, yêu cầu >= 3)")
                        min_len = min(min_len, block_len)
                    validation.explanation_length = min_len

        return validation, is_valid

    def validate_all_questions(self, text: str) -> Tuple[List[QuestionValidation], List[int]]:
        """
        Kiểm tra toàn bộ đề bài
        """
        print(f"\n{'='*70}")
        print(f"🔍 BẮT ĐẦU KIỂM TRA TOÀN BỘ ĐỀ BÀI ({self.question_type})")
        print(f"{'='*70}\n")
        
        questions = self.parse_questions(text)
        validations = []
        invalid_questions_details = []
        
        print(f"   - Đã phân tích được: {len(questions)} câu.")
        print(f"   - Yêu cầu số lượng: {self.required_count} câu.\n")
        
        for qnum, qtext in sorted(questions.items()):
            validation_obj, is_valid_flag = self.validate_single_question(qtext, qnum)
            validations.append(validation_obj)
            if not is_valid_flag:
                invalid_questions_details.append(validation_obj)
        
        existing_nums = set(questions.keys())
        required_nums = set(range(1, self.required_count + 1))
        missing_nums = sorted(list(required_nums - existing_nums))
        
        print("--- KẾT QUẢ SƠ BỘ ---")
        print(f"   ✅ Câu hỏi hợp lệ: {len(validations) - len(invalid_questions_details)}")
        print(f"   ⚠️  Câu hỏi thiếu thành phần: {len(invalid_questions_details)}")
        if invalid_questions_details:
            for v in invalid_questions_details[:5]: # Chỉ hiển thị 5 lỗi đầu
                print(f"      - Câu {v.question_num}: Thiếu {', '.join(v.missing_parts)}")
        print(f"   ❌ Câu hỏi thiếu hoàn toàn: {len(missing_nums)}")
        if missing_nums:
            print(f"      - Các câu số: {str(missing_nums[:10])}{'...' if len(missing_nums) > 10 else ''}")
        print("-" * 23 + "\n")
        
        # Trả về list validations chứa tất cả các object, dù valid hay không
        return [v for v in validations if not self.validate_single_question(self.parse_questions(text).get(v.question_num, ""), v.question_num)[1]], missing_nums

    def generate_fix_prompt(self, validations: List[QuestionValidation],
                            missing_nums: List[int],
                            original_prompt: str,
                            full_text: str) -> str:
        """
        Tạo ra một prompt có cấu trúc chặt chẽ để AI sửa lỗi và sinh bù câu hỏi.
        Sử dụng các thẻ XML-like để Gemini 2.5 Pro hiểu rõ từng nhiệm vụ.
        """
        questions_to_fix = [v for v, is_valid in [self.validate_single_question(self.parse_questions(full_text).get(v.question_num, ""), v.question_num) for v in validations] if not is_valid]

        if not questions_to_fix and not missing_nums:
            return None  # Không có gì cần sửa

        prompt_parts = [
            "<master_request>",
            "    <role>Bạn là một trợ lý AI chuyên sửa lỗi và hoàn thiện nội dung. Hãy thực hiện các nhiệm vụ sau một cách chính xác và chỉ trả về nội dung được yêu cầu.</role>",
            ""
        ]

        # --- PHẦN 1: SỬA CÁC CÂU BỊ LỖI ---
        if questions_to_fix:
            prompt_parts.append("    <correction_tasks>")
            prompt_parts.append("        <instruction>Hãy sửa lại HOÀN CHỈNH các câu hỏi dưới đây. Chỉ trả về phiên bản đã được sửa đúng của những câu này.</instruction>")
            
            parsed_questions = self.parse_questions(full_text)
            for v in questions_to_fix:
                if v.question_num in parsed_questions:
                    faulty_text = parsed_questions[v.question_num]
                    
                    prompt_parts.append(f"        <task id='fix_{v.question_num}'>")
                    prompt_parts.append(f"            <question_number>{v.question_num}</question_number>")
                    prompt_parts.append(f"            <faulty_content><![CDATA[\n{faulty_text}\n]]></faulty_content>")
                    prompt_parts.append(f"            <detected_errors>")
                    # Lấy lại missing_parts mới nhất
                    current_missing_parts = self.validate_single_question(faulty_text, v.question_num)[0].missing_parts
                    for error in current_missing_parts:
                        prompt_parts.append(f"                <error>{error}</error>")
                    prompt_parts.append(f"            </detected_errors>")
                    prompt_parts.append(f"            <request>Dựa vào nội dung gốc, hãy viết lại toàn bộ câu {v.question_num} để khắc phục các lỗi trên và đảm bảo tuân thủ 100% format từ prompt gốc.</request>")
                    prompt_parts.append(f"        </task>")

            prompt_parts.append("    </correction_tasks>")
            prompt_parts.append("")

        # --- PHẦN 2: SINH MỚI CÁC CÂU BỊ THIẾU ---
        if missing_nums:
            prompt_parts.append("    <generation_tasks>")
            prompt_parts.append("        <instruction>Hãy sinh mới HOÀN TOÀN các câu hỏi dưới đây. Nội dung phải khác biệt với các câu đã có và tuân thủ format gốc.</instruction>")
            
            missing_nums_str = ', '.join(map(str, missing_nums))
            prompt_parts.append(f"        <task id='generate_missing'>")
            prompt_parts.append(f"            <question_numbers_to_generate>{missing_nums_str}</question_numbers_to_generate>")
            prompt_parts.append(f"            <request>Sinh mới các câu hỏi có số thứ tự trên, đảm bảo mỗi câu đều đầy đủ, đúng format và bám sát chủ đề từ prompt gốc.</request>")
            prompt_parts.append(f"        </task>")
            
            prompt_parts.append("    </generation_tasks>")
            prompt_parts.append("")

        # --- PHẦN 3: CUNG CẤP NGỮ CẢNH VÀ FORMAT GỐC ---
        prompt_parts.append("    <master_prompt_reference>")
        prompt_parts.append("        <instruction>Đây là một phần của prompt gốc để bạn tham khảo về format và các quy tắc chính.</instruction>")
        prompt_parts.append(f"        <content><![CDATA[\n{original_prompt[:2500]}\n]]></content>")
        prompt_parts.append("    </master_prompt_reference>")
        prompt_parts.append("")

        # --- PHẦN 4: YÊU CẦU ĐẦU RA CUỐI CÙNG ---
        prompt_parts.append("    <final_output_instruction>")
        prompt_parts.append("        Mệnh lệnh: Chỉ trả về nội dung của các câu hỏi đã được sửa và các câu hỏi được sinh mới. KHÔNG thêm bất kỳ lời giải thích, lời chào, hay các nội dung khác ngoài yêu cầu.")
        prompt_parts.append("    </final_output_instruction>")
        
        prompt_parts.append("</master_request>")

        return "\n".join(prompt_parts)
    
    
    def fix_questions_with_ai(self, text: str, original_prompt: str,
                             client: VertexClient, max_attempts: int = 2) -> str:
        """
        Tự động kiểm tra và bổ sung câu hỏi bằng AI
        """
        current_text = text
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"\n{'='*70}")
            print(f"🔄 VÒNG LẶP KIỂM TRA & SỬA LỖI LẦN {attempt}/{max_attempts}")
            print(f"{'='*70}")
            
            # Lấy danh sách các câu không hợp lệ và các câu thiếu
            invalid_validations, missing_nums = self.validate_all_questions(current_text)
            
            if not invalid_validations and not missing_nums:
                print("\n🎉 TUYỆT VỜI! Toàn bộ câu hỏi đã hợp lệ và đầy đủ. Không cần sửa chữa.\n")
                return current_text
            
            fix_prompt = self.generate_fix_prompt(
                invalid_validations, missing_nums, original_prompt, current_text
            )
            
            if not fix_prompt:
                 break

            print(f"   - Tạo prompt sửa lỗi và gửi đến AI...")
            try:
                fixed_content_response = client.send_data_to_check(prompt=fix_prompt, temperature=0.5)
                print(f"   - Đã nhận phản hồi sửa lỗi từ AI.")

                # Lấy tất cả các câu HỢP LỆ từ văn bản cũ
                parsed_old_text = self.parse_questions(current_text)
                valid_questions_map = {}
                for q_num, q_text in parsed_old_text.items():
                    _, is_valid = self.validate_single_question(q_text, q_num)
                    if is_valid:
                        valid_questions_map[q_num] = q_text

                newly_fixed_questions_map = self.parse_questions(fixed_content_response)
                
                final_questions_map = {**valid_questions_map, **newly_fixed_questions_map}
                
                final_text_parts = []
                for i in range(1, self.required_count + 1):
                    if i in final_questions_map:
                        final_text_parts.append(final_questions_map[i])
                
                current_text = "\n\n".join(final_text_parts)
                print(f"   - Đã cập nhật lại toàn bộ văn bản.")

            except Exception as e:
                print(f"   - ❌ Lỗi khi gọi API sửa lỗi: {e}\n")
                break
        
        print(f"\n--- KẾT THÚC QUÁ TRÌNH TỰ ĐỘNG SỬA LỖI ---\n")
        return current_text


# ==================== FUNCTIONS ĐỂ TÍCH HỢP VÀO response2docx.py ====================

def validate_and_fix_response(AIresponse: str, original_prompt: str,
                              client: VertexClient, question_type: str = "tracnghiem") -> str:
    """
    Hàm tiện ích để tích hợp vào response2docx_improved()
    """
    validator = QuestionValidator(question_type=question_type)
    fixed_text = validator.fix_questions_with_ai(
        AIresponse, 
        original_prompt, 
        client,
        max_attempts=2 
    )
    return fixed_text

def validate_question_topic(question_text: str, allowed_topics: set, 
                           allowed_keywords: set) -> bool:
    """
    Kiểm tra câu hỏi có liên quan đến allowed topics không
    """
    # Lấy tất cả từ khóa từ câu hỏi
    question_words = set(re.findall(r'\b\w+\b', question_text.lower()))
    
    # Kiểm tra overlap với allowed topics/keywords
    topic_overlap = question_words & {t.lower() for t in allowed_topics}
    keyword_overlap = question_words & {k.lower() for k in allowed_keywords}
    
    return bool(topic_overlap or keyword_overlap)


def detect_question_level(question_text: str) -> str:
    """
    Phát hiện mức độ câu hỏi dựa trên từ khóa
    """
    recognition_keywords = ['là gì', 'định nghĩa', 'khái niệm', 'gọi là', 'được hiểu là']
    comprehension_keywords = ['tại sao', 'vì sao', 'so sánh', 'phân biệt', 'giải thích']
    application_keywords = ['áp dụng', 'tình huống', 'ví dụ', 'trường hợp', 'nếu', 'khi']
    advanced_keywords = ['phân tích', 'đánh giá', 'sáng tạo', 'thiết kế', 'tối ưu', 'kết hợp']
    
    text_lower = question_text.lower()
    
    if any(kw in text_lower for kw in advanced_keywords):
        return "vận dụng_cao"
    elif any(kw in text_lower for kw in application_keywords):
        return "vận dụng"
    elif any(kw in text_lower for kw in comprehension_keywords):
        return "thông hiểu"
    else:
        return "nhận biết"