import re
from typing import List, Dict, Tuple, Set
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
    explanation_length: int = 0  # Số dòng giải thích
    
    @property
    def is_valid(self) -> bool:
        """Kiểm tra câu hỏi có hợp lệ không"""
        return (
            self.has_title and
            self.has_content and
            self.answer_count == 4 and
            self.has_solution_header and
            self.has_correct_answer and
            self.has_separator and
            self.has_explanation and
            self.explanation_length >= 1  # Ít nhất 3 dòng giải thích
        )
    
    @property
    def missing_parts(self) -> List[str]:
        """Liệt kê các phần bị thiếu"""
        missing = []
        if not self.has_title:
            missing.append("Tiêu đề câu hỏi")
        if not self.has_content:
            missing.append("Nội dung câu hỏi")
        if self.answer_count < 4:
            missing.append(f"Đáp án (chỉ có {self.answer_count}/4)")
        if not self.has_solution_header:
            missing.append("Header 'Lời giải'")
        if not self.has_correct_answer:
            missing.append("Đáp án đúng (1-4 hoặc 1010)")
        if not self.has_separator:
            missing.append("Dấu phân cách ####")
        if not self.has_explanation:
            missing.append("Giải thích")
        elif self.explanation_length < 3:
            missing.append(f"Giải thích quá ngắn ({self.explanation_length} dòng, cần ít nhất 3)")
        return missing

class ValidQuestionStorage:
    """Class lưu trữ các câu hỏi đã hợp lệ để tránh sinh lại"""
    
    def __init__(self):
        self.valid_questions: Dict[int, str] = {}  # {question_num: question_text}
        self.valid_nums: Set[int] = set()
    
    def add_valid_question(self, question_num: int, question_text: str):
        """Thêm câu hỏi hợp lệ vào storage"""
        self.valid_questions[question_num] = question_text
        self.valid_nums.add(question_num)
    
    def get_valid_count(self) -> int:
        """Đếm số câu hợp lệ"""
        return len(self.valid_questions)
    
    def get_missing_nums(self, required_count: int) -> List[int]:
        """Lấy danh sách số câu còn thiếu"""
        required_nums = set(range(1, required_count + 1))
        missing = sorted(required_nums - self.valid_nums)
        return missing
    
    def reconstruct_full_text(self) -> str:
        """Ghép lại text đầy đủ từ các câu hợp lệ"""
        sorted_questions = sorted(self.valid_questions.items())
        return "\n\n".join([text for _, text in sorted_questions])
    
    def has_question(self, question_num: int) -> bool:
        """Kiểm tra câu hỏi đã tồn tại chưa"""
        return question_num in self.valid_nums



