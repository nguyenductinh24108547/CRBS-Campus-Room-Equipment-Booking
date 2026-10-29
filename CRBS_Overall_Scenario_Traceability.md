# CRBS — Kịch bản tổng thể và luồng truy vết

**Trạng thái tài liệu:** Bản dự thảo để nhóm rà soát theo nhận xét của giảng viên.  
**Nguồn:** `Scenario First`, `UseCases`, `Requirements`, `State & Decision Rules`, `Business Rules`, `Hazard Trace`, `TestCases`, `TestCode`, `Expanded Trace` trong workbook CRBS hiện có.

## 1. Kịch bản tổng thể SC-00

Trường đại học cần quản lý việc tìm kiếm, đăng ký, phê duyệt, sử dụng và bảo trì phòng học/thiết bị dùng chung. Sinh viên hoặc giảng viên phát sinh nhu cầu sử dụng tài nguyên vào một khung giờ; hệ thống kiểm tra thông tin, quyền truy cập, sức chứa, trạng thái bảo trì và lịch đặt hiện tại. Với buổi thực hành của sinh viên, yêu cầu phải gắn với một giảng viên hướng dẫn được chỉ định và đi qua bước xác nhận hướng dẫn trước khi nhân viên cơ sở vật chất quyết định. Với yêu cầu do giảng viên tự gửi, giảng viên là người khởi tạo booking; nhân viên cơ sở vật chất chịu trách nhiệm duyệt hoặc từ chối. Khi booking được duyệt, nhân viên có thể bàn giao thiết bị; khi hoàn trả phải ghi nhận tình trạng. Nếu thiết bị hỏng hoặc thất lạc, tài nguyên bị chặn khỏi việc sử dụng cho đến khi sự cố được xử lý. Các quyết định quan trọng cần được ghi nhật ký và thông báo cho người liên quan.

SC-00 là bản tổng hợp từ các kịch bản chi tiết hiện có, không phải một sự kiện đã được quan sát độc lập. Nhóm cần xác nhận rằng đây đúng là phạm vi nghiệp vụ cuối cùng.

## 2. Các kịch bản con

| ID | Kịch bản | Luồng chính | Trường hợp ngoại lệ |
|---|---|---|---|
| SC-01 | Giảng viên đặt phòng cho lớp dạy bù/dạy thêm | Giảng viên đăng nhập → tìm phòng/thiết bị → nhập thời gian, mục đích, số người → gửi một yêu cầu → nhân viên cơ sở vật chất duyệt/từ chối → ghi audit và thông báo. | Phòng/thiết bị hết chỗ, sai sức chứa, tài nguyên bị bảo trì, lịch bị xung đột, thiếu quyền, thông báo lỗi. |
| SC-02 | Sinh viên xin phòng thực hành có giảng viên hướng dẫn | Sinh viên chọn phòng và thiết bị → chỉ định giảng viên → gửi yêu cầu ở trạng thái chờ giảng viên xác nhận → giảng viên xác nhận/từ chối → nếu xác nhận, chuyển sang hàng đợi nhân viên cơ sở vật chất → quyết định cuối. | Không có giảng viên, giảng viên khác cố xác nhận, giảng viên từ chối, nhân viên duyệt trước xác nhận, thiết bị không còn khả dụng. |
| SC-03 | Trả thiết bị bị hỏng | Nhân viên ghi nhận checkout/check-in → chọn tình trạng Good/Damaged/Missing → nếu hỏng/thất lạc, mở hoặc liên kết sự cố → đánh dấu tài nguyên không khả dụng → đóng sự cố khi có hướng xử lý. | Không nhập tình trạng, nhập tình trạng không hợp lệ, đóng sự cố không có resolution, có nhiều sự cố đang mở. |
| SC-04 | Hai nhóm cạnh tranh cùng phòng | Hai yêu cầu cùng phòng/khung giờ được gửi gần như đồng thời → hệ thống phải kiểm tra lại khả dụng và giao dịch không cho hai yêu cầu cùng thành công. | Kiểm tra khả dụng bị cũ, yêu cầu đồng thời, phòng hoặc thiết bị đi kèm trở nên không khả dụng, tạo bản ghi một phần. |

## 3. Luồng trạng thái chính

### Booking do giảng viên tự tạo
`Logged In → Pending Staff Approval → Approved / Rejected → (có thể Cancelled nếu đáp ứng chính sách)`

