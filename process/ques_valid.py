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
            self.explanation_length >= 3  # Ít nhất 3 dòng giải thích
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
                "",
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
                "",
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
                             client: VertexClient, max_attempts: int = 2) -> str:
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
        max_attempts=2
    )
    return fixed_text