class QuestionValidator:
    """Class kiểm tra và bổ sung câu hỏi"""
    
    def __init__(self, question_type: str = "tracnghiem"):
        """
        Args:
            question_type: "tracnghiem" hoặc "dungsai"
        """
        self.question_type = question_type
        self.required_count = 80 if question_type == "tracnghiem" else 40
    
    def parse_questions(self, text: str) -> Dict[int, str]:
        """
        Tách text thành từng câu hỏi riêng biệt
        
        Returns:
            Dict {question_num: question_text}
        """
        questions = {}
        lines = text.split("\n")
        current_question_num = None
        current_question_lines = []
        
        for line in lines:
            # Phát hiện tiêu đề câu hỏi mới
            match = re.match(r'^\*?\*?Câu\s+(\d+)[:\.]?\*?\*?', line, re.IGNORECASE)
            if match:
                # Lưu câu hỏi cũ
                if current_question_num is not None and current_question_lines:
                    questions[current_question_num] = "\n".join(current_question_lines)
                
                # Bắt đầu câu hỏi mới
                current_question_num = int(match.group(1))
                current_question_lines = [line]
            else:
                # Tiếp tục câu hỏi hiện tại
                if current_question_num is not None:
                    current_question_lines.append(line)
        
        # Lưu câu hỏi cuối
        if current_question_num is not None and current_question_lines:
            questions[current_question_num] = "\n".join(current_question_lines)
        
        return questions
    
    def validate_single_question(self, question_text: str, question_num: int) -> QuestionValidation:
        """
        Kiểm tra một câu hỏi có đầy đủ thành phần không
        
        Args:
            question_text: Nội dung câu hỏi
            question_num: Số thứ tự câu hỏi
            
        Returns:
            QuestionValidation object
        """
        validation = QuestionValidation(question_num=question_num)
        lines = question_text.split("\n")
        
        in_explanation = False
        explanation_lines = 0
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 1. Kiểm tra tiêu đề
            if re.match(r'^\*?\*?Câu\s+\d+[:\.]?\*?\*?', line, re.IGNORECASE):
                validation.has_title = True
            
            # 2. Kiểm tra có nội dung câu hỏi (dòng không phải đáp án, không phải header)
            elif (not re.match(r'^[A-Da-d][\.\)]', line_stripped) and
                  not re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE) and
                  not re.match(r'^[1-4]$', line_stripped) and
                  not re.match(r'^[01]{4}$', line_stripped) and
                  line_stripped != "####" and
                  not in_explanation):
                validation.has_content = True
            
            # 3. Kiểm tra hình ảnh
            if re.search(r'\[?\s*(HÌNH ẢNH|Hình ảnh|hình ảnh)', line, re.IGNORECASE):
                validation.has_image = True
            
            # 4. Đếm đáp án A/B/C/D hoặc a)/b)/c)/d)
            if re.match(r'^[A-Da-d][\.\)]', line_stripped):
                validation.answer_count += 1
            
            # 5. Kiểm tra header "Lời giải"
            if re.match(r'^\*?\*?Lời giải[:\.]?\*?\*?', line, re.IGNORECASE):
                validation.has_solution_header = True
            
            # 6. Kiểm tra đáp án đúng (1-4 hoặc 1010)
            if re.match(r'^[1-4]$', line_stripped) or re.match(r'^[01]{4}$', line_stripped):
                validation.has_correct_answer = True
            
            # 7. Kiểm tra dấu phân cách ####
            if line_stripped == "####":
                validation.has_separator = True
                in_explanation = True
            
            # 8. Đếm dòng giải thích (sau dấu ####)
            if in_explanation and line_stripped and line_stripped != "####":
                explanation_lines += 1
        
        validation.has_explanation = explanation_lines > 0
        validation.explanation_length = explanation_lines
        
        return validation
    
    def validate_all_questions(self, text: str) -> Tuple[List[QuestionValidation], List[int]]:
        """
        Kiểm tra toàn bộ đề bài
        
        Returns:
            Tuple (list_validations, missing_question_numbers)
        """
        print(f"\n{'='*60}")
        print(f"🔍 BẮT ĐẦU KIỂM TRA ĐỀ BÀI")
        print(f"{'='*60}\n")
        
        questions = self.parse_questions(text)
        validations = []
        
        print(f"📊 Tìm thấy {len(questions)} câu trong đề bài")
        print(f"📋 Yêu cầu: {self.required_count} câu\n")
        
        # Kiểm tra từng câu có trong text
        for qnum, qtext in sorted(questions.items()):
            validation = self.validate_single_question(qtext, qnum)
            validations.append(validation)
            
            if not validation.is_valid:
                print(f"⚠️  Câu {qnum}: THIẾU - {', '.join(validation.missing_parts)}")
            else:
                print(f"✅ Câu {qnum}: Hợp lệ")
        
        # Tìm câu bị thiếu hoàn toàn
        existing_nums = set(questions.keys())
        required_nums = set(range(1, self.required_count + 1))
        missing_nums = sorted(required_nums - existing_nums)
        
        if missing_nums:
            print(f"\n❌ THIẾU HOÀN TOÀN {len(missing_nums)} CÂU: {missing_nums[:10]}" + 
                  (f" và {len(missing_nums)-10} câu khác" if len(missing_nums) > 10 else ""))
        
        print(f"\n{'='*60}")
        print(f"📊 KẾT QUẢ KIỂM TRA")
        print(f"{'='*60}")
        valid_count = sum(1 for v in validations if v.is_valid)
        invalid_count = len(validations) - valid_count
        print(f"✅ Câu hợp lệ: {valid_count}")
        print(f"⚠️  Câu thiếu thành phần: {invalid_count}")
        print(f"❌ Câu thiếu hoàn toàn: {len(missing_nums)}")
        print(f"{'='*60}\n")
        
        return validations, missing_nums
    
    def generate_fix_prompt(self, validations: List[QuestionValidation], 
                           missing_nums: List[int],
                           original_prompt: str,
                           full_text: str) -> str:
        """
        Tạo prompt để AI bổ sung/sửa các câu hỏi
        
        Args:
            validations: Danh sách kết quả kiểm tra
            missing_nums: Danh sách số câu thiếu hoàn toàn
            original_prompt: Prompt gốc
            full_text: Toàn bộ text hiện tại
            
        Returns:
            Prompt để gửi cho AI
        """
        # Lấy các câu cần sửa
        questions_to_fix = [v for v in validations if not v.is_valid]
        
        if not questions_to_fix and not missing_nums:
            return None  # Không cần sửa gì
        
        prompt_parts = [
            "# YÊU CẦU BỔ SUNG VÀ SỬA CHỮA ĐỀ BÀI\n",
            "## TÌNH TRẠNG HIỆN TẠI\n"
        ]
        
        # 1. Liệt kê câu thiếu hoàn toàn
        if missing_nums:
            prompt_parts.append(f"\n### ❌ THIẾU HOÀN TOÀN {len(missing_nums)} CÂU:")
            prompt_parts.append(f"Các câu số: {', '.join(map(str, missing_nums[:20]))}")
            if len(missing_nums) > 20:
                prompt_parts.append(f"... và {len(missing_nums)-20} câu khác")
            prompt_parts.append("\n**YÊU CẦU:** Sinh đầy đủ các câu này theo đúng format.\n")
        
        # 2. Liệt kê câu thiếu thành phần
        if questions_to_fix:
            prompt_parts.append(f"\n### ⚠️  CÓ {len(questions_to_fix)} CÂU THIẾU THÀNH PHẦN:")
            for v in questions_to_fix[:10]:  # Chỉ liệt kê 10 câu đầu
                prompt_parts.append(f"\n**Câu {v.question_num}:**")
                for missing_part in v.missing_parts:
                    prompt_parts.append(f"  - Thiếu: {missing_part}")
            
            if len(questions_to_fix) > 10:
                prompt_parts.append(f"\n... và {len(questions_to_fix)-10} câu khác cũng thiếu thành phần")
            
            prompt_parts.append("\n**YÊU CẦU:** Bổ sung đầy đủ các phần còn thiếu.\n")
        
        # 3. Yêu cầu cụ thể
        prompt_parts.extend([
            "\n## YÊU CẦU CHI TIẾT\n",
            "1. **Đối với câu THIẾU HOÀN TOÀN:** Sinh lại toàn bộ câu hỏi theo đúng format",
            "2. **Đối với câu THIẾU THÀNH PHẦN:** Chỉ bổ sung phần thiếu, GIỮ NGUYÊN phần đã có",
            "3. **Format bắt buộc:**",
            "   - Tiêu đề: **Câu X:**",
            "   - Nội dung câu hỏi (ít nhất 2-3 dòng)",
            "   - 4 đáp án A, B, C, D (hoặc a), b), c), d) với đúng/sai)",
            "   - Header: **Lời giải:**",
            "   - Đáp án đúng: 1 số từ 1-4 (hoặc mã 1010 với đúng/sai)",
            "   - Dấu phân cách: ####",
            "   - Giải thích chi tiết (ít nhất 3 dòng)",
            "4. **TUYỆT ĐỐI KHÔNG:**",
            "   - Thay đổi số thứ tự câu hỏi",
            "   - Thay đổi nội dung các câu đã hợp lệ",
            "   - Thêm lời mở đầu hay kết thúc ngoài yêu cầu",
            "\n## FORMAT MONG MUỐN\n"
        ])
        
        # 4. Thêm format mẫu
        if self.question_type == "tracnghiem":
            prompt_parts.extend([
                "```",
                "**Câu X:**",
                "[Nội dung câu hỏi]",
                "[HÌNH ẢNH: mô tả] (nếu cần)",
                "",
                "A. [Đáp án 1]",
                "B. [Đáp án 2]",
                "C. [Đáp án 3]",
                "D. [Đáp án 4]",
                "**Lời giải:**",
                "2",
                "####",
                "[Giải thích chi tiết tại sao đáp án 2 đúng, ít nhất 3 dòng]",
                "```\n"
            ])
        else:  # dungsai
            prompt_parts.extend([
                "```",
                "**Câu X:**",
                "[Đoạn văn 50-100 từ mô tả tình huống]",
                "[HÌNH ẢNH: mô tả] (nếu cần)",
                "",
                "a) [Phát biểu 1]",
                "b) [Phát biểu 2]",
                "c) [Phát biểu 3]",
                "d) [Phát biểu 4]",
                "**Lời giải:**",
                "1010",
                "####",
                "- [Nội dung phát biểu a] là ĐÚNG.",
                "Giải thích chi tiết (ít nhất 3 dòng).",
                "",
                "- [Nội dung phát biểu b] là SAI.",
                "Giải thích chi tiết (ít nhất 3 dòng).",
                "...",
                "```\n"
            ])
        
        # 5. Đính kèm đề hiện tại
        prompt_parts.extend([
            "\n## ĐỀ BÀI HIỆN TẠI (để tham khảo)\n",
            "```",
            full_text[:5000],  # Chỉ lấy 5000 ký tự đầu để tránh quá dài
            "```\n" if len(full_text) > 5000 else "```\n",
            "\n## BẮT ĐẦU BỔ SUNG/SỬA CHỮA\n",
            "Hãy trả về TOÀN BỘ đề bài đã được sửa chữa và bổ sung đầy đủ.",
            "GIỮ NGUYÊN các câu đã hợp lệ, chỉ sửa/thêm các câu có vấn đề.\n"
        ])
        
        return "\n".join(prompt_parts)
    
    def fix_questions_with_ai(self, text: str, original_prompt: str,
                             client: VertexClient, max_attempts: int = 5) -> str:
        """
        Tự động kiểm tra và bổ sung câu hỏi bằng AI
        
        Args:
            text: Text đề bài hiện tại
            original_prompt: Prompt gốc để tham khảo format
            client: VertexClient để gọi API
            max_attempts: Số lần thử tối đa
            
        Returns:
            Text đề bài đã được sửa chữa
        """
        current_text = text
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"\n{'='*60}")
            print(f"🔄 VÒNG KIỂM TRA VÀ SỬA LẦN {attempt}/{max_attempts}")
            print(f"{'='*60}\n")
            
            # Kiểm tra
            validations, missing_nums = self.validate_all_questions(current_text)
            
            # Kiểm tra xem có cần sửa không
            invalid_questions = [v for v in validations if not v.is_valid]
            
            if not invalid_questions and not missing_nums:
                print("\n🎉 ĐỀ BÀI ĐÃ HOÀN HẢO! Không cần sửa gì thêm.\n")
                return current_text
            
            # Tạo prompt sửa
            fix_prompt = self.generate_fix_prompt(
                validations, missing_nums, original_prompt, current_text
            )
            
            print(f"\n📤 Gửi yêu cầu sửa chữa đến AI...")
            print(f"   - Số câu cần sửa thành phần: {len(invalid_questions)}")
            print(f"   - Số câu thiếu hoàn toàn: {len(missing_nums)}\n")
            
            # Gọi AI
            try:
                fixed_text = client.send_data_to_check(prompt=fix_prompt)
                current_text = fixed_text
                print(f"✅ Đã nhận phản hồi từ AI\n")
            except Exception as e:
                print(f"❌ Lỗi khi gọi AI: {e}\n")
                break
        
        # Kiểm tra lần cuối
        print(f"\n{'='*60}")
        print(f"🔍 KIỂM TRA CUỐI CÙNG")
        print(f"{'='*60}\n")
        validations, missing_nums = self.validate_all_questions(current_text)
        invalid_questions = [v for v in validations if not v.is_valid]
        
        if not invalid_questions and not missing_nums:
            print("\n🎉 ĐỀ BÀI ĐÃ HOÀN CHỈNH!\n")
        else:
            print(f"\n⚠️  VẪN CÒN {len(invalid_questions)} CÂU THIẾU THÀNH PHẦN")
            print(f"⚠️  VẪN CÒN {len(missing_nums)} CÂU THIẾU HOÀN TOÀN")
            print(f"💡 Bạn có thể chạy lại hoặc kiểm tra thủ công.\n")
        
        return current_text


