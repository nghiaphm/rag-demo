# RAG Demo V1 - Ghi chú kỹ thuật

## Vector database
RAG Demo V1 lưu vector trong PostgreSQL phiên bản 16 kèm phần mở rộng pgvector 0.8.6.
Mỗi embedding model được lưu trong một table riêng, ví dụ rag_chunks_gemini_embedding_001.

## Chunking
Chiến lược chunk mặc định là RecursiveCharacterTextSplitter với chunk_size 500 ký tự
và chunk_overlap 50 ký tự. Cả hai giá trị đều được đọc từ file cấu hình, không hard-code.

## Embedding
Embedding baseline dùng model gemini-embedding-001 do Google cung cấp qua API (free tier).
Vector của model này có 3072 chiều. Khi đổi embedding model thì phải re-index toàn bộ dữ liệu.

## LLM
LLM baseline được gọi qua OpenRouter và có thể đổi model bằng biến cấu hình LLM_MODEL
mà không cần sửa pipeline chính.

## Cost control
Dự án ưu tiên model free hoặc free tier ở baseline để giữ chi phí gần 0 trong giai đoạn test.
