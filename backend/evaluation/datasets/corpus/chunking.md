# Chiến lược chunking

Chiến lược chia văn bản mặc định là RecursiveCharacterTextSplitter.
Giá trị mặc định của chunk_size là 500 ký tự.
Giá trị mặc định của chunk_overlap là 50 ký tự.
Hai giá trị này được đọc từ file cấu hình, không hard-code trong code.
Chunk quá lớn làm loãng ngữ cảnh, còn chunk quá nhỏ làm mất ngữ cảnh.