# ==================== FUNCTIONS ĐỂ TÍCH HỢP VÀO response2docx.py ====================

def validate_and_fix_response(AIresponse: str, original_prompt: str,
                              client: VertexClient, question_type: str = "tracnghiem") -> str:
    """
    Hàm tiện ích để tích hợp vào response2docx_improved()
    
    Usage trong response2docx_improved():
        # Sau khi nhận AIresponse_final từ AI
        AIresponse_final = validate_and_fix_response(
            AIresponse_final, 
            prompt, 
            client, 
            question_type
        )
    """
    validator = QuestionValidator(question_type=question_type)
    fixed_text = validator.fix_questions_with_ai(
        AIresponse, 
        original_prompt, 
        client,
        max_attempts=5
    )
    return fixed_text

def validate_and_store_questions(text: str, storage: ValidQuestionStorage, 
                                 question_type: str = "tracnghiem") -> Tuple[List[int], List[int]]:
    """
    Validate text và lưu các câu hợp lệ vào storage
    
    Returns:
        List số câu không hợp lệ hoặc thiếu
    """
    validator = QuestionValidator(question_type=question_type)
    
    # Parse câu hỏi từ text
    questions = validator.parse_questions(text)
    
    print(f"\n{'='*60}")
    print(f"🔍 VALIDATE VÀ LƯU CÂU HỢP LỆ")
    print(f"{'='*60}\n")
    
    invalid_nums = []
    new_valid_count = 0
    
    for qnum, qtext in sorted(questions.items()):
        # Bỏ qua câu đã lưu trước đó
        if storage.has_question(qnum):
            print(f"⏭️  Câu {qnum}: Đã lưu trước đó")
            continue
        
        # Validate câu mới
        validation = validator.validate_single_question(qtext, qnum)
        
        if validation.is_valid:
            storage.add_valid_question(qnum, qtext)
            new_valid_count += 1
            print(f"\n✅ Câu {qnum}: Hợp lệ → LƯU\n")
        else:
            invalid_nums.append(qnum)
            print(f"\n❌ Câu {qnum}: Thiếu {', '.join(validation.missing_parts)}\n")
    required_count = validator.required_count
    all_nums_in_text = set(questions.keys())
    all_nums_needed = set(range(1, required_count + 1))
    missing_nums = sorted(all_nums_needed - all_nums_in_text - storage.valid_nums)
    
    print(f"\n📊 Tổng kết:\n")
    print(f"   - Câu mới hợp lệ: {new_valid_count}\n")
    print(f"   - Câu không hợp lệ: {len(invalid_nums)}\n")
    print(f"   - Câu thiếu hoàn toàn: {len(missing_nums)}\n")
    print(f"   - Tổng đã lưu: {storage.get_valid_count()}\n")
    
    return invalid_nums, missing_nums

