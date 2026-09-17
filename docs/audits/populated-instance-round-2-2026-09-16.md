# Polaris — rà soát giao diện có dữ liệu, đợt 2

## Kết luận và phạm vi

Đã rà soát giao diện và thao tác bằng dữ liệu SQLite giả: 23 provider, 87
credentials, 696 bản ghi sử dụng, trace/audit/log, 8 khóa ảo, danh tính, phiên,
định tuyến, chính sách AI và backup. Không dùng tác tử phụ, tài khoản provider
thật, Docker hay commit. Các thay đổi có sẵn trong worktree được giữ nguyên.

Theo Impeccable, giữ hệ thống thiết kế hiện hữu, phân cấp chữ và thành phần dùng
chung; không thiết kế lại chỉ để tạo khác biệt. Control 32px, mục sidebar 36px
và tối đa bốn credentials mỗi hàng vẫn theo lựa chọn của chủ dự án. Dùng một
lượt baseline và một lượt xác nhận bố cục; lỗi dữ liệu minh họa phát hiện khi
đọc ảnh được kiểm chứng riêng, không mở thêm một vòng thiết kế toàn ứng dụng.

Implementation integrity: đạt trong phạm vi đã thử. Các lỗi xác nhận đã được
sửa và có kiểm thử hồi quy; không còn lỗi chặn các luồng đã kiểm tra. Đây không
phải chứng nhận mọi tổ hợp dữ liệu, WCAG đầy đủ hay độ ổn định upstream.

## Phát hiện và sửa

| Mức | Lỗi đã tái hiện | Sửa và chứng cứ |
| --- | --- | --- |
| P1 | Bộ lọc credentials bỏ qua Muse Code, Meta, Groq, DeepSeek, Mistral, Cerebras; chọn provider mới có thể vẫn giữ kết quả provider trước | Bỏ allowlist viết tay trong `getFilterDefinitions()`, dùng các lựa chọn hiện hữu và capability catalog. Test đỏ trước sửa, sau sửa cả 23 lựa chọn và deep link đều đúng; giá trị chưa đăng ký vẫn bị loại |
| P1 | Modal credential bắt nhập endpoint ngay cả khi provider cho phép để trống dùng mặc định; chỉ đổi tên cũng bị HTML validation chặn | Endpoint chỉ bắt buộc cho kết nối Ollama. Đổi tên DeepSeek với endpoint trống lưu được qua API thật của runtime giả; không discovery hoặc thay khóa. Ollama vẫn bắt buộc endpoint |
| P2 | Thẻ thống kê provider trên Dashboard ép phần tên xuống khoảng 4px tại 768px, chữ và số chồng nhau | Tên/logo ở hàng riêng, ba chỉ số chia đều hàng dưới. Header rộng tối thiểu 242px trong ma trận sau sửa. Giữ override riêng của bảng kết quả nhập credentials |
| P2 — dữ liệu kiểm thử | Preset Antigravity gắn nhầm `account_rate_limits`, che phần quota từng model; Grok thêm cửa sổ chung không cần thiết, Kiro gắn thời lượng vào tài nguyên | Sửa `tools/demo_credentials.py`: Antigravity đi vào renderer theo model, Grok theo tháng/tuần, Kiro theo tài nguyên/trial. Test hợp đồng đỏ→xanh và kiểm tra modal riêng cho cả ba |

Không đổi chuẩn xác thực, giới hạn quota, chính sách định tuyến, URL provider hay
validation bảo mật backend. Không thêm framework, dependency hoặc chuỗi dịch.
Tên nhãn thử có nội dung giống HTML vẫn chỉ hiển thị như văn bản.

Hai vấn đề ở công cụ kiểm thử cũng đã được chỉnh, không làm yếu kiểm tra sản phẩm:

- Tooltip tier đã có tiền tố dịch `Cấp:` nhưng bài cũ chỉ mong giá trị thô. Cập
  nhật kỳ vọng chính xác, vẫn kiểm tra chuỗi dài, XSS, overflow và 15 locale.