### Booking thực hành do sinh viên yêu cầu
`Submitted → Pending Lecturer Confirmation → Pending Staff Approval → Approved / Rejected`

Giảng viên được chỉ định có thể từ chối yêu cầu đang chờ mình xác nhận; nhân viên cơ sở vật chất không được phê duyệt trước bước xác nhận đó.

### Vòng đời thiết bị
`Available → Reserved / In Use → check-in Good → Available`  
`Available / In Use → Damaged hoặc Missing → Under Maintenance / Unavailable → Incident Resolved → Available nếu không còn sự cố mở`

Các tên trạng thái này cần thống nhất với `State & Decision Rules` và các sơ đồ M-05/M-07/M-06 trước khi được coi là baseline chính thức.

## 4. Mỗi loại dữ liệu có vai trò gì?

- **`project`**: định nghĩa bài toán, mục tiêu và phạm vi.
- **`scenarios`**: mô tả tình huống nghiệp vụ và đường đi từ đầu đến cuối.
- **`stakeholders`**: xác định ai có nhu cầu/quyền quyết định. Vai trò hiện được suy ra từ use case; mức ảnh hưởng và bằng chứng elicitation cần nhóm xác nhận.
- **`requirements` / `nfrs`**: diễn đạt điều hệ thống phải làm và mức chất lượng phải đạt.
- **`use_cases`**: mô tả actor, mục tiêu, điều kiện trước, luồng chính và ngoại lệ.
- **`state_rules`**: mô tả điều kiện chuyển trạng thái và hành vi phải chặn. State rule không phải requirement ID.
- **`models`**: liệt kê sơ đồ dùng để giải thích nghiệp vụ/trạng thái.
- **`hazards`**: nối nguyên nhân → trạng thái không an toàn → hậu quả → biện pháp kiểm soát.
- **`test_data`**: định nghĩa fixture/tham số đầu vào cụ thể cho mỗi test. Dữ liệu còn ở trạng thái draft không được coi là dữ liệu đã thực thi.
- **`test_cases`**: mô tả mục tiêu kiểm thử, bước chạy và kết quả mong đợi.
- **`test_case_analysis`**: nối test case về lại kịch bản, requirement, use case, state rule, hazard, file dữ liệu và hàm test.
- **`evidence/`**: lưu log thực thi và ghi rõ phần mềm/môi trường đã được kiểm tra.

## 5. Ví dụ truy vết một test

**SC-04 → SR-05 → HZ-01 → TC-02 → TD-TC-02 → `test_TC02_overlapping_room_booking_is_rejected` → log pytest**

- SC-04 nói rằng hai nhóm cố đặt cùng một phòng/khung giờ.
- SR-05 định nghĩa quy tắc phát hiện khoảng thời gian bị chồng lấp.
- HZ-01 mô tả hậu quả khi hai booking cùng được chấp nhận.
- TC-02 kiểm tra một yêu cầu mới bị từ chối nếu khung giờ đã có booking xung đột.
- TD-TC-02 cung cấp phòng A101, booking hiện có dài 120 phút, yêu cầu mới bắt đầu lệch 30 phút và kéo dài 60 phút.
- Hàm test tạo dữ liệu, gọi `create_booking`, kiểm tra lỗi và xác nhận chỉ còn booking ban đầu.

Bài test này chạy trên **prototype Python/SQLite** trong gói. Nó không thay thế kiểm thử đồng thời thật trên database của ứng dụng nhóm.

## 6. Các khoảng trống cần nói rõ với giảng viên

1. Trong gói nguồn hiện tại chưa có nhật ký phỏng vấn/workshop có ngày và người tham gia; không được ghi giả định thành buổi elicitation đã diễn ra.
2. TC-01, TC-02, TC-03, TC-05, TC-06, TC-11 và TC-26 có test tự động chạy được trên prototype. TC-04 chưa có file benchmark gốc.
3. Các test còn lại trong danh mục 42 test chưa được thực thi trên ứng dụng nhóm; các dòng `Planned` và `Design Walkthrough` vẫn cần giữ đúng ý nghĩa.
4. Các quy tắc như giới hạn thời hạn đặt trước, quota theo tuần, giới hạn giờ đặt và ranh giới hủy cần được xác nhận trước khi đưa thành chính sách chính thức.
5. Các ID `SC`, `REQ`, `NFR`, `UC`, `SR`, `HZ`, `TC`, `TD` phải được giữ nguyên trong workbook, JSON/CSV, source code và tài liệu giải thích.
