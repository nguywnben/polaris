# Polaris — rà soát bản cài chưa có dữ liệu, đợt 1

## Phạm vi và kết luận

Rà soát theo yêu cầu chia hai đợt của chủ dự án. Đợt này dùng các runtime SQLite
mới, chỉ lắng nghe loopback, cơ sở dữ liệu và hồ sơ Chromium dùng một lần. Không
dùng preview đang chứa tài khoản thật, không gọi provider thật, không thay đổi
Docker, không commit. Không dùng tác tử phụ.

“Chưa có dữ liệu” là chưa có credential provider, mô hình định tuyến đã cấu hình,
khóa ảo hoặc lưu lượng suy luận. Chủ sở hữu cục bộ, phiên đăng nhập và sự kiện
setup do chính ứng dụng tạo vẫn tồn tại; không xóa chúng để tạo ảnh rỗng giả.
Các bài kiểm tra lỗi và khôi phục sử dụng phản hồi giả lập hoặc backup của chính
runtime tạm, không phải dữ liệu người dùng.

Hệ thống giao diện hiện hữu nhất quán ở các trạng thái đã thử. Không phát hiện
lỗi chặn thao tác trong phạm vi này. Giữ nguyên control 32px, sidebar 36px, bố cục
provider và các khác biệt giao thức. Chỉ sửa chỗ có căn cứ; không thiết kế lại các
trang đã hoạt động đúng.

## Phát hiện và điều chỉnh

| Mức | Phát hiện | Kết quả |
| --- | --- | --- |
| P2 | Playground mở biểu mẫu gửi yêu cầu trên bản cài chưa có mô hình, nhưng không có đường dẫn hướng dẫn tiếp theo | Thêm thông báo danh mục rỗng với nút đến Mô hình và định tuyến; giữ khả năng soạn/gửi yêu cầu, không tự chuyển trang |
| P2 | Bài `empty_state_regression_smoke.py` còn tìm liên kết Cài đặt đã bỏ và đòi hiện chính sách định tuyến khi chưa có mô hình, trái contract hiện tại | Đi qua sidebar; kiểm tra riêng onboarding rỗng và chính sách của tuyến đã cấu hình bằng phản hồi giả lập; vẫn giữ thử lỗi/lưu lại và chứng minh không ghi tuyến |
| P2 — công cụ kiểm chứng | Duyệt locator `details:not([open])` rồi mở từng phần làm danh sách đổi chỉ số và bỏ qua một số disclosure | Duyệt danh sách `details` ổn định; mở tất cả mục nhìn thấy và form nhập API key; gửi trống phải bị chặn trước mọi request ghi |

Playground dùng trạng thái/skeleton dùng chung, có thông báo lỗi và nút thử lại.
Chỉ coi danh mục là rỗng khi API trả đúng một mảng rỗng; lỗi HTTP, JSON sai hoặc
timeout không bị biến thành “chưa có mô hình”. Kết quả cũ không ghi đè kết quả mới.
Request đọc có thời hạn 10 giây, dùng cache danh mục hiện hữu, không ép discovery,
không suy luận, không thêm polling. Cache hết hạn vẫn tuân theo cơ chế discovery
của backend; đây không phải API mới chỉ đọc dữ liệu đã lưu.

Theo hướng dẫn Impeccable, trạng thái rỗng cung cấp bước tiếp theo thay vì chỉ báo
không có dữ liệu. Dùng lại bản dịch và thành phần hiện có, không thêm hệ thống
thiết kế, màu sắc, font hay thư viện mới.

## Bản đồ kiểm chứng

