# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: warning (nâng lên critical nếu duy trì > 15m hoặc p99 > 5000ms)
- SLI/SLO liên quan: `latency_p95_ms` — objective 3000ms, target 99.5% (`config/slo.yaml`)
- Điều kiện và thời gian duy trì: p95 của `latency_ms` trên event `response_sent` > 3000ms, duy trì 5 phút, tối thiểu 10 response trong cửa sổ.
- Ảnh hưởng tới người dùng: người dùng chờ quá 3 giây mới nhận được câu trả lời; ở p99 nhiều request có nguy cơ chạm timeout 30s của client (`scripts/load_test.py`). Hệ thống vẫn trả lời đúng nhưng chậm — đây là degradation, không phải outage.
- Ba bước kiểm tra đầu tiên:
  1. `curl -s localhost:8000/metrics` — so sánh `latency_p50` với `latency_p95`. Nếu p50 vẫn thấp mà p95/p99 cao thì chỉ một phần request bị chậm (nghi vấn một dependency cụ thể), còn nếu cả p50 tăng thì toàn bộ pipeline chậm.
  2. Khoanh vùng theo `feature` để biết degradation có giới hạn ở một luồng không:
     `jq -r 'select(.event=="response_sent") | "\(.feature) \(.latency_ms)"' data/logs.jsonl | sort | uniq -c`
  3. Lấy `correlation_id` của một request chậm rồi mở trace tương ứng trong Langfuse, xem span nào chiếm phần lớn thời gian (retrieval hay generation):
     `jq -r 'select(.event=="response_sent" and .latency_ms>3000) | .correlation_id' data/logs.jsonl | head`
- Mitigation tạm thời: giảm tải phía dependency chậm (hạ số document retrieve hoặc bật cache), thông báo degradation cho người dùng, và chỉ rollback prompt/model version nếu mốc thời gian bắt đầu chậm trùng với lần đổi version.
- Owner: Đặng Thái Nam Sơn

## Alert 2

