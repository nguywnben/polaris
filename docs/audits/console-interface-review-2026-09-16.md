# Rà soát giao diện Polaris — 16/09/2026

## Phạm vi và định hướng

Thực hiện theo yêu cầu rà soát và chỉnh sửa toàn bộ console, dùng hướng dẫn
Impeccable (Operate, Audit, Layout, Typeset, Harden) và Frontend UI Engineering.
Giữ phong cách đơn sắc, gọn cho thao tác quản trị; không đổi giao thức provider,
quyền hạn, dữ liệu, cơ chế đăng nhập hoặc chiều cao control 32px đã được duyệt.
Không dùng tác tử phụ, không commit, không cập nhật Docker.

Đặc tả và phạm vi kiểm chứng: [console-interface-review](../specs/console-interface-review.md).
Engine kiểm tra tự động của Impeccable chưa được cài đặt. Đã dùng hướng dẫn của
skill, đọc mã nguồn, đo DOM và xem ảnh Chromium; không tuyên bố chứng nhận từ engine.

## Những vấn đề đã xử lý

| Mức | Vấn đề | Điều chỉnh |
| --- | --- | --- |
| Cao | Custom modal chưa cô lập nền, chưa khóa cuộn; Escape dùng listener toàn tài liệu có thể đóng nhiều hộp thoại | Quản lý lớp modal, khôi phục trạng thái `inert`, khóa cuộn, giới hạn Escape trong hộp thoại sở hữu sự kiện; trả focus về nơi mở |
| Cao | Hộp xác nhận đặt focus ngay vào hành động đồng ý | Focus vào bề mặt hộp thoại; Tab mới đi vào các nút, tránh Enter vô tình xác nhận |
| Vừa | Các vùng Identity, Access, About, Activity và quản lý credential có khoảng trắng hoặc chỉ chữ chờ tải | Skeleton dùng chung cho lần tải đầu, `aria-busy`, dọn skeleton khi lỗi; giữ nội dung khi yêu cầu làm mới đang chạy |
| Vừa | Tiêu đề và chữ phụ dùng nhiều cỡ độc lập, một số chữ 11px | Token chữ dùng chung: trang 28px/24px màn hẹp; workspace và modal 20px; section 16px; nội dung 14px; nhãn 13px; metadata 12px |
| Vừa | Một số viền trạng thái dùng màu sáng ngay cả trong theme tối | Màu nền/chữ/viền ngữ nghĩa cho thành công, cảnh báo, lỗi, thông tin và gói cao cấp |
| Vừa | Toast không có nút đóng và có thể che chân custom modal | Thêm nút đóng có nhãn truy cập; nâng vị trí khỏi chân modal; tạm dừng tự ẩn khi hover hoặc focus; giữ focus của thao tác hiện tại |
| Vừa | Skeleton danh sách có độ rộng tối thiểu cứng | Giới hạn theo chiều rộng vùng chứa, dùng được ở 320px |
| Nhỏ | Disclosure thiết lập OIDC chỉ cao khoảng 22px | Vùng bấm tối thiểu 32px, đồng bộ cỡ nhãn và khoảng cách |
| Nhỏ | Toast thao tác credential có thể hiện mã `disable`/`enable` | Dùng tên thao tác từ danh mục bản dịch |
| Vừa | Hủy chỉnh sửa credential dùng field tạo động trả về lựa chọn đầu tiên thay vì cấu hình đã lưu | Ghi nhận giá trị mặc định khi dựng form; kiểm thử hồi quy OpenCode Go/Zen và URL đi kèm |

Ngoài ra: chuẩn hóa khoảng cách tiêu đề/mô tả, chiều cao dòng và ngắt chuỗi dài;
modal dùng giới hạn chiều cao `dvh`, vùng nội dung cuộn riêng và hạn chế cuộn lan
ra nền; tiêu đề chi tiết trace/audit luôn có thể truy cập khi cuộn. Skeleton của
metrics ban đầu, chi tiết trace và cấu hình Google không hiển thị giá trị giả.
Chế độ giảm chuyển động nhắm vào các hiệu ứng chuyển động thay vì ép thời lượng
gần bằng không cho toàn bộ trang.

## Phạm vi đã kiểm chứng

- Ma trận trước/sau: 16 màn hình hoặc biến thể × 6 viewport × 2 theme = 192
  trường hợp mỗi lượt. Viewport: 360×800, 768×1024, 844×390, 1024×768,
  1440×900, 1920×1080. Các bài kiểm tra trạng thái bổ sung 320px.
- Setup, login, OAuth callback; dashboard rỗng/có lưu lượng/phân trang/lỗi;
  danh mục provider và workspace của 23 provider; OAuth/API key, nhập file,
  JSON mẫu, cấu hình nâng cao và kết quả lưu giả lập.
- Credentials: nhận diện OAuth/API key, section 4 cột, thao tác theo provider;
  modal có quota, mô hình, sửa cấu hình, lỗi, thử mô hình, xác minh, xác thực lại,
  hiện/ẩn dữ liệu nhạy cảm theo yêu cầu và xác nhận xóa.