- Ảnh modal phải chụp viewport; chụp toàn trang credentials dài làm modal bị thu
  nhỏ đến mức không đọc được. Báo cáo giữ ảnh trang dài và ảnh viewport riêng.

## Bao phủ giao diện và nghiệp vụ

| Nhóm | Nội dung đã thực hiện |
| --- | --- |
| Toàn bộ giao diện chính | 13 view: Dashboard, Providers, Credentials, Models, AI Quality, Playground, Access, Identity, Activity/traces, Audit, Runtime logs, Config, About; mở disclosure và mục con nhìn thấy |
| Kích cỡ/theme | 360×800, 768×1024, 844×390, 1024×768, 1440×900, 1920×1080; sáng/tối; các suite tương tác còn kiểm tra 320px |
| Providers | Mở cả 23 workspace, cài đặt nâng cao và form key; kiểm tra link OAuth, thao tác lưu thủ công, kết quả thành công/retry, JSON/ZIP và từ chối tệp sai. Không đăng nhập thật |
| Credentials | Mở modal cả 23 variant; sáu họ OAuth với facts khác nhau; API key không đòi email/quota không được hỗ trợ; lọc, deep link, phân trang, chọn/xóa lựa chọn, thao tác theo provider và xác nhận hàng loạt |
| Quản lý credential | Đổi nhãn qua API/DB, bật/tắt, hủy xóa; test riêng xác nhận xóa, verify/test model giả lập, secret chỉ hiện khi yêu cầu, môi trường chỉ đọc, quota lỗi/retry không giữ phần trăm cũ |
| Khóa ảo | Tạo, chỉnh sửa, xoay vòng, thu hồi qua API/DB; xem usage; xác nhận và đóng vùng secret dùng một lần |
| Models / AI Quality / Config | Lưu và tải lại thật; chọn/sắp thứ tự, tìm kiếm, trạng thái thiếu model; profile, kiểm tra đầu vào, phụ thuộc và khóa môi trường; save thất bại/retry |
| Danh tính / phiên | Tạo bản ghi thật trong DB giả; quyền owner/read-only, xung đột giữ draft, hủy thu hồi, tải lỗi và phục hồi. OIDC bên ngoài vẫn tắt |
| Activity | Bộ lọc chung, bàn phím đổi tab, phân trang, trace/audit detail, pivot, runtime log, các trạng thái có dữ liệu/rỗng/lỗi |
| Backup | Tải backup mã hóa, dry run hợp lệ/không hợp lệ, conflict, hủy, restore vào runtime tạm và đăng nhập lại; không restore đè preview đang dùng |
| Playground | Bốn giao thức, JSON/stream, controls mở rộng, output an toàn, validation/lỗi; chỉ dùng upstream giả |
| Setup / Login / Sidebar | Setup thật của runtime tạm, login, callback thất bại thật/thành công giả; drawer mobile inert/focus/Escape, focus quay về phần tử mở |
| Skeleton / toast / modal | Initial loading, refresh giữ nội dung, lỗi dọn skeleton, retry, modal cuộn/focus/đóng, toast không chiếm focus; kiểm tra bằng các suite trạng thái riêng |
| Ngôn ngữ | 15 locale, 14 bề mặt ở 360/1440 sáng/tối; provider/credential/plan modal cũng có kiểm tra 15 locale; 1.357 khóa tham chiếu có bản dịch |

Kiểm thử CRUD và ghi cấu hình chạy trên database tạm riêng. Fixture HTTP chỉ
dùng khi cần tái hiện lỗi upstream, quota từng loại, quyền và kết quả OAuth;
không dùng fixture để thay API ghi của bài CRUD thật.

## Kết quả định lượng và bằng chứng

- Baseline và confirmation: **384 trường hợp mỗi lượt**. Confirmation hoàn tất
  trong 123 giây; không có lỗi JavaScript hoặc HTTP API ngoài dự kiến, không có
  phát hiện của bộ đo overflow, bounds modal, accessible labels, placeholder,
  contrast văn bản và các overlap được khai báo.
- Dashboard warmed localhost: 2.333ms baseline, 1.064ms confirmation, dưới mức
  2.500ms trong `CONSTRAINTS.md`. Chỉ là hai mẫu cục bộ, không khẳng định mức cải
  thiện hiệu năng có ý nghĩa thống kê hay p95 production.
