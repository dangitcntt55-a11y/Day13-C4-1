# Template Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

---

## Alert 1 {#alert-1}

- **Tên**: `high_latency_p95`
- **Severity**: Warning
- **SLI/SLO liên quan**: `latency_p95_ms` — SLO: P95 ≤ 3000ms, target 99.5%
- **Điều kiện và thời gian duy trì**: `percentile(latency_ms, 95) > 3000ms` kéo dài liên tục trong **5 phút**
- **Ảnh hưởng tới người dùng**: Phần lớn người dùng (top 5%) phải chờ hơn 3 giây để nhận phản hồi; trải nghiệm tệ, có nguy cơ user timeout hoặc retry storm.
- **Ba bước kiểm tra đầu tiên**:
  1. Mở dashboard panel **Latency** → xác nhận P95 đang vượt ngưỡng và bắt đầu từ lúc nào.
  2. Mở một trace chậm trên Langfuse → so sánh thời gian các span (RAG, LLM, middleware).
  3. Tìm log có cùng correlation ID → xác định span nào bị trì hoãn (ví dụ `rag_slow` incident).
- **Mitigation tạm thời**: Chạy `python scripts/inject_incident.py --scenario rag_slow --disable` nếu đang có incident practice; nếu production thì scale out replica hoặc bật circuit-breaker cho RAG layer.
- **Owner**: `dashboard-slo-team`

---

## Alert 2 {#alert-2}

- **Tên**: `high_error_rate`
- **Severity**: Critical
- **SLI/SLO liên quan**: `error_rate_pct` — SLO: error rate ≤ 2%, target 99.0%
- **Điều kiện và thời gian duy trì**: `count(request_failed) / count(request_received) * 100 > 2%` kéo dài liên tục trong **3 phút**
- **Ảnh hưởng tới người dùng**: Hơn 1/50 request thất bại; người dùng nhận lỗi HTTP 500, mất tin tưởng vào hệ thống và có thể dừng sử dụng dịch vụ.
- **Ba bước kiểm tra đầu tiên**:
  1. Mở dashboard panel **Errors** → kiểm tra error breakdown theo `error_type` để xác định loại lỗi chiếm đa số.
  2. Tìm log `event == "request_failed"` trong khoảng thời gian alert → lấy correlation ID và `error_type`.
  3. Mở trace tương ứng trên Langfuse → xác định span nào raise exception (LLM call, RAG, validation).
- **Mitigation tạm thời**: Nếu lỗi từ LLM timeout → tăng retry và timeout; nếu lỗi từ RAG → tắt incident bằng `inject_incident.py --disable`; nếu lỗi validation → kiểm tra schema input.
- **Owner**: `dashboard-slo-team`

---

## Alert 3 {#alert-3}

- **Tên**: `low_quality_score`
- **Severity**: Warning
- **SLI/SLO liên quan**: `quality_score_avg` — SLO: mean quality ≥ 0.75, target 95.0%
- **Điều kiện và thời gian duy trì**: `mean(quality_score) < 0.75` kéo dài liên tục trong **10 phút**
- **Ảnh hưởng tới người dùng**: Chất lượng câu trả lời suy giảm; người dùng nhận được phản hồi không đủ độ chính xác hoặc liên quan, ảnh hưởng đến giá trị sản phẩm.
- **Ba bước kiểm tra đầu tiên**:
  1. Mở dashboard panel **Quality** → xác nhận trend giảm và thời điểm bắt đầu suy giảm.
  2. Kiểm tra Langfuse → xem prompt version đang active (`prompt_label`) có khớp với phiên bản mong muốn không.
  3. So sánh quality score trước/sau lần đổi label prompt gần nhất → xác định liệu rollback prompt có cải thiện chỉ số không.
- **Mitigation tạm thời**: Rollback về prompt version cũ trên Langfuse bằng cách đổi label `production` về version trước; khởi động lại API để fetch prompt mới.
- **Owner**: `dashboard-slo-team`
