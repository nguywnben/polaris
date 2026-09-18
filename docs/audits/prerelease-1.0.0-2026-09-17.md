# Polaris 1.0.0 — rà soát trước phát hành

## Kết luận

Đã hoàn tất lượt rà soát và sửa lỗi trên working tree ngày 17/09/2026. Các
lỗi tái hiện trong phạm vi dưới đây đã có kiểm tra hồi quy đạt. **Chưa đủ bằng
chứng để tuyên bố release-ready**: còn Docker/Compose, CI Linux/Python 3.12 và
benchmark trên đúng commit ứng viên. Không tạo commit/tag, push hay phát hành.

Giữ nguyên thay đổi có sẵn, database thật và tài khoản provider thật. Mọi phép
thử CRUD chạy trên SQLite tạm; preview 4285 được tải lại bằng chính database mẫu
đang dùng, vẫn 89 credentials/23 biến thể provider, không seed lại.

## Phạm vi và phương pháp

Theo Impeccable/frontend engineering, giữ hệ thống thiết kế hiện hữu: control
32px, sidebar 36px, mỗi provider một section và tối đa bốn credentials mỗi hàng.
Không thêm dữ liệu trang trí hoặc che tràn bằng cách ẩn scrollbar toàn cục.
Theo TDD/debugging, lỗi hành vi được tái hiện trước sửa. Một lượt review bảo mật
độc lập theo skill code-review đã phát hiện hai lỗi phân quyền và một alias hỏng.

| Phạm vi | Kiểm tra trong đợt này |
| --- | --- |
| Toàn bộ console | 13 route/subview: dashboard, providers, credentials, models, AI Quality, Playground, access, identity, activity/trace/audit/runtime, config, about |
| Provider | Mở 23 workspace, phần nâng cao, nhập khóa, tùy chọn và trạng thái trống; production parser đọc fixture upstream có nguồn, không gọi tài khoản thật |
| Credentials | 23 modal đại diện; lọc/provider section, phân trang, chọn trang, đổi nhãn, bật/tắt, hủy/xác nhận xóa, lỗi quota/retry, model/quota/config/errors độc lập |
| Các nghiệp vụ khác | Route/giao thức/stream qua upstream giả, chính sách AI, khóa ảo tạo/sửa/rotate/revoke, danh tính, trace và audit, cấu hình, hướng dẫn backup/update/recovery |
| Auth và quyền | Setup thật trên runtime tạm, login/logout/login lại, API key sai, role/granular-scope matrix bằng HTTP; viewer/operator/admin và lỗi tải quyền trên UI |
| Modal/toast/loading | Focus trap và trả focus, Escape, xác nhận/hủy, toast không chiếm focus, skeleton initial/error/retry, refresh giữ nội dung, reveal/hide/close xóa payload nhạy cảm |
| Kích thước/chủ đề | Sáu viewport của harness, gồm mobile/tablet/desktop/landscape; cả sáng/tối. Modal/provider tập trung 360/1440; credential regression thêm 768 và 844×390 |
| Ngôn ngữ | 15 locale × 14 bề mặt × hai cấu hình viewport/theme; placeholder, tên truy cập, khóa dịch, chuyển ngôn ngữ và callback lỗi |

Một baseline và một confirmation toàn bộ; sau các lỗi phát hiện trong review,
chỉ chạy lại các nhánh bị ảnh hưởng và gate bắt buộc. Ảnh contact sheet dùng để
so sánh hệ thống bố cục; ảnh riêng credentials/modal được xem ở kích thước đọc
được. Không khẳng định đã đọc từng pixel hay thử mọi tổ hợp dữ liệu có thể có.

## Phát hiện và sửa