- 8/8 luồng CRUD/hồi quy của `populated_workflow_smoke.py` qua; kiểm tra bổ sung
  `provider-specific-quota-presets` qua sau khi chỉnh dữ liệu.
- 52 tests tập trung qua; bổ sung một test shape preset rồi chạy lại toàn bộ 5
  tests `test_demo_database` đều qua (**53 test độc lập** trong phạm vi này).
- 19 browser suites liệt kê dưới đây đều qua. Fast gate qua: lint/format Python,
  compile, manifest 255 core modules, syntax JS, YAML/shell và whitespace.
- Không đo phần trăm changed-line coverage; môi trường chưa có công cụ coverage.
  Không thay ngưỡng, bỏ assertion hoặc đánh dấu skip để qua kiểm tra.

Artifact nằm trong thư mục `temp` được gitignore, không phải source cần commit:

- `temp/populated-instance/before/report.json` và `after/report.json`: ma trận
  DOM/layout và ảnh 13 view, auth, workspace, modal. Ba ảnh quota trong ma trận
  này có trước sửa preset; ảnh xác nhận cuối nằm ở mục kế tiếp.
- `temp/populated-workflows/after/report.json`: kết quả CRUD và ảnh thống kê mới.
- `temp/populated-workflows/quota-presets/`: ba ảnh quota và report xác nhận preset.
- `temp/round2-full-ready/verification/data-report.json`: đối chiếu bản preview
  sau cập nhật, vẫn 87 credentials, 696 lượt gọi, 7.160.680 token, 8 khóa ảo và
  sáu họ OAuth có snapshot.

Các browser suites đã chạy:

```text
credential_management_smoke        credentials_workspace_smoke
provider_quota_smoke               models_ui_smoke
quality_ui_smoke                   settings_ui_smoke
interface_states_smoke             modal_toast_ui_smoke
identity_ui_smoke                  identity_navigation_smoke
activity_ui_smoke                  page_completion_smoke
playground_ui_smoke                extended_providers_smoke
provider_save_result_smoke         provider_entry_smoke
muse_provider_smoke                oauth_callback_ui_smoke
localization_ui_smoke
```

Lệnh tái hiện những kiểm tra mới:

```powershell
.venv/Scripts/python.exe tools/populated_instance_smoke.py --stage review --strict
.venv/Scripts/python.exe tools/populated_workflow_smoke.py --stage review
.venv/Scripts/python.exe -m unittest backend.tests.test_credential_fleet_console backend.tests.test_production_dashboard backend.tests.test_extended_credential_configuration backend.tests.test_demo_application backend.tests.test_demo_database backend.tests.test_demo_preview -q
.venv/Scripts/python.exe tools/quality_gate.py fast
node tools/i18n-audit.mjs
```

## Đánh giá Impeccable trong phạm vi kiểm chứng

| Trục | Điểm / 4 | Cơ sở và giới hạn |
| --- | --- | --- |
| Accessibility | 3 | Nhãn, focus, keyboard, modal, contrast và loading đã thử; chưa chứng nhận bằng screen reader thật |
| Performance | 3 | Dashboard đáp ứng mục tiêu warmed-local; danh sách phân trang, không thêm polling; chưa load-test production |
| Responsive | 3 | Sáu viewport và hai theme qua; control 32px là lựa chọn chủ dự án, không tuyên bố mọi target đạt 44px |
| Theming | 3 | Dùng token hiện hữu, kiểm tra sáng/tối; chưa khẳng định mọi tổ hợp component/OS/browser |
| Implementation integrity | 3 | Sửa tại cơ chế dùng chung, giữ khác biệt provider và dữ liệu chưa biết; đầu vào provider thật vẫn cần kiểm chứng riêng |
| **Tổng** | **15/20** | **Tốt trong phạm vi thử nghiệm, không phải chứng nhận toàn diện** |

