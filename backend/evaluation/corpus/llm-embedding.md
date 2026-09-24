# LLM và embedding provider

LLM baseline được gọi qua OpenRouter và cấu hình bằng biến LLM_MODEL.
Embedding baseline dùng model gemini-embedding-001 của Google.
Vector của gemini-embedding-001 có 3072 chiều.
Khi đổi embedding model thì phải re-index toàn bộ dữ liệu.
Provider embedding được cấu hình độc lập với provider LLM.
