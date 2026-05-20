# 🧭 SEO Outline Generator

Công cụ tạo outline bài viết SEO tự động:
**Keyword → DataForSEO Top 10 → Crawl Headings → Final Outline (Competitor + AI)**

## Tính năng

- ✅ Lấy Top 10 organic Google qua **DataForSEO API** (lọc sạch social, Wikipedia, spam)
- ✅ **Crawl headings** H1-H4 từ từng URL đối thủ
- ✅ **Claude AI** phân tích gap + tạo outline unique
- ✅ Outline = competitor insights + AI angles không bị trùng lặp
- ✅ Export `.txt` hoặc JSON
- ✅ Hỗ trợ nhiều thị trường (VN, US, UK, AU, SG)

## Deploy lên Streamlit Cloud

### Bước 1: Push lên GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/outline-tool.git
git push -u origin main
```

### Bước 2: Tạo app trên Streamlit Cloud

1. Vào [share.streamlit.io](https://share.streamlit.io)
2. "New app" → chọn repo này
3. Main file: `app.py`
4. Deploy

### Bước 3: Nhập API keys

Trong sidebar của app:
- **DataForSEO Login** (email) + **Password** → lấy tại [dataforseo.com](https://dataforseo.com)
- **Anthropic API Key** → lấy tại [console.anthropic.com](https://console.anthropic.com)

> API keys chỉ tồn tại trong session, không lưu vào đâu cả.

## Cài đặt local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Cấu trúc

```
outline-tool/
├── app.py            # Toàn bộ app (single file)
├── requirements.txt
└── README.md
```

## Luồng xử lý

```
Keyword
  │
  ▼
DataForSEO SERP API (Top 10 organic, lọc social)
  │
  ▼
Crawl headings (H1-H4) từng URL song song
  │
  ▼
Claude AI phân tích:
  - Tổng hợp headings phổ biến từ đối thủ
  - Tìm gaps (sections đối thủ bỏ sót)
  - Tạo outline unique với H2/H3
  - Gợi ý FAQ
  │
  ▼
Final Outline = Competitor insights + AI angles
```

## Notes

- Nếu URL đối thủ chặn crawl (403/Cloudflare), tool sẽ bỏ qua và vẫn tiếp tục
- Crawl timeout mặc định 10s/URL, có thể chỉnh trong sidebar
- Kết quả SERP phụ thuộc vào location/language setting