| Bề mặt | Kiểm tra trong đợt 1 |
| --- | --- |
| Setup | Lần chạy đầu, token/preflight giả lập, mật khẩu trống/ngắn/phổ biến/không khớp, hiện/ẩn, khóa khi gửi, lỗi và hoàn tất trên DB tạm |
| Login/callback | Form trống, mật khẩu sai, lỗi mạng, tránh gửi lặp, đăng nhập thành công, callback thiếu tham số và bản dịch |
| Sidebar | Desktop/mobile/ngang thấp, mở/đóng, Tab/Shift+Tab, Escape, trả focus, chuyển trang và thay đổi breakpoint |
| Dashboard | Chưa có credential/lưu lượng, số liệu rỗng, tình trạng yêu cầu, hoạt động gần đây, hướng dẫn kết nối đầu tiên |
| Providers | Danh mục, tìm không có kết quả, phân trang; cả 23 workspace, disclosure và cài đặt nâng cao; mở form API key và chặn dữ liệu trống |
| Credentials | Onboarding chưa có thông tin xác thực, đường dẫn thêm/nhập ZIP; không hiện thống kê/thao tác hàng loạt giả |
| Models | Chưa có mô hình và đường dẫn onboarding; chính sách định tuyến không cạnh tranh với trạng thái này; lưu lỗi/thử lại được kiểm tra riêng bằng tuyến giả lập |
| AI Quality | Bốn profile, field phụ thuộc và bị khóa, validation, preview, save lỗi/thành công, load lỗi/thử lại |
| Playground | Các giao thức, field/tham số/ví dụ client; hướng dẫn rỗng mới, skeleton và retry; kiểm tra gửi/hủy/stream bằng phản hồi tổng hợp, không gọi mô hình |
| Access | Root key được che, ví dụ client, chưa có khóa ảo; mở/đóng modal tạo khóa và các field/scopes |
| Identity | Chủ sở hữu và phiên do setup tạo; OIDC chưa cấu hình, quyền hiệu lực và hướng dẫn nhóm mở rộng; modal tạo danh tính, hủy và trả focus |
| Activity | Request trace rỗng, bộ lọc chưa áp dụng/đã áp dụng/xóa, audit do thao tác quản trị tạo, runtime log rỗng; loading và lỗi |
| Settings | Các nhóm cài đặt, giới hạn bởi môi trường, mật khẩu, lưu/reset giả lập, validation; backup mã hóa, sai/đúng mật khẩu, dry-run, đổi lựa chọn làm mất hiệu lực kế hoạch, hủy/xác nhận restore trên DB tạm và đăng nhập lại |
| About | Thông tin bản dựng/hồ sơ hỗ trợ, các liên kết; skeleton, tải lỗi và giữ nội dung khi làm mới thất bại |
| Modal/toast | Modal native/custom, lớp lồng nhau, focus containment/return, Escape, cuộn nội dung, xác nhận không focus sẵn nút đồng ý; toast đóng được và không cướp focus |

Các provider đã mở: Google Antigravity, Google AI Studio, Grok Build, SpaceXAI
Console, Codex, OpenAI Platform, Claude Code, Claude Platform, Ollama, Kimi API
Platform, Kiro, Cloudflare Workers AI, NVIDIA, OpenCode, Poolside Platform,
Kimchi Coding, Kilo, Muse Code, Meta Model API, GroqCloud, DeepSeek Platform,
Mistral AI Studio và Cerebras Cloud. Luồng đăng nhập provider thật chưa khởi chạy.

## Ma trận và bằng chứng

- Ma trận trang: 16 màn hình/biến thể × 6 kích cỡ × 2 theme = **192** trường hợp.
  Kích cỡ: 360×800, 768×1024, 844×390, 1024×768, 1440×900, 1920×1080.
- Ma trận mở rộng: 13 trang/biến thể + 23 workspace provider + 2 modal tạo mới,
  mỗi bề mặt ở 360/1440px, sáng/tối = **152** trường hợp. Lượt xác nhận đã mở
  thêm form API key và kiểm tra gửi trống. Không cộng trùng lượt sửa bộ duyệt.
- Xác nhận trang thay đổi: Playground, **12** trường hợp theo ma trận trang.
- 15 locale, 14 bề mặt, desktop sáng/mobile tối; kiểm tra placeholder, bản dịch,
  modal tạo khóa, callback và lỗi JavaScript. Không phải chứng nhận dịch bản ngữ.
- Các ma trận không phát hiện tràn ngang, thiếu tên nhập liệu, placeholder sai
  quy tắc, tương phản chữ dưới ngưỡng đo hoặc lỗi JavaScript. Đã xem ảnh để đối
  chiếu thứ bậc chữ, khoảng cách và trạng thái, không chỉ dựa vào assertions.

Ảnh và báo cáo cục bộ (không đưa dữ liệu thử vào Git):

- `temp/design-consistency/empty-round1-before/`
- `temp/empty-instance/expanded-forms/report.json` và ảnh đi kèm
- `temp/design-consistency/empty-round1-confirm/`
- `temp/setup-ui/`, `temp/login-ui/`, `temp/interface-states/`,
  `temp/page-completion/`, `temp/quality-ui/`, `temp/settings-ui/`,
  `temp/playground-ui/`, `temp/localization-ui/`

Kiểm thử hành vi: `setup_ui_smoke`, `login_ui_smoke`, `interface_states_smoke`,
`empty_state_regression_smoke`, `page_completion_smoke`, `quality_ui_smoke`,
`settings_ui_smoke`, `modal_toast_ui_smoke`, `playground_ui_smoke` đều đạt.
Playground có regression viết và chạy thất bại trước khi triển khai, sau đó đạt;
kiểm tra rỗng/có mô hình/lỗi/sai schema/race nằm trong cùng contract.

Static gate: lint, format, Python compile, test manifest, JS/YAML/shell và
whitespace đạt. 1.357 key tham chiếu có đủ 15 locale; backend locale audit đạt.
Core suite: **2.246 test, không thất bại, 22 skip PostgreSQL/MongoDB tùy chọn
đã có sẵn** (198 giây). Log: `temp/empty-instance/core-tests.log`.

## Đánh giá nội bộ theo Impeccable

| Trục | Điểm / 4 | Căn cứ và giới hạn |
| --- | --- | --- |
| Accessibility | 3 | Nhãn, focus, trạng thái, tương phản chữ đã đo; chưa kiểm tra screen reader thực |
| Performance | 2 | Không thêm polling/framework, lookup có timeout; không chạy benchmark/Core Web Vitals trong đợt này |
| Responsive | 3 | Các viewport nêu trên đạt; control 32px theo quyết định chủ dự án, không tuyên bố đạt mục tiêu cảm ứng 44px của skill |
| Theming | 3 | Token và sáng/tối trên ma trận; không chứng nhận mọi tổ hợp màu/dữ liệu |
| Implementation integrity | 3 | Dùng lại UI/state/copy, hướng dẫn rỗng có hành động; sửa công cụ kiểm chứng bị lệch contract |
| Tổng | 14 / 20 | Tốt trong phạm vi kiểm tra, không phải chứng nhận chất lượng toàn sản phẩm |

Bộ nạp/detector Impeccable không hoạt động do engine chưa được cài; không cài thêm
vào môi trường của người dùng. Chrome DevTools MCP không khả dụng; dùng Playwright
Chromium hiện có. Các kết quả là đo DOM và kiểm chứng runtime, không phải kết quả
được engine Impeccable chứng nhận.

## Tự rà mã và ranh giới đợt 2

Thay đổi sản phẩm chỉ ở fragment và module Playground; không sửa auth, provider
protocol, dữ liệu hoặc schema. Output dùng helper tạo text node, không đưa payload
hay secret lên thông báo. Không thêm dependency; module vẫn dưới 1.500 dòng.
Những thay đổi provider audit có sẵn được giữ nguyên và không nhận là việc mới.

Đợt 2 dành cho card/modal credential với thông tin thực của từng provider, plan,
quota ngày/tuần/theo mô hình, credits và thao tác tài khoản; danh sách dài, phân
trang, tuyến thật, lưu lượng/usage/cost, trace/audit chi tiết thực và lỗi provider.
Không suy ra độ ổn định hoặc tính đúng đắn của các dữ liệu này từ kiểm tra rỗng.
Firefox/Safari, thiết bị cảm ứng thật, screen reader và mọi tổ hợp dữ liệu tùy ý
chưa được kiểm chứng. Chờ chủ dự án cung cấp phạm vi và dữ liệu cho đợt 2.
