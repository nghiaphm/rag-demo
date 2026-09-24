# PostgreSQL và pgvector

Hệ thống RAG Demo lưu vector trong PostgreSQL phiên bản 16.
Phần mở rộng pgvector dùng để lưu và truy vấn vector, phiên bản cài đặt là 0.8.6.
Mỗi embedding model được lưu trong một table riêng để không trộn vector giữa các model.
Container PostgreSQL map cổng 5432 trong container ra cổng 5433 trên host.
Kết nối database dùng driver psycopg 3 thông qua SQLAlchemy.
