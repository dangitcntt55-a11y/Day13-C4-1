# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: 
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò: 

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: 100/100 (4/4 check PASSED, chạy lúc 2026-08-11T11:28 +0700)
- Tổng số traces: 23 log records (10 `request_received` + 10 `response_sent` + 1 `app_started` + 2 control events); 12 correlation ID duy nhất
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard:

### Ghi chú về tính toàn vẹn của evidence

`data/logs.jsonl` là file append-only và **không được track trong git** (xem `.gitignore`), nên nó tích luỹ output qua nhiều lần chạy.

Lần validate trước cho 50/100 vì file còn chứa 20 record sinh lúc `03:44:xx UTC` (= 10:44 +0700) — tức **trước** commit `45ddb4b` "feat(observability): implement correlation IDs, log context, and PII scrubbing" (10:58 +0700). Những record đó thiếu `correlation_id` và 4 field enrichment vì code lúc ấy chưa có phần này. Mọi record sinh sau commit đó đều PASS.

Xử lý: **không xoá và không sửa** record nào. Toàn bộ file cũ được lưu nguyên vẹn tại `data/logs.archive-preimpl.jsonl` (47 records) để đối chiếu, sau đó evidence được sinh lại từ đầu bằng cách chạy thật với code hiện tại tại commit `5ac0c21`:

```bash
python scripts/inject_incident.py --disable   # baseline sạch
python scripts/load_test.py --challenge       # 5 request, ~155ms
python scripts/inject_incident.py             # bật rag_slow
python scripts/load_test.py --challenge       # 5 request, ~2654ms
python scripts/validate_logs.py               # 100/100
```

Kết quả 100/100 đến từ output thật của code hiện tại, không phải từ việc chỉnh sửa file log.

## 3. Logging và tracing

- Evidence correlation ID:
- Evidence PII redaction:
- Evidence trace waterfall:
- Giải thích một span đáng chú ý:

## 4. Prompt versioning

- Prompt name: `day13-chat`
- Version/label baseline: `local-v1` (Thay bằng Version thực tế trên Langfuse, VD: `v1`)
- Version/label candidate: (Thay bằng Version thực tế trên Langfuse, VD: `v2`)
- Trace ID của mỗi version: 
  - Trace ID bản baseline: [ĐIỀN TRACE ID]
  - Trace ID bản candidate: [ĐIỀN TRACE ID]
- Bằng chứng đổi label hoặc rollback: [LƯU ẢNH VÀO THƯ MỤC `submission/evidence/` VÀ ĐIỀN LINK TẠI ĐÂY, VD: `evidence/rollback.png`]

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`:
- Evidence dashboard:
- SLO đã chọn và lý do:
- Alert rules và runbook:

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| | | | |