Impeccable launcher không chạy vì engine chưa có sẵn. Đã thông báo, không tự cài
package; đọc hướng dẫn và ngữ cảnh dự án trực tiếp, dùng Playwright cùng bộ đo
hiện hữu. Không coi kết quả detector bằng 0 là bằng chứng giao diện hoàn hảo;
lỗi header bị ép chữ được xác nhận qua ảnh và phép đo chiều rộng riêng.

Rà diff theo correctness/readability/architecture/security/performance: không
thêm dependency, không đọc secret để dựng modal, không đổi auth/backend trust
boundary, không tăng số request trang. Các file production chạm tới dưới 1.500
dòng; thay đổi nhỏ thuộc đúng owner nên không tách module hoặc refactor rộng.

## Preview và giới hạn

Preview offline vẫn ở **http://127.0.0.1:4285**. Đã xác nhận nó phục vụ CSS/JS mới.
Chỉ cập nhật **10 snapshot giả** của Antigravity/Grok/Kiro, giữ thời điểm quan sát
cũ, credential, nhãn, mật khẩu, khóa, lưu lượng và cấu hình còn lại. Snapshot sửa
được sao lưu bằng SQLite backup trước khi ghi; bản phục hồi ở
`temp/round2-full-ready/before-quota-preset-fix-2.db`. Một kiểm tra số lượng ban đầu
dừng trước câu UPDATE; bản sao đầu vẫn được giữ. Sau đó dùng số lượng đã xác nhận
trong metadata và chỉ khởi động lại tiến trình demo 4285.

Không có dữ liệu thật bị xóa hoặc ghi đè. Không triển khai Docker hay commit.

Dữ liệu giả chỉ kiểm chứng UI và contract nội bộ, không chứng minh plan/quota,
OAuth, refresh token, billing, inference hoặc độ ổn định thật của nhà cung cấp.
Giá trị phần trăm, thời lượng, tên model và gói minh họa không phải catalog hiện
hành. Chưa thử Firefox/Safari, screen reader/thiết bị cảm ứng thật, mọi mức zoom,
dịch vụ OIDC/PostgreSQL/MongoDB từ xa hoặc mọi tổ hợp trạng thái tùy ý.

Không còn đề xuất sửa thiết kế bắt buộc từ lượt này. Trước khi phát hành, cần
kiểm thử tích hợp thật trong môi trường được cấp quyền và chạy release gate;
không lặp thêm vòng polish chỉ vì một kết quả tổng hợp đạt điểm tốt.

## Bổ sung 2026-09-17: provider không biến mất khi sang ngày mới

Tái hiện trên preview 4285: có 87 credentials nhưng kỳ Hôm nay có 0 lượt gọi,
Dashboard trước sửa hiện danh sách trống. Bộ lọc provider chỉ dựa vào lưu lượng;
nhánh dự phòng đọc thuộc tính `primaryCreds.items` không tồn tại trong manager.

`GET /api/usage/stats/page` bổ sung `provider_inventory`: nhóm credentials hiện có
theo `provider` và `credential_type`, kèm số lượng `credentials`, gồm cả nhóm chưa
có lượt gọi. Danh sách này không phụ thuộc trang hoặc kỳ thống kê; bỏ credentials
đã xóa/lịch sử và lượt gọi chưa gán. `provider_totals` giữ nguyên nghĩa lưu lượng.
Không thêm truy vấn HTTP, dữ liệu bí mật hoặc thay đổi schema database.

Dashboard dùng inventory này để giữ cả provider cũ/mới ở trạng thái chờ, hiển thị
0 lượt gọi và dấu gạch ngang cho tỷ lệ chưa có mẫu. Trống thật vẫn có hướng dẫn kết
nối. Mốc phân loại 60% chưa thay đổi; chấm màu và mô tả truy cập được giữ nguyên.

25 kiểm thử dashboard/pagination đạt; Chromium đạt empty/populated/idle/error,
320–1440px sáng/tối và hover/focus/Esc/chạm. Sau khi khởi động lại riêng preview,
kiểm tra trực tiếp thấy đủ 23 provider khi chuyển Hôm nay → Tất cả → Hôm nay,
vẫn giữ 87 credentials và 696 lượt gọi lịch sử. Không seed lại dữ liệu hay cập nhật Docker.
