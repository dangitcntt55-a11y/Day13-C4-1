# Khung thiết kế Observability — bản hoàn thiện

Bản điền của [blueprint-template.md](blueprint-template.md), dựng từ code thật trong repo chứ không phải từ ý định thiết kế. Mọi ô trong bảng đều dẫn được về một file/dòng cụ thể; phần nào chưa có trong code thì nằm ở mục [Khoảng trống](#khoảng-trống-đã-phát-hiện) chứ không được ghi lẫn vào bảng như thể đã làm.

Kết quả đo dùng để chốt ngưỡng nằm trong [`../submission/REPORT.md`](../submission/REPORT.md).

---

## 1. Người dùng và luồng chính

### Ai gửi request?

| Nguồn | Đường vào | Ghi chú |
|---|---|---|
| `scripts/load_test.py` | `POST /chat` | 10 câu trong `data/sample_queries.jsonl`, hoặc 5 câu chính thức khi có `--challenge` |
| Lab Coach / người điều tra | `POST /incidents/{name}/enable\|disable` | đổi `app/incidents.py:STATE`, được ghi log ở mức `warning` |
| Người chấm / healthcheck | `GET /health`, `GET /metrics` | không đi qua agent, không sinh trace |

Không có người dùng cuối thật: `app/mock_llm.py` và `app/mock_rag.py` là fake, nên mọi con số cost/token là ước lượng theo công thức trong `app/agent.py:_estimate_cost`, không phải hoá đơn nhà cung cấp.

### Request đi qua những thành phần nào?

```text
client
  │
  ├─(1) CorrelationIdMiddleware            app/middleware.py:12
  │      clear_contextvars() → tránh rò context giữa các request
  │      correlation_id = header x-request-id  hoặc  "req-<8 hex>"
  │      bind_contextvars(correlation_id=...)
  │
  ├─(2) POST /chat                          app/main.py:46
  │      bind_contextvars(user_id_hash, session_id, feature, model, env)
  │      log "request_received"  ← payload đã qua summarize_text()
  │
  ├─(3) LabAgent.run  @observe(as_type="generation")   app/agent.py:29
  │      ├─ retrieve(message)              app/mock_rag.py:14   ← điểm chèn sự cố rag_slow
  │      ├─ resolve_prompt(...)            app/prompt_management.py:30
  │      ├─ FakeLLM.generate(prompt)       app/mock_llm.py
  │      ├─ _heuristic_quality(...)        app/agent.py:98
  │      ├─ update_current_trace / update_current_generation → Langfuse
  │      └─ metrics.record_request(...)    app/metrics.py:15   ← counter trong RAM
  │
  ├─(4) log "response_sent" (hoặc "request_failed" + record_error)
  │
  └─(5) response + header x-request-id, x-response-time-ms
```

Ba đích đến của tín hiệu, mỗi đích có tính chất bền vững khác nhau:

| Đích | File/hệ thống | Bền vững | Dùng để |
|---|---|---|---|
| Log JSON | `data/logs.jsonl` (append-only, `LOG_PATH`) | còn sau khi process chết | nguồn chuẩn của dashboard và của mọi kết luận root cause |
| Trace | Langfuse cloud, tag `day13` | phụ thuộc mạng lúc flush | khoanh vùng span, đối chiếu prompt version |
| Metrics | biến module trong `app/metrics.py` | **mất khi restart** | xem nhanh trong buổi lab, không dùng làm evidence |

### Correlation ID được tạo và truyền ở đâu?

| Bước | Vị trí | Hành vi |
|---|---|---|
| Nhận | `app/middleware.py:18` | ưu tiên header `x-request-id` của client — cho phép nối ID từ tầng trước |
| Sinh | `app/middleware.py:20` | `req-<8 ký tự hex>` khi client không gửi |
| Truyền trong process | `app/middleware.py:23` | `bind_contextvars` → mọi `log.*` sau đó tự có field, không phải truyền tay |
| Trả ra ngoài | `app/middleware.py:31`, `app/main.py:80` | header `x-request-id` **và** field `correlation_id` trong body |
| Dọn | `app/middleware.py:14` | `clear_contextvars()` đầu mỗi request, chặn rò context giữa hai request |

Correlation ID ≠ trace ID. Correlation ID do repo này sinh và chỉ sống trong log; trace ID do Langfuse SDK sinh (ví dụ `cbbe76e20d236ef4fa6bb86b7a5d0696`). Hiện **không có** field nào nối trực tiếp hai ID này — xem [G2](#g2--không-nối-được-correlation_id-với-trace-id).

---

## 2. Tín hiệu quan sát

Cột "đã có" mô tả code hiện tại. Cột "còn thiếu" là đề xuất, chưa được triển khai.

| Thành phần | Log đã có | Metric đã có | Span đã có | Còn thiếu |
|---|---|---|---|---|
| **API** (`app/main.py`, `app/middleware.py`) | `app_started`, `request_received`, `response_sent`, `request_failed`, `incident_enabled/disabled`; mỗi record có `ts`, `level`, `service`, `event`, `correlation_id`, `env`, `user_id_hash`, `session_id`, `feature`, `model` | `traffic`, `error_rate_pct`, `error_breakdown`, `latency_p50/p95/p99` (`app/metrics.py:40`) | span gốc do `@observe` tạo, `user_id`(hash), `session_id`, tags `[lab, day13, day13-chat, <feature>, <model>]` | `http_status`, `route`, `client_latency_ms` (thời gian client thật sự chờ, khác `latency_ms`) |
| **Retrieval** (`app/mock_rag.py`) | — không có event riêng — | — | — không có span riêng — | span `retrieval`, field `doc_count` và cờ `retrieval_miss` trong `response_sent` ([G1](#g1--retrieval-không-có-span-riêng), [G3](#g3--prompt_source-và-doc_count-chỉ-có-trong-trace)) |
| **Prompt** (`app/prompt_management.py`) | — không có field nào — | — | metadata `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source`, `prompt_fetch_error` (`app/agent.py:46-74`) | `prompt_version` + `prompt_source` trong `response_sent` ([G3](#g3--prompt_source-và-doc_count-chỉ-có-trong-trace)) |
| **LLM** (`app/mock_llm.py`, `app/agent.py`) | `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `payload.answer_preview` (đã scrub) | `latency_*`, `avg_cost_usd`, `total_cost_usd`, `tokens_in_total`, `tokens_out_total`, `quality_avg` | generation span: `model`, `usage_details`, `cost_details`, link prompt managed, `doc_count`, `query_preview` | tách `time_to_first_token` khi chuyển sang LLM thật |

Quy ước đặt tên (đang được tuân thủ trong `app/main.py`): event là `snake_case` ở thì quá khứ, mọi nội dung do người dùng nhập nằm dưới `payload.*` để `scrub_event` chỉ phải quét đúng một nhánh (`app/logging_config.py:26`).

### Ba tín hiệu dùng theo thứ tự nào

| Câu hỏi | Tầng | Nguồn cụ thể |
|---|---|---|
| Có đang hỏng không? Hỏng ở chỉ số nào? | Metrics | 6 panel `config/dashboard.yaml`, tính từ `data/logs.jsonl` |
| Hỏng ở bước nào trong một request? | Traces | Langfuse, lọc `tags:day13`, sắp theo latency giảm dần |
| Vì sao bước đó hỏng? | Logs | `data/logs.jsonl`, lọc theo `correlation_id` / `session_id` |

Chiều ngược lại không hoạt động: không thể đi từ một trace về log nếu không có `session_id` trùng, vì trace không mang `correlation_id`.

---

## 3. SLO và alert

Nguồn chuẩn: [`../config/slo.yaml`](../config/slo.yaml) và [`../config/alert_rules.yaml`](../config/alert_rules.yaml); runbook ở [`alerts.md`](alerts.md). Ngưỡng đặt theo quy tắc **objective ≈ 2× p95 quan sát được** để có headroom mà vẫn bắt được hiện tượng nhảy bậc.

| SLI | Mục tiêu | Cửa sổ đo | Alert | Vì sao cần |
|---|---:|---|---|---|
| `latency_p95_ms` | ≤ 3000 ms | 28d, alert `for: 5m`, min 10 response | `HighLatencyP95` (warning) | triệu chứng người dùng chờ lâu |
| `error_rate_pct` | ≤ 2 % | 28d, `for: 5m`, min 20 request | `HighErrorRate` (critical) | mất chức năng, HTTP 500 |
| `daily_cost_usd` | ≤ 2.5 USD | 24h, `for: 15m` | `DailyCostBudgetBurn` (warning) | trần ngân sách ngày |
| `traffic_rate_per_minute` | ≥ 1 req/min | `for: 10m` | `TrafficDropout` (critical) | bịt vùng mù: mẫu số = 0 thì mọi tỷ lệ trông đẹp |
| `quality_score_avg` | ≥ 0.75 | `for: 10m`, min 20 response | `LowQualityScore` (warning) | HTTP 200 nhưng nội dung vô dụng |
| `cost_per_request_usd` | ≤ 0.006 USD | `for: 10m`, min 20 response | `CostPerRequestSpike` (warning) | tách "tăng tải" khỏi "tăng đơn giá" |
| `output_tokens_p95` | ≤ 400 token | `for: 10m`, min 20 response | `OutputTokenBloat` (warning) | nguyên nhân gốc chung của latency + cost |
| `pii_in_output_count` | = 0 | tức thời | `PIIInModelOutput` (critical) | ngưỡng tuân thủ, không phải hiệu năng |

Nguyên tắc đã áp dụng khi viết 8 alert:

1. **Dựa trên triệu chứng, không dựa trên tên sự cố nội bộ.** Không alert nào nhắc `rag_slow`/`tool_fail`/`cost_spike` — sự cố lần sau sẽ không mang tên đó.
2. **Mọi alert tỷ lệ đều có `min_sample`.** Với traffic thấp, 1 lỗi = 100% error rate.
3. **Severity theo hậu quả**: critical = mất chức năng hoặc vi phạm tuân thủ; warning = degradation hoặc ngân sách.
4. **Mỗi alert có owner và runbook 3 bước đầu tiên**, không để người trực tự nghĩ ra cách điều tra lúc 2 giờ sáng.

Hai SLI đã thiết kế nhưng **chưa bật** vì log chưa đủ field, ghi ở `planned_slis` trong `config/slo.yaml`: `prompt_fallback_rate_pct` và `retrieval_grounding_rate_pct`. Xem [G3](#g3--prompt_source-và-doc_count-chỉ-có-trong-trace).

---

## 4. Rủi ro dữ liệu

### PII có thể xuất hiện ở đâu?

| Vị trí | Có PII không | Đã xử lý ra sao |
|---|---|---|
| `body.message` do người dùng gửi | **có** — sample query chứa email, số điện thoại VN, số thẻ test | `summarize_text()` trước khi vào `payload.message_preview` (`app/main.py:59`) |
| `body.user_id` | **có** — định danh trực tiếp | `hash_user_id()` → SHA-256 cắt 12 ký tự, log lưu `user_id_hash`, không lưu `user_id` gốc (`app/main.py:49`) |
| Câu trả lời của model | **có thể** — model nhắc lại PII của input | `summarize_text()` cho `payload.answer_preview` (`app/main.py:76`) |
| Body của exception | **có thể** — `str(exc)` có thể chứa input | vào `payload.detail`, được `scrub_event` quét (`app/main.py:94`) |
| **Response body trả về client** | **có** | ❌ **không được scrub** — xem [G4](#g4--response-body-không-được-scrub) |
| Trace Langfuse | một phần | chỉ gửi `query_preview` đã scrub và `user_id` đã hash |
| `body.session_id` | không | ghi nguyên văn, được coi là ID kỹ thuật |

### Dữ liệu nào được phép ghi vào log?

Cho phép: ID kỹ thuật (`correlation_id`, `session_id`), định danh đã hash (`user_id_hash`), số đo (`latency_ms`, `tokens_*`, `cost_usd`, `quality_score`), phân loại (`feature`, `model`, `env`, `error_type`), và **preview tối đa 80 ký tự đã qua redaction**.

Cấm: `user_id` gốc, message/answer đầy đủ, API key, và bất kỳ chuỗi nào khớp `PII_PATTERNS` (`app/pii.py:6`): `email`, `phone_vn`, `cccd`, `credit_card`, `passport`, `vietnam_address`.

### Redaction diễn ra trước bước nào?

Hai lớp, cố ý chồng lên nhau:

```text
lớp 1 — tại call site:      summarize_text(body.message)      app/main.py:59
        scrub_text() rồi mới cắt 80 ký tự
        ↓ thứ tự này bắt buộc: cắt trước rồi mới scrub sẽ tạo
          chuỗi PII cụt không khớp regex và lọt qua bộ lọc

lớp 2 — trong pipeline:     scrub_event                       app/logging_config.py:26
        quét lại toàn bộ payload.* của mọi event
        ↓ đặt TRƯỚC JsonlFileProcessor trong danh sách processor
          (app/logging_config.py:40-51) — scrub sau khi render JSON
          thì bản đã ghi ra đĩa vẫn còn PII

lớp 3 — kiểm tra độc lập:   scripts/validate_logs.py
        regex riêng, không import app/pii.py, nên không "đồng loã"
        với lỗi trong chính bộ scrub
```

Lớp 2 là lưới an toàn cho code mới quên gọi `summarize_text` ở lớp 1. Cả hai đều chạy trước khi bất kỳ byte nào chạm `data/logs.jsonl`.

---

## Khoảng trống đã phát hiện

Mỗi mục dưới đây là hiện tượng quan sát được, kèm bằng chứng kiểm chứng lại được, không phải phỏng đoán.

### G1 — Retrieval không có span riêng

`retrieve()` chạy bên trong `LabAgent.run`, mà chỉ `run` được bọc `@observe`. Trace vì thế chỉ có **đúng một observation**:

```bash
GET /api/public/observations?traceId=cbbe76e20d236ef4fa6bb86b7a5d0696
→ {"totalItems": 1}   # GENERATION "run", 3.386s, không có con
```

Hệ quả: khi `rag_slow` bật, trace cho biết *request này chậm* nhưng không cho biết *chậm ở retrieval hay ở generation*. Bước "dùng trace để khoanh vùng span bất thường" phải thay bằng suy luận trên code. Fix: bọc `retrieve()` bằng span riêng.

### G2 — Không nối được `correlation_id` với trace ID

`update_current_trace` (`app/agent.py:46`) gửi `user_id`, `session_id`, `tags`, `metadata` — **không gửi `correlation_id`**. Đi từ log sang trace hiện phải nối bằng `session_id` + mốc thời gian, chỉ đúng khi mỗi session có một request. Fix: thêm `correlation_id` vào `metadata` hoặc `tags` của trace.

### G3 — `prompt_source` và `doc_count` chỉ có trong trace

Khi Langfuse lỗi, `resolve_prompt` rơi về template local, đặt `prompt_source="local-fallback"` và vẫn trả HTTP 200 (`app/prompt_management.py:52-81`). Thông tin này **chỉ đi vào trace**, không vào log.

Bằng chứng thật, không phải giả định: trace `cf4d16e8037d62bd0b79c660ef81ee50` có `prompt_source=local-fallback`, `prompt_version=local-v1` trong khi request trả 200 bình thường. Tệ hơn, hai request lúc `05:56:44` và `05:56:45` có log đầy đủ nhưng trace không bao giờ tới Langfuse (xem [G5](#g5--trace-có-thể-mất-log-thì-không)) — với hai request đó, **không tồn tại bất kỳ bản ghi nào** cho biết chúng đã dùng prompt version nào.

Đây chính là lý do `prompt_fallback_rate_pct` và `retrieval_grounding_rate_pct` phải nằm ở `planned_slis` chứ chưa bật được.

### G4 — Response body không được scrub

`scrub_event` chỉ làm sạch log. `ChatResponse.answer` (`app/main.py:79`) trả nguyên văn output của model về client. Nếu model nhắc lại PII của input, log sạch nhưng client vẫn nhận PII. Alert `PIIInModelOutput` được thiết kế để bắt đúng trường hợp này — nó phát hiện `[REDACTED_` trong `answer_preview`, tức là dấu vết cho thấy PII **đã** đi qua model.

### G5 — Trace có thể mất, log thì không

Trong lần chạy 2026-08-11, mạng tới `cloud.langfuse.com` gián đoạn (`Temporary failure in name resolution`). Hai request `req-warm-baseline` (05:56:44) và `req-cp2base2` (05:56:45) có log đầy đủ trong `data/logs.jsonl` nhưng **không có trace nào** trên Langfuse cho session `cp2-baseline-warmup` / `cp2-baseline-2`, trong khi cặp request cùng kịch bản chạy sau đó (`cp2-candidate-warmup`, `cp2-candidate-2`) thì có đủ.

Kết luận thiết kế: **log là nguồn chuẩn, trace là công cụ hỗ trợ**. Đây cũng là lý do `config/dashboard.yaml` lấy nguồn từ `data/logs.jsonl` chứ không từ Langfuse.

### G6 — `latency_ms` không phải thời gian người dùng chờ

`POST /chat` khai báo `async def` nhưng `LabAgent.run` là code đồng bộ chặn (`time.sleep` trong `mock_rag`, generate trong `mock_llm`), nên nó chặn event loop và các request đồng thời bị xếp hàng.

Đo được khi chạy `load_test.py --challenge --concurrency 5` lúc bật `rag_slow`:

| | request 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| `latency_ms` server ghi | 3384 | 2650 | 2651 | 2651 | 2650 |
| thời gian client thật sự chờ | 3444 | 14065 | 14068 | 14069 | 14070 |

Server báo 2.65s trong khi người dùng thứ 5 chờ 14s — đúng bằng tổng thời gian của 5 request nối tiếp. SLO `latency_p95_ms ≤ 3000` tính trên `latency_ms` vì thế **không phản ánh trải nghiệm thật**. Fix: chạy phần chặn trong threadpool (`def` thay vì `async def`, hoặc `run_in_executor`), và ghi thêm `client_latency_ms` từ `x-response-time-ms`.

### G7 — `/metrics` là counter tích luỹ trong RAM

`app/metrics.py` giữ list toàn cục, không có cửa sổ thời gian và mất sạch khi restart. `latency_p95` ở đó là p95 từ lúc khởi động, không phải p95 60 phút gần nhất như `config/dashboard.yaml` yêu cầu. Dùng `/metrics` để xem nhanh thì được; dashboard và evidence phải tính từ `data/logs.jsonl`.
