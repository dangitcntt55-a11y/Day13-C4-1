# Báo cáo Day 13 Observability

Thiết kế đầy đủ nằm ở [`docs/observability-blueprint.md`](../docs/observability-blueprint.md). Báo cáo này chỉ ghi **kết quả đo được**; mỗi nhận định đều dẫn về một trace ID, một dòng log hoặc một file cụ thể.

Toàn bộ số liệu dưới đây đến từ một lần chạy end-to-end ngày **2026-08-11, 05:54–06:57 UTC (12:54–13:57 +0700)**, không phải gộp nhiều lần chạy rời rạc.

## 1. Thông tin nhóm

- Tên nhóm: C4-1 *(suy ra từ tên repo `Day13-C4-1` — sửa lại nếu nhóm có tên chính thức khác)*
- Repository URL: https://github.com/dangitcntt55-a11y/Day13-C4-1
- Commit SHA cuối: `c6dab22cb32c2d1a039d0099f0324c2b36035a7c` *(HEAD lúc viết báo cáo — **cập nhật lại sau commit cuối cùng trước khi nộp**)*
- Upstream: https://github.com/VinUni-AI20k/Day13-K3-Observability
- Thành viên và vai trò: xem [mục 7](#7-đóng-góp-cá-nhân) (đối chiếu trực tiếp với `git log`)

## 2. Kết quả kỹ thuật

| Hạng mục | Kết quả | Cách kiểm chứng |
|---|---|---|
| `python scripts/validate_logs.py` | **100/100** — 4/4 check PASSED | `submission/evidence/log_validation.txt` |
| Bản ghi log phân tích | 115 record, 53 correlation ID duy nhất | cùng file |
| Record thiếu field bắt buộc | 0 | cùng file |
| Record thiếu enrichment | 0 | cùng file |
| PII leak còn lại | **0** | cùng file + `sample_logs.txt` |
| `python scripts/validate_dashboard.py` | **HỢP LỆ: 6/6 panel** | `submission/evidence/dashboard_validation.txt` |
| `python -m pytest -q` | **22 passed** | chạy lại tại repo root |
| Traces trên Langfuse (`tags:day13`) | **38 trace** (yêu cầu tối thiểu 10) | `submission/evidence/traces_list.txt` |
| Prompt version trên Langfuse | **10 version** của `day13-chat` | `submission/evidence/prompt_versions.txt` |
| Link/đường dẫn dashboard | ⚠️ **chưa có dashboard runtime** — xem [mục 5](#5-dashboard-slo-và-alerts) | — |

### Ghi chú về tính toàn vẹn của evidence

`data/logs.jsonl` là file append-only và **không được track trong git** (xem `.gitignore`), nên nó tích luỹ output qua nhiều lần chạy. Không record nào bị xoá hoặc sửa trong suốt bài lab.

Lần validate đầu tiên cho 50/100 vì file còn chứa 20 record sinh lúc `03:44:xx UTC` (= 10:44 +0700) — tức **trước** commit `45ddb4b` "feat(observability): implement correlation IDs, log context, and PII scrubbing" (10:58 +0700). Những record đó thiếu `correlation_id` và 4 field enrichment vì code lúc ấy chưa có phần này.

Xử lý: **không xoá và không sửa** record nào. Toàn bộ file cũ được lưu nguyên vẹn tại `data/logs.archive-preimpl.jsonl` (47 record, có track trong git) để đối chiếu, rồi evidence được sinh lại bằng cách chạy thật với code hiện tại:

```bash
# CP2 — prompt A/B: khởi động lại API với từng label, gửi cùng một input
LANGFUSE_PROMPT_LABEL=baseline  uvicorn app.main:app   # → req-cp2base3
LANGFUSE_PROMPT_LABEL=candidate uvicorn app.main:app   # → req-cp2cand2

# Baseline dashboard
python scripts/load_test.py --concurrency 5            # 10 request

# CP3 — challenge, đo before/after trên hai process sạch
python scripts/load_test.py --challenge --concurrency 5   # incident OFF
python scripts/inject_incident.py                         # bật rag_slow
python scripts/load_test.py --challenge --concurrency 5   # incident ON
python scripts/inject_incident.py --disable

python scripts/validate_logs.py        # 100/100
python scripts/validate_dashboard.py   # 6/6
```

Mỗi phase before/after chạy trên một process mới để `/metrics` (counter tích luỹ trong RAM, `app/metrics.py`) không lẫn số liệu giữa hai phase.

## 3. Logging và tracing

### Evidence correlation ID

`submission/evidence/sample_logs.txt`. Một request sinh đúng hai record cùng `correlation_id`, ví dụ `req-b4fa75e9` (session `k3-challenge-s01`):

```json
{"event":"request_received","correlation_id":"req-b4fa75e9","session_id":"k3-challenge-s01","user_id_hash":"026c7a407135","feature":"refund","model":"claude-sonnet-4-5","env":"dev","service":"api","level":"info","ts":"2026-08-11T05:54:53.347...Z"}
{"event":"response_sent","correlation_id":"req-b4fa75e9","latency_ms":150,"tokens_in":29,"tokens_out":156,"cost_usd":0.002427,"quality_score":0.9,...}
```

Cơ chế: `CorrelationIdMiddleware` (`app/middleware.py:12`) đọc header `x-request-id` nếu client gửi, nếu không thì sinh `req-<8 hex>`, rồi `bind_contextvars` để mọi log sau đó tự mang field. `clear_contextvars()` ở đầu mỗi request chặn rò context giữa hai request. ID cũng được trả ra ngoài qua header `x-request-id` và field `correlation_id` trong response body — nhờ vậy các request thủ công trong lần chạy này đặt được ID có ý nghĩa (`req-cp2base3`, `req-cp2cand2`).

### Evidence PII redaction

`submission/evidence/sample_logs.txt`, 3 loại PII trong `data/sample_queries.jsonl` đều bị che, `validate_logs.py` báo 0 leak:

| Input gốc (trong `data/sample_queries.jsonl`) | Ghi vào log | correlation_id |
|---|---|---|
| `...My email is student@vinuni.edu.vn` | `...My email is [REDACTED_EMAIL]` | `req-3e005f9e` |
| `Here is my phone 0987654321, ...` | `Here is my phone [REDACTED_PHONE_VN], ...` | `req-3dd4864b` |
| `...credit card 4111 1111 1111 1111?` | `...credit card [REDACTED_CREDIT_CARD]?` | `req-1617b743` |

`user_id` gốc không bao giờ vào log — chỉ có `user_id_hash` (SHA-256 cắt 12 ký tự, `app/pii.py:29`).

Hai chi tiết về thứ tự xử lý, cả hai đều là lỗi kinh điển nếu làm ngược:

1. `summarize_text()` **scrub trước rồi mới cắt 80 ký tự** (`app/pii.py:24`). Cắt trước sẽ tạo chuỗi PII cụt không khớp regex và lọt lưới.
2. `scrub_event` được đặt **trước** `JsonlFileProcessor` trong danh sách processor (`app/logging_config.py:40-51`). Scrub sau khi render JSON thì bản đã ghi ra đĩa vẫn còn PII.

`scripts/validate_logs.py` dùng bộ regex riêng, **không import `app/pii.py`**, nên nó không "đồng loã" với lỗi trong chính bộ scrub của mình.

### Evidence trace waterfall

`submission/evidence/trace_waterfall.png` (danh sách trace, filter `tags:day13`) và `submission/evidence/trace_sample.txt` (waterfall chi tiết lấy từ Langfuse API).

Trace chậm nhất của challenge: **`cbbe76e20d236ef4fa6bb86b7a5d0696`** — session `k3-challenge-s01`, `2026-08-11T05:55:03.655Z → 05:55:07.041Z`, latency **3.386s**.

### Giải thích một span đáng chú ý

So sánh hai trace **cùng session, cùng câu hỏi, cùng prompt version 9, cùng `doc_count=1`**, chỉ khác trạng thái incident:

| | trace `618fb6e6e2dc6bedbde5ccb42771e7a2` | trace `cbbe76e20d236ef4fa6bb86b7a5d0696` |
|---|---|---|
| Thời điểm | 05:54:53.348Z (incident OFF) | 05:55:03.655Z (incident ON) |
| Span `run` (GENERATION) | **0.150s** | **3.386s** |
| `doc_count` | 1 | 1 |
| `prompt_version` / `prompt_label` | 9 / production | 9 / production |
| Số observation trong trace | 1 | 1 |

Chênh lệch 3.236s nằm gọn trong một span duy nhất, trong khi mọi biến số khác giữ nguyên → loại trừ được prompt version, retrieval miss và kích thước output.

**Nhưng span này chưa đủ để kết luận root cause.** Trace chỉ có đúng một observation:

```bash
GET /api/public/observations?traceId=cbbe76e20d236ef4fa6bb86b7a5d0696
→ {"totalItems": 1}      # GENERATION "run", không có span con
```

`retrieve()` chạy bên trong `LabAgent.run` mà chỉ `run` được bọc `@observe` (`app/agent.py:29`), nên retrieval không có span riêng. Trace nói được "request này chậm" chứ chưa nói được "chậm ở retrieval hay generation" — phải xuống log và code mới chốt được (xem [mục 6](#6-điều-tra-challenge)). Đây là khoảng trống G1 trong blueprint và là preventive measure số 1.

## 4. Prompt versioning

- Prompt name: `day13-chat` (`LANGFUSE_PROMPT_NAME`), hiện có **10 version** trên Langfuse
- Version/label baseline: **version 9**, label `baseline` + `production`
- Version/label candidate: **version 10**, label `candidate` + `latest`
- Khác biệt giữa hai version (đúng yêu cầu "một thay đổi nhỏ về format"):
  - v9: `Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}`
  - v10: `Feature={{feature}}\nDocs={{docs}}\nUser Question={{message}}`

### Trace ID của mỗi version

Cùng một input (`feature=monitoring`, `message="Explain why metrics traces and logs work together"`), khác nhau duy nhất ở `LANGFUSE_PROMPT_LABEL` khi khởi động API:

| | Baseline | Candidate |
|---|---|---|
| **Trace ID** | `99c0460f55cddd60fbb09cf0d8ee89a4` | `5e8d2948327a583a0438525fc42608eb` |
| `correlation_id` | `req-cp2base3` | `req-cp2cand2` |
| `session_id` | `cp2-baseline-3` | `cp2-candidate-2` |
| `prompt_label` | `baseline` | `candidate` |
| `prompt_version` | **9** | **10** |
| `prompt_source` | `langfuse` | `langfuse` |
| Thời điểm | 2026-08-11T06:57:14.275Z | 2026-08-11T05:57:02.096Z |

Trace metadata hiển thị đủ `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source`, `doc_count`, `query_preview` — xem `submission/evidence/prompt_versions.txt` (số liệu lấy qua API cho đúng cặp trace ở trên) và `submission/evidence/trace_v2.png`.

Lưu ý về ảnh: `trace_v2.png` chụp panel Metadata của một trace **thuộc lần chạy sớm hơn** (`prompt_version: 5`, `prompt_label: production`), nên nó chứng minh *trace có mang đủ các field prompt*, chứ không phải chứng minh cặp v9/v10 ở bảng trên. Bằng chứng cho cặp v9/v10 là hai trace ID kèm giá trị metadata lấy trực tiếp từ API.

### Bằng chứng đổi label / rollback

`submission/evidence/label_rollback.png` — danh sách version trên Langfuse UI sau khi rollback: `#2` giữ label `candidate`, `#1` được trả lại label `production` + `baseline`.

Trạng thái label hiện tại kiểm chứng lại được bất kỳ lúc nào qua API, và nó chứng minh label đã dịch chuyển khỏi version cũ:

```bash
GET /api/public/v2/prompts/day13-chat?version=9   → labels: ["baseline","production"]
GET /api/public/v2/prompts/day13-chat?version=10  → labels: ["candidate","latest"]
GET /api/public/v2/prompts/day13-chat?version=1   → labels: []      # production đã rời khỏi v1
```

⚠️ **Hạn chế của evidence này, ghi rõ để không bị hiểu nhầm:** ảnh `label_rollback.png` chụp cặp version `#1`/`#2` từ vòng chạy `scripts/role2_setup.py` đầu tiên, còn cặp version đang hoạt động là `#9`/`#10` (script được chạy 5 lần, mỗi lần tạo thêm 2 version). Ảnh chỉ ghi lại **trạng thái sau rollback**, chưa có ảnh trạng thái trước đó. Muốn evidence đầy đủ thì trên Langfuse UI: chuyển `production` sang v10 → chụp ảnh → rollback `production` về v9 → chụp ảnh, đặt tên `label_promotion.png` và `label_rollback_v9.png`.

### Phát hiện thêm: prompt fallback không để lại dấu vết trong log

Trace `cf4d16e8037d62bd0b79c660ef81ee50` (session `cp2-baseline`, 05:54:15Z) có `prompt_source=local-fallback`, `prompt_version=local-v1` — Langfuse fetch quá `fetch_timeout_seconds=2` nên `resolve_prompt` âm thầm rơi về template local (`app/prompt_management.py:52`) và request vẫn trả **HTTP 200** với latency 3.441s.

Nặng hơn: hai request `req-warm-baseline` (05:56:44) và `req-cp2base2` (05:56:45) có log đầy đủ nhưng trace không bao giờ tới Langfuse do mạng đứt (`Temporary failure in name resolution`), trong khi cặp request cùng kịch bản chạy ngay sau đó (`cp2-candidate-warmup`, `cp2-candidate-2`) có đủ trace. Với hai request đó, **không tồn tại bản ghi nào** cho biết chúng đã dùng prompt version nào — vì `prompt_source`/`prompt_version` chỉ được gửi sang trace, không được ghi vào log.

Đây là bằng chứng thực nghiệm cho `planned_slis.prompt_fallback_rate_pct` trong `config/slo.yaml`: prompt đổi mà không ai biết là sự cố LLM-ops điển hình và **không SLI nào đang bật bắt được nó**. Fix: ghi `prompt_version`, `prompt_source`, `prompt_fetch_error` vào event `response_sent`.

## 5. Dashboard, SLO và alerts

### Kết quả `validate_dashboard.py`

```text
HỢP LỆ: 6/6 panel có trong dashboard contract.
```

### Giá trị đo thật đối chiếu threshold

Tính từ `data/logs.jsonl`, cửa sổ baseline 10 request lúc 05:54:41–43 (`scripts/load_test.py --concurrency 5`, incident OFF):

| Panel | Đơn vị | Threshold (`config/dashboard.yaml`) | Đo được | Kết luận |
|---|---|---|---:|---|
| `latency` | ms | p95 ≤ 3000 | p50 150 / p95 896 / p99 896 | ✅ |
| `traffic` | req/phút | rate ≥ 1 | 10 request trong ~2.3s | ✅ |
| `errors` | % | error_rate ≤ 2 | 0.00 (0/10, `error_breakdown` rỗng) | ✅ |
| `cost` | USD | total ≤ 2.5 | 0.020595 | ✅ |
| `tokens` | token | sum ≤ 50000 | in 330 / out 1307 | ✅ |
| `quality` | 0–1 | mean ≥ 0.75 | 0.88 | ✅ |

Giá trị `p95 = 896ms` không phải nhiễu: đó là request đầu tiên sau khi process khởi động, gồm cả lần fetch prompt đầu từ Langfuse (cache `cache_ttl_seconds=60` còn rỗng). Từ request thứ hai trở đi latency về đúng 150ms. Đây là lý do alert `HighLatencyP95` đặt `for: 5m` và `min_sample: 10` — nếu bắn ngay lập tức thì mỗi lần deploy sẽ tạo một báo động giả.

### Evidence dashboard

⚠️ **Đây là hạng mục bắt buộc duy nhất còn thiếu hoàn toàn.** Contract 6 panel đã hợp lệ và số liệu đã có, nhưng nhóm **chưa dựng dashboard runtime** nên chưa có ảnh thể hiện tên panel, time range 60 phút, đơn vị và threshold line như `docs/dashboard-spec.md` yêu cầu. `submission/evidence/dashboard_validation.txt` chỉ chứng minh contract, không chứng minh biểu đồ.

Việc còn phải làm: dựng 6 panel từ `data/logs.jsonl` bằng Streamlit/notebook/Grafana theo `docs/DASHBOARD_SETUP.md`, chụp ảnh trước và sau khi bật `rag_slow` (panel latency phải nhảy rõ), lưu vào `submission/evidence/dashboard_before.png` và `dashboard_after.png`.

### SLO đã chọn và lý do

`config/slo.yaml` — 8 SLI đang bật, chia hai nhóm. Ngưỡng đặt theo quy tắc **objective ≈ 2× p95 quan sát được**, đủ headroom để không báo động giả nhưng vẫn bắt được hiện tượng nhảy bậc.

Baseline dùng để chốt ngưỡng (ghi trong phần comment đầu `config/slo.yaml`, đo trên 10 request): `cost_usd` mean 0.0020 / p95 0.0027, `tokens_out` mean 127 / p95 173, `quality` mean 0.87. Lần chạy lại ngày 2026-08-11 cho số tương đương — `cost_usd` mean 0.0021, `tokens_out` p95 178, `quality` mean 0.88 — nên các ngưỡng vẫn còn đúng, không cần chỉnh lại.

**Nhóm SLO hạ tầng** — dùng chung cho mọi service:

| SLI | Objective | Target | Lý do chọn |
|---|---:|---:|---|
| `latency_p95_ms` | 3000 | 99.5% | trùng threshold panel `latency`; p95 thay vì mean vì mean che mất đuôi chậm |
| `error_rate_pct` | 2 | 99.0% | mất chức năng trực tiếp |
| `daily_cost_usd` | 2.5 | 100% | trần ngân sách ngày |
| `traffic_rate_per_minute` | 1 | 99.0% | **sàn liveness**, không phải mục tiêu chất lượng. Tồn tại để bịt vùng mù của `error_rate_pct`: service chết → 0 request → mẫu số bằng 0 → error rate bằng 0 và mọi metric tỷ lệ đều xanh |

**Nhóm SLO đặc thù LLM/agent** — đây là phần một dashboard web thông thường không có:

| SLI | Objective | Target | Lý do chọn |
|---|---:|---:|---|
| `quality_score_avg` | 0.75 | 95.0% | LLM trả HTTP 200, latency bình thường, chi phí bình thường mà **nội dung vẫn vô dụng**. `error_rate` không thay thế được SLI này |
| `cost_per_request_usd` | 0.006 | 99.0% | ~2× p95 quan sát (0.0027). Tách khỏi `daily_cost_usd` vì tăng traffic (bình thường) và tăng đơn giá (bất thường) cần hành động khác nhau |
| `output_tokens_p95` | 400 | 99.0% | ~2× p95 quan sát (173). Token output phình là **nguyên nhân gốc chung** của cả tăng cost lẫn tăng latency — bắt ở đây thì không phải chờ hai alert kia bắn |
| `pii_in_output_count` | 0 | 100% | ngưỡng **tuân thủ**, không phải hiệu năng; nên objective tuyệt đối bằng 0 |

Hai SLI đã thiết kế nhưng **chưa bật**, ghi ở `planned_slis` kèm `blocked_on`: `prompt_fallback_rate_pct` (cần ghi `prompt_source` vào log — đã có bằng chứng thật ở [mục 4](#phát-hiện-thêm-prompt-fallback-không-để-lại-dấu-vết-trong-log)) và `retrieval_grounding_rate_pct` (cần cờ retrieval-miss riêng; `doc_count` hiện luôn ≥ 1 kể cả khi miss, vì `app/mock_rag.py:23` trả câu fallback vẫn tính là 1 document).

### Alert rules và runbook

`config/alert_rules.yaml` (8 alert) + `docs/alerts.md` (runbook 8 mục, mỗi mục có 3 bước kiểm tra đầu tiên kèm lệnh `jq`/`curl` chạy được, mitigation tạm thời và owner).

| Alert | Severity | SLI | `for` | `min_sample` |
|---|---|---|---|---|
| `HighLatencyP95` | warning | `latency_p95_ms` | 5m | 10 response |
| `HighErrorRate` | critical | `error_rate_pct` | 5m | 20 request |
| `DailyCostBudgetBurn` | warning | `daily_cost_usd` | 15m | — (ngưỡng tuyệt đối) |
| `LowQualityScore` | warning | `quality_score_avg` | 10m | 20 response |
| `TrafficDropout` | critical | `traffic_rate_per_minute` | 10m | — (vắng dữ liệu **là** tín hiệu) |
| `CostPerRequestSpike` | warning | `cost_per_request_usd` | 10m | 20 response |
| `OutputTokenBloat` | warning | `output_tokens_p95` | 10m | 20 response |
| `PIIInModelOutput` | critical | `pii_in_output_count` | 0m | — (một lần là đủ điều tra) |

Bốn nguyên tắc đã áp dụng:

1. **Dựa trên triệu chứng người dùng, không dựa trên tên sự cố nội bộ.** Không alert nào nhắc `rag_slow`/`tool_fail`/`cost_spike`. Tên implementation sẽ đổi, còn triệu chứng thì không — và sự cố lần sau sẽ không mang tên nào trong ba tên đó.
2. **Mọi alert tỷ lệ đều có `min_sample`.** Với traffic thấp, 1 request lỗi = 100% error rate.
3. **Severity theo hậu quả:** critical = mất chức năng hoặc vi phạm tuân thủ (gọi page ngay); warning = degradation hoặc ngân sách (xử lý trong giờ làm việc). `DailyCostBudgetBurn` cố ý để warning: nó không ảnh hưởng người dùng, đánh thức người trực lúc 2 giờ sáng vì tiền là cách nhanh nhất khiến alert bị tắt tiếng.
4. **`TrafficDropout` là alert dễ bỏ sót nhất** và nó bịt đúng vùng mù của `HighErrorRate` — xem lý do ở bảng SLO hạ tầng.

Runbook cũng ghi các tương tác ngược giữa alert, để người xử lý không sửa chỗ này làm hỏng chỗ kia: siết `max_tokens` để dập `OutputTokenBloat` có thể kéo `quality_score` xuống dưới ngưỡng vì `_heuristic_quality` cộng điểm khi answer dài hơn 40 ký tự (`app/agent.py:102`), làm `LowQualityScore` bắn.

## 6. Điều tra challenge

### Challenge ID

`day13-k3-observability-v1` — cohort K3, `incident: rag_slow`, `seed: 1303`, `affected_feature: refund`, `latency_threshold_ms: 2000` (`config/challenge.json`, không sửa đổi).

Chạy: `python scripts/load_test.py --challenge --concurrency 5` với 5 câu hỏi refund chính thức, một lần khi incident OFF và một lần khi ON, trên hai process sạch.

### Bước 1 — Triệu chứng từ metrics

| Chỉ số | Before (05:54:53) | After (05:55:03–17) | Thay đổi |
|---|---:|---:|---|
| `latency_p50` | 150 ms | **2651 ms** | **×17.7** |
| `latency_p95` | 913 ms | **3384 ms** | **×3.7** |
| latency min | 150 ms | 2650 ms | ×17.7 |
| `error_rate_pct` | 0.00 | **0.00** | không đổi |
| `quality_avg` | 0.86 | **0.86** | không đổi |
| `avg_cost_usd` | 0.002242 | 0.001894 | giảm nhẹ |
| `tokens_in_total` | 162 | **162** | không đổi |
| `tokens_out_total` | 715 | 599 | giảm nhẹ |

Đọc bảng này ra được hai kết luận trước khi mở bất kỳ trace nào:

1. **Đây là sự cố latency thuần tuý.** Error rate 0%, quality không đổi → không phải outage, không phải hỏng chất lượng. Người dùng vẫn nhận đúng câu trả lời, chỉ là chờ lâu. `HighLatencyP95` bắn, `HighErrorRate` và `LowQualityScore` im lặng — đúng như thiết kế.
2. **Chậm đều, không phải chậm ở đuôi.** Latency **min** cũng nhảy lên 2650ms. Nếu chỉ p95 tăng còn p50 giữ nguyên thì nghi vấn là một nhánh code hiếm gặp; ở đây mọi request đều chậm như nhau → một bước cố định trong pipeline chậm thêm một lượng cố định. Ngưỡng `latency_threshold_ms: 2000` trong challenge bị vượt ở **cả 5/5 request**.

Delta gần như hằng số: 2651 − 150 = **2501ms** ≈ 2.5s.

### Bước 2 — Trace ID liên quan

Lọc Langfuse `tags:day13`, sắp theo latency giảm dần, lấy hai trace **cùng session `k3-challenge-s01`, cùng câu hỏi "What is your refund policy?"**:

| | Before | After |
|---|---|---|
| **Trace ID** | `618fb6e6e2dc6bedbde5ccb42771e7a2` | `cbbe76e20d236ef4fa6bb86b7a5d0696` |
| Latency | 0.150s | **3.386s** |
| `doc_count` | 1 | 1 |
| `prompt_version` / `label` | 9 / production | 9 / production |
| `prompt_source` | langfuse | langfuse |
| `model` | claude-sonnet-4-5 | claude-sonnet-4-5 |
| `tokens_in` | 29 | 29 |

Bốn trace chậm còn lại: `fd84d047958f21b93155dc5e254cd122`, `89d8c4fb6d08eeee30370e6e9af4d61c`, `a04203514a69da85a7f4717383305e92`, `b8a0c2c3e9cee47d3fe642f906107106` — tất cả 2.651–2.653s.

Trace loại trừ được prompt version, model, retrieval miss và kích thước input: mọi biến số giữ nguyên, chỉ thời gian đổi. **Nhưng trace không chỉ ra được span nào chậm**, vì cả trace chỉ có 1 observation (`GENERATION run`) — `retrieve()` không có span riêng (khoảng trống G1).

### Bước 3 — Log line/correlation ID liên quan

`data/logs.jsonl` cho mốc thời gian chính xác và cặp before/after nối bằng `session_id`:

```text
05:54:51.919542  incident_disabled  {"name":"rag_slow"}     ← control event, level=warning
05:54:53.499169  req-b4fa75e9  k3-challenge-s01  refund  latency_ms=150

05:55:03.412859  incident_enabled   {"name":"rag_slow"}     ← ranh giới before/after
05:55:07.042334  req-b3fb4b1f  k3-challenge-s01  refund  latency_ms=3384
05:55:09.701893  req-0ad4ee0a  k3-challenge-s02  refund  latency_ms=2650
05:55:12.357248  req-8036c6e0  k3-challenge-s04  refund  latency_ms=2651
05:55:15.013305  req-a6e334ed  k3-challenge-s03  refund  latency_ms=2651
05:55:17.667154  req-d7481539  k3-challenge-s05  refund  latency_ms=2650

05:55:18.162909  incident_disabled  {"name":"rag_slow"}     ← khôi phục
```

Log chốt lại nhân quả mà metrics và trace không chốt được: **mọi request sau `incident_enabled` đều chậm, mọi request trước đó đều nhanh, không có trường hợp ngoại lệ.**

### Root cause

`app/mock_rag.py:14-18` — hàm `retrieve()` kiểm tra cờ toàn cục trước khi tra corpus:

```python
def retrieve(message: str) -> list[str]:
    if STATE["tool_fail"]:
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        time.sleep(2.5)          # ← +2500ms cố định trên mọi request
```

`STATE["rag_slow"]` được bật qua `POST /incidents/rag_slow/enable` (`app/incidents.py:10`). Vì `retrieve()` được gọi ở dòng đầu tiên của `LabAgent.run` (`app/agent.py:32`), độ trễ này cộng thẳng vào `latency_ms` của **mọi** request, không phụ thuộc nội dung câu hỏi.

Chuỗi bằng chứng khép kín:

| Bằng chứng | Nguồn | Chứng minh điều gì |
|---|---|---|
| p50 150→2651ms, error 0%, quality 0.86 không đổi | metrics before/after | sự cố latency thuần tuý, không phải outage |
| latency **min** cũng tăng ×17.7 | metrics | chậm đều mọi request → một bước cố định, không phải đuôi |
| delta = 2501ms ≈ 2.5s | metrics | khớp chính xác `time.sleep(2.5)` |
| trace `618fb6e6…` vs `cbbe76e2…` giống hệt nhau trừ latency | Langfuse | loại trừ prompt version, model, doc_count, tokens |
| `incident_enabled` lúc 05:55:03.412859 chia đôi tập request | `data/logs.jsonl` | nhân quả theo thời gian, không ngoại lệ |
| `if STATE["rag_slow"]: time.sleep(2.5)` | `app/mock_rag.py:18` | vị trí chính xác trong code |

### Phát hiện phụ: incident bị khuếch đại ×5 bởi head-of-line blocking

Client thấy tệ hơn nhiều so với những gì server tự báo:

| | req 1 | req 2 | req 3 | req 4 | req 5 |
|---|---:|---:|---:|---:|---:|
| `latency_ms` (server ghi) | 3384 | 2650 | 2651 | 2651 | 2650 |
| thời gian client thật sự chờ | 3444 | 14065 | 14068 | 14069 | 14070 |

Với `--concurrency 5`, người dùng thứ 5 chờ **14 giây** trong khi log ghi 2.65s. Nguyên nhân: `POST /chat` khai báo `async def` (`app/main.py:46`) nhưng `LabAgent.run` là code đồng bộ chặn (`time.sleep` trong `mock_rag`), nên nó chặn event loop và 5 request bị xếp hàng nối tiếp — 5 × 2.65s ≈ 13.99s ≈ đúng con số quan sát được.

Hệ quả cho SLO: `latency_p95_ms` đang tính trên `latency_ms` do server tự đo, **không phản ánh trải nghiệm thật của người dùng**. Một sự cố tương tự có thể khiến người dùng chờ 14s mà dashboard vẫn báo 2.65s.

### Fix action

| # | Hành động | Trạng thái |
|---|---|---|
| 1 | Tắt incident: `python scripts/inject_incident.py --disable` | ✅ đã làm — `incident_disabled` lúc 05:55:18.162909, `/health` xác nhận `rag_slow: false` |
| 2 | Xác nhận bằng request thật, không chỉ dựa vào `/health` | ✅ đã làm — request sau đó về lại 150ms |
| 3 | Ngoài đời thật, tương đương: đặt timeout cho vector store, bật cache cho truy vấn lặp, và fail-fast trả câu trả lời fallback thay vì để người dùng chờ | đề xuất |

### Preventive measure

| # | Biện pháp | Chặn được điều gì | Vị trí sửa |
|---|---|---|---|
| 1 | **Bọc `retrieve()` bằng span riêng** | Lần sau trace tự chỉ ra retrieval chiếm 2.5/2.65s; không phải suy luận qua code (khoảng trống G1) | `app/agent.py:32` |
| 2 | **Đưa `correlation_id` vào metadata của trace** | Hiện phải nối log↔trace qua `session_id` + mốc thời gian, chỉ đúng khi mỗi session có 1 request (G2) | `app/agent.py:46` |
| 3 | **Chạy phần chặn trong threadpool** (`def` thay vì `async def`, hoặc `run_in_executor`) | Head-of-line blocking khuếch đại ×5 mọi sự cố latency (G6) | `app/main.py:46` |
| 4 | **Ghi thêm `client_latency_ms`** từ header `x-response-time-ms` | SLO đang đo thời gian server, không đo thời gian người dùng chờ | `app/main.py:68` |
| 5 | **Bật alert `HighLatencyP95`** với `for: 5m`, `min_sample: 10` | Sự cố này bị phát hiện thủ công; alert sẽ bắn sau 5 phút | `config/alert_rules.yaml` |
| 6 | **Đặt timeout cho `retrieve()`** | Dependency chậm hiện có thể treo vô hạn — không có timeout nào ở tầng retrieval | `app/mock_rag.py:14` |
| 7 | **Ghi `prompt_version`/`prompt_source` vào log** | Silent fallback không để lại dấu vết nào khi trace bị mất (G3, G5) | `app/main.py:68` |

## 7. Đóng góp cá nhân

Đối chiếu trực tiếp với `git log` — mọi dòng dưới đây kiểm chứng được bằng `git show <sha>`.

| Thành viên (git author) | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Dương Mạnh Phong (`DangIT404`) | Logging & PII: `CorrelationIdMiddleware`, `bind_contextvars`/`clear_contextvars`, enrichment 5 field, bật `scrub_event`, thêm pattern `passport` + `vietnam_address`. Thu thập evidence trace/prompt trên Langfuse. | `45ddb4b` (app/middleware.py, app/main.py, app/logging_config.py, app/pii.py), `0637e40` (6 file evidence), `286e7de` (4 ảnh Langfuse, scripts/test_trace.py) | Thứ tự processor quyết định tất cả: `scrub_event` phải đứng trước `JsonlFileProcessor`, và `scrub_text` phải chạy trước khi cắt 80 ký tự, nếu không PII vẫn lọt ra đĩa |
| Đặng Thái Nam Sơn (`sondang04`) | Metrics `quality_avg`; SLO 8 SLI + 2 `planned_slis` với lý do từng ngưỡng; 8 alert rule symptom-based; runbook `docs/alerts.md`; lưu `data/logs.archive-preimpl.jsonl` để giữ toàn vẹn evidence | `32419b3` (app/metrics.py), `b7f9869` + PR #2 `7f1276d` (config/slo.yaml, config/alert_rules.yaml, docs/alerts.md), `7ae7227`, `327d7f9` | Alert phải dựa trên triệu chứng người dùng chứ không dựa vào tên sự cố nội bộ; và mọi alert tỷ lệ cần `min_sample`, nếu không 1 lỗi trên traffic thấp thành 100% error rate |
| Chu Thành Dũng (`Dung`) | Tự động hoá tạo prompt version trên Langfuse (`create_prompt` v1 `baseline`+`production`, v2 `candidate`) | `601ab75` (scripts/role2_setup.py) | Đổi `LANGFUSE_PROMPT_LABEL` không có tác dụng với API server đang chạy vì `resolve_prompt` đọc env trong process của server — bắt buộc phải restart, và script đã ghi rõ giới hạn này thay vì giả vờ đã đổi được |
| Trần Đình Đăng (`dangitcntt55-a11y`) | Chủ repo, review và merge PR #1, PR #2, thiết lập Langfuse, chạy API và load test, thiết lập evidence, middleware, main, logging config, pii | `5ac0c21`, `7f1276d` | — |

*(Commit của **HungBil** — `b95464c`, `f1a02e5`, `7a57bfb`, `cd84f4f` — là scaffolding và bản release challenge do Lab Coach cung cấp, không tính vào đóng góp của nhóm.)*

Ngoặc đơn sau mỗi tên là git author name tương ứng, để người chấm đối chiếu trực tiếp `git log --author=...` theo yêu cầu B2 của rubric.

⚠️ Một phần việc mà Trần Đình Đăng khai (middleware, main, logging config, pii) trùng với commit `45ddb4b` đang mang git author `DangIT404`. Nếu hai người cùng làm phần đó theo kiểu pair programming thì ghi rõ trong bảng; nếu không, cần chỉnh lại cho khớp với Git — rubric B2 chấm đúng điểm này.

## 8. Việc còn phải làm trước khi nộp

| # | Việc | Vì sao cần |
|---|---|---|
| 1 | **Dựng dashboard runtime và chụp ảnh** (`dashboard_before.png`, `dashboard_after.png`) | Hạng mục evidence bắt buộc duy nhất còn thiếu; validator chỉ chứng minh contract |
| 2 | Chụp bổ sung ảnh **promotion** label (`production` → v10) để có cặp trước/sau đầy đủ | Ảnh hiện có chỉ ghi trạng thái sau rollback, và ở cặp version `#1`/`#2` cũ |
| 3 | Xác nhận **tên nhóm** chính thức (đang suy ra từ tên repo là `C4-1`) | Mục 1 |
| 4 | Làm rõ phần việc trùng giữa Trần Đình Đăng và commit `45ddb4b` (author `DangIT404`) | Mục 7 — rubric B2 chấm khớp Git |
| 5 | Cập nhật **commit SHA cuối** sau commit cuối cùng | Mục 1 |
| 6 | Kiểm tra `git status --short` và xác nhận `.env` không bị commit | `SUBMISSION.md` — lộ secret là bài nộp không hợp lệ |