- Tên: `HighErrorRate`
- Severity: critical
- SLI/SLO liên quan: `error_rate_pct` — objective 2%, target 99.0% (`config/slo.yaml`)
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100` > 2%, duy trì 5 phút, tối thiểu 20 request trong cửa sổ. Ngưỡng mẫu tối thiểu là bắt buộc: với traffic thấp một request lỗi đã thành 100% error rate.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 và không có câu trả lời nào. Đây là mất chức năng trực tiếp, nghiêm trọng hơn Alert 1 nên để severity critical.
- Ba bước kiểm tra đầu tiên:
  1. `curl -s localhost:8000/metrics` — đọc `error_rate_pct` và `error_breakdown`. `error_breakdown` cho biết loại exception đang chiếm đa số.
  2. Xem log lỗi thật kèm correlation ID để tái hiện:
     `jq -r 'select(.event=="request_failed") | "\(.correlation_id) \(.error_type) \(.payload.detail)"' data/logs.jsonl | tail -20`
  3. Kiểm tra lỗi tập trung ở một `feature`/`model` hay rải đều — nếu chỉ một nhánh thì nghi vấn dependency của nhánh đó, nếu rải đều thì nghi vấn thay đổi chung (deploy, config, credential hết hạn).
- Mitigation tạm thời: rollback về version prompt/model gần nhất còn ổn định, bật fallback trả lời an toàn thay vì 500, và nếu lỗi đến từ một tool phụ thì tạm ngắt tool đó để giữ luồng chính hoạt động.
- Owner: Đặng Thái Nam Sơn

## Alert 3

- Tên: `DailyCostBudgetBurn`
- Severity: warning
- SLI/SLO liên quan: `daily_cost_usd` — objective 2.5 USD/ngày (`config/slo.yaml`)
- Điều kiện và thời gian duy trì: `sum(cost_usd)` trên event `response_sent` trong 24h > 2.5 USD, duy trì 15 phút trước khi bắn.
- Ảnh hưởng tới người dùng: không có tác động trực tiếp tới người dùng — đây là triệu chứng ngân sách, nên để warning và xử lý trong giờ làm việc thay vì gọi page ban đêm. Rủi ro thật là hết ngân sách dẫn tới bị nhà cung cấp chặn, lúc đó mới thành outage.
- Ba bước kiểm tra đầu tiên:
  1. `curl -s localhost:8000/metrics` — so sánh `total_cost_usd`, `avg_cost_usd` và `traffic`. Nếu `traffic` tăng mà `avg_cost_usd` giữ nguyên thì là tăng tải bình thường; nếu `avg_cost_usd` tăng thì mỗi request đang đắt lên bất thường.
  2. Kiểm tra token có phình không (nguyên nhân phổ biến nhất khi giá mỗi request tăng):
     `jq -r 'select(.event=="response_sent") | "\(.tokens_in) \(.tokens_out)"' data/logs.jsonl | tail -20`
  3. Đối chiếu thời điểm chi phí tăng với lần đổi prompt version hoặc model — prompt dài hơn hoặc model đắt hơn đều làm `avg_cost_usd` nhảy bậc.
- Mitigation tạm thời: rollback về prompt version ngắn hơn, đặt trần `max_tokens` cho output, hoặc hạ model xuống bậc rẻ hơn cho các feature không cần chất lượng cao nhất.
- Owner: Đặng Thái Nam Sơn

## Alert 4

- Tên: `LowQualityScore`
- Severity: warning
- SLI/SLO liên quan: `quality_score_avg` — objective 0.75, target 95% (`config/slo.yaml`)
- Điều kiện và thời gian duy trì: `mean(quality_score)` trên event `response_sent` < 0.75, duy trì 10 phút, tối thiểu 20 response.
- Ảnh hưởng tới người dùng: đây là chế độ hỏng đặc thù của LLM — hệ thống trả HTTP 200, latency bình thường, chi phí bình thường, nhưng **nội dung câu trả lời vô dụng**. Alert 1 và Alert 2 đều không bắt được trường hợp này. Người dùng nhận được câu trả lời sai hoặc lạc đề mà mọi metric hạ tầng vẫn xanh.
- Ba bước kiểm tra đầu tiên:
  1. Xác nhận mức tụt và phân bố điểm:
     `jq -r 'select(.event=="response_sent") | .quality_score' data/logs.jsonl | sort -n | uniq -c`
  2. Khoanh vùng theo `feature` — điểm thấp tập trung ở một feature nghĩa là corpus của feature đó không khớp câu hỏi:
     `jq -r 'select(.event=="response_sent") | "\(.feature) \(.quality_score)"' data/logs.jsonl | sort | uniq -c`
  3. Đọc `_heuristic_quality` trong `app/agent.py` để biết thành phần nào kéo điểm xuống: thiếu doc (-0.2), câu trả lời quá ngắn (-0.1), hoặc có `[REDACTED` trong answer (-0.2). Nếu nguyên nhân là `[REDACTED` thì xử lý theo Alert 8 trước.
- Mitigation tạm thời: rollback prompt về version có điểm tốt hơn, và nếu điểm thấp do retrieval không khớp thì bổ sung document cho feature đó. Cảnh báo: `quality_score` là heuristic nội bộ, không phải đánh giá của con người — trước khi kết luận, hãy đọc vài `answer_preview` thật để xác nhận chất lượng đúng là có giảm chứ không phải heuristic bị lệch.
- Owner: Đặng Thái Nam Sơn

## Alert 5

- Tên: `TrafficDropout`
- Severity: critical
- SLI/SLO liên quan: `traffic_rate_per_minute` — panel `traffic` (`config/dashboard.yaml`), threshold `rate_per_minute >= 1`
- Điều kiện và thời gian duy trì: `count(request_received)` theo phút < 1, duy trì 10 phút.
- Ảnh hưởng tới người dùng: không ai gọi được service. Đây là alert quan trọng nhất mà đa số nhóm bỏ sót, vì **nó bắt đúng vùng mù của Alert 2**: nếu service chết hoàn toàn thì không có request nào, mà không có request thì không có lỗi, nên `error_rate_pct` bằng 0 và Alert 2 im lặng. Mọi metric "tỷ lệ" đều trông khỏe mạnh khi mẫu số bằng 0.
- Ba bước kiểm tra đầu tiên:
  1. `curl -s localhost:8000/health` — phân biệt "app chết" với "app sống nhưng không có traffic tới".
  2. Xem log còn được ghi không (nếu file đứng im thì process đã dừng hoặc mất quyền ghi):
     `ls -la data/logs.jsonl && tail -3 data/logs.jsonl`
  3. Nếu app sống mà không có request, kiểm tra tầng phía trước: process có bind đúng cổng không (`ss -ltnp | grep 8000`), client/load generator có đang chạy không.
- Mitigation tạm thời: khởi động lại service, và xác nhận bằng một request thật (`scripts/load_test.py`) chứ không chỉ dựa vào `/health`. Nếu nguyên nhân là mất quyền ghi log thì service có thể vẫn phục vụ được nhưng đang chạy mù — ưu tiên khôi phục logging.
- Owner: Đặng Thái Nam Sơn

## Alert 6

- Tên: `CostPerRequestSpike`
- Severity: warning
- SLI/SLO liên quan: `cost_per_request_usd` — objective 0.006 USD (`config/slo.yaml`, ~2x p95 quan sát 0.0027)
- Điều kiện và thời gian duy trì: `mean(cost_usd)` trên event `response_sent` > 0.006 USD, duy trì 10 phút, tối thiểu 20 response.
- Ảnh hưởng tới người dùng: không trực tiếp, nhưng đây là cảnh báo **sớm** hơn Alert 3. Alert 3 chỉ bắn khi đã tiêu hết 2.5 USD/ngày; alert này bắn ngay khi đơn giá mỗi request tăng bất thường, tức trước khi ngân sách bị đốt hết. Tách hai alert vì tăng traffic (bình thường) và tăng đơn giá (bất thường) đòi hỏi hành động khác nhau.
- Ba bước kiểm tra đầu tiên:
  1. `curl -s localhost:8000/metrics` — nếu `avg_cost_usd` tăng mà `traffic` không tăng thì chắc chắn là đơn giá, không phải tải.
  2. Tách phần input và output để biết bên nào phình (công thức giá ở `_estimate_cost`, `app/agent.py`: output đắt gấp 5 lần input):
     `jq -r 'select(.event=="response_sent") | "\(.tokens_in) \(.tokens_out) \(.cost_usd)"' data/logs.jsonl | tail -20`
  3. Kiểm tra `model` có bị đổi sang bậc đắt hơn không:
     `jq -r 'select(.event=="response_sent") | .model' data/logs.jsonl | uniq -c`
- Mitigation tạm thời: nếu `tokens_in` phình thì cắt bớt số document đưa vào prompt; nếu `tokens_out` phình thì xử lý theo Alert 7; nếu do đổi model thì rollback về model cũ.
- Owner: Đặng Thái Nam Sơn

## Alert 7

- Tên: `OutputTokenBloat`
- Severity: warning
- SLI/SLO liên quan: `output_tokens_p95` — objective 400 token (`config/slo.yaml`, ~2x p95 quan sát 173)
- Điều kiện và thời gian duy trì: `percentile(tokens_out, 95)` > 400, duy trì 10 phút, tối thiểu 20 response.
- Ảnh hưởng tới người dùng: câu trả lời dài lê thê, khó đọc, và thời gian chờ tăng theo. Đây là **nguyên nhân gốc chung** của cả Alert 1 và Alert 6: token output nhiều thì vừa sinh lâu (latency) vừa đắt (cost, giá output gấp 5 lần input). Bắt được ở đây thì thường không phải chờ hai alert kia bắn.
- Ba bước kiểm tra đầu tiên:
  1. Xác nhận phân bố token output đã dịch lên thật sự:
     `jq -r 'select(.event=="response_sent") | .tokens_out' data/logs.jsonl | sort -n | tail -20`
  2. Đối chiếu với thời điểm đổi prompt version — prompt mới yêu cầu "giải thích chi tiết" là nguyên nhân phổ biến nhất.
  3. Kiểm tra tương quan với `latency_ms` và `cost_usd` để xác nhận đúng là một hiện tượng chứ không phải ba sự cố rời rạc:
     `jq -r 'select(.event=="response_sent") | "\(.tokens_out) \(.latency_ms) \(.cost_usd)"' data/logs.jsonl | tail -20`
- Mitigation tạm thời: đặt trần `max_tokens` cho output, và thêm ràng buộc độ dài vào prompt. Lưu ý `_heuristic_quality` cộng điểm khi answer dài hơn 40 ký tự, nên siết quá tay có thể kéo `quality_score` xuống và làm Alert 4 bắn — chỉnh từ từ và theo dõi cả hai.
- Owner: Đặng Thái Nam Sơn

## Alert 8

- Tên: `PIIInModelOutput`
- Severity: critical
- SLI/SLO liên quan: `pii_in_output_count` — objective 0 (`config/slo.yaml`), ngưỡng tuân thủ tuyệt đối
- Điều kiện và thời gian duy trì: xuất hiện `[REDACTED_` trong `payload.answer_preview` của event `response_sent`. Không có thời gian duy trì và không có `min_sample` — một lần là đủ để điều tra.
- Ảnh hưởng tới người dùng: PII của người dùng bị model nhắc lại trong câu trả lời. Redaction đã chặn được ở tầng log, nhưng dấu `[REDACTED_` nằm trong *answer* nghĩa là PII **đã đi qua model và đã nằm trong response trả về cho client** — nơi không có bộ lọc nào. Đây là rủi ro rò rỉ dữ liệu và tuân thủ, nên để critical dù không ảnh hưởng tới tính khả dụng.
- Ba bước kiểm tra đầu tiên:
  1. Tách rõ PII ở chiều vào (người dùng gửi lên, chấp nhận được) và chiều ra (model nhắc lại, không chấp nhận được):
     `jq -r 'select(.event=="response_sent" and (.payload.answer_preview | test("\\[REDACTED_"))) | "\(.correlation_id) \(.payload.answer_preview)"' data/logs.jsonl`
  2. Lấy `correlation_id` ở bước 1, truy ngược `request_received` tương ứng để biết PII vào hệ thống từ đâu.
  3. Xác định loại PII từ hậu tố marker (`_EMAIL`, `_PHONE_VN`, `_CCCD`, `_CREDIT_CARD`, `_PASSPORT`) và đối chiếu với `PII_PATTERNS` trong `app/pii.py` để biết pattern nào đang khớp.
- Mitigation tạm thời: thêm bước scrub cho response trước khi trả về client (hiện `scrub_event` trong `app/logging_config.py` chỉ làm sạch log, **không** làm sạch response body), và bổ sung chỉ dẫn vào prompt yêu cầu model không nhắc lại thông tin cá nhân. Kiểm tra thêm liệu PII có bị lưu ở nơi khác ngoài log không (trace Langfuse, cache).
- Owner: Đặng Thái Nam Sơn
