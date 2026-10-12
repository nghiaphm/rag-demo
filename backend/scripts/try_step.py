"""Script test thủ công cho Phase 1: file -> LangChain Document -> chunks.

Cách chạy (khuyến nghị chạy từ project root):
    python backend/scripts/try_step.py [duong_dan_file]

Nếu không truyền đường dẫn, script tự tạo fixture `sample_rag.md` trong
`backend/fixtures/` (không dùng thư mục runtime `data/documents/`), sau đó load
và split để in ra số document, số chunk và metadata của chunk đầu tiên.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "fixtures"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Console Windows mặc định dùng cp1252 nên không in được tiếng Việt.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.rag.loader import load_document
from app.rag.splitter import split_documents

SAMPLE_FILE_NAME = "sample_rag.md"

SAMPLE_CONTENT = """# RAG Demo - Tài liệu mẫu

## 1. RAG là gì?
Retrieval-Augmented Generation (RAG) là kỹ thuật kết hợp giữa truy hồi thông tin
và mô hình ngôn ngữ lớn. Thay vì chỉ dựa vào kiến thức đã học trong tham số,
hệ thống RAG tìm các đoạn tài liệu liên quan tới câu hỏi, rồi đưa chúng vào
prompt để mô hình sinh câu trả lời có căn cứ.

## 2. Kiến trúc của project này
Project được xây theo hướng API-first. LLM được gọi qua OpenRouter, embedding
được gọi qua một provider API hỗ trợ bởi LangChain, và vector được lưu trong
MongoDB Atlas giữ metadata và active version; Qdrant Cloud lưu vector retrieval.
Toàn bộ V1 thao tác qua terminal, script và HTTP API, chưa có frontend.

## 3. Document ingestion
Giai đoạn ingestion gồm ba bước chính. Bước một là load file thành đối tượng
Document của LangChain. Bước hai là chia nhỏ văn bản thành các chunk bằng
RecursiveCharacterTextSplitter. Bước ba là tạo embedding và lưu vào vector store.
Phase 1 của project chỉ thực hiện hai bước đầu tiên.

## 4. Chunking
Chunk quá lớn có thể làm loãng thông tin đưa vào prompt, còn chunk quá nhỏ có
thể làm mất ngữ cảnh. Vì vậy cần cân bằng giữa chunk_size và chunk_overlap.
Giá trị mặc định của project là chunk_size 500 ký tự và chunk_overlap 50 ký tự,
và cả hai đều lấy từ file cấu hình thay vì hard-code trong code.

## 5. Retrieval
Retriever chịu trách nhiệm tìm ra top_k chunk gần nhất với câu hỏi của người
dùng. Độ tương đồng thường được tính bằng khoảng cách cosine giữa vector câu hỏi
và vector của từng chunk. Việc lựa chọn top_k ảnh hưởng trực tiếp tới chất lượng
câu trả lời và chi phí gọi API.

## 6. Sinh câu trả lời
Sau khi truy hồi được context, hệ thống ghép context đó với câu hỏi và một
system instruction. Prompt bắt buộc mô hình chỉ sử dụng thông tin trong context,
không được bịa nguồn, và phải nói rõ khi tài liệu không chứa câu trả lời.

## 7. Đánh giá
Đánh giá chất lượng RAG không chỉ là kiểm tra xem mô hình có trả lời hay không.
Cần đo mức độ liên quan của câu trả lời, mức độ trung thành với tài liệu nguồn,
và độ chính xác của bước truy hồi. Project sẽ dùng một golden set nhỏ nhưng có
chất lượng, chạy lặp lại được để so sánh các cấu hình khác nhau.

## 8. Ghi chú
Tài liệu mẫu này chỉ dùng để kiểm thử pipeline load và split. Nội dung không
đại diện cho bất kỳ tài liệu sản phẩm nào.
"""


def _ensure_sample_file() -> Path:
    """Tạo fixture trong `backend/fixtures/` nếu chưa tồn tại và trả về đường dẫn.

    Fixture được tách khỏi thư mục runtime `data/documents/` để không lẫn với
    dữ liệu demo/upload.
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    sample_path = FIXTURES_DIR / SAMPLE_FILE_NAME
    if not sample_path.exists():
        sample_path.write_text(SAMPLE_CONTENT, encoding="utf-8")
    return sample_path


def main() -> None:
    """Load + split file được truyền vào, hoặc file mẫu, rồi in kết quả."""
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
    else:
        file_path = _ensure_sample_file()

    documents = load_document(file_path)
    chunks = split_documents(documents)

    print(f"File              : {file_path}")
    print(f"Số document       : {len(documents)}")
    print(f"Số chunk          : {len(chunks)}")
    print(f"chunk_size/overlap: {settings.chunk_size}/{settings.chunk_overlap}")

    if documents:
        print(f"Metadata doc[0]   : {documents[0].metadata}")
    if chunks:
        print(f"Metadata chunk[0] : {chunks[0].metadata}")
        preview = chunks[0].page_content[:200].replace("\n", " ")
        print(f"Chunk[0] preview  : {preview}...")


if __name__ == "__main__":
    main()
