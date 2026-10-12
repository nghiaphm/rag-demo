# Qdrant Cloud

Hệ thống RAG Demo dùng Qdrant Cloud làm vector database cho retrieval runtime.
Collection ứng dụng mặc định có tên `rag_documents` và dùng cosine distance.
Evaluation được cô lập trong collection riêng `rag_documents_eval`, không trộn với dữ liệu ứng dụng.
MongoDB Atlas giữ document identity và active version; retriever chỉ cho phép các Qdrant points thuộc active version.
