# Rà soát chức năng và trách nhiệm 14 trang Polaris

Ngày: 2026-09-15. Trạng thái: **báo cáo và đề xuất, chưa triển khai các thay đổi bên dưới**.

## Kết luận

**Giữ 14 trang hiện tại: 11 trang quản trị và 3 trang phục vụ xác thực. Chưa cần thêm hoặc xóa trang. Tuy nhiên, chưa thể gọi toàn bộ luồng giao diện là đầy đủ.**

Các điểm cần xử lý trước khi chốt phạm vi chức năng:

1. Sửa bảng sử dụng bị giới hạn âm thầm ở 100 mục.
2. Đưa sao lưu hệ thống, kiểm tra bản sao lưu và khôi phục lên giao diện Cài đặt; backend đã có.
3. Bổ sung lối đăng nhập OIDC khi tính năng đã bật, cùng hướng dẫn bật tại Danh tính và phiên.
4. Chọn một nơi chỉnh chính sách chọn thông tin xác thực, hiện đang xuất hiện ở cả Mô hình và Cài đặt.

Đây không phải yêu cầu sao chép tất cả tính năng của các dự án tham khảo. Polaris phục vụ một người hoặc nhóm tin cậy 1–20 người, một instance tự lưu trữ; giới hạn sản phẩm trong `CONSTRAINTS.md` vẫn là căn cứ.

## Phạm vi và mức độ bằng chứng

- Đối chiếu fragment trang, điều hướng, JavaScript gọi API, backend tương ứng và tài liệu vận hành của Polaris.
- Hai tác tử đọc độc lập mã nguồn tham khảo; tác tử chính kiểm tra Polaris và xác minh các phát hiện quan trọng.
- Các bản tham khảo nằm trong `C:/Users/nben6/Downloads/repo`: `9router-0.5.35`, `CLIProxyAPI-7.2.137`, `OmniRoute-3.8.49`, `gateway-1.15.2`, `langfuse-4.15.0`, `litellm-1.97.0`.
- Không chạy mã nguồn tải về, không gọi nhà cung cấp có tính phí, không tạo/xóa khóa, đổi cấu hình, khôi phục dữ liệu hay thay đổi Docker.
- Kiểm tra `test_product_surface_inventory.py`: **10/10 đạt**. Kiểm tra này chứng minh việc lập danh mục trang/API/control, không chứng minh mọi luồng sản phẩm đã hoàn chỉnh.
- Kiểm tra cô lập bằng dữ liệu giả lập 101 mục: endpoint sử dụng trả `returned=100`, `total_items=101`, `has_more=True`. Không dùng dữ liệu thật.
- Không chạy lại toàn bộ hành trình có dữ liệu thật của 14 trang trong lượt này. Những chức năng ghi là “đã có” là đã tìm thấy triển khai; không đồng nghĩa đã kiểm chứng mọi biến thể runtime.
- Báo cáo giao diện trạng thái rỗng trước đó không thay thế kiểm tra chức năng có dữ liệu, quyền hạn và lỗi.

## Danh mục và trách nhiệm từng trang

| Trang | Trách nhiệm và chức năng đã có | Kết luận / phần cần hoàn thiện |
| --- | --- | --- |
| `/setup` | Kiểm tra điều kiện cài đặt và mã thiết lập; mở phần tạo mật khẩu sau xác minh; kiểm tra mật khẩu/xác nhận; tạo chủ sở hữu. | Giữ. Chưa tìm thấy thiếu sót chức năng mới trong phạm vi đối chiếu. Không đặt cấu hình nhà cung cấp hoặc quản trị nhóm vào đây. |
| `/login` | Đăng nhập chủ sở hữu bằng mật khẩu; ẩn/hiện mật khẩu; xử lý lỗi và phiên đăng nhập. | Giữ. Thiếu lối vào OIDC trên giao diện khi OIDC đã được cấu hình; endpoint đăng nhập nhóm đã có. |
| `/dashboard` | Tổng lưu lượng, thành công/lỗi, token/chi phí, biểu đồ thời gian, sử dụng theo thông tin xác thực, sức khỏe tuyến và hoạt động gần đây. | Giữ. Sửa giới hạn 100 mục; phân tích theo mô hình/khóa/ngày tùy chọn là nâng cấp, không phải một trang bắt buộc mới. |
| `/providers` | Chọn nhà cung cấp, kết nối OAuth/API key, nhập thông tin xác thực, thiết lập endpoint và cấu hình riêng của nhà cung cấp. | Giữ. Phụ trách kết nối mới, không thay thế việc vận hành kho đã kết nối. Nhiều endpoint tương thích độc lập là mở rộng tùy chọn. |
| `/pool` | Danh sách/lọc/phân trang thông tin xác thực; bật/tắt/xóa, thao tác hàng loạt, kiểm tra, thử mô hình, quota/cooldown tùy khả năng nhà cung cấp, nhập/xuất ZIP. | Giữ. Chức năng kho khá đầy đủ. Cần phân biệt rõ ZIP thông tin xác thực với sao lưu hệ thống. Không yêu cầu quota ở nhà cung cấp không hỗ trợ. |
| `/models` | Danh mục mô hình, tuyến ảo `polaris`, sắp thứ tự dự phòng, chiến lược chọn thông tin xác thực, xác minh, chuyển sang Playground, xử lý tuyến bị đánh dấu không khả dụng. | Giữ. Nên là nơi sở hữu chính sách định tuyến. Hiện chỉ có một alias; nhiều tuyến có tên là nâng cấp tùy chọn, không phải lỗi của baseline một tuyến. |
| `/ai-quality` | Hồ sơ chính sách, phản hồi/ngữ cảnh/guardrail/cache, thứ tự hiệu lực và nguồn ghi đè, lưu/khôi phục, mô phỏng tác động dựa trên metadata. | Giữ. Mô phỏng không phải đánh giá chất lượng câu trả lời thật. Không cần thêm nền tảng đánh giá hoặc kho prompt để trang này đúng chức năng. |
| `/playground` | Thử bốn giao thức, tin nhắn văn bản và chỉ dẫn hệ thống, tham số sinh, stream/hủy, phản hồi thô và metadata, sao chép yêu cầu tương đương. | Giữ. Chưa có trình soạn tools/JSON schema/native body trên UI; backend nhận native request. Đây là phần nên mở rộng nếu muốn kiểm tra đầy đủ yêu cầu của công cụ lập trình. |
| `/access` | Khóa gốc, endpoint, ví dụ client; khóa ảo với phạm vi/mô hình, RPM/TPM, ngân sách/ngày hết hạn, sử dụng, sửa/rotate/revoke. | Giữ. Không thiếu trang quản lý API key. Mẫu cấu hình ứng dụng lập trình cụ thể sẽ hữu ích hơn việc chỉ có mẫu giao thức/SDK. |
| `/identity` | Danh tính/quyền hiệu lực, OIDC và khả năng khôi phục, gán vai trò/bật tắt danh tính, danh sách và thu hồi phiên, vô hiệu hóa phiên OIDC theo chính sách. | Giữ kể cả khi truy cập nhóm tắt. Nên có hướng dẫn kích hoạt OIDC và liên kết đăng nhập; không cần biến thành hệ thống tổ chức/doanh nghiệp. |
| `/activity` | Ba tab dấu vết yêu cầu, kiểm toán/bảo mật, nhật ký runtime; bộ lọc chung và riêng, chi tiết, phân trang/xuất dữ liệu, liên kết điều tra theo request ID. | Giữ làm nơi điều tra. Lọc theo độ trễ/chi phí là bổ sung tùy chọn. Không cần tách lại trang Logs/Audit trên sidebar. |
| `/config` | Ngôn ngữ/giao diện, truy cập máy chủ và mật khẩu, log, lưu trữ/proxy, định tuyến/thử lại, tương thích, keep-alive và lưu giữ trace/audit. | Giữ. Thiếu UI sao lưu/khôi phục; có thể bổ sung trạng thái telemetry hiện có. Tránh chỉnh cùng chính sách định tuyến ở hai trang. |
| `/about` | Thông tin dự án, bản dựng, phạm vi hỗ trợ, kiểm tra cập nhật, liên kết tài liệu bảo trì và tài trợ. | Giữ. Chức năng phù hợp. Không nên đặt thao tác khôi phục dữ liệu thật hoặc sửa cấu hình ở đây. |
| `/callback` | Kết quả callback OAuth nhà cung cấp, trạng thái thành công/lỗi và đường quay lại quy trình. | Giữ, không đưa vào sidebar. Callback OIDC `/api/identity/oidc/callback` là endpoint chuyển hướng riêng, không phải trang quản trị thứ 15. |

Nguồn điều hướng: `frontend/js/core/navigation.js:5`, `:142`; route server: `backend/core/panel/root.py:273`, `:332`.
Các đường `/provider`, `/oauth`, `/upload`, `/audit`, `/logs` là đường tương thích hoặc lối vào tab/chức năng hiện hữu; không đếm chúng thành các trang sản phẩm độc lập.

## A. Thiếu sót cần ưu tiên

### A1. Tổng quan: phân trang không bao phủ dữ liệu sau mục 100

**Loại:** lỗi bao phủ dữ liệu, cần sửa trước khi khẳng định bảng đầy đủ.

`backend/core/panel/usage_routes.py:43` chỉ nhận `period`, `timezone_offset_minutes`, `page_size`; tại dòng 64 trả `ordered[:page_size]`, có `total_items`/`has_more` nhưng không có cursor hoặc offset để lấy phần tiếp theo.

`frontend/js/features/dashboard.js:254` yêu cầu 100 mục; dòng 268 chỉ lưu `.data`. `renderUsageList` tại dòng 636 và danh sách lịch sử chỉ chia trang trên mảng đã bị cắt. Tổng hợp theo nhà cung cấp tại dòng 681 cũng dùng tập con này.

Hệ quả: khi có hơn 100 mục nguồn, người dùng không thể xem các mục sau đó; tổng hợp theo nhà cung cấp có thể thiếu. **Không kết luận tổng chi phí toàn hệ thống sai:** `/api/usage/aggregated` tại `usage_routes.py:71` tính từ toàn bộ tập dữ liệu.

Đề xuất: phân trang server thực sự và tổng hợp nhà cung cấp độc lập với trang hiện tại. Nếu chủ ý chỉ hiển thị top 100, phải ghi rõ và cung cấp cách truy cập phần còn lại; cách đó chưa đáp ứng mong muốn xem đầy đủ của chủ dự án.

Điều kiện nghiệm thu: dữ liệu 101+ mục, có mục lịch sử, chuyển trang tới mục cuối; số liệu tổng không thay đổi theo trang; không bỏ sót/trùng mục.

### A2. Cài đặt: thiếu luồng sao lưu và khôi phục hệ thống trên UI

**Loại:** backend đã có, giao diện chưa cung cấp.

`backend/core/panel/backup_routes.py:176`, `:195`, `:216`, `:242` cung cấp tạo bản sao lưu mã hóa, kiểm tra/dry-run, khôi phục, xuất dữ liệu đã loại bỏ thông tin nhạy cảm. Tìm kiếm các fragment và JavaScript không thấy caller `/api/backups`; `frontend/fragments/pages/about.html:41` chỉ dẫn tới tài liệu.

ZIP tại `frontend/js/features/credential-pool.js:55` và `:161` gọi `/api/credentials/download-all`, không phải full-system backup. Sao lưu/khôi phục là hành trình core của chính Polaris (`CONSTRAINTS.md`, Required User Journeys), không chỉ là tính năng học theo đối thủ.

Đề xuất: section **Sao lưu và khôi phục** trong Cài đặt. Có tải bản mã hóa, nhập archive/passphrase, xem kế hoạch kiểm tra trước, xác nhận khôi phục riêng, trạng thái thành công/lỗi và yêu cầu đăng nhập lại. Giải thích sanitized export không dùng để khôi phục. About vẫn giữ liên kết tài liệu.

Điều kiện nghiệm thu: kiểm tra quyền; archive sai/passphrase sai không đổi dữ liệu; dry-run không ghi; khôi phục cần xác nhận; thất bại giữ hoặc phục hồi trạng thái cũ; không ghi bí mật vào toast/log. Chỉ kiểm tra restore thật trong môi trường thử nghiệm có bản sao lưu.

### A3. Login và Identity: hoàn thiện lối vào truy cập nhóm

**Loại:** thiếu khả năng tìm và bắt đầu luồng khi chế độ tùy chọn đã bật.

`frontend/fragments/auth/login.html:10` chỉ có form mật khẩu; `frontend/js/features/authentication.js:440` đăng nhập qua `/api/auth/login`. Không tìm thấy liên kết khởi tạo OIDC trong frontend.

Trong khi đó `backend/core/panel/identity_browser_routes.py:60` có `/api/identity/oidc/start`; tài liệu `docs/oidc-foundation.md:147` mô tả truy cập trực tiếp. OIDC không bị thiếu backend và quản trị viên vẫn có thể chia sẻ URL này.

Đề xuất: nút **Đăng nhập bằng tài khoản nhóm** trên Login khi cấu hình công khai an toàn báo OIDC khả dụng; Identity có hướng dẫn bật, trạng thái và đường dẫn liên quan. Cấu hình bằng môi trường vẫn có thể giữ nguyên; không bắt buộc đưa secret OIDC lên UI. Giữ đăng nhập chủ sở hữu cục bộ và đường khôi phục độc lập.

Điều kiện nghiệm thu: OIDC tắt/bật/cấu hình lỗi/IdP không truy cập được; quay lại Login có thông báo phù hợp; chủ sở hữu vẫn vào được khi OIDC lỗi; không lộ issuer secret hoặc token.

### A4. Models và Settings: cùng sửa một chính sách định tuyến

**Loại:** trùng trách nhiệm, không phải hai chức năng độc lập.

`frontend/fragments/pages/models.html:53` và `frontend/fragments/pages/settings.html:107` cùng có chiến lược chọn thông tin xác thực/nhà cung cấp ưu tiên. `frontend/js/features/model-pool.js:506` và `:516` ghi `routing_strategy`/`preferred_provider` vào `/api/config/save`.

Đề xuất: **Models là nơi chỉnh chính**. Cài đặt hiển thị tóm tắt/liên kết tới Models nếu cần. Chính sách thử lại và giới hạn runtime vẫn ở Cài đặt. Không cần xóa một trong hai trang.

Điều kiện nghiệm thu: một nguồn dữ liệu có thẩm quyền; thay đổi không bị form cũ ở trang khác ghi đè; khóa bởi môi trường được giải thích thống nhất.

## B. Tính năng đáng cân nhắc, không phải thiếu sót bắt buộc của baseline

| Bổ sung | Đặt tại | Bằng chứng so sánh và giới hạn |
| --- | --- | --- |
| Nhiều tuyến có tên, ví dụ coding/fast/quality | Models | 9router `src/app/api/combos/route.js:21` tạo nhiều combo theo tên. Polaris `backend/core/model_pool.py:18`, `:181`, `:323` chỉ có alias `polaris`. Một tuyến hiện tại vẫn đáp ứng baseline; nhiều tuyến cần đặc tả lifecycle và tính tương thích trước khi làm. |
| Soạn native JSON/tools/structured output | Playground | OmniRoute `src/app/(dashboard)/dashboard/playground/components/tabs/BuildTab.tsx:84`, `:89` có tools/schema. Polaris UI `frontend/js/features/playground.js:16`, `:63` chỉ dựng tin nhắn văn bản/tham số; backend `backend/core/panel/playground.py:81` nhận native request. Nên ưu tiên kiểm tra khả năng công cụ lập trình trước tính năng chat giải trí. |
| Mẫu cấu hình ứng dụng, chọn mô hình cho ví dụ | Access | 9router `src/app/(dashboard)/dashboard/cli-tools/components/CodexToolCard.js:167`, `:233` có cấu hình ứng dụng và trường hợp gateway từ xa. Polaris `frontend/js/features/virtual-keys.js:22` có cURL/PowerShell/Python/Node, ví dụ dùng `polaris`. Cần placeholder, không tự sửa tệp máy client từ container. |
| Nhóm sử dụng theo mô hình/khóa và khoảng ngày tùy chọn | Dashboard | LiteLLM `ui/litellm-dashboard/src/app/(dashboard)/usage/_components/components/EntityUsage/EntityUsage.tsx:119`, `:158`, `:802` có ngày/nhóm/export. Polaris usage API chủ yếu theo period và credential; Access đã có tổng dùng riêng của khóa tại `virtual-keys.js:536`. Không gọi việc ghi nhận chi phí theo khóa là hoàn toàn thiếu. |
| Lọc yêu cầu chậm hoặc tốn chi phí | Activity | Langfuse `web/src/features/filters/config/traces-config.ts:92`, `:137`. Polaris đã lưu/hiển thị thời gian và chi phí, bộ lọc `frontend/js/features/traces.js:102` chưa có ngưỡng hai trường này. Không cần tạo trang Analytics riêng. |
| Trạng thái và hướng dẫn telemetry đang hỗ trợ | Settings | LiteLLM `ui/litellm-dashboard/src/components/logging_settings_view.tsx:65`. Polaris `backend/core/panel/observability_routes.py:63` trả telemetry; `backend/core/telemetry_policy.py:28` chiếu an toàn trạng thái Prometheus/OTel nhưng Dashboard chưa hiển thị. Langfuse cần projection thích hợp nếu đưa lên UI. “Đã bật” không đồng nghĩa “đang gửi thành công”. |
| So sánh hai mô hình | Playground | OmniRoute `src/app/(dashboard)/dashboard/playground/components/tabs/CompareTab.tsx:15`, `:332` có so sánh giới hạn. Ưu tiên thấp; phải báo số request/chi phí tăng và hỗ trợ hủy. |
| Nhiều kết nối endpoint tương thích độc lập | Providers | 9router `src/app/api/provider-nodes/route.js:32`; CLIProxyAPI `internal/config/config_types.go:641`. Polaris đã cho đổi endpoint toàn cục, không phải hoàn toàn không hỗ trợ URL tùy chỉnh. Chỉ mở rộng khi có nhu cầu nhiều endpoint đồng thời và được chấp thuận phạm vi. |

