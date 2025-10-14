"""
Module quét và phân tích nội dung PDF để sinh câu hỏi chính xác
VERSION 3.0: Tối ưu hóa tuyệt đối để tránh lạc đề và thiếu câu
"""
import os
import re
import json
from typing import List, Dict, Tuple
from api.callAPI import VertexClient


class PDFScanner:
    """Class quét và phân tích nội dung từ các file PDF với độ chính xác cao."""
    
    def __init__(self, project_id: str, creds, model_name: str = "gemini-2.5-pro"):
        self.client = VertexClient(project_id, creds, model_name)
        self.pdf_types = {
            "sgk": "Sách Giáo Khoa",
            "sbt": "Sách Bài Tập", 
            "sgv": "Sách Giáo Viên"
        }
    
    def identify_pdf_types(self, pdf_files: List[str]) -> Dict[str, str]:
        """Nhận diện loại của mỗi file PDF dựa trên tên file."""
        print(f"\n{'='*70}")
        print("🔍 NHẬN DIỆN LOẠI FILE PDF")
        print(f"{'='*70}\n")
        
        pdf_mapping = {}
        identified_types = set()

        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path).lower()
            pdf_type = None
            if ("sgk" in filename or "sach_giao_khoa" in filename or "giaokhoa" in filename) and "sgk" not in identified_types:
                pdf_type = "sgk"
            elif ("sbt" in filename or "sach_bai_tap" in filename or "baitap" in filename) and "sbt" not in identified_types:
                pdf_type = "sbt"
            elif ("sgv" in filename or "sach_giao_vien" in filename or "giaovien" in filename) and "sgv" not in identified_types:
                pdf_type = "sgv"
            
            if pdf_type:
                pdf_mapping[pdf_path] = pdf_type
                identified_types.add(pdf_type)
                print(f"   ✓ {os.path.basename(pdf_path)} → {self.pdf_types[pdf_type]}")

        unidentified_files = [f for f in pdf_files if f not in pdf_mapping]
        available_types = ["sgk", "sbt", "sgv"]
        for pdf_path in unidentified_files:
            for type_code in available_types:
                if type_code not in identified_types:
                    pdf_mapping[pdf_path] = type_code
                    identified_types.add(type_code)
                    print(f"   ✓ {os.path.basename(pdf_path)} → {self.pdf_types[type_code]} (Dự đoán)")
                    break
        
        print()
        return pdf_mapping
    
    def scan_pdf_to_json(self, pdf_files: List[str]) -> Dict[str, dict]:
        """
        Quét nội dung của từng file PDF và yêu cầu trả về JSON có cấu trúc.
        VERSION 3.0: Tối ưu hóa để trích xuất đầy đủ và chính xác
        """
        print(f"\n{'='*70}")
        print("📖 QUÉT VÀ TRÍCH XUẤT DỮ LIỆU CẤU TRÚC (JSON) TỪ PDF")
        print(f"{'='*70}\n")
        
        pdf_mapping = self.identify_pdf_types(pdf_files)
        structured_data = {}
        
        # Prompt tối ưu hóa - yêu cầu trích xuất đầy đủ và chi tiết
        scan_prompt = """
<role>
Bạn là một công cụ trích xuất dữ liệu thông minh chuyên nghiệp. Nhiệm vụ của bạn là phân tích TOÀN BỘ file PDF được cung cấp và trả về một đối tượng JSON duy nhất, đầy đủ và chi tiết.
</role>

<critical_requirements>
1. Đọc TOÀN BỘ tài liệu từ đầu đến cuối
2. Trích xuất TẤT CẢ các khái niệm, định nghĩa, công thức
3. Tóm tắt BẢN CHẤT của định nghĩa (đủ để hiểu, không cần nguyên văn)  # ← SỬA
4. Phân loại độ quan trọng: 'critical', 'high', 'medium', 'low'
5. Đảm bảo JSON hợp lệ và đầy đủ
</critical_requirements>

<output_format>
Trả về JSON với cấu trúc sau (KHÔNG thêm text nào khác):
{
  "main_topic": "Tên chính xác của bài học/chương (NGUYÊN VĂN từ PDF)",
  "sub_topics": [
    "Chủ đề phụ 1",
    "Chủ đề phụ 2",
    "Chủ đề phụ 3"
  ],
  "learning_objectives": [
    "Mục tiêu học tập 1 (NGUYÊN VĂN)",
    "Mục tiêu học tập 2 (NGUYÊN VĂN)"
  ],
  "key_concepts": [
    {
      "concept": "Tên khái niệm",
      "definition": "Định nghĩa NGUYÊN VĂN từ PDF - ĐẦY ĐỦ",
      "explanation": "Giải thích chi tiết thêm (nếu có)",
      "examples": ["Ví dụ 1", "Ví dụ 2"],
      "importance": "critical|high|medium|low",
      "page_reference": "Trang X"
    }
  ],
  "formulas_and_rules": [
    {
      "name": "Tên công thức/quy tắc",
      "formula": "Công thức (LaTeX nếu có)",
      "description": "Mô tả cách sử dụng",
      "conditions": "Điều kiện áp dụng (nếu có)",
      "importance": "critical|high|medium|low"
    }
  ],
  "procedures_and_methods": [
    {
      "name": "Tên phương pháp/quy trình",
      "steps": ["Bước 1", "Bước 2", "Bước 3"],
      "notes": "Lưu ý quan trọng",
      "importance": "high|medium|low"
    }
  ],
  "important_tables": [
    {
      "title": "Tiêu đề bảng",
      "content": "Mô tả chi tiết nội dung bảng",
      "page_reference": "Trang Y"
    }
  ],
  "diagrams_and_figures": [
    {
      "title": "Tiêu đề hình/sơ đồ",
      "description": "Mô tả chi tiết các thành phần",
      "page_reference": "Trang Z"
    }
  ],
  "keywords": ["Từ khóa 1", "Từ khóa 2", "Từ khóa 3"],
  "content_boundary": {
    "start_page": 1,
    "end_page": 50,
    "total_concepts": 15,
    "coverage": "Bài 1: Tên bài - Tất cả nội dung từ trang X đến Y"
  }
}
</output_format>

<extraction_instructions>
1. **Quét toàn bộ**: Đọc từ trang đầu đến trang cuối
2. **Ưu tiên độ quan trọng**:
   - critical: Định nghĩa cốt lõi, công thức chính
   - high: Khái niệm quan trọng, quy trình chính
   - medium: Ví dụ minh họa, lưu ý
   - low: Thông tin bổ sung
3. **Trích xuất nguyên văn**: Định nghĩa phải giữ nguyên 100% từ PDF
4. **Ghi chú vị trí**: Luôn ghi số trang tham chiếu
5. **Phạm vi nội dung**: Xác định rõ phạm vi bài học để tránh lạc đề
</extraction_instructions>

<quality_check>
Trước khi trả về, kiểm tra:
- ✓ JSON hợp lệ (có thể parse được)
- ✓ Có ít nhất 10 key_concepts
- ✓ Tất cả định nghĩa đều có đầy đủ
- ✓ Đã ghi rõ phạm vi nội dung (content_boundary)
- ✓ Không có placeholder hay dữ liệu giả
</quality_check>
"""
        
        for pdf_path, pdf_type in pdf_mapping.items():
            print(f"📄 Đang quét {self.pdf_types[pdf_type]}: {os.path.basename(pdf_path)}...")
            try:
                response_text = self.client.send_data_to_AI(
                    prompt=scan_prompt,
                    file_paths=[pdf_path],
                    temperature=0.4
                )
                
                # Làm sạch và parse JSON
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```|({[\s\S]*})', response_text)
                if json_match:
                    json_str = json_match.group(1) or json_match.group(2)
                    data = json.loads(json_str)
                    
                    # Kiểm tra chất lượng dữ liệu
                    concepts_count = len(data.get('key_concepts', []))
                    if concepts_count < 5:
                        print(f"   ⚠️ Cảnh báo: Chỉ trích xuất được {concepts_count} khái niệm")
                    
                    structured_data[pdf_type] = data
                    print(f"   ✓ Hoàn thành trích xuất:")
                    print(f"      - {concepts_count} khái niệm")
                    print(f"      - {len(data.get('formulas_and_rules', []))} công thức/quy tắc")
                    print(f"      - {len(data.get('procedures_and_methods', []))} quy trình")
                    print(f"      - Phạm vi: {data.get('content_boundary', {}).get('coverage', 'N/A')}")
                else:
                    print(f"   ✗ Lỗi: Không tìm thấy JSON trong phản hồi.")
                    structured_data[pdf_type] = {}

            except json.JSONDecodeError as e:
                print(f"   ✗ Lỗi JSON: {e}")
                print(f"   → Phản hồi: {response_text[:200]}...")
                structured_data[pdf_type] = {}
            except Exception as e:
                print(f"   ✗ Lỗi nghiêm trọng: {e}\n")
                structured_data[pdf_type] = {}
        
        return structured_data

    def generate_topic_guide_from_json(self, structured_data: Dict[str, dict]) -> str:
        """
        Tạo hướng dẫn chủ đề từ dữ liệu JSON đã trích xuất.
        VERSION 3.0: Tăng cường ràng buộc để tránh lạc đề
        """
        print(f"\n{'='*70}")
        print("🎯 TẠO HÀNG RÀO KIẾN THỨC TỪ DỮ LIỆU JSON")
        print(f"{'='*70}\n")
        
        guide_parts = [
            "<knowledge_base>",
            "    <master_instruction>",
            "        MỘT CÁCH TUYỆT ĐỐI: Mọi câu hỏi, đáp án, và giải thích PHẢI được suy ra TRỰC TIẾP từ các thông tin được cung cấp trong knowledge_base này.",
            "        NGHIÊM CẤM:",
            "        - Sử dụng kiến thức bên ngoài phạm vi đã định nghĩa",
            "        - Lấy nội dung từ bài khác, chương khác",
            "        - Tạo câu hỏi về chủ đề không xuất hiện trong danh sách sub_topics",
            "        - Phát minh định nghĩa hoặc công thức mới",
            "    </master_instruction>",
            ""
        ]
        
        # Tổng hợp tất cả chủ đề được phép
        all_allowed_topics = set()
        all_keywords = set()
        
        for pdf_type, data in structured_data.items():
            if not data:
                continue
            
            guide_parts.append(f"    <source name='{self.pdf_types.get(pdf_type, 'Unknown')}'>")
            
            # Chủ đề chính
            main_topic = data.get('main_topic', 'N/A')
            guide_parts.append(f"        <main_topic>{main_topic}</main_topic>")
            all_allowed_topics.add(main_topic)
            
            # Chủ đề phụ
            sub_topics = data.get('sub_topics', [])
            if sub_topics:
                guide_parts.append("        <sub_topics>")
                for st in sub_topics:
                    guide_parts.append(f"            <topic>{st}</topic>")
                    all_allowed_topics.add(st)
                guide_parts.append("        </sub_topics>")
            
            # Phạm vi nội dung
            content_boundary = data.get('content_boundary', {})
            if content_boundary:
                guide_parts.append("        <content_boundary>")
                guide_parts.append(f"            <coverage>{content_boundary.get('coverage', 'N/A')}</coverage>")
                guide_parts.append(f"            <start_page>{content_boundary.get('start_page', 'N/A')}</start_page>")
                guide_parts.append(f"            <end_page>{content_boundary.get('end_page', 'N/A')}</end_page>")
                guide_parts.append("        </content_boundary>")
            
            # Từ khóa
            keywords = data.get('keywords', [])
            if keywords:
                guide_parts.append("        <keywords>")
                for kw in keywords:
                    guide_parts.append(f"            <keyword>{kw}</keyword>")
                    all_keywords.add(kw)
                guide_parts.append("        </keywords>")
            
            # Khái niệm chính - ưu tiên theo importance
            key_concepts = data.get('key_concepts', [])
            sorted_concepts = sorted(
                key_concepts, 
                key=lambda x: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x.get('importance', 'low'), 4)
            )
            
            if sorted_concepts:
                guide_parts.append("        <key_concepts>")
                for concept in sorted_concepts:
                    importance = concept.get('importance', 'low')
                    guide_parts.append(f"            <concept importance='{importance}'>")
                    guide_parts.append(f"                <name>{concept.get('concept', 'N/A')}</name>")
                    guide_parts.append(f"                <definition><![CDATA[{concept.get('definition', 'N/A')}]]></definition>")
                    
                    if concept.get('explanation'):
                        guide_parts.append(f"                <explanation><![CDATA[{concept.get('explanation')}]]></explanation>")
                    
                    examples = concept.get('examples', [])
                    if examples:
                        guide_parts.append("                <examples>")
                        for ex in examples:
                            guide_parts.append(f"                    <example>{ex}</example>")
                        guide_parts.append("                </examples>")
                    
                    if concept.get('page_reference'):
                        guide_parts.append(f"                <page_reference>{concept.get('page_reference')}</page_reference>")
                    
                    guide_parts.append("            </concept>")
                guide_parts.append("        </key_concepts>")
            
            # Công thức và quy tắc
            formulas = data.get('formulas_and_rules', [])
            if formulas:
                guide_parts.append("        <formulas_and_rules>")
                for formula in formulas:
                    guide_parts.append(f"            <formula importance='{formula.get('importance', 'medium')}'>")
                    guide_parts.append(f"                <name>{formula.get('name', 'N/A')}</name>")
                    guide_parts.append(f"                <formula_text><![CDATA[{formula.get('formula', 'N/A')}]]></formula_text>")
                    guide_parts.append(f"                <description>{formula.get('description', 'N/A')}</description>")
                    if formula.get('conditions'):
                        guide_parts.append(f"                <conditions>{formula.get('conditions')}</conditions>")
                    guide_parts.append("            </formula>")
                guide_parts.append("        </formulas_and_rules>")
            
            # Quy trình và phương pháp
            procedures = data.get('procedures_and_methods', [])
            if procedures:
                guide_parts.append("        <procedures_and_methods>")
                for proc in procedures:
                    guide_parts.append(f"            <procedure importance='{proc.get('importance', 'medium')}'>")
                    guide_parts.append(f"                <name>{proc.get('name', 'N/A')}</name>")
                    steps = proc.get('steps', [])
                    if steps:
                        guide_parts.append("                <steps>")
                        for step in steps:
                            guide_parts.append(f"                    <step>{step}</step>")
                        guide_parts.append("                </steps>")
                    if proc.get('notes'):
                        guide_parts.append(f"                <notes>{proc.get('notes')}</notes>")
                    guide_parts.append("            </procedure>")
                guide_parts.append("        </procedures_and_methods>")
            
            guide_parts.append("    </source>")
            guide_parts.append("")
            guide_parts.append("    <usage_instruction>")
            guide_parts.append("        Sử dụng các định nghĩa này làm CƠ SỞ, KHÔNG trích dẫn nguyên văn.")
            guide_parts.append("        Hãy DIỄN ĐẠT LẠI bằng cách:")
            guide_parts.append("            - Thay đổi cấu trúc câu")
            guide_parts.append("            - Thêm ví dụ minh họa mới")
            guide_parts.append("            - Kết hợp với tình huống thực tế")
            guide_parts.append("    </usage_instruction>")
            guide_parts.append("")
        
        
        # Thêm phần kiểm soát chủ đề nghiêm ngặt
        guide_parts.append("    <topic_control>")
        guide_parts.append("        <allowed_topics>")
        for topic in sorted(all_allowed_topics):
            guide_parts.append(f"            <topic>{topic}</topic>")
        guide_parts.append("        </allowed_topics>")
        guide_parts.append("        <allowed_keywords>")
        for kw in sorted(all_keywords):
            guide_parts.append(f"            <keyword>{kw}</keyword>")
        guide_parts.append("        </allowed_keywords>")
        guide_parts.append("        <validation_rule>")
        guide_parts.append("            MỖI câu hỏi phải liên quan TRỰC TIẾP đến ít nhất 1 trong các allowed_topics hoặc allowed_keywords ở trên.")
        guide_parts.append("            Nếu câu hỏi không liên quan, KHÔNG ĐƯỢC tạo câu đó.")
        guide_parts.append("        </validation_rule>")
        guide_parts.append("    </topic_control>")

        guide_parts.append("</knowledge_base>")
        
        topic_guide = "\n".join(guide_parts)
        print(f"✓ Đã tạo hàng rào kiến thức ({len(topic_guide)} ký tự)")
        print(f"✓ Số chủ đề được phép: {len(all_allowed_topics)}")
        print(f"✓ Số từ khóa: {len(all_keywords)}\n")
        return topic_guide,all_allowed_topics, all_keywords


def enhance_prompt_with_pdf_scan(prompt: str, pdf_files: List[str], 
                                 project_id: str, creds) -> str:
    """
    Hàm tiện ích để quét PDF, trích xuất JSON và chèn 'knowledge_base' vào prompt.
    VERSION 3.0: Tối ưu hóa để đảm bảo không lạc đề
    """
    scanner = PDFScanner(project_id, creds)
    structured_data = scanner.scan_pdf_to_json(pdf_files)
    topic_guide, all_allowed_topics, all_keywords = scanner.generate_topic_guide_from_json(structured_data)
    # Chèn topic_guide vào prompt
    if "{topic_guide}" in prompt:
        enhanced_prompt = prompt.replace("{topic_guide}", topic_guide)
    else:
        # Chèn ngay sau phần VAI TRÒ
        enhanced_prompt = topic_guide + "\n\n" + prompt
    
    # Thêm lệnh kiểm soát cuối cùng
    final_instruction = """

<final_generation_control>
    <pre_generation_check>
        Trước khi sinh MỖI câu hỏi, hãy tự hỏi:
        1. Câu hỏi này có liên quan TRỰC TIẾP đến một trong các allowed_topics không?
        2. Câu hỏi này có sử dụng ít nhất 1 trong các key_concepts đã được định nghĩa không?
        3. Đáp án và giải thích có DỰA VÀO kiến thức từ knowledge_base (đã tái cấu trúc) không? 
        
        Nếu câu trả lời cho bất kỳ câu hỏi nào là KHÔNG, hãy BỎ QUA câu hỏi đó và tạo câu khác.
    </pre_generation_check>
    
    <creativity_instruction>
        - Mỗi câu hỏi là SẢN PHẨM SÁNG TẠO từ kiến thức đã quét
        - KHÔNG copy/trích dẫn nguyên văn từ tài liệu
        - Tự do tạo tình huống mới miễn BÁM SÁT chủ đề
        - Đáp án nhiễu phải hợp lý và gây nhầm lẫn
    </creativity_instruction>
    
    <quality_assurance>
        - Mỗi câu hỏi phải trích dẫn được nguồn từ knowledge_base
        - Không tạo câu hỏi dựa trên suy đoán hoặc kiến thức chung
        - Đảm bảo 100% câu hỏi nằm trong phạm vi content_boundary
    </quality_assurance>
    
    <creativity_requirements>
        - Mỗi câu hỏi phải là SẢN PHẨM SÁNG TẠO từ kiến thức gốc
        - Tăng độ khó bằng cách kết hợp nhiều khái niệm
        - Sử dụng ngữ cảnh/tình huống KHÁC với sách
        - Đáp án nhiễu phải HỢP LÝ và GÂY NHẦM LẪN cao
    </creativity_requirements>
</final_generation_control>
"""
    
    enhanced_prompt += final_instruction
    
    return enhanced_prompt,all_allowed_topics, all_keywords


# ==================== MISSING QUESTION FIXER (Tối ưu hóa) ====================

class MissingQuestionFixer:
    """Class sinh lại câu hỏi bị thiếu với cơ chế kiểm soát chặt chẽ"""
    
    def __init__(self, project_id: str, creds, model_name: str = "gemini-1.5-pro-preview-0514"):
        self.client = VertexClient(project_id, creds, model_name)
    
    def generate_missing_questions(self, missing_nums: List[int], 
                               original_prompt: str,
                               existing_text: str,
                               question_type: str = "tracnghiem") -> str:
        """Sinh lại câu thiếu với kiểm tra trùng lặp"""
        
        max_retry_per_question = 3  # Mỗi câu thử tối đa 3 lần
        successful_questions = []
        
        existing_questions = self._extract_existing_questions(existing_text)
        existing_topics = self._extract_topics_from_questions(existing_questions)
        
        for q_num in missing_nums:
            print(f"\n🔄 Sinh câu {q_num}...")
            
            for attempt in range(max_retry_per_question):
                regenerate_prompt = self._create_regenerate_prompt(
                    [q_num],  # Sinh từng câu một
                    original_prompt,
                    existing_questions,
                    existing_topics,
                    question_type
                )
                
                # Thêm cảnh báo chống trùng vào prompt
                regenerate_prompt += f"""

    🚨 **CẢNH BÁO NGHIÊM TRỌNG - LẦN THỬ {attempt+1}/{max_retry_per_question}:**
    - Câu {q_num} TUYỆT ĐỐI KHÔNG được giống bất kỳ câu nào đã có
    - Phải thay đổi HOÀN TOÀN: chủ đề, góc nhìn, tình huống
    - Nếu trùng > 65% → BỊ TỪ CHỐI
    """
                
                try:
                    new_question = self.client.send_data_to_check(
                        prompt=regenerate_prompt,
                        temperature=0.85 + (attempt * 0.05)  # Tăng dần mỗi lần thử
                    )
                    
                    # Kiểm tra trùng
                    parsed_new = self._extract_existing_questions(new_question)
                    if q_num in parsed_new:
                        is_duplicate = self._check_duplication(
                            parsed_new[q_num], 
                            existing_questions
                        )
                        
                        if not is_duplicate:
                            print(f"   ✅ Câu {q_num} hợp lệ (lần thử {attempt+1})")
                            successful_questions.append(new_question)
                            existing_questions[q_num] = parsed_new[q_num]  # Thêm vào danh sách
                            break
                        else:
                            print(f"   ⚠️ Câu {q_num} bị trùng, thử lại...")
                            
                except Exception as e:
                    print(f"   ❌ Lỗi sinh câu {q_num}: {e}")
            
            else:  # Nếu hết số lần thử mà vẫn trùng
                print(f"   ⛔ Câu {q_num} thất bại sau {max_retry_per_question} lần thử")
        
        return "\n\n".join(successful_questions)
    
    def _extract_existing_questions(self, text: str) -> Dict[int, str]:
        """Trích xuất các câu hỏi đã có"""
        questions = {}
        lines = text.split("\n")
        current_num = None
        current_lines = []
        
        for line in lines:
            match = re.match(r'^\*?\*?Câu\s+(\d+)', line, re.IGNORECASE)
            if match:
                if current_num and current_lines:
                    questions[current_num] = "\n".join(current_lines)
                current_num = int(match.group(1))
                current_lines = [line]
            elif current_num:
                current_lines.append(line)
        
        if current_num and current_lines:
            questions[current_num] = "\n".join(current_lines)
        
        return questions
    
    def _check_duplication(self, new_text: str, existing_questions: Dict[int, str]) -> bool:
        """Kiểm tra câu hỏi mới có trùng với câu đã có không"""
        from difflib import SequenceMatcher
        
        # Lấy nội dung câu hỏi (bỏ tiêu đề)
        new_content = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', new_text).strip()
        new_content = new_content.split('**Lời giải:**')[0].strip()[:300]
        
        for q_num, q_text in existing_questions.items():
            exist_content = re.sub(r'\*\*Câu\s+\d+:?\*\*', '', q_text).strip()
            exist_content = exist_content.split('**Lời giải:**')[0].strip()[:300]
            
            # Tính độ tương đồng
            similarity = SequenceMatcher(None, new_content, exist_content).ratio()
            
            if similarity > 0.65:  # Trùng > 65%
                print(f"      ❌ Trùng {similarity*100:.1f}% với câu {q_num}")
                return True
        
        return False

    def _extract_topics_from_questions(self, questions: Dict[int, str]) -> Dict[str, int]:
        """Phân tích các chủ đề đã được sử dụng và tần suất"""
        topics = {}
        
        for q_num, q_text in questions.items():
            # Tìm các từ khóa chính trong câu hỏi
            keywords = re.findall(r'\b[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ][a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]+', q_text)
            
            for kw in keywords[:3]:  # Lấy 3 từ khóa đầu
                topics[kw] = topics.get(kw, 0) + 1
        
        return topics
    
    def _create_regenerate_prompt(self, missing_nums: List[int],
                                  original_prompt: str,
                                  existing_questions: Dict[int, str],
                                  existing_topics: Dict[str, int],
                                  question_type: str) -> str:
        """Tạo prompt sinh lại với cơ chế kiểm soát chặt chẽ"""
        
        prompt_parts = [
            "<regeneration_task>",
            "    <role>Bạn là trợ lý AI chuyên sinh câu hỏi chất lượng cao. Nhiệm vụ: sinh CHÍNH XÁC các câu hỏi bị thiếu.</role>",
            "",
            "    <critical_requirements>",
            f"        1. Sinh ĐÚNG {len(missing_nums)} câu với số thứ tự: {', '.join(map(str, missing_nums))}",
            "        2. MỖI câu PHẢI đầy đủ: tiêu đề, nội dung, 4 đáp án, lời giải, giải thích",
            "        3. Nội dung HOÀN TOÀN KHÁC với các câu đã có",
            "        4. BÁM SÁT knowledge_base và allowed_topics",
            "        5. KHÔNG lấy nội dung từ bài khác hoặc lạc đề",
            "    </critical_requirements>",
            "",
            "    <missing_questions>",
            f"        <count>{len(missing_nums)}</count>",
            f"        <numbers>{', '.join(map(str, missing_nums))}</numbers>",
            "    </missing_questions>",
            ""
        ]
        
        # Phân tích chủ đề còn thiếu
        if existing_topics:
            prompt_parts.extend([
                "    <topic_analysis>",
                "        <existing_topics_frequency>",
            ])
            for topic, freq in sorted(existing_topics.items(), key=lambda x: x[1], reverse=True)[:10]:
                prompt_parts.append(f"            <topic name='{topic}' used='{freq}'/>")
            prompt_parts.extend([
                "        </existing_topics_frequency>",
                "        <instruction>Phân bổ câu hỏi mới để cân bằng các chủ đề, ưu tiên các chủ đề ít được sử dụng.</instruction>",
                "    </topic_analysis>",
                ""
            ])
        
        # Mẫu câu hỏi tốt
        prompt_parts.extend([
            "    <example_questions>",
            "        <instruction>Dưới đây là 3 câu hỏi MẪU đã có (để tham khảo format, KHÔNG được sao chép nội dung):</instruction>",
            ""
        ])
        
        sample_questions = list(existing_questions.items())[:3]
        for num, content in sample_questions:
            lines = content.split("\n")[:8]  # Chỉ lấy 8 dòng đầu
            preview = "\n".join(lines)
            prompt_parts.append(f"        <example id='{num}'><![CDATA[\n{preview}\n...]]></example>")
        
        prompt_parts.extend([
            "    </example_questions>",
            "",
            "    <non_duplication_check>",
            "        <instruction>Trước khi sinh mỗi câu, kiểm tra:",
            "            1. Chủ đề có trùng với câu đã có không?",
            "            2. Đáp án có giống với câu đã có không?",
            "            3. Lời giải có tương đồng với câu đã có không?",
            "        Nếu có bất kỳ sự trùng lặp nào, hãy thay đổi hoàn toàn.</instruction>",
            "    </non_duplication_check>",
            "",
            "    <original_prompt_reference>",
            "        <instruction>Tuân thủ nghiêm ngặt các quy tắc format từ prompt gốc:</instruction>",
            f"        <content><![CDATA[\n{original_prompt[:3000]}\n]]></content>",
            "    </original_prompt_reference>",
            "",
            "    <output_format>",
            "        <instruction>Chỉ trả về NỘI DUNG các câu hỏi, không thêm lời mở đầu/kết thúc.</instruction>",
            "        <structure>",
            "            **Câu X:**",
            "            [Nội dung câu hỏi 40-80 từ]",
            "            [HÌNH ẢNH: ...] (nếu cần)",
            "            ",
            "            A. [Đáp án 1]",
            "            B. [Đáp án 2]",
            "            C. [Đáp án 3]",
            "            D. [Đáp án 4]",
            "            **Lời giải:**",
            "            [1-4 hoặc 1010]",
            "            ####",
            "            [Giải thích chi tiết ≥3 dòng]",
            "        </structure>",
            "    </output_format>",
            "",
            "    <generation_instruction>",
            f"        BẮT ĐẦU SINH {len(missing_nums)} CÂU HỎI MỚI NGAY BÂY GIỜ:",
            "    </generation_instruction>",
            "</regeneration_task>"
        ])
        
        return "\n".join(prompt_parts)


def regenerate_missing_questions(missing_nums: List[int], original_prompt: str, 
                                 existing_text: str, project_id: str, creds, 
                                 question_type: str = "tracnghiem") -> str:
    """Hàm tiện ích để sinh lại câu hỏi thiếu"""
    fixer = MissingQuestionFixer(project_id, creds)
    new_questions = fixer.generate_missing_questions(
        missing_nums, original_prompt, existing_text, question_type
    )
    return new_questions