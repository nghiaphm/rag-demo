# RAG Demo - Tài liệu mẫu

## 1. RAG là gì?
Retrieval-Augmented Generation (RAG) là kỹ thuật kết hợp giữa truy hồi thông tin
và mô hình ngôn ngữ lớn. Thay vì chỉ dựa vào kiến thức đã học trong tham số,
hệ thống RAG tìm các đoạn tài liệu liên quan tới câu hỏi, rồi đưa chúng vào
prompt để mô hình sinh câu trả lời có căn cứ.

## 2. Kiến trúc của project này
Project được xây theo hướng API-first. LLM được gọi qua OpenRouter, embedding
được gọi qua một provider API hỗ trợ bởi LangChain, và vector được lưu trong
PostgreSQL cùng phần mở rộng pgvector. Docker Compose dùng để chạy database.
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