def regenerate_invalid_questions(invalid_nums: List[int], 
                                 original_prompt: str,
                                 storage: ValidQuestionStorage,
                                 client: VertexClient,
                                 question_type: str = "tracnghiem",
                                 max_attempts: int = 5) -> str:
    """
    Sinh lại chỉ các câu không hợp lệ/thiếu
    
    Returns:
        Text chứa các câu mới được sinh
    """
    if not invalid_nums:
        return ""
    
    print(f"\n{'='*60}")
    print(f"\n🔄 SINH LẠI {len(invalid_nums)} CÂU\n")
    print(f"Danh sách: {invalid_nums[:20]}" + (f"... và {len(invalid_nums)-20} câu khác" if len(invalid_nums) > 20 else ""))
    print(f"\n{'='*60}\n")
    
    # Lấy mẫu từ các câu hợp lệ để tránh trùng
    existing_samples = []
    for qnum in sorted(storage.valid_nums)[:5]:
        qtext = storage.valid_questions[qnum]
        preview = qtext.split("\n")[1:3]
        existing_samples.append(f"Câu {qnum}: {' '.join(preview)[:80]}...")
    
    # Tạo prompt sinh lại
    regenerate_prompt = f"""{original_prompt}

# YÊU CẦU BỔ SUNG CÂU HỎI

## TÌNH HUỐNG
Đã có {storage.get_valid_count()} câu hợp lệ. Cần sinh lại {len(invalid_nums)} câu BỊ LỖI hoặc THIẾU.

## CÁC CÂU CẦN SINH (QUAN TRỌNG)
Sinh CHÍNH XÁC các câu sau: {', '.join(map(str, invalid_nums[:20]))}
{'... và ' + str(len(invalid_nums)-20) + ' câu khác' if len(invalid_nums) > 20 else ''}

## MỘT SỐ CÂU ĐÃ HỢP LỆ (TRÁNH TRÙNG LẶP)
{chr(10).join(existing_samples)}

## YÊU CẦU TUYỆT ĐỐI
1. CHỈ sinh các câu trong danh sách trên, ĐÚNG SỐ THỨ TỰ
2. Nội dung HOÀN TOÀN KHÁC với các câu đã có
3. Mỗi câu PHẢI ĐẦY ĐỦ format: tiêu đề, nội dung, 4 đáp án, lời giải, giải thích
4. BÁM SÁT chủ đề từ PDF đã quét
5. KHÔNG thêm lời mở đầu/kết thúc

BẮT ĐẦU SINH:
"""
    successfully_generated = []
    
    # Sinh với retry
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"\n   Lần thử {attempt}/{max_attempts}...")
            new_text = client.send_data_to_check(
                prompt=regenerate_prompt,
                temperature=0.6 + (attempt * 0.1)
            )
            
            # Parse và validate từng câu mới sinh
            from process.ques_valid import QuestionValidator
            validator = QuestionValidator(question_type=question_type)
            new_questions = validator.parse_questions(new_text)
            
            print(f"   📝 Nhận được {len(new_questions)} câu từ AI")
            
            # Validate và lưu từng câu
            newly_valid = []
            for qnum, qtext in sorted(new_questions.items()):
                # Chỉ xử lý câu trong danh sách cần sinh
                if qnum not in invalid_nums:
                    print(f"   ⏭️  Câu {qnum}: Không trong danh sách cần sinh, bỏ qua")
                    continue
                
                # Bỏ qua câu đã lưu trước đó
                if storage.has_question(qnum):
                    print(f"   ⏭️  Câu {qnum}: Đã hợp lệ từ trước")
                    continue
                
                # Validate
                validation = validator.validate_single_question(qtext, qnum)
                
                if validation.is_valid:
                    storage.add_valid_question(qnum, qtext)
                    newly_valid.append(qnum)
                    successfully_generated.append(qnum)
                    print(f"\n   ✅ Câu {qnum}: Hợp lệ → LƯU\n")
                else:
                    print(f"\n   ❌ Câu {qnum}: Vẫn thiếu {', '.join(validation.missing_parts)}\n")
            
            # Kiểm tra xem còn câu nào cần sinh không
            remaining = [n for n in invalid_nums if n not in successfully_generated]
            
            if not remaining:
                print(f"\n   🎉 Đã sinh đủ tất cả {len(invalid_nums)} câu!\n")
                break
            else:
                print(f"\n   ⚠️  Còn {len(remaining)} câu cần sinh tiếp")
                # Cập nhật danh sách cần sinh cho lần thử tiếp theo
                invalid_nums = remaining
                
        except Exception as e:
            print(f"   ✗ Lỗi: {e}")
    
    # Ghép lại text từ các câu đã sinh thành công
    result_parts = []
    for qnum in sorted(successfully_generated):
        result_parts.append(storage.valid_questions[qnum])
    
    print(f"\n📊 Kết quả: Sinh thành công {len(successfully_generated)} câu")
    return "\n\n".join(result_parts)