- Models: tìm/chọn/sắp xếp mô hình, lưu lỗi/thành công, chuyển Playground.
  AI Quality: profile, phụ thuộc field, khóa bởi môi trường, preview và lưu.
  Playground: giao thức, streaming, nội dung dài, lỗi, hủy và ví dụ client.
- Access: API key ảo, tạo/sửa/thu hồi, phạm vi, clipboard và form modal.
  Identity: quyền, danh tính, phiên, xung đột tạo, thu hồi/hủy, hướng dẫn OIDC.
- Activity: trace/audit/runtime, lọc, phân trang, chi tiết và chuyển qua lại theo
  request. Settings: cấu hình, mật khẩu, khóa môi trường, backup/dry-run/restore
  và đăng nhập lại trong runtime dùng một lần. About: metadata, capability,
  cập nhật, thiếu dữ liệu/lỗi/thử lại.
- Sidebar: mở/đóng, Tab/Shift+Tab, Escape, chuyển trang và thay đổi breakpoint.
  Modal: nội dung dài, màn hình ngang ngắn, lớp lồng nhau, focus/return-focus,
  xác nhận an toàn. Toast: trước/sau native/custom modal, không cướp focus,
  đóng chủ động, tạm dừng khi đọc và tự ẩn khi rời đi.
- 15 ngôn ngữ; 4.211 phép đo control qua 11 trang, 23 provider, theme và
  breakpoint: giữ 32px, không phát hiện chữ nút bị cắt trong tập dữ liệu đã thử.

## Kết quả và bằng chứng

Ma trận sau sửa: không phát hiện tràn ngang, thiếu tên field, placeholder sai
quy tắc hoặc lỗi tương phản **chữ** theo phép đo. Disclosure OIDC phát hiện ở
lượt này đã được sửa và kiểm chứng riêng lại 12 trường hợp. Các bước chỉnh cuối
được xác nhận lại bằng bài kiểm tra tương ứng, không chạy lặp toàn bộ ma trận.

- Các browser journey nêu trên đạt với dữ liệu tổng hợp/API giả lập và runtime
  cục bộ dùng một lần. Không gọi mô hình thật hoặc sửa credential thật.
- Core: chạy 2.223 kiểm thử; **không thất bại**, 22 skip sẵn có theo môi trường.
  Các fixture DOM được cập nhật để nạp helper skeleton thực tế; không bỏ test
  hoặc hạ ngưỡng để che lỗi.
- Fast gate đạt: lint, format, compile, manifest, JavaScript, YAML, shell,
  whitespace. Kiểm tra bản dịch đạt: 1.349 key tham chiếu có đủ các locale.
- Bản preview `http://127.0.0.1:4284` trả HTTP 200; bundle đang phục vụ chứa
  token chữ, skeleton, toast và cơ chế modal mới. Không cần restart/Docker.

Bằng chứng được giữ trong workspace (không đưa dữ liệu thử vào Git):

- `temp/design-consistency/audit-2026-09-16-before/` và
  `temp/design-consistency/audit-2026-09-16-after/`: ảnh và báo cáo DOM.
- `temp/design-consistency/audit-2026-09-16-confirm/`: xác nhận OIDC.
- `temp/design-consistency/audit-2026-09-16-activity-confirm/`: xác nhận Activity.
- `temp/interface-states/`, `temp/credential-management/`
  và các thư mục `temp/*-ui/`: trạng thái loading, modal và trang có dữ liệu.
- `temp/design-consistency/*smoke*.log`, `core-suite-final.log`,
  `fast-gate-final.log`, `control-sizing-final.log`: kết quả kiểm thử.

## Tự rà mã và giới hạn

Đã rà tính đúng, cấu trúc, khả năng đọc, an toàn đầu ra và chi phí runtime.
Không thêm dependency/framework/API. Nội dung toast và skeleton dùng DOM/text;
SVG nút đóng là hình học tĩnh. Quản lý nền modal lưu và khôi phục `inert` cũ,
không tự mở khóa vùng vốn đã bị khóa. Mỗi skeleton chỉ có ba dòng; không thêm
polling hay request mạng. Không tách/rewrite các module ổn định chỉ để làm đẹp.
Các thay đổi token CSS là cơ học; helper trạng thái và modal nằm ở lớp UI dùng
chung, không trộn vào backend provider.
`providers-and-models.css` đã vượt 1.500 dòng: đợt này chủ yếu đổi khai báo chữ và
token tại selector hiện hữu; không đưa logic mới vào file hoặc thay đổi thứ tự
bundle để tách stylesheet, tránh xáo trộn cascade ngoài phạm vi chỉnh giao diện.

Đây là kiểm chứng Chromium trên Windows với viewport mô phỏng, không thay thế
thử bằng Safari/Firefox, thiết bị cảm ứng thật hoặc trình đọc màn hình. Các giao
dịch provider/OAuth thật, dữ liệu tài khoản thật và mọi tổ hợp dữ liệu tùy ý không
nằm trong lần kiểm chứng này. Không tuyên bố đã bao phủ vô hạn trường hợp hoặc
đạt chứng nhận WCAG toàn diện.