Không bổ sung chỉ vì repo tham khảo có: billing, organizations, SAML/SCIM, plugin marketplace, HA/Kubernetes, prompt datasets/evaluations toàn diện, hàng trăm nhà cung cấp hoặc media platform. Langfuse là một nền tảng kỹ thuật LLM rộng hơn; repo `gateway-1.15.2` cũng không đại diện đầy đủ cho giao diện Portkey hosted. Log UI trong repo gateway nằm ở `src/start-server.ts:44`, `:72`, có điều kiện development; Polaris đã có log trực tiếp có xác thực.

## C. Có trang dư hoặc cần thêm không?

- **Không xóa Providers hoặc Pool:** một trang kết nối mới, một trang vận hành các kết nối đã có. Các lối nhập file có thể dùng chung component mà vẫn hợp lý ở cả hai.
- **Không gộp Access và Identity:** Access cấp quyền cho client API; Identity cấp quyền cho người quản trị và phiên console.
- **Không gộp Dashboard và Activity:** một trang tổng quan/tổng hợp, một trang điều tra sự kiện cụ thể.
- **Không tách Audit/Logs:** đã là tab của Activity.
- **Không thêm Backup, Usage, Integrations, CLI Tools chỉ để đạt parity:** các phần cần thiết có chủ sở hữu trong Settings, Dashboard và Access.
- **Không đưa Setup/Login/Callback lên sidebar:** đó là các bước vòng đời truy cập, không phải nơi quản trị thường xuyên.

Thứ tự xử lý đề xuất: A1 → A2 → A3 → A4, sau đó cân nhắc native request trong Playground, cấu hình ứng dụng trong Access và nhiều tuyến trong Models. Mỗi phần là một thay đổi riêng có tiêu chí nghiệm thu; không ngầm coi danh sách B là yêu cầu đã duyệt.

## D. Điều kiện để chốt “đầy đủ”

Không dùng số lượng trang, trạng thái rỗng đẹp hoặc kiểm tra danh mục đạt làm bằng chứng đầy đủ chức năng. Trước khi chốt cần:

1. Hoàn thiện hoặc ghi nhận quyết định rõ cho A1–A4.
2. Kiểm tra mỗi thao tác theo quyền: xem, tạo, sửa, thu hồi/xóa khi có ý nghĩa; trang nhật ký không cần CRUD nội dung nhật ký.
3. Kiểm tra rỗng/có dữ liệu/nhiều trang dữ liệu, lỗi mạng, timeout, dữ liệu cũ, giới hạn môi trường và quyền không đủ.
4. Chạy hành trình provider → credential → route → Playground → virtual key/client → trace/usage bằng môi trường thử nghiệm phù hợp.
5. Kiểm tra sao lưu/khôi phục và OIDC riêng trong môi trường kiểm thử; không suy ra từ việc API tồn tại.

Lượt này chỉ thêm báo cáo; không sửa chức năng, không commit/push, không thay đổi dịch vụ đang chạy.