| Mức | Bằng chứng | Sửa |
| --- | --- | --- |
| Critical | Viewer/granular `credentials.read` nhận raw payload qua `/api/credentials/detail/{filename}` | Chuyển endpoint sang `credentials.export`; HTTP regression kiểm tra 403 trước storage và không lộ sentinel secret; admin vẫn đọc được |
| High | Operator/granular `credentials.operate` có thể gửi `action=delete` vào API chung | Dependency riêng yêu cầu thêm `credentials.manage` trước đọc target, preview hoặc idempotency; áp dụng cả single, batch preview và execute |
| P1 | Alias ẩn `verify-project` không có manifest, trả 500 sau xác thực | Bỏ alias đã retire; canonical `verify` giữ nguyên; alias nay 404 |
| P2 | UI dựa vào capability provider, không giao với quyền người dùng | Đọc quyền session; giao quyền với capability cho card/section/batch/modal, nhập/xuất ZIP. Không đọc được quyền thì khóa thao tác nhạy cảm; chỉ hiện payload khi có quyền export |
| P2 | Credentials nhiều khoảng trống, badge phụ làm khó đọc, modal có cuộn lồng nhau | Thu gọn stats/filter/card; tách trạng thái/auth khỏi plan/cooldown; căn metrics/actions; email một dòng có title đầy đủ; quota toàn chiều rộng, hai cột desktop và một cột mobile |
| P2 | Quota/model có scrollbar riêng trong modal | Bỏ giới hạn chiều cao riêng, dùng vùng cuộn chính của modal. Danh sách dài vẫn truy cập đủ; không ẩn thông tin để tránh cuộn |
| P2 | Metadata quota sát thanh hạn mức; select thử model lệch nút 7px | Thêm khoảng cách nhóm facts; reset margin của label trong hàng thử model; kiểm tra hình học đạt |
| P2 | Dashboard ép bốn provider ở 1024px, vùng tên chỉ 131,75px | Grid tự chia cột theo không gian; kiểm tra tên đủ rộng tại 768/1024/1440/1920 |
| P2 | Logo đơn sắc chìm trên nền tối ngoài trang providers | Áp dụng dark inversion thống nhất cho Codex, DeepSeek, Ollama, SpaceXAI; logo màu không đổi |
| P2 | Lỗi catalog Playground dùng chuỗi tiếng Anh trực tiếp | Dùng thông báo từ catalog dịch có sẵn |
| Fixture | Mistral thiếu `capabilities.completion_chat`, production filter loại hết mô hình | Sửa phản hồi transport mẫu theo hợp đồng thật; giữ nguyên production filter; regression đi qua adapter/parser thật |

Không sửa quota thành số giả, không mặc định quota thiếu thành 100%, không đổi
thuật toán định tuyến/giá/cách tính usage chỉ để giao diện đẹp hơn. Các lỗi cố ý
trong bộ mẫu (token invalid/quota unavailable) vẫn giữ nguyên. Những kỳ vọng cũ
trong harness (87 credentials, model `demo-*`, số cửa sổ quota cũ) được thay bằng
manifest và hợp đồng dữ liệu hiện tại, không bỏ assertion lỗi sản phẩm.

Quyền API vẫn là nguồn quyết định cuối cùng; việc ẩn nút không thay thế backend.
Scoped key không đọc được `/api/identity/session` sẽ không được UI suy đoán quyền.
Scope legacy rộng giữ tương thích hiện có; key chỉ có granular `credentials.read`
không được xuất bí mật. Không thay định nghĩa vai trò hay mở rộng quyền.

## Kết quả kiểm chứng

- Core suite cuối: **2.288 tests**, exit 0. 22 skip của backend tùy chọn/live đã
  có trước (PostgreSQL/MongoDB khi thiếu URI), không bỏ qua đường core mới.
- Fast gate đạt: lint/format 556 Python files, compile, manifest 257 modules,
  JavaScript syntax, YAML, shell, whitespace. Không thêm suppression/skip.
- `pip check` đạt; `pip_audit --local --progress-spinner off`: không phát hiện
  lỗ hổng dependency đã biết tại thời điểm chạy. Không thêm dependency.
- Browser smoke cuối **9/9** critical journeys, thêm 11 routes × bốn viewport
  và bàn phím sidebar/provider selector. Upstream giả được khai báo rõ.
- Populated baseline/confirmation: **384 cases mỗi lượt**; confirmation không
  có phát hiện DOM/layout hoặc lỗi JavaScript/HTTP ngoài dự kiến.
- Empty baseline/confirmation: **152 cases mỗi lượt**, không phát hiện lỗi.
- **15 locales, 14 surfaces**, 360/1440 sáng/tối đạt; cả 1.357 khóa tham chiếu
  có bản dịch. Static/JS/backend i18n audit đạt.
- Populated workflows: chín nhánh đạt sau sửa; ba nhánh CRUD/pagination/layout
  chạy lại sau sửa quyền cũng đạt. HTTP ghi thật vào database tạm.
- `credential_management_smoke`, `interface_states_smoke`,
  `modal_toast_ui_smoke` đạt. Management suite chạy lại sau sửa quyền đạt.
- `prerelease_credentials_smoke`: bốn viewport, không cuộn lồng trong quota/models,
  full-width quota, khoảng cách metadata, căn nút, bốn logo sáng/tối, ma trận
  viewer/operator/admin/permissions-unavailable đều đạt.
- Runtime smoke chuẩn CI: fresh setup rồi đăng nhập với DB đã setup đều đạt;
  gồm health/ready, bundles/CSP, canonical route, chặn API key sai và logout.
- Dashboard warmed localhost: baseline 2.185ms, confirmation 2.113ms, dưới
  ngưỡng 2.500ms. Đây là hai mẫu cục bộ, **không** là cải thiện có ý nghĩa thống
  kê hoặc bằng chứng gateway p95. Không tối ưu suy đoán từ chênh lệch này.

Artifact kiểm tra (gitignored):

- `temp/populated-instance/prerelease-before/` và `prerelease-after/`: report,
  ảnh trang/provider/modal; ảnh quota trong confirmation trước sửa margin cuối.
- `temp/prerelease-credentials/`: report và ảnh Muse Code xác nhận cuối.
- `temp/empty-instance/prerelease-before/` và `prerelease-after/`.
- `temp/populated-workflows/prerelease/`, `prerelease-confirm/` và
  `prerelease-security/`: baseline, các nhánh lỗi đã sửa và CRUD sau sửa quyền.
- `temp/localization-ui/`, `temp/credential-management/`: ảnh locale và modal.

## Giới hạn và gate còn lại trước release

1. **Docker/Compose chưa chạy**: CLI có nhưng Docker Desktop Linux daemon không
   hoạt động. Cần kiểm tra build image, fresh setup, recreate giữ dữ liệu,
   backup/restore/rollback và graceful stop trên container đúng ứng viên.
2. **Benchmark routine chưa chạy trên bản cuối**: runner hiện dùng `git archive
   HEAD`, trong khi code đang ở dirty working tree. Chạy nó lúc này sẽ đo bản cũ.
   Sau khi chốt commit, chạy profile 120 giây/5 RPS/concurrency 8; không hạ
   ngưỡng p95 ≤100ms, error <0,1%, memory bounded trong `CONSTRAINTS.md`.
3. Local chạy Windows/Python 3.14/Chromium. CI Linux/Python 3.12 và các môi trường
   lưu trữ tùy chọn chưa được chứng nhận trong lượt này. Không dùng kết quả mock
   để tuyên bố OAuth, gói/hạn mức hoặc inference live của 23 provider đều ổn.
4. Không đo changed-line coverage bằng công cụ coverage; regression có thực thi
   các nhánh sửa nhưng không phải chứng nhận phần trăm. Không phải chứng nhận
   WCAG đầy đủ, bản dịch native-speaker hay hỗ trợ mọi trình duyệt.

Thanh cuộn chính của trang hoặc modal dài là cần thiết và được giữ. Không còn
cuộn lồng dư thừa đã tái hiện trong quota/model; không có document horizontal
overflow trong ma trận đã chạy. Log hoặc dữ liệu dài vẫn có vùng cuộn có chủ ý.

Các file lớn đã có trước (`credentials.py`, `credential-manager.js`, CSS chung)
không bị viết lại toàn bộ: thay đổi tập trung tại điểm sở hữu. Dependency phân
quyền phá hủy được tách thành `credential_security.py` để không nhồi thêm logic
bảo mật vào router dài. Việc tách module rộng hơn cần một thay đổi riêng có test.

## Preview

`http://127.0.0.1:4285/credentials` đang phục vụ bản sửa. Health, ready, trang
credentials đều 200; authenticated fleet vẫn 89 mục và header synthetic=true.
Một listener loopback; không mở ra mạng, không đổi mật khẩu hoặc dữ liệu mẫu.
