// Contextual authentication copy shared by old and new provider workspaces.
const PROVIDER_AUTH_KEYS = ['intro', 'notice', 'method', 'token_region', 'start_url', 'key_help', 'login_help', 'import_description', 'add_description', 'token_label', 'token_placeholder', 'error'];
const PROVIDER_AUTH_COPY = {
    en: ['Sign in to Kiro with OAuth, or use an API key from your Kiro account.', 'Direct Kiro API compatibility follows the reference implementation and may change with the upstream service.', 'Sign-in method', 'AWS sign-in region', 'IAM Identity Center start URL', 'Alternatively, create a key under API Keys in your Kiro account. A supported paid plan is required.', 'Generate a device code, open the sign-in page, approve access, then check authorization here.', 'Import JSON or ZIP credentials. Importing does not verify access; check the credential and test a model in the pool.', 'Load the model catalog and save the credential. A model test is still needed to confirm inference access.', 'API token', 'Paste your API token', 'Kiro sign-in could not be completed. Check your connection and try again, or start a new login.'],
    vi: ['Đăng nhập Kiro bằng OAuth hoặc dùng khóa API từ tài khoản Kiro.', 'Khả năng tương thích API Kiro trực tiếp dựa trên mã tham khảo và có thể thay đổi theo dịch vụ thượng nguồn.', 'Phương thức đăng nhập', 'Khu vực đăng nhập AWS', 'URL bắt đầu của IAM Identity Center', 'Bạn cũng có thể tạo khóa tại mục API Keys trong tài khoản Kiro. Cần gói trả phí được hỗ trợ.', 'Tạo mã thiết bị, mở trang đăng nhập, cấp quyền rồi kiểm tra trạng thái cấp quyền tại đây.', 'Nhập thông tin xác thực từ JSON hoặc ZIP. Thao tác nhập không xác minh quyền truy cập; hãy xác minh thông tin và kiểm tra một mô hình trong kho.', 'Tải danh mục mô hình và lưu thông tin xác thực. Vẫn cần kiểm tra một mô hình để xác nhận quyền gọi.', 'Token API', 'Dán API token của bạn', 'Chưa hoàn tất đăng nhập Kiro. Kiểm tra kết nối rồi thử lại hoặc bắt đầu phiên đăng nhập mới.'],
    'zh-CN': ['通过 OAuth 登录 Kiro，或使用 Kiro 账户的 API 密钥。', '直接调用 Kiro API 的兼容性基于参考实现，可能随上游服务变化。', '登录方式', 'AWS 登录区域', 'IAM Identity Center 起始 URL', '也可在 Kiro 账户的 API Keys 中创建密钥，需要受支持的付费套餐。', '生成设备代码，打开登录页面并授权，然后在此检查授权状态。', '从 JSON 或 ZIP 导入凭据。导入不会验证访问权限；请在凭据池中验证凭据并测试模型。', '加载模型目录并保存凭据。仍需测试模型以确认推理权限。', 'API 令牌', '粘贴 API 令牌', '无法完成 Kiro 登录。请检查连接后重试，或重新登录。'],
    'zh-TW': ['透過 OAuth 登入 Kiro，或使用 Kiro 帳戶的 API 金鑰。', '直接呼叫 Kiro API 的相容性依據參考實作，可能隨上游服務變更。', '登入方式', 'AWS 登入區域', 'IAM Identity Center 起始 URL', '也可在 Kiro 帳戶的 API Keys 建立金鑰，需要支援的付費方案。', '產生裝置代碼，開啟登入頁面並授權，再於此檢查授權狀態。', '從 JSON 或 ZIP 匯入憑證。匯入不會驗證存取權；請在憑證集區中驗證憑證並測試模型。', '載入模型目錄並儲存憑證。仍需測試模型以確認推論權限。', 'API 權杖', '貼上 API 權杖', '無法完成 Kiro 登入。請檢查連線後重試，或重新登入。'],
    ja: ['OAuth で Kiro にログインするか、Kiro アカウントの API キーを使用します。', 'Kiro API への直接接続は参照実装に基づいており、接続先の変更により動作が変わる場合があります。', 'ログイン方法', 'AWS ログインリージョン', 'IAM Identity Center の開始 URL', 'Kiro アカウントの API Keys でキーを作成することもできます。対応する有料プランが必要です。', 'デバイスコードを生成し、ログインページでアクセスを許可してから、ここで認証状態を確認します。', 'JSON または ZIP から認証情報をインポートします。インポートではアクセス権を検証しません。プールで認証情報を検証し、モデルをテストしてください。', 'モデル一覧を取得して認証情報を保存します。推論のアクセス権を確認するには、モデルのテストが必要です。', 'API トークン', 'API トークンを貼り付け', 'Kiro へのログインを完了できませんでした。接続を確認して再試行するか、ログインをやり直してください。'],
    ko: ['OAuth로 Kiro에 로그인하거나 Kiro 계정의 API 키를 사용하세요.', 'Kiro API 직접 연결은 참조 구현을 기반으로 하며 상위 서비스 변경에 따라 달라질 수 있습니다.', '로그인 방식', 'AWS 로그인 리전', 'IAM Identity Center 시작 URL', 'Kiro 계정의 API Keys에서 키를 만들 수도 있습니다. 지원되는 유료 요금제가 필요합니다.', '기기 코드를 생성하고 로그인 페이지에서 접근을 승인한 다음 여기에서 인증 상태를 확인하세요.', 'JSON 또는 ZIP에서 인증 정보를 가져옵니다. 가져오기는 접근 권한을 검증하지 않습니다. 풀에서 인증 정보를 검증하고 모델을 테스트하세요.', '모델 목록을 불러와 인증 정보를 저장합니다. 추론 접근 권한을 확인하려면 모델 테스트가 필요합니다.', 'API 토큰', 'API 토큰 붙여넣기', 'Kiro 로그인을 완료하지 못했습니다. 연결을 확인하고 다시 시도하거나 새 로그인을 시작하세요.'],
    de: ['Mit OAuth bei Kiro anmelden oder einen API-Schlüssel des Kiro-Kontos verwenden.', 'Die direkte Kiro-API-Anbindung basiert auf der Referenzimplementierung und kann sich mit dem Dienst ändern.', 'Anmeldemethode', 'AWS-Anmelderegion', 'Start-URL von IAM Identity Center', 'Alternativ unter API Keys im Kiro-Konto einen Schlüssel erstellen. Ein unterstützter kostenpflichtiger Tarif ist erforderlich.', 'Gerätecode erzeugen, Anmeldeseite öffnen und Zugriff erlauben. Anschließend hier die Autorisierung prüfen.', 'Zugangsdaten aus JSON oder ZIP importieren. Der Import prüft keinen Zugriff; Zugangsdaten im Pool prüfen und ein Modell testen.', 'Modellkatalog laden und Zugangsdaten speichern. Ein Modelltest muss den Inferenzzugriff noch bestätigen.', 'API-Token', 'API-Token einfügen', 'Kiro-Anmeldung nicht abgeschlossen. Verbindung prüfen und erneut versuchen oder eine neue Anmeldung starten.'],
    es: ['Inicia sesión en Kiro con OAuth o usa una clave API de tu cuenta de Kiro.', 'La compatibilidad directa con la API de Kiro se basa en la implementación de referencia y puede cambiar con el servicio.', 'Método de inicio de sesión', 'Región de inicio de sesión de AWS', 'URL de inicio de IAM Identity Center', 'También puedes crear una clave en API Keys de tu cuenta de Kiro. Se requiere un plan de pago compatible.', 'Genera un código de dispositivo, abre la página de inicio de sesión, autoriza el acceso y comprueba aquí la autorización.', 'Importa credenciales JSON o ZIP. La importación no verifica el acceso; verifica las credenciales y prueba un modelo en el grupo.', 'Carga el catálogo de modelos y guarda las credenciales. Aún debes probar un modelo para confirmar el acceso a inferencia.', 'Token de API', 'Pega tu token de API', 'No se pudo completar el inicio de sesión en Kiro. Comprueba la conexión y reintenta o inicia una nueva sesión.'],
    fr: ['Connectez-vous à Kiro avec OAuth ou utilisez une clé API de votre compte Kiro.', 'La compatibilité directe avec l’API Kiro repose sur l’implémentation de référence et peut évoluer avec le service.', 'Méthode de connexion', 'Région de connexion AWS', 'URL de démarrage IAM Identity Center', 'Vous pouvez aussi créer une clé dans API Keys de votre compte Kiro. Un forfait payant compatible est requis.', 'Générez un code d’appareil, ouvrez la page de connexion, autorisez l’accès, puis vérifiez l’autorisation ici.', 'Importez des identifiants JSON ou ZIP. L’importation ne vérifie pas l’accès ; vérifiez les identifiants et testez un modèle dans le pool.', 'Chargez le catalogue de modèles et enregistrez les identifiants. Un test de modèle reste nécessaire pour confirmer l’accès à l’inférence.', 'Jeton API', 'Collez votre jeton API', 'La connexion à Kiro n’a pas abouti. Vérifiez la connexion et réessayez, ou relancez l’authentification.'],
    it: ['Accedi a Kiro con OAuth oppure usa una chiave API del tuo account Kiro.', 'La compatibilità diretta con l’API Kiro si basa sull’implementazione di riferimento e può cambiare con il servizio.', 'Metodo di accesso', 'Regione di accesso AWS', 'URL iniziale di IAM Identity Center', 'Puoi anche creare una chiave in API Keys del tuo account Kiro. È richiesto un piano a pagamento supportato.', 'Genera un codice dispositivo, apri la pagina di accesso, autorizza l’accesso e verifica qui l’autorizzazione.', 'Importa credenziali JSON o ZIP. L’importazione non verifica l’accesso; verifica le credenziali e prova un modello nel pool.', 'Carica il catalogo dei modelli e salva le credenziali. Devi ancora provare un modello per confermare l’accesso all’inferenza.', 'Token API', 'Incolla il token API', 'Accesso a Kiro non completato. Controlla la connessione e riprova oppure avvia un nuovo accesso.'],
    pt: ['Entre no Kiro com OAuth ou use uma chave API da sua conta Kiro.', 'A compatibilidade direta com a API do Kiro segue a implementação de referência e pode mudar com o serviço.', 'Método de login', 'Região de login da AWS', 'URL inicial do IAM Identity Center', 'Você também pode criar uma chave em API Keys na sua conta Kiro. É necessário um plano pago compatível.', 'Gere um código de dispositivo, abra a página de login, autorize o acesso e verifique a autorização aqui.', 'Importe credenciais JSON ou ZIP. A importação não verifica o acesso; verifique as credenciais e teste um modelo no pool.', 'Carregue o catálogo de modelos e salve as credenciais. Ainda é necessário testar um modelo para confirmar o acesso à inferência.', 'Token de API', 'Cole seu token de API', 'Não foi possível concluir o login no Kiro. Verifique a conexão e tente novamente ou inicie um novo login.'],
    ru: ['Войдите в Kiro через OAuth или используйте API-ключ своей учётной записи Kiro.', 'Прямое подключение к API Kiro основано на эталонной реализации и может меняться вместе с сервисом.', 'Способ входа', 'Регион входа AWS', 'Начальный URL IAM Identity Center', 'Также можно создать ключ в разделе API Keys учётной записи Kiro. Требуется поддерживаемый платный тариф.', 'Создайте код устройства, откройте страницу входа и разрешите доступ. Затем проверьте авторизацию здесь.', 'Импортируйте учётные данные из JSON или ZIP. Импорт не проверяет доступ; проверьте учётные данные и протестируйте модель в пуле.', 'Загрузите каталог моделей и сохраните учётные данные. Для подтверждения доступа к генерации необходимо протестировать модель.', 'Токен API', 'Вставьте токен API', 'Не удалось завершить вход в Kiro. Проверьте соединение и повторите попытку или начните новый вход.'],
    id: ['Masuk ke Kiro dengan OAuth atau gunakan kunci API akun Kiro Anda.', 'Kompatibilitas API Kiro langsung mengikuti implementasi referensi dan dapat berubah bersama layanan hulu.', 'Metode masuk', 'Wilayah masuk AWS', 'URL awal IAM Identity Center', 'Anda juga dapat membuat kunci di API Keys pada akun Kiro. Diperlukan paket berbayar yang didukung.', 'Buat kode perangkat, buka halaman masuk, izinkan akses, lalu periksa otorisasi di sini.', 'Impor kredensial JSON atau ZIP. Impor tidak memverifikasi akses; verifikasi kredensial dan uji model di kumpulan.', 'Muat katalog model dan simpan kredensial. Uji model tetap diperlukan untuk memastikan akses inferensi.', 'Token API', 'Tempel token API Anda', 'Login Kiro belum selesai. Periksa koneksi dan coba lagi atau mulai login baru.'],
    th: ['เข้าสู่ระบบ Kiro ด้วย OAuth หรือใช้คีย์ API จากบัญชี Kiro ของคุณ', 'การเชื่อมต่อ API ของ Kiro โดยตรงอิงตามการใช้งานอ้างอิงและอาจเปลี่ยนแปลงตามบริการต้นทาง', 'วิธีเข้าสู่ระบบ', 'ภูมิภาคที่ใช้เข้าสู่ระบบ AWS', 'URL เริ่มต้นของ IAM Identity Center', 'คุณสามารถสร้างคีย์ในเมนู API Keys ของบัญชี Kiro ได้เช่นกัน โดยต้องใช้แผนแบบชำระเงินที่รองรับ', 'สร้างรหัสอุปกรณ์ เปิดหน้าเข้าสู่ระบบ อนุญาตการเข้าถึง แล้วตรวจสอบการอนุญาตที่นี่', 'นำเข้าข้อมูลรับรองจาก JSON หรือ ZIP การนำเข้าไม่ตรวจสอบสิทธิ์การเข้าถึง โปรดตรวจสอบข้อมูลรับรองและทดสอบโมเดลในคลัง', 'โหลดรายการโมเดลและบันทึกข้อมูลรับรอง ยังต้องทดสอบโมเดลเพื่อยืนยันสิทธิ์การอนุมาน', 'โทเค็น API', 'วางโทเค็น API ของคุณ', 'เข้าสู่ระบบ Kiro ไม่สำเร็จ โปรดตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง หรือเริ่มเข้าสู่ระบบใหม่'],
    tr: ['Kiro’ya OAuth ile giriş yapın veya Kiro hesabınızın API anahtarını kullanın.', 'Doğrudan Kiro API uyumluluğu referans uygulamayı temel alır ve üst hizmetle birlikte değişebilir.', 'Giriş yöntemi', 'AWS giriş bölgesi', 'IAM Identity Center başlangıç URL’si', 'Kiro hesabınızdaki API Keys bölümünde de anahtar oluşturabilirsiniz. Desteklenen ücretli bir plan gerekir.', 'Cihaz kodu oluşturun, giriş sayfasını açıp erişime izin verin ve yetkilendirmeyi burada kontrol edin.', 'JSON veya ZIP kimlik bilgilerini içe aktarın. İçe aktarma erişimi doğrulamaz; havuzda kimlik bilgilerini doğrulayın ve bir modeli test edin.', 'Model kataloğunu yükleyip kimlik bilgilerini kaydedin. Çıkarım erişimini doğrulamak için model testi yine de gereklidir.', 'API belirteci', 'API belirtecinizi yapıştırın', 'Kiro girişi tamamlanamadı. Bağlantınızı kontrol edip tekrar deneyin veya yeni bir giriş başlatın.']
};
// One interaction vocabulary for all provider workspaces; no claim of inference validation.
const PROVIDER_UI_KEYS = ['add_key', 'key_intro', 'get_link', 'device_code', 'open_login', 'expires_at', 'copy_code'];
const PROVIDER_UI_COPY = {
    en: ['Add key', 'Add your API key to the credential pool. Then test a model in the pool to confirm access.', 'Get sign-in link', 'Device code', 'Open sign-in page', 'Expires at {time}', 'Copy code'],
    vi: ['Thêm khóa', 'Thêm khóa API vào kho thông tin xác thực. Sau đó kiểm tra một mô hình trong kho để xác nhận quyền truy cập.', 'Lấy liên kết đăng nhập', 'Mã thiết bị', 'Mở trang đăng nhập', 'Hết hạn lúc {time}', 'Sao chép mã'],
    'zh-CN': ['添加密钥', '将 API 密钥添加到凭据池，然后在池中测试一个模型以确认访问权限。', '获取登录链接', '设备代码', '打开登录页面', '到期时间：{time}', '复制代码'],
    'zh-TW': ['新增金鑰', '將 API 金鑰新增至憑證集區，再於集區中測試一個模型以確認存取權限。', '取得登入連結', '裝置代碼', '開啟登入頁面', '到期時間：{time}', '複製代碼'],
    de: ['Schlüssel hinzufügen', 'Fügen Sie den API-Schlüssel zum Zugangsdatenpool hinzu. Testen Sie anschließend dort ein Modell, um den Zugriff zu bestätigen.', 'Anmeldelink abrufen', 'Gerätecode', 'Anmeldeseite öffnen', 'Gültig bis {time}', 'Code kopieren'],
    es: ['Añadir clave', 'Añade tu clave API al grupo de credenciales. Después, prueba un modelo del grupo para confirmar el acceso.', 'Obtener enlace de acceso', 'Código de dispositivo', 'Abrir página de acceso', 'Caduca a las {time}', 'Copiar código'],
    fr: ['Ajouter la clé', 'Ajoutez votre clé API au pool d’identifiants, puis testez un modèle du pool pour confirmer l’accès.', 'Obtenir le lien de connexion', 'Code de l’appareil', 'Ouvrir la page de connexion', 'Expire à {time}', 'Copier le code'],
    id: ['Tambah kunci', 'Tambahkan kunci API ke kumpulan kredensial. Lalu uji model di kumpulan untuk memastikan akses.', 'Dapatkan tautan masuk', 'Kode perangkat', 'Buka halaman masuk', 'Kedaluwarsa pukul {time}', 'Salin kode'],
    it: ['Aggiungi chiave', 'Aggiungi la chiave API al pool di credenziali. Poi verifica l’accesso provando un modello nel pool.', 'Ottieni link di accesso', 'Codice dispositivo', 'Apri pagina di accesso', 'Scade alle {time}', 'Copia codice'],
    ja: ['キーを追加', 'API キーを認証情報プールに追加します。その後、プール内のモデルをテストしてアクセス権を確認してください。', 'ログインリンクを取得', 'デバイスコード', 'ログインページを開く', '有効期限：{time}', 'コードをコピー'],
    ko: ['키 추가', 'API 키를 인증 정보 풀에 추가한 다음 풀에서 모델을 테스트하여 접근 권한을 확인하세요.', '로그인 링크 받기', '기기 코드', '로그인 페이지 열기', '만료 시간: {time}', '코드 복사'],
    pt: ['Adicionar chave', 'Adicione sua chave de API ao pool de credenciais. Depois, teste um modelo no pool para confirmar o acesso.', 'Obter link de login', 'Código do dispositivo', 'Abrir página de login', 'Expira às {time}', 'Copiar código'],
    ru: ['Добавить ключ', 'Добавьте API-ключ в пул учётных данных. Затем проверьте модель в пуле, чтобы подтвердить доступ.', 'Получить ссылку для входа', 'Код устройства', 'Открыть страницу входа', 'Действует до {time}', 'Копировать код'],
    th: ['เพิ่มคีย์', 'เพิ่มคีย์ API ลงในพูลข้อมูลรับรอง จากนั้นทดสอบโมเดลในพูลเพื่อยืนยันสิทธิ์เข้าถึง', 'รับลิงก์เข้าสู่ระบบ', 'รหัสอุปกรณ์', 'เปิดหน้าเข้าสู่ระบบ', 'หมดอายุเวลา {time}', 'คัดลอกรหัส'],
    tr: ['Anahtar ekle', 'API anahtarınızı kimlik bilgisi havuzuna ekleyin. Ardından erişimi doğrulamak için havuzdaki bir modeli test edin.', 'Giriş bağlantısı al', 'Cihaz kodu', 'Giriş sayfasını aç', 'Son geçerlilik saati: {time}', 'Kodu kopyala']
};
const PROVIDER_PORTAL_KEYS = ['help', 'start', 'manual', 'submit', 'remote', 'unsupported', 'link_label', 'copy', 'manual_help'];
const PROVIDER_PORTAL_COPY = {
    en: ["Generate a sign-in link, open it in your browser, and sign in with Google or GitHub. Then return here and click Save credentials.", 'Sign in with Kiro', 'Paste callback URL', 'Complete sign-in', 'Using Polaris on another machine? Copy the full localhost callback URL from the sign-in tab and paste it here.', 'This sign-in method did not return a supported authorization code. Use Google or GitHub, or the AWS sign-in section below.', "Authorization link", "Copy", "After signing in to Kiro, copy the full callback URL from the address bar and paste it here. Leave this blank if Polaris has already received the callback."],
    vi: ["Lấy liên kết đăng nhập, mở liên kết trong trình duyệt rồi đăng nhập bằng Google hoặc GitHub. Sau đó quay lại đây và bấm Lưu thông tin xác thực.", 'Đăng nhập Kiro', 'Dán URL callback', 'Hoàn tất đăng nhập', 'Nếu Polaris chạy trên máy khác, hãy sao chép toàn bộ URL callback localhost từ tab đăng nhập và dán vào đây.', 'Phương thức này không trả về mã cấp quyền được hỗ trợ. Hãy dùng Google hoặc GitHub, hoặc mục đăng nhập AWS bên dưới.', "Liên kết cấp quyền", "Sao chép", "Sau khi đăng nhập Kiro, sao chép toàn bộ URL callback từ thanh địa chỉ và dán vào đây. Có thể để trống nếu Polaris đã nhận callback."],
    'zh-CN': ["生成登录链接，在浏览器中打开，然后通过 Google 或 GitHub 登录。 然后返回此处并点击保存凭据。", '登录 Kiro', '粘贴回调 URL', '完成登录', '如果 Polaris 在另一台机器上运行，请从登录标签页复制完整的 localhost 回调 URL 并粘贴到此处。', '此登录方式未返回受支持的授权码。请使用 Google、GitHub 或下方的 AWS 登录选项。', "授权链接", "复制", "登录 Kiro 后，从地址栏复制完整的回调 URL 并粘贴到此处。如果 Polaris 已收到回调，可以留空。"],
    'zh-TW': ["產生登入連結，在瀏覽器中開啟，再透過 Google 或 GitHub 登入。 接著返回此處並點選儲存憑證。", '登入 Kiro', '貼上回呼 URL', '完成登入', '若 Polaris 在另一台機器上執行，請從登入分頁複製完整的 localhost 回呼 URL 並貼到此處。', '此登入方式未傳回支援的授權碼。請使用 Google、GitHub 或下方的 AWS 登入選項。', "授權連結", "複製", "登入 Kiro 後，從網址列複製完整的回呼 URL 並貼到此處。如果 Polaris 已收到回呼，可以留空。"],
    ja: ["ログインリンクを生成してブラウザーで開き、Google または GitHub でログインします。 その後ここに戻り、認証情報を保存するボタンを押してください。", 'Kiro にログイン', 'コールバック URL を貼り付け', 'ログインを完了', 'Polaris が別のマシンで動作している場合は、ログインタブから localhost のコールバック URL 全体をコピーし、ここに貼り付けてください。', 'このログイン方法では対応する認可コードが返されませんでした。Google、GitHub、または下の AWS ログインを使用してください。', "認可リンク", "コピー", "Kiro にログインした後、アドレスバーからコールバック URL 全体をコピーしてここに貼り付けてください。Polaris がすでにコールバックを受信している場合は空欄のままにできます。"],
    ko: ["로그인 링크를 생성하고 브라우저에서 연 다음 Google 또는 GitHub로 로그인하세요. 그런 다음 여기로 돌아와 자격 증명 저장 버튼을 누르세요.", 'Kiro 로그인', '콜백 URL 붙여넣기', '로그인 완료', 'Polaris가 다른 컴퓨터에서 실행 중이라면 로그인 탭에서 전체 localhost 콜백 URL을 복사해 여기에 붙여넣으세요.', '이 로그인 방식은 지원되는 인증 코드를 반환하지 않았습니다. Google, GitHub 또는 아래 AWS 로그인 항목을 이용하세요.', "인증 링크", "복사", "Kiro에 로그인한 후 주소 표시줄에서 전체 콜백 URL을 복사해 여기에 붙여넣으세요. Polaris가 이미 콜백을 받았다면 비워 두어도 됩니다."],
    de: ["Erzeugen Sie einen Anmeldelink, öffnen Sie ihn im Browser und melden Sie sich mit Google oder GitHub an. Kehren Sie anschließend hierher zurück und klicken Sie auf Zugangsdaten speichern.", 'Bei Kiro anmelden', 'Callback-URL einfügen', 'Anmeldung abschließen', 'Läuft Polaris auf einem anderen Rechner? Kopieren Sie die vollständige localhost-Callback-URL aus dem Anmeldetab und fügen Sie sie hier ein.', 'Diese Anmeldemethode hat keinen unterstützten Autorisierungscode zurückgegeben. Verwenden Sie Google, GitHub oder die AWS-Anmeldung unten.', "Autorisierungslink", "Kopieren", "Kopieren Sie nach der Anmeldung bei Kiro die vollständige Callback-URL aus der Adressleiste und fügen Sie sie hier ein. Lassen Sie das Feld leer, wenn Polaris den Callback bereits erhalten hat."],
    es: ["Genera un enlace de inicio de sesión, ábrelo en el navegador e inicia sesión con Google o GitHub. Después vuelve aquí y pulsa Guardar credenciales.", 'Iniciar sesión en Kiro', 'Pegar URL de retorno', 'Completar inicio de sesión', 'Si Polaris se ejecuta en otro equipo, copia la URL completa de retorno a localhost desde la pestaña de inicio de sesión y pégala aquí.', 'Este método no devolvió un código de autorización compatible. Usa Google, GitHub o la sección de acceso con AWS de abajo.', "Enlace de autorización", "Copiar", "Tras iniciar sesión en Kiro, copia la URL de retorno completa de la barra de direcciones y pégala aquí. Puedes dejar este campo vacío si Polaris ya recibió la respuesta."],
    fr: ["Générez un lien de connexion, ouvrez-le dans votre navigateur, puis connectez-vous avec Google ou GitHub. Revenez ensuite ici et cliquez sur Enregistrer les identifiants.", 'Se connecter à Kiro', 'Coller l’URL de retour', 'Terminer la connexion', 'Si Polaris fonctionne sur une autre machine, copiez l’URL complète de retour vers localhost depuis l’onglet de connexion et collez-la ici.', 'Cette méthode n’a pas renvoyé de code d’autorisation pris en charge. Utilisez Google, GitHub ou la section de connexion AWS ci-dessous.', "Lien d’autorisation", "Copier", "Après la connexion à Kiro, copiez l’URL de retour complète depuis la barre d’adresse et collez-la ici. Vous pouvez laisser ce champ vide si Polaris a déjà reçu le retour."],
    id: ["Buat tautan login, buka di browser, lalu masuk dengan Google atau GitHub. Setelah itu, kembali ke sini dan klik Simpan kredensial.", 'Masuk ke Kiro', 'Tempel URL callback', 'Selesaikan login', 'Jika Polaris berjalan di komputer lain, salin seluruh URL callback localhost dari tab login dan tempel di sini.', 'Metode login ini tidak mengembalikan kode otorisasi yang didukung. Gunakan Google, GitHub, atau bagian login AWS di bawah.', "Tautan otorisasi", "Salin", "Setelah masuk ke Kiro, salin seluruh URL callback dari bilah alamat dan tempel di sini. Biarkan kosong jika Polaris sudah menerima callback."],
    it: ["Genera un link di accesso, aprilo nel browser e accedi con Google o GitHub. Poi torna qui e fai clic su Salva credenziali.", 'Accedi a Kiro', 'Incolla URL di callback', 'Completa l’accesso', 'Se Polaris è in esecuzione su un altro computer, copia l’intero URL di callback localhost dalla scheda di accesso e incollalo qui.', 'Questo metodo non ha restituito un codice di autorizzazione supportato. Usa Google, GitHub o la sezione di accesso AWS qui sotto.', "Link di autorizzazione", "Copia", "Dopo l’accesso a Kiro, copia l’URL di callback completo dalla barra degli indirizzi e incollalo qui. Puoi lasciare il campo vuoto se Polaris ha già ricevuto il callback."],
    pt: ["Gere um link de login, abra-o no navegador e entre com Google ou GitHub. Depois volte aqui e clique em Salvar credenciais.", 'Entrar no Kiro', 'Colar URL de callback', 'Concluir login', 'Se o Polaris estiver em outro computador, copie a URL completa de callback localhost da aba de login e cole aqui.', 'Este método não retornou um código de autorização compatível. Use Google, GitHub ou a seção de login AWS abaixo.', "Link de autorização", "Copiar", "Após entrar no Kiro, copie a URL completa de callback da barra de endereços e cole aqui. Deixe em branco se o Polaris já recebeu o callback."],
    ru: ["Создайте ссылку для входа, откройте её в браузере и войдите через Google или GitHub. Затем вернитесь сюда и нажмите кнопку сохранения учётных данных.", 'Войти в Kiro', 'Вставить URL обратного вызова', 'Завершить вход', 'Если Polaris работает на другом компьютере, скопируйте полный URL обратного вызова localhost из вкладки входа и вставьте его сюда.', 'Этот способ входа не вернул поддерживаемый код авторизации. Используйте Google, GitHub или раздел входа через AWS ниже.', "Ссылка авторизации", "Копировать", "После входа в Kiro скопируйте полный URL обратного вызова из адресной строки и вставьте его сюда. Поле можно оставить пустым, если Polaris уже получил обратный вызов."],
    th: ["สร้างลิงก์เข้าสู่ระบบ เปิดลิงก์ในเบราว์เซอร์ แล้วเข้าสู่ระบบด้วย Google หรือ GitHub จากนั้นกลับมาที่นี่แล้วกดปุ่มบันทึกข้อมูลรับรอง", 'เข้าสู่ระบบ Kiro', 'วาง URL callback', 'เสร็จสิ้นการเข้าสู่ระบบ', 'หาก Polaris ทำงานบนเครื่องอื่น ให้คัดลอก URL callback ของ localhost ทั้งหมดจากแท็บเข้าสู่ระบบแล้ววางที่นี่', 'วิธีเข้าสู่ระบบนี้ไม่ได้ส่งรหัสอนุญาตที่รองรับกลับมา โปรดใช้ Google, GitHub หรือส่วนเข้าสู่ระบบ AWS ด้านล่าง', "ลิงก์อนุญาต", "คัดลอก", "หลังเข้าสู่ระบบ Kiro ให้คัดลอก URL callback ทั้งหมดจากแถบที่อยู่แล้ววางที่นี่ เว้นว่างได้หาก Polaris ได้รับ callback แล้ว"],
    tr: ["Giriş bağlantısı oluşturun, tarayıcınızda açın ve Google veya GitHub ile giriş yapın. Ardından buraya dönün ve kimlik bilgilerini kaydetme düğmesine tıklayın.", 'Kiro’ya giriş yap', 'Geri çağırma URL’sini yapıştır', 'Girişi tamamla', 'Polaris başka bir bilgisayarda çalışıyorsa giriş sekmesindeki localhost geri çağırma URL’sinin tamamını kopyalayıp buraya yapıştırın.', 'Bu giriş yöntemi desteklenen bir yetkilendirme kodu döndürmedi. Google, GitHub veya aşağıdaki AWS giriş bölümünü kullanın.', "Yetkilendirme bağlantısı", "Kopyala", "Kiro’ya giriş yaptıktan sonra adres çubuğundaki geri çağırma URL’sinin tamamını kopyalayıp buraya yapıştırın. Polaris geri çağırmayı zaten aldıysa boş bırakabilirsiniz."]
};
function applyProviderAuthCopy() {
for (const [locale, values] of Object.entries(PROVIDER_AUTH_COPY)) {
    const copy = PAGE_LOCALE_TRANSLATIONS[locale];
    PROVIDER_PORTAL_KEYS.forEach((key, index) => { copy[`provider.portal.${key}`] = PROVIDER_PORTAL_COPY[locale][index]; });
    PROVIDER_UI_KEYS.forEach((key, index) => { copy[`provider.ui.${key}`] = PROVIDER_UI_COPY[locale][index]; });
    copy['runtime.get_provider_auth'] = copy['provider.ui.get_link'];
    PROVIDER_AUTH_KEYS.forEach((key, index) => { copy[`provider.auth.${key}`] = values[index]; });
    copy['provider.ext.kiro_notice'] = values[1];
    copy['provider.ext.import_description'] = values[7];
    copy['provider.ext.add_description'] = values[8];
    for (const provider of ['grok', 'xai', 'gemini', 'codex', 'openai', 'claude', 'anthropic', 'ollama', 'antigravity']) {
        copy[`provider.copy.${provider}_import`] = values[7];
    }
}
}
applyProviderAuthCopy();

// Muse is an OAuth subscription connection, not the Meta Model API key form.
const MUSE_PROVIDER_COPY = {
    en: ['Connect an eligible Muse Code subscription using OAuth.', 'Get a sign-in link, confirm the device code on Meta’s page, then return and save the credential. No callback URL is needed.', 'Muse Code is separate from Meta Model API. Its model IDs start with muse-code/. Direct protocol compatibility may change with Muse Code.', 'Muse Code sign-in could not be completed. Check your subscription and connection, then retry or start a new sign-in.'],
    vi: ['Kết nối gói Muse Code đủ điều kiện bằng OAuth.', 'Lấy liên kết đăng nhập, xác nhận mã thiết bị trên trang Meta, rồi quay lại lưu thông tin xác thực. Không cần dán URL callback.', 'Muse Code tách biệt với Meta Model API. Mã mô hình bắt đầu bằng muse-code/. Khả năng tương thích giao thức trực tiếp có thể thay đổi theo Muse Code.', 'Chưa hoàn tất đăng nhập Muse Code. Kiểm tra gói dịch vụ và kết nối, rồi thử lại hoặc bắt đầu phiên đăng nhập mới.'],
    'zh-CN': ['通过 OAuth 连接符合条件的 Muse Code 订阅。', '获取登录链接，在 Meta 页面确认设备代码，然后返回并保存凭据。无需回调 URL。', 'Muse Code 与 Meta Model API 相互独立。模型 ID 以 muse-code/ 开头。直接协议兼容性可能随 Muse Code 发生变化。', '未能完成 Muse Code 登录。请检查订阅和网络连接，然后重试或重新开始登录。'],
    'zh-TW': ['透過 OAuth 連接符合資格的 Muse Code 訂閱。', '取得登入連結，在 Meta 頁面確認裝置代碼，然後返回並儲存憑證。不需要回呼 URL。', 'Muse Code 與 Meta Model API 相互獨立。模型 ID 以 muse-code/ 開頭。直接協定相容性可能隨 Muse Code 變更。', '無法完成 Muse Code 登入。請檢查訂閱和網路連線，然後重試或重新開始登入。'],
    de: ['Verbinden Sie ein berechtigtes Muse-Code-Abonnement über OAuth.', 'Erstellen Sie einen Anmeldelink, bestätigen Sie den Gerätecode auf der Meta-Seite und kehren Sie zurück, um die Zugangsdaten zu speichern. Eine Callback-URL ist nicht erforderlich.', 'Muse Code ist von der Meta Model API getrennt. Modell-IDs beginnen mit muse-code/. Die direkte Protokollkompatibilität kann sich mit Muse Code ändern.', 'Die Anmeldung bei Muse Code konnte nicht abgeschlossen werden. Prüfen Sie Abonnement und Verbindung und versuchen Sie es erneut oder starten Sie eine neue Anmeldung.'],
    es: ['Conecta una suscripción válida de Muse Code mediante OAuth.', 'Obtén un enlace de inicio de sesión, confirma el código de dispositivo en la página de Meta y vuelve para guardar la credencial. No se necesita una URL de retorno.', 'Muse Code es independiente de Meta Model API. Sus identificadores de modelo empiezan por muse-code/. La compatibilidad directa del protocolo puede cambiar con Muse Code.', 'No se pudo completar el inicio de sesión en Muse Code. Comprueba la suscripción y la conexión y vuelve a intentarlo o inicia una nueva sesión.'],
    fr: ['Connectez un abonnement Muse Code éligible via OAuth.', 'Obtenez un lien de connexion, confirmez le code de l’appareil sur la page Meta, puis revenez enregistrer les identifiants. Aucune URL de rappel n’est nécessaire.', 'Muse Code est distinct de Meta Model API. Ses identifiants de modèle commencent par muse-code/. La compatibilité directe du protocole peut évoluer avec Muse Code.', 'La connexion à Muse Code n’a pas abouti. Vérifiez votre abonnement et votre connexion réseau, puis réessayez ou relancez la connexion.'],
    id: ['Hubungkan langganan Muse Code yang memenuhi syarat melalui OAuth.', 'Dapatkan tautan masuk, konfirmasikan kode perangkat di halaman Meta, lalu kembali untuk menyimpan kredensial. URL callback tidak diperlukan.', 'Muse Code terpisah dari Meta Model API. ID modelnya diawali muse-code/. Kompatibilitas protokol langsung dapat berubah seiring perubahan Muse Code.', 'Login Muse Code belum selesai. Periksa langganan dan koneksi Anda, lalu coba lagi atau mulai login baru.'],
    it: ['Collega un abbonamento Muse Code idoneo tramite OAuth.', 'Ottieni un link di accesso, conferma il codice dispositivo sulla pagina Meta, quindi torna per salvare le credenziali. Non serve un URL di callback.', 'Muse Code è separato da Meta Model API. Gli ID dei modelli iniziano con muse-code/. La compatibilità diretta del protocollo può cambiare con Muse Code.', 'Impossibile completare l’accesso a Muse Code. Controlla l’abbonamento e la connessione, quindi riprova o avvia un nuovo accesso.'],
    ja: ['対象の Muse Code サブスクリプションを OAuth で接続します。', 'ログインリンクを取得し、Meta のページでデバイスコードを確認してから、ここに戻って認証情報を保存してください。コールバック URL は不要です。', 'Muse Code は Meta Model API とは別の接続です。モデル ID は muse-code/ で始まります。直接接続のプロトコル互換性は Muse Code の変更に伴って変わる場合があります。', 'Muse Code へのログインを完了できませんでした。サブスクリプションと接続を確認し、再試行するか新しいログインを開始してください。'],
    ko: ['사용 가능한 Muse Code 구독을 OAuth로 연결합니다.', '로그인 링크를 생성하고 Meta 페이지에서 기기 코드를 확인한 다음 돌아와 자격 증명을 저장하세요. 콜백 URL은 필요하지 않습니다.', 'Muse Code는 Meta Model API와 별개입니다. 모델 ID는 muse-code/로 시작합니다. 직접 연결의 프로토콜 호환성은 Muse Code 변경에 따라 달라질 수 있습니다.', 'Muse Code 로그인을 완료하지 못했습니다. 구독과 연결을 확인한 후 다시 시도하거나 새 로그인을 시작하세요.'],
    pt: ['Conecte uma assinatura elegível do Muse Code via OAuth.', 'Obtenha um link de login, confirme o código do dispositivo na página da Meta e volte para salvar a credencial. Não é necessária uma URL de retorno.', 'Muse Code é separado da Meta Model API. Seus IDs de modelo começam com muse-code/. A compatibilidade direta do protocolo pode mudar com o Muse Code.', 'Não foi possível concluir o login no Muse Code. Verifique sua assinatura e conexão e tente novamente ou inicie um novo login.'],
    ru: ['Подключите подходящую подписку Muse Code через OAuth.', 'Получите ссылку для входа, подтвердите код устройства на странице Meta, затем вернитесь и сохраните учётные данные. URL обратного вызова не нужен.', 'Muse Code не связан с ключами Meta Model API. Идентификаторы его моделей начинаются с muse-code/. Совместимость прямого протокола может меняться вместе с Muse Code.', 'Не удалось завершить вход в Muse Code. Проверьте подписку и подключение, затем повторите попытку или начните вход заново.'],
    th: ['เชื่อมต่อการสมัครใช้บริการ Muse Code ที่มีสิทธิ์ผ่าน OAuth', 'รับลิงก์เข้าสู่ระบบ ยืนยันรหัสอุปกรณ์บนหน้า Meta แล้วกลับมาบันทึกข้อมูลรับรอง โดยไม่ต้องใช้ URL callback', 'Muse Code แยกจาก Meta Model API โดยรหัสโมเดลขึ้นต้นด้วย muse-code/ ความเข้ากันได้ของโปรโตคอลโดยตรงอาจเปลี่ยนแปลงตาม Muse Code', 'เข้าสู่ระบบ Muse Code ไม่สำเร็จ โปรดตรวจสอบการสมัครใช้บริการและการเชื่อมต่อ แล้วลองอีกครั้งหรือเริ่มเข้าสู่ระบบใหม่'],
    tr: ['Uygun bir Muse Code aboneliğini OAuth ile bağlayın.', 'Giriş bağlantısı alın, Meta sayfasında cihaz kodunu doğrulayın ve kimlik bilgilerini kaydetmek için buraya dönün. Geri çağırma URL’si gerekmez.', 'Muse Code, Meta Model API’den ayrıdır. Model kimlikleri muse-code/ ile başlar. Doğrudan protokol uyumluluğu Muse Code ile birlikte değişebilir.', 'Muse Code girişi tamamlanamadı. Aboneliğinizi ve bağlantınızı kontrol edip tekrar deneyin veya yeni bir giriş başlatın.']
};
for (const [locale, values] of Object.entries(MUSE_PROVIDER_COPY)) {
    ['provider.ext.muse_code', 'provider.muse.help', 'provider.muse.notice', 'provider.muse.error'].forEach((key, index) => {
        PAGE_LOCALE_TRANSLATIONS[locale][key] = values[index];
    });
}

const MUSE_SETTINGS_HELP = {
    en: 'Optional name for the saved account. Applied when you request a new login link.',
    vi: 'Tên tùy chọn cho tài khoản được lưu. Áp dụng khi bạn lấy liên kết đăng nhập mới.',
    'zh-CN': '为保存的账户设置可选名称。获取新的登录链接时生效。',
    'zh-TW': '為儲存的帳戶設定選用名稱。取得新的登入連結時生效。',
    de: 'Optionaler Name für das gespeicherte Konto. Wird beim Anfordern eines neuen Anmeldelinks übernommen.',
    es: 'Nombre opcional para la cuenta guardada. Se aplica al solicitar un nuevo enlace de inicio de sesión.',
    fr: 'Nom facultatif du compte enregistré. Appliqué lorsque vous demandez un nouveau lien de connexion.',
    id: 'Nama opsional untuk akun yang disimpan. Diterapkan saat Anda meminta tautan masuk baru.',
    it: 'Nome facoltativo per l’account salvato. Si applica quando richiedi un nuovo link di accesso.',
    ja: '保存するアカウントの名前（任意）。新しいログインリンクを取得すると適用されます。',
    ko: '저장할 계정의 이름입니다(선택 사항). 새 로그인 링크를 요청할 때 적용됩니다.',
    pt: 'Nome opcional para a conta salva. Aplicado ao solicitar um novo link de login.',
    ru: 'Необязательное имя сохраняемого аккаунта. Применяется при запросе новой ссылки для входа.',
    th: 'ชื่อที่ไม่บังคับสำหรับบัญชีที่บันทึก จะใช้เมื่อคุณขอลิงก์เข้าสู่ระบบใหม่',
    tr: 'Kaydedilen hesap için isteğe bağlı ad. Yeni bir giriş bağlantısı istediğinizde uygulanır.'
};
for (const [locale, copy] of Object.entries(MUSE_SETTINGS_HELP)) {
    PAGE_LOCALE_TRANSLATIONS[locale]['provider.muse.settings_help'] = copy;
}

// Product descriptions explain purpose; authentication methods belong in badges and forms.
// Source notes and editorial scope: docs/providers/provider-descriptions-2026-09-16.md.
const PROVIDER_DESCRIPTION_KEYS = [
    "providers.antigravity_description",
    "providers.ai_studio_description",
    "providers.grok_description",
    "providers.spacexai_description",
    "providers.codex_description",
    "providers.openai_description",
    "providers.claude_code_description",
    "providers.claude_platform_description",
    "providers.ollama_description",
    "provider.ext.kimi",
    "provider.ext.kiro",
    "provider.ext.cloudflare",
    "provider.ext.nvidia",
    "provider.ext.opencode",
    "provider.ext.poolside",
    "provider.ext.kimchi",
    "provider.ext.kilo",
    "provider.ext.meta",
    "provider.ext.muse_code",
    "provider.ext.groq",
    "provider.ext.deepseek",
    "provider.ext.mistral",
    "provider.ext.cerebras"
];
const PROVIDER_PRODUCT_COPY = {
    "en": [
        "Google’s AI development environment, bringing agents into the editor and terminal to help build and test software.",
        "Google’s workspace for experimenting with Gemini models, refining prompts and prototyping AI applications.",
        "SpaceXAI’s coding agent, using Grok to explore codebases, edit files and automate development tasks in the terminal.",
        "SpaceXAI’s developer platform for building applications with Grok models for conversation, reasoning and coding.",
        "OpenAI’s coding agent for understanding repositories, implementing changes and reviewing code across development workflows.",
        "OpenAI’s developer platform for building applications and agents with GPT and reasoning models.",
        "Anthropic’s coding assistant for exploring projects, editing files, fixing bugs and running development commands.",
        "Anthropic’s developer platform for using Claude in applications that need language understanding, reasoning and code generation.",
        "A tool for running open models locally or in the cloud, with a model library for chat and coding.",
        "Moonshot AI’s model platform, offering Kimi models for reasoning, programming and working with long context.",
        "An AI development environment built around specifications, turning requirements into designs, implementation tasks and code.",
        "Cloudflare’s serverless model service, running AI inference on managed infrastructure without requiring you to operate GPUs.",
        "NVIDIA’s optimized model inference services, designed to help developers deploy and run AI on GPU infrastructure.",
        "An open-source coding agent with Zen and Go model services for use in AI-assisted development workflows.",
        "An AI platform for software engineering, bringing models and agents into enterprise development workflows.",
        "A multi-model coding platform backed by Kimchi Inference, combining coding agents with hosted open models.",
        "An open-source coding platform with a unified model gateway for agents in the editor, terminal and cloud.",
        "Meta’s developer platform for building applications with Muse models, including conversational, reasoning and coding workloads.",
        "Meta’s terminal-based coding assistant, using Muse models to explore projects and carry out software development tasks.",
        "Groq’s cloud inference platform, using specialized hardware to serve language models with a focus on low latency.",
        "DeepSeek’s model platform for conversational applications, reasoning tasks, code generation and text analysis.",
        "Mistral AI’s development workspace for experimenting with models and building applications for language, reasoning and coding.",
        "Cerebras’s cloud inference service, using wafer-scale hardware to deliver language model responses at high speed."
    ],
    "vi": [
        "Môi trường lập trình AI của Google, kết hợp tác tử với trình soạn thảo và terminal để xây dựng và kiểm thử phần mềm.",
        "Không gian làm việc của Google để thử nghiệm mô hình Gemini, tinh chỉnh câu lệnh và tạo nguyên mẫu ứng dụng AI.",
        "Tác tử lập trình của SpaceXAI, sử dụng Grok để tìm hiểu mã nguồn, chỉnh sửa tệp và tự động hóa tác vụ trong terminal.",
        "Nền tảng dành cho nhà phát triển của SpaceXAI, cung cấp mô hình Grok cho ứng dụng hội thoại, suy luận và lập trình.",
        "Tác tử lập trình của OpenAI, hỗ trợ tìm hiểu kho mã, triển khai thay đổi và rà soát mã trong quy trình phát triển.",
        "Nền tảng dành cho nhà phát triển của OpenAI, cung cấp mô hình GPT và mô hình suy luận để xây dựng ứng dụng và tác tử.",
        "Trợ lý lập trình của Anthropic, hỗ trợ tìm hiểu dự án, chỉnh sửa tệp, sửa lỗi và chạy lệnh phục vụ phát triển phần mềm.",
        "Nền tảng dành cho nhà phát triển của Anthropic, đưa Claude vào ứng dụng cần hiểu ngôn ngữ, suy luận và tạo mã.",
        "Công cụ chạy mô hình mở trên máy cục bộ hoặc đám mây, với thư viện mô hình phục vụ hội thoại và lập trình.",
        "Nền tảng mô hình của Moonshot AI, cung cấp các mô hình Kimi cho suy luận, lập trình và xử lý ngữ cảnh dài.",
        "Môi trường lập trình AI theo đặc tả, giúp chuyển yêu cầu thành thiết kế, các tác vụ triển khai và mã nguồn.",
        "Dịch vụ mô hình serverless của Cloudflare, chạy suy luận AI trên hạ tầng được quản lý mà không cần tự vận hành GPU.",
        "Dịch vụ suy luận mô hình được NVIDIA tối ưu, giúp nhà phát triển triển khai và vận hành AI trên hạ tầng GPU.",
        "Tác tử lập trình mã nguồn mở, đi kèm dịch vụ mô hình Zen và Go dành cho quy trình phát triển có AI hỗ trợ.",
        "Nền tảng AI cho kỹ thuật phần mềm, đưa mô hình và tác tử vào quy trình phát triển của doanh nghiệp.",
        "Nền tảng lập trình đa mô hình dựa trên Kimchi Inference, kết hợp tác tử lập trình với các mô hình mở được lưu trữ sẵn.",
        "Nền tảng lập trình mã nguồn mở với cổng mô hình thống nhất cho tác tử trong trình soạn thảo, terminal và đám mây.",
        "Nền tảng dành cho nhà phát triển của Meta, cung cấp mô hình Muse để xây dựng ứng dụng hội thoại, suy luận và lập trình.",
        "Trợ lý lập trình trong terminal của Meta, sử dụng mô hình Muse để tìm hiểu dự án và thực hiện các tác vụ phát triển phần mềm.",
        "Nền tảng suy luận đám mây của Groq, sử dụng phần cứng chuyên dụng để phục vụ mô hình ngôn ngữ với độ trễ thấp.",
        "Nền tảng mô hình của DeepSeek, phục vụ ứng dụng hội thoại, tác vụ suy luận, tạo mã và phân tích văn bản.",
        "Không gian phát triển của Mistral AI để thử nghiệm mô hình và xây dựng ứng dụng xử lý ngôn ngữ, suy luận và lập trình.",
        "Dịch vụ suy luận đám mây của Cerebras, sử dụng phần cứng quy mô wafer để cung cấp phản hồi từ mô hình ngôn ngữ ở tốc độ cao."
    ],
    "de": [
        "Googles KI-Entwicklungsumgebung verbindet Agenten mit Editor und Terminal, um Software zu entwickeln und zu testen.",
        "Googles Arbeitsumgebung zum Erproben von Gemini-Modellen, Verfeinern von Prompts und Erstellen von KI-Prototypen.",
        "Der Coding-Agent von SpaceXAI nutzt Grok, um Codebasen zu erkunden, Dateien zu bearbeiten und Entwicklungsaufgaben im Terminal zu automatisieren.",
        "Die Entwicklerplattform von SpaceXAI bietet Grok-Modelle für Anwendungen mit Dialogen, Schlussfolgerungen und Programmierung.",
        "Der Coding-Agent von OpenAI hilft dabei, Repositories zu verstehen, Änderungen umzusetzen und Code in Entwicklungsabläufen zu prüfen.",
        "OpenAIs Entwicklerplattform stellt GPT- und Reasoning-Modelle zum Erstellen von Anwendungen und Agenten bereit.",
        "Anthropics Programmierassistent erkundet Projekte, bearbeitet Dateien, behebt Fehler und führt Entwicklungsbefehle aus.",
        "Anthropics Entwicklerplattform integriert Claude in Anwendungen für Sprachverständnis, Schlussfolgerungen und Codegenerierung.",
        "Ein Werkzeug zum lokalen oder cloudbasierten Ausführen offener Modelle, mit einer Modellbibliothek für Dialoge und Programmierung.",
        "Die Modellplattform von Moonshot AI bietet Kimi-Modelle für Schlussfolgerungen, Programmierung und die Verarbeitung langer Kontexte.",
        "Eine spezifikationsbasierte KI-Entwicklungsumgebung, die Anforderungen in Entwürfe, Implementierungsaufgaben und Code überführt.",
        "Cloudflares serverloser Modelldienst führt KI-Inferenz auf verwalteter Infrastruktur aus, ohne dass eigene GPUs betrieben werden müssen.",
        "NVIDIAs optimierte Inferenzdienste unterstützen Entwickler beim Bereitstellen und Ausführen von KI auf GPU-Infrastruktur.",
        "Ein quelloffener Coding-Agent mit den Modelldiensten Zen und Go für KI-gestützte Entwicklungsabläufe.",
        "Eine KI-Plattform für Softwareentwicklung, die Modelle und Agenten in die Entwicklungsabläufe von Unternehmen integriert.",
        "Eine Multi-Modell-Plattform auf Basis von Kimchi Inference, die Coding-Agenten mit gehosteten offenen Modellen verbindet.",
        "Eine quelloffene Coding-Plattform mit einem zentralen Modell-Gateway für Agenten im Editor, Terminal und in der Cloud.",
        "Metas Entwicklerplattform bietet Muse-Modelle für Anwendungen mit Dialogen, Schlussfolgerungen und Programmierung.",
        "Metas terminalbasierter Programmierassistent nutzt Muse-Modelle, um Projekte zu erkunden und Softwareentwicklungsaufgaben auszuführen.",
        "Groqs Cloud-Inferenzplattform nutzt spezialisierte Hardware, um Sprachmodelle mit niedriger Latenz bereitzustellen.",
        "DeepSeeks Modellplattform unterstützt Dialoganwendungen, Schlussfolgerungen, Codegenerierung und Textanalyse.",
        "Mistral AIs Entwicklungsumgebung zum Erproben von Modellen und Erstellen von Anwendungen für Sprache, Schlussfolgerungen und Programmierung.",
        "Cerebras bietet Cloud-Inferenz auf Wafer-Scale-Hardware, um Antworten von Sprachmodellen mit hoher Geschwindigkeit bereitzustellen."
    ],
    "es": [
        "El entorno de desarrollo con IA de Google combina agentes con el editor y la terminal para crear y probar software.",
        "El espacio de trabajo de Google para probar modelos Gemini, ajustar instrucciones y crear prototipos de aplicaciones de IA.",
        "El agente de programación de SpaceXAI usa Grok para explorar código, editar archivos y automatizar tareas de desarrollo en la terminal.",
        "La plataforma para desarrolladores de SpaceXAI ofrece modelos Grok para aplicaciones de conversación, razonamiento y programación.",
        "El agente de programación de OpenAI ayuda a comprender repositorios, implementar cambios y revisar código durante el desarrollo.",
        "La plataforma para desarrolladores de OpenAI ofrece modelos GPT y de razonamiento para crear aplicaciones y agentes.",
        "El asistente de programación de Anthropic permite explorar proyectos, editar archivos, corregir errores y ejecutar comandos de desarrollo.",
        "La plataforma para desarrolladores de Anthropic integra Claude en aplicaciones de comprensión del lenguaje, razonamiento y generación de código.",
        "Una herramienta para ejecutar modelos abiertos localmente o en la nube, con una biblioteca de modelos para conversación y programación.",
        "La plataforma de Moonshot AI ofrece modelos Kimi para razonamiento, programación y procesamiento de contextos largos.",
        "Un entorno de desarrollo con IA basado en especificaciones que convierte requisitos en diseños, tareas de implementación y código.",
        "El servicio de modelos sin servidor de Cloudflare ejecuta inferencia de IA en infraestructura gestionada, sin tener que administrar GPU.",
        "Los servicios de inferencia optimizados de NVIDIA ayudan a desplegar y ejecutar modelos de IA en infraestructura GPU.",
        "Un agente de programación de código abierto con los servicios de modelos Zen y Go para el desarrollo asistido por IA.",
        "Una plataforma de IA para ingeniería de software que integra modelos y agentes en los flujos de desarrollo de las empresas.",
        "Una plataforma de programación multimodelo basada en Kimchi Inference que combina agentes con modelos abiertos alojados.",
        "Una plataforma de programación de código abierto con una pasarela unificada de modelos para agentes en el editor, la terminal y la nube.",
        "La plataforma para desarrolladores de Meta ofrece modelos Muse para aplicaciones de conversación, razonamiento y programación.",
        "El asistente de programación de Meta para la terminal usa modelos Muse para explorar proyectos y realizar tareas de desarrollo de software.",
        "La plataforma de inferencia en la nube de Groq utiliza hardware especializado para ofrecer modelos de lenguaje con baja latencia.",
        "La plataforma de modelos de DeepSeek ofrece conversación, razonamiento, generación de código y análisis de texto para aplicaciones.",
        "El espacio de desarrollo de Mistral AI permite probar modelos y crear aplicaciones de lenguaje, razonamiento y programación.",
        "El servicio de inferencia en la nube de Cerebras utiliza hardware a escala de oblea para generar respuestas de modelos de lenguaje a gran velocidad."
    ],
    "fr": [
        "L’environnement de développement IA de Google associe des agents à l’éditeur et au terminal pour créer et tester des logiciels.",
        "L’espace de travail de Google pour tester les modèles Gemini, affiner les instructions et prototyper des applications d’IA.",
        "L’agent de programmation de SpaceXAI utilise Grok pour explorer le code, modifier des fichiers et automatiser des tâches dans le terminal.",
        "La plateforme de développement de SpaceXAI propose les modèles Grok pour les applications de conversation, de raisonnement et de programmation.",
        "L’agent de programmation d’OpenAI aide à comprendre les dépôts, à implémenter des modifications et à examiner le code.",
        "La plateforme de développement d’OpenAI propose des modèles GPT et de raisonnement pour créer des applications et des agents.",
        "L’assistant de programmation d’Anthropic explore les projets, modifie les fichiers, corrige les bugs et exécute des commandes de développement.",
        "La plateforme de développement d’Anthropic intègre Claude aux applications de compréhension du langage, de raisonnement et de génération de code.",
        "Un outil pour exécuter des modèles ouverts localement ou dans le cloud, avec une bibliothèque dédiée au dialogue et à la programmation.",
        "La plateforme de Moonshot AI propose les modèles Kimi pour le raisonnement, la programmation et le traitement de contextes longs.",
        "Un environnement de développement IA fondé sur les spécifications, qui transforme les exigences en conceptions, tâches et code.",
        "Le service de modèles sans serveur de Cloudflare exécute l’inférence IA sur une infrastructure gérée, sans avoir à administrer de GPU.",
        "Les services d’inférence optimisés de NVIDIA aident à déployer et à exécuter des modèles d’IA sur une infrastructure GPU.",
        "Un agent de programmation open source accompagné des services de modèles Zen et Go pour le développement assisté par IA.",
        "Une plateforme d’IA pour le génie logiciel qui intègre modèles et agents aux processus de développement des entreprises.",
        "Une plateforme de programmation multimodèle reposant sur Kimchi Inference, qui associe des agents à des modèles ouverts hébergés.",
        "Une plateforme de programmation open source avec une passerelle de modèles unifiée pour les agents dans l’éditeur, le terminal et le cloud.",
        "La plateforme de développement de Meta propose les modèles Muse pour les applications de conversation, de raisonnement et de programmation.",
        "L’assistant de programmation de Meta dans le terminal utilise les modèles Muse pour explorer les projets et réaliser des tâches de développement.",
        "La plateforme d’inférence cloud de Groq utilise du matériel spécialisé pour servir des modèles de langage avec une faible latence.",
        "La plateforme de modèles de DeepSeek prend en charge les applications de conversation, de raisonnement, de génération de code et d’analyse de texte.",
        "L’espace de développement de Mistral AI permet de tester des modèles et de créer des applications de langage, de raisonnement et de programmation.",
        "Le service d’inférence cloud de Cerebras utilise du matériel à l’échelle d’une tranche de silicium pour produire rapidement les réponses des modèles de langage."
    ],
    "it": [
        "L’ambiente di sviluppo IA di Google integra agenti nell’editor e nel terminale per creare e testare software.",
        "Lo spazio di lavoro di Google per provare i modelli Gemini, affinare i prompt e creare prototipi di applicazioni IA.",
        "L’agente di programmazione di SpaceXAI usa Grok per esplorare il codice, modificare file e automatizzare attività nel terminale.",
        "La piattaforma per sviluppatori di SpaceXAI offre modelli Grok per applicazioni di conversazione, ragionamento e programmazione.",
        "L’agente di programmazione di OpenAI aiuta a comprendere i repository, implementare modifiche e revisionare il codice.",
        "La piattaforma per sviluppatori di OpenAI offre modelli GPT e di ragionamento per creare applicazioni e agenti.",
        "L’assistente di programmazione di Anthropic esplora progetti, modifica file, corregge errori ed esegue comandi di sviluppo.",
        "La piattaforma per sviluppatori di Anthropic integra Claude in applicazioni di comprensione del linguaggio, ragionamento e generazione di codice.",
        "Uno strumento per eseguire modelli aperti in locale o nel cloud, con una libreria dedicata alla conversazione e alla programmazione.",
        "La piattaforma di Moonshot AI offre modelli Kimi per ragionamento, programmazione ed elaborazione di contesti lunghi.",
        "Un ambiente di sviluppo IA basato su specifiche che trasforma i requisiti in progetti, attività di implementazione e codice.",
        "Il servizio di modelli serverless di Cloudflare esegue inferenza IA su infrastruttura gestita, senza dover amministrare GPU.",
        "I servizi di inferenza ottimizzati di NVIDIA aiutano a distribuire ed eseguire modelli IA su infrastruttura GPU.",
        "Un agente di programmazione open source con i servizi di modelli Zen e Go per lo sviluppo assistito dall’IA.",
        "Una piattaforma IA per l’ingegneria del software che integra modelli e agenti nei processi di sviluppo aziendali.",
        "Una piattaforma di programmazione multimodello basata su Kimchi Inference, che combina agenti e modelli aperti ospitati.",
        "Una piattaforma di programmazione open source con un gateway unificato di modelli per agenti nell’editor, nel terminale e nel cloud.",
        "La piattaforma per sviluppatori di Meta offre modelli Muse per applicazioni di conversazione, ragionamento e programmazione.",
        "L’assistente di programmazione di Meta nel terminale usa i modelli Muse per esplorare progetti e svolgere attività di sviluppo software.",
        "La piattaforma di inferenza cloud di Groq usa hardware specializzato per fornire modelli linguistici a bassa latenza.",
        "La piattaforma di modelli di DeepSeek supporta applicazioni di conversazione, ragionamento, generazione di codice e analisi del testo.",
        "Lo spazio di sviluppo di Mistral AI permette di provare modelli e creare applicazioni per linguaggio, ragionamento e programmazione.",
        "Il servizio di inferenza cloud di Cerebras usa hardware su scala wafer per produrre risposte dei modelli linguistici ad alta velocità."
    ],
    "zh-CN": [
        "Google 的 AI 开发环境，将智能体融入编辑器和终端，帮助开发者构建与测试软件。",
        "Google 的模型实验工作区，用于试用 Gemini、优化提示词并构建 AI 应用原型。",
        "SpaceXAI 的编程智能体，通过 Grok 探索代码库、编辑文件，并在终端中自动执行开发任务。",
        "SpaceXAI 的开发者平台，提供 Grok 模型，用于构建对话、推理和编程应用。",
        "OpenAI 的编程智能体，可理解代码仓库、实现修改并在开发流程中审查代码。",
        "OpenAI 的开发者平台，提供 GPT 和推理模型，用于构建应用与智能体。",
        "Anthropic 的编程助手，可探索项目、编辑文件、修复错误并运行开发命令。",
        "Anthropic 的开发者平台，让应用使用 Claude 进行语言理解、推理和代码生成。",
        "在本地或云端运行开放模型的工具，提供用于对话和编程的模型库。",
        "Moonshot AI 的模型平台，提供适用于推理、编程和长上下文处理的 Kimi 模型。",
        "以规格说明为核心的 AI 开发环境，将需求转化为设计、实施任务和代码。",
        "Cloudflare 的无服务器模型服务，在托管基础设施上运行 AI 推理，无需自行管理 GPU。",
        "NVIDIA 优化的模型推理服务，帮助开发者在 GPU 基础设施上部署和运行 AI。",
        "开源编程智能体，配套提供 Zen 和 Go 模型服务，支持 AI 辅助开发流程。",
        "面向软件工程的 AI 平台，将模型与智能体融入企业开发流程。",
        "基于 Kimchi Inference 的多模型编程平台，将编程智能体与托管的开放模型相结合。",
        "开源编程平台，为编辑器、终端和云端的智能体提供统一的模型网关。",
        "Meta 的开发者平台，提供 Muse 模型，用于构建对话、推理和编程应用。",
        "Meta 的终端编程助手，使用 Muse 模型探索项目并执行软件开发任务。",
        "Groq 的云端推理平台，使用专用硬件提供低延迟的语言模型服务。",
        "DeepSeek 的模型平台，支持对话应用、推理任务、代码生成和文本分析。",
        "Mistral AI 的开发工作区，用于试用模型并构建语言处理、推理和编程应用。",
        "Cerebras 的云端推理服务，使用晶圆级硬件高速生成语言模型响应。"
    ],
    "zh-TW": [
        "Google 的 AI 開發環境，將代理融入編輯器與終端機，協助開發者建置及測試軟體。",
        "Google 的模型實驗工作區，用於試用 Gemini、調整提示詞並建立 AI 應用程式原型。",
        "SpaceXAI 的程式開發代理，透過 Grok 探索程式碼、編輯檔案，並在終端機自動執行開發任務。",
        "SpaceXAI 的開發者平台，提供 Grok 模型，用於建置對話、推理和程式開發應用。",
        "OpenAI 的程式開發代理，可理解程式碼儲存庫、實作變更並在開發流程中審查程式碼。",
        "OpenAI 的開發者平台，提供 GPT 與推理模型，用於建置應用程式和代理。",
        "Anthropic 的程式開發助手，可探索專案、編輯檔案、修復錯誤並執行開發指令。",
        "Anthropic 的開發者平台，讓應用程式使用 Claude 進行語言理解、推理和程式碼生成。",
        "在本機或雲端執行開放模型的工具，提供用於對話及程式開發的模型庫。",
        "Moonshot AI 的模型平台，提供適用於推理、程式開發及長上下文處理的 Kimi 模型。",
        "以規格為核心的 AI 開發環境，將需求轉化為設計、實作任務和程式碼。",
        "Cloudflare 的無伺服器模型服務，在代管基礎設施上執行 AI 推理，無需自行管理 GPU。",
        "NVIDIA 最佳化的模型推理服務，協助開發者在 GPU 基礎設施上部署和執行 AI。",
        "開源程式開發代理，搭配 Zen 與 Go 模型服務，支援 AI 輔助開發流程。",
        "面向軟體工程的 AI 平台，將模型與代理融入企業開發流程。",
        "以 Kimchi Inference 為基礎的多模型程式開發平台，結合程式開發代理與代管的開放模型。",
        "開源程式開發平台，為編輯器、終端機及雲端的代理提供統一模型閘道。",
        "Meta 的開發者平台，提供 Muse 模型，用於建置對話、推理和程式開發應用。",
        "Meta 的終端機程式開發助手，使用 Muse 模型探索專案並執行軟體開發任務。",
        "Groq 的雲端推理平台，使用專用硬體提供低延遲的語言模型服務。",
        "DeepSeek 的模型平台，支援對話應用、推理任務、程式碼生成和文字分析。",
        "Mistral AI 的開發工作區，用於試用模型並建置語言處理、推理和程式開發應用。",
        "Cerebras 的雲端推理服務，使用晶圓級硬體高速產生語言模型回應。"
    ],
    "ja": [
        "Google の AI 開発環境。エディターやターミナルにエージェントを組み込み、ソフトウェアの開発とテストを支援します。",
        "Gemini モデルの試用、プロンプトの調整、AI アプリのプロトタイプ作成に使える Google のワークスペースです。",
        "Grok を使ってコードベースを探索し、ファイル編集やターミナルでの開発作業を自動化する SpaceXAI のコーディングエージェントです。",
        "対話、推論、プログラミング向けの Grok モデルを提供する SpaceXAI の開発者プラットフォームです。",
        "リポジトリの理解、変更の実装、コードレビューを開発ワークフロー全体で支援する OpenAI のコーディングエージェントです。",
        "GPT モデルと推論モデルを使ったアプリやエージェントの構築を支える OpenAI の開発者プラットフォームです。",
        "プロジェクトの探索、ファイル編集、バグ修正、開発コマンドの実行を行う Anthropic のコーディングアシスタントです。",
        "言語理解、推論、コード生成を必要とするアプリに Claude を組み込むための Anthropic の開発者プラットフォームです。",
        "オープンモデルをローカルやクラウドで実行するツール。対話やプログラミング向けのモデルライブラリを備えています。",
        "推論、プログラミング、長いコンテキストの処理に使える Kimi モデルを提供する Moonshot AI のプラットフォームです。",
        "仕様に基づく AI 開発環境。要件を設計、実装タスク、コードへと具体化します。",
        "GPU を自分で管理せずに、マネージド基盤上で AI 推論を実行できる Cloudflare のサーバーレスモデルサービスです。",
        "GPU 基盤上での AI のデプロイと実行を支援する、NVIDIA の最適化されたモデル推論サービスです。",
        "AI を活用した開発向けに Zen と Go のモデルサービスを備えた、オープンソースのコーディングエージェントです。",
        "モデルとエージェントを企業の開発ワークフローに組み込む、ソフトウェアエンジニアリング向けの AI プラットフォームです。",
        "Kimchi Inference を基盤とし、コーディングエージェントとホスト型オープンモデルを組み合わせたマルチモデル開発プラットフォームです。",
        "エディター、ターミナル、クラウドのエージェントに統一モデルゲートウェイを提供する、オープンソースの開発プラットフォームです。",
        "対話、推論、プログラミング向けアプリの構築に使える Muse モデルを提供する Meta の開発者プラットフォームです。",
        "Muse モデルでプロジェクトを探索し、ソフトウェア開発タスクを実行する Meta のターミナル型コーディングアシスタントです。",
        "専用ハードウェアを使い、低遅延の言語モデル処理を提供する Groq のクラウド推論プラットフォームです。",
        "対話アプリ、推論タスク、コード生成、テキスト分析に対応する DeepSeek のモデルプラットフォームです。",
        "モデルの試用と、言語処理・推論・プログラミング向けアプリの構築に使える Mistral AI の開発ワークスペースです。",
        "ウェハースケールのハードウェアで言語モデルの応答を高速に生成する Cerebras のクラウド推論サービスです。"
    ],
    "ko": [
        "에이전트를 편집기 및 터미널과 결합하여 소프트웨어 개발과 테스트를 돕는 Google의 AI 개발 환경입니다.",
        "Gemini 모델을 시험하고 프롬프트를 다듬으며 AI 앱의 프로토타입을 만드는 Google의 작업 공간입니다.",
        "Grok으로 코드베이스를 탐색하고 파일을 편집하며 터미널의 개발 작업을 자동화하는 SpaceXAI의 코딩 에이전트입니다.",
        "대화, 추론 및 프로그래밍 앱을 위한 Grok 모델을 제공하는 SpaceXAI의 개발자 플랫폼입니다.",
        "저장소 이해, 변경 사항 구현 및 코드 검토를 개발 워크플로 전반에서 돕는 OpenAI의 코딩 에이전트입니다.",
        "GPT 및 추론 모델로 앱과 에이전트를 만들 수 있는 OpenAI의 개발자 플랫폼입니다.",
        "프로젝트 탐색, 파일 편집, 버그 수정 및 개발 명령 실행을 돕는 Anthropic의 코딩 도우미입니다.",
        "언어 이해, 추론 및 코드 생성이 필요한 앱에 Claude를 통합하는 Anthropic의 개발자 플랫폼입니다.",
        "로컬이나 클라우드에서 개방형 모델을 실행하는 도구로, 대화와 코딩을 위한 모델 라이브러리를 제공합니다.",
        "추론, 프로그래밍 및 긴 컨텍스트 처리를 위한 Kimi 모델을 제공하는 Moonshot AI의 모델 플랫폼입니다.",
        "요구 사항을 설계, 구현 작업 및 코드로 구체화하는 명세 중심의 AI 개발 환경입니다.",
        "GPU를 직접 운영하지 않고 관리형 인프라에서 AI 추론을 실행하는 Cloudflare의 서버리스 모델 서비스입니다.",
        "GPU 인프라에서 AI를 배포하고 실행하도록 돕는 NVIDIA의 최적화된 모델 추론 서비스입니다.",
        "AI 기반 개발 워크플로를 위한 Zen 및 Go 모델 서비스를 갖춘 오픈 소스 코딩 에이전트입니다.",
        "모델과 에이전트를 기업의 개발 워크플로에 통합하는 소프트웨어 엔지니어링용 AI 플랫폼입니다.",
        "Kimchi Inference를 기반으로 코딩 에이전트와 호스팅된 개방형 모델을 결합한 다중 모델 코딩 플랫폼입니다.",
        "편집기, 터미널 및 클라우드의 에이전트에 통합 모델 게이트웨이를 제공하는 오픈 소스 코딩 플랫폼입니다.",
        "대화, 추론 및 프로그래밍 앱을 위한 Muse 모델을 제공하는 Meta의 개발자 플랫폼입니다.",
        "Muse 모델로 프로젝트를 탐색하고 소프트웨어 개발 작업을 수행하는 Meta의 터미널 기반 코딩 도우미입니다.",
        "전용 하드웨어를 사용하여 지연 시간이 짧은 언어 모델 서비스를 제공하는 Groq의 클라우드 추론 플랫폼입니다.",
        "대화 앱, 추론 작업, 코드 생성 및 텍스트 분석을 위한 DeepSeek의 모델 플랫폼입니다.",
        "모델을 시험하고 언어 처리, 추론 및 프로그래밍 앱을 만드는 Mistral AI의 개발 작업 공간입니다.",
        "웨이퍼 규모의 하드웨어로 언어 모델 응답을 빠르게 생성하는 Cerebras의 클라우드 추론 서비스입니다."
    ],
    "id": [
        "Lingkungan pengembangan AI Google yang memadukan agen dengan editor dan terminal untuk membantu membangun serta menguji perangkat lunak.",
        "Ruang kerja Google untuk mencoba model Gemini, menyempurnakan prompt, dan membuat prototipe aplikasi AI.",
        "Agen pemrograman SpaceXAI yang menggunakan Grok untuk menjelajahi kode, mengedit file, dan mengotomatiskan tugas pengembangan di terminal.",
        "Platform pengembang SpaceXAI yang menyediakan model Grok untuk aplikasi percakapan, penalaran, dan pemrograman.",
        "Agen pemrograman OpenAI untuk memahami repositori, menerapkan perubahan, dan meninjau kode dalam alur pengembangan.",
        "Platform pengembang OpenAI yang menyediakan model GPT dan penalaran untuk membangun aplikasi serta agen.",
        "Asisten pemrograman Anthropic untuk menjelajahi proyek, mengedit file, memperbaiki bug, dan menjalankan perintah pengembangan.",
        "Platform pengembang Anthropic untuk memakai Claude dalam aplikasi yang membutuhkan pemahaman bahasa, penalaran, dan pembuatan kode.",
        "Alat untuk menjalankan model terbuka secara lokal atau di cloud, dengan pustaka model untuk percakapan dan pemrograman.",
        "Platform model Moonshot AI yang menyediakan model Kimi untuk penalaran, pemrograman, dan pengolahan konteks panjang.",
        "Lingkungan pengembangan AI berbasis spesifikasi yang mengubah kebutuhan menjadi desain, tugas implementasi, dan kode.",
        "Layanan model serverless Cloudflare yang menjalankan inferensi AI pada infrastruktur terkelola tanpa perlu mengoperasikan GPU sendiri.",
        "Layanan inferensi model yang dioptimalkan NVIDIA untuk membantu pengembang menerapkan dan menjalankan AI pada infrastruktur GPU.",
        "Agen pemrograman sumber terbuka dengan layanan model Zen dan Go untuk alur pengembangan berbantuan AI.",
        "Platform AI untuk rekayasa perangkat lunak yang menghadirkan model dan agen ke dalam alur pengembangan perusahaan.",
        "Platform pemrograman multimodel berbasis Kimchi Inference yang menggabungkan agen pemrograman dengan model terbuka terhosting.",
        "Platform pemrograman sumber terbuka dengan gerbang model terpadu untuk agen di editor, terminal, dan cloud.",
        "Platform pengembang Meta yang menyediakan model Muse untuk aplikasi percakapan, penalaran, dan pemrograman.",
        "Asisten pemrograman Meta berbasis terminal yang menggunakan model Muse untuk menjelajahi proyek dan mengerjakan tugas pengembangan perangkat lunak.",
        "Platform inferensi cloud Groq yang menggunakan perangkat keras khusus untuk menyediakan model bahasa dengan latensi rendah.",
        "Platform model DeepSeek untuk aplikasi percakapan, tugas penalaran, pembuatan kode, dan analisis teks.",
        "Ruang pengembangan Mistral AI untuk mencoba model dan membangun aplikasi bahasa, penalaran, serta pemrograman.",
        "Layanan inferensi cloud Cerebras yang menggunakan perangkat keras berskala wafer untuk menghasilkan respons model bahasa dengan kecepatan tinggi."
    ],
    "pt": [
        "O ambiente de desenvolvimento com IA do Google integra agentes ao editor e ao terminal para criar e testar software.",
        "O espaço de trabalho do Google para experimentar modelos Gemini, ajustar prompts e criar protótipos de aplicações de IA.",
        "O agente de programação da SpaceXAI usa o Grok para explorar código, editar arquivos e automatizar tarefas de desenvolvimento no terminal.",
        "A plataforma para desenvolvedores da SpaceXAI oferece modelos Grok para aplicações de conversação, raciocínio e programação.",
        "O agente de programação da OpenAI ajuda a compreender repositórios, implementar mudanças e revisar código nos fluxos de desenvolvimento.",
        "A plataforma para desenvolvedores da OpenAI oferece modelos GPT e de raciocínio para criar aplicações e agentes.",
        "O assistente de programação da Anthropic explora projetos, edita arquivos, corrige erros e executa comandos de desenvolvimento.",
        "A plataforma para desenvolvedores da Anthropic integra o Claude a aplicações de compreensão de linguagem, raciocínio e geração de código.",
        "Uma ferramenta para executar modelos abertos localmente ou na nuvem, com uma biblioteca para conversação e programação.",
        "A plataforma da Moonshot AI oferece modelos Kimi para raciocínio, programação e processamento de contextos longos.",
        "Um ambiente de desenvolvimento com IA baseado em especificações, que transforma requisitos em projetos, tarefas de implementação e código.",
        "O serviço de modelos serverless da Cloudflare executa inferência de IA em infraestrutura gerenciada, sem precisar administrar GPUs.",
        "Os serviços de inferência otimizados da NVIDIA ajudam a implantar e executar modelos de IA em infraestrutura de GPU.",
        "Um agente de programação de código aberto com os serviços de modelos Zen e Go para desenvolvimento assistido por IA.",
        "Uma plataforma de IA para engenharia de software que integra modelos e agentes aos fluxos de desenvolvimento das empresas.",
        "Uma plataforma de programação multimodelo baseada no Kimchi Inference, que combina agentes com modelos abertos hospedados.",
        "Uma plataforma de programação de código aberto com um gateway unificado de modelos para agentes no editor, no terminal e na nuvem.",
        "A plataforma para desenvolvedores da Meta oferece modelos Muse para aplicações de conversação, raciocínio e programação.",
        "O assistente de programação da Meta no terminal usa modelos Muse para explorar projetos e executar tarefas de desenvolvimento de software.",
        "A plataforma de inferência em nuvem da Groq usa hardware especializado para servir modelos de linguagem com baixa latência.",
        "A plataforma de modelos da DeepSeek atende a aplicações de conversação, raciocínio, geração de código e análise de texto.",
        "O espaço de desenvolvimento da Mistral AI permite experimentar modelos e criar aplicações de linguagem, raciocínio e programação.",
        "O serviço de inferência em nuvem da Cerebras usa hardware em escala de wafer para gerar respostas de modelos de linguagem em alta velocidade."
    ],
    "ru": [
        "Среда ИИ-разработки Google объединяет агентов с редактором и терминалом для создания и тестирования программного обеспечения.",
        "Рабочая среда Google для экспериментов с моделями Gemini, настройки запросов и создания прототипов ИИ-приложений.",
        "Агент-программист SpaceXAI использует Grok для изучения кода, редактирования файлов и автоматизации задач разработки в терминале.",
        "Платформа SpaceXAI для разработчиков предоставляет модели Grok для диалоговых приложений, рассуждений и программирования.",
        "Агент-программист OpenAI помогает разбираться в репозиториях, вносить изменения и проверять код в процессе разработки.",
        "Платформа OpenAI для разработчиков предоставляет модели GPT и модели рассуждений для создания приложений и агентов.",
        "Помощник-программист Anthropic изучает проекты, редактирует файлы, исправляет ошибки и выполняет команды разработки.",
        "Платформа Anthropic для разработчиков позволяет использовать Claude в приложениях для понимания языка, рассуждений и генерации кода.",
        "Инструмент для запуска открытых моделей локально или в облаке с библиотекой моделей для диалогов и программирования.",
        "Платформа Moonshot AI предоставляет модели Kimi для рассуждений, программирования и работы с длинным контекстом.",
        "Среда ИИ-разработки на основе спецификаций, которая преобразует требования в проектные решения, задачи реализации и код.",
        "Бессерверный сервис моделей Cloudflare выполняет ИИ-инференс на управляемой инфраструктуре без необходимости самостоятельно обслуживать GPU.",
        "Оптимизированные сервисы инференса NVIDIA помогают разработчикам развёртывать и запускать ИИ на инфраструктуре GPU.",
        "Агент-программист с открытым исходным кодом и сервисами моделей Zen и Go для разработки с помощью ИИ.",
        "Платформа ИИ для программной инженерии, интегрирующая модели и агентов в корпоративные процессы разработки.",
        "Мультимодельная платформа программирования на базе Kimchi Inference, объединяющая агентов с размещёнными в облаке открытыми моделями.",
        "Платформа программирования с открытым исходным кодом и единым шлюзом моделей для агентов в редакторе, терминале и облаке.",
        "Платформа Meta для разработчиков предоставляет модели Muse для диалоговых приложений, рассуждений и программирования.",
        "Терминальный помощник-программист Meta использует модели Muse для изучения проектов и выполнения задач разработки ПО.",
        "Облачная платформа инференса Groq использует специализированное оборудование для работы языковых моделей с низкой задержкой.",
        "Платформа моделей DeepSeek предназначена для диалоговых приложений, рассуждений, генерации кода и анализа текста.",
        "Рабочая среда Mistral AI для экспериментов с моделями и создания приложений для обработки языка, рассуждений и программирования.",
        "Облачный сервис инференса Cerebras использует оборудование масштаба кремниевой пластины для быстрой генерации ответов языковых моделей."
    ],
    "th": [
        "สภาพแวดล้อมพัฒนา AI ของ Google ที่ผสานเอเจนต์เข้ากับตัวแก้ไขโค้ดและเทอร์มินัล เพื่อช่วยสร้างและทดสอบซอฟต์แวร์",
        "พื้นที่ทำงานของ Google สำหรับทดลองโมเดล Gemini ปรับแต่งพรอมป์ต์ และสร้างต้นแบบแอปพลิเคชัน AI",
        "เอเจนต์เขียนโค้ดของ SpaceXAI ที่ใช้ Grok สำรวจโค้ด แก้ไขไฟล์ และทำงานพัฒนาในเทอร์มินัลแบบอัตโนมัติ",
        "แพลตฟอร์มนักพัฒนาของ SpaceXAI ที่ให้บริการโมเดล Grok สำหรับแอปสนทนา การให้เหตุผล และการเขียนโปรแกรม",
        "เอเจนต์เขียนโค้ดของ OpenAI ที่ช่วยทำความเข้าใจคลังโค้ด ลงมือแก้ไข และตรวจทานโค้ดในกระบวนการพัฒนา",
        "แพลตฟอร์มนักพัฒนาของ OpenAI ที่ให้บริการโมเดล GPT และโมเดลให้เหตุผลสำหรับสร้างแอปพลิเคชันและเอเจนต์",
        "ผู้ช่วยเขียนโค้ดของ Anthropic สำหรับสำรวจโปรเจกต์ แก้ไขไฟล์ แก้บั๊ก และรันคำสั่งในการพัฒนา",
        "แพลตฟอร์มนักพัฒนาของ Anthropic สำหรับใช้ Claude ในแอปที่ต้องการความเข้าใจภาษา การให้เหตุผล และการสร้างโค้ด",
        "เครื่องมือสำหรับรันโมเดลแบบเปิดในเครื่องหรือบนคลาวด์ พร้อมคลังโมเดลสำหรับการสนทนาและการเขียนโปรแกรม",
        "แพลตฟอร์มโมเดลของ Moonshot AI ที่ให้บริการ Kimi สำหรับการให้เหตุผล การเขียนโปรแกรม และการประมวลผลบริบทยาว",
        "สภาพแวดล้อมพัฒนา AI ที่ยึดข้อกำหนดเป็นหลัก ช่วยเปลี่ยนความต้องการให้เป็นแบบออกแบบ งานที่ต้องทำ และโค้ด",
        "บริการโมเดลแบบไร้เซิร์ฟเวอร์ของ Cloudflare ที่รันการอนุมาน AI บนโครงสร้างพื้นฐานที่มีผู้ดูแล โดยไม่ต้องจัดการ GPU เอง",
        "บริการอนุมานโมเดลที่ NVIDIA ปรับแต่งให้เหมาะสม เพื่อช่วยนักพัฒนาติดตั้งและรัน AI บนโครงสร้างพื้นฐาน GPU",
        "เอเจนต์เขียนโค้ดแบบโอเพนซอร์ส พร้อมบริการโมเดล Zen และ Go สำหรับกระบวนการพัฒนาที่ใช้ AI ช่วย",
        "แพลตฟอร์ม AI สำหรับวิศวกรรมซอฟต์แวร์ ที่นำโมเดลและเอเจนต์มาใช้ในกระบวนการพัฒนาขององค์กร",
        "แพลตฟอร์มเขียนโค้ดหลายโมเดลบน Kimchi Inference ที่ผสานเอเจนต์เขียนโค้ดกับโมเดลแบบเปิดที่มีบริการโฮสต์",
        "แพลตฟอร์มเขียนโค้ดแบบโอเพนซอร์ส พร้อมเกตเวย์โมเดลแบบรวมสำหรับเอเจนต์ในตัวแก้ไขโค้ด เทอร์มินัล และคลาวด์",
        "แพลตฟอร์มนักพัฒนาของ Meta ที่ให้บริการโมเดล Muse สำหรับแอปสนทนา การให้เหตุผล และการเขียนโปรแกรม",
        "ผู้ช่วยเขียนโค้ดในเทอร์มินัลของ Meta ที่ใช้โมเดล Muse สำรวจโปรเจกต์และทำงานพัฒนาซอฟต์แวร์",
        "แพลตฟอร์มอนุมานบนคลาวด์ของ Groq ที่ใช้ฮาร์ดแวร์เฉพาะทางเพื่อให้บริการโมเดลภาษาด้วยเวลาแฝงต่ำ",
        "แพลตฟอร์มโมเดลของ DeepSeek สำหรับแอปสนทนา งานให้เหตุผล การสร้างโค้ด และการวิเคราะห์ข้อความ",
        "พื้นที่พัฒนาของ Mistral AI สำหรับทดลองโมเดลและสร้างแอปด้านภาษา การให้เหตุผล และการเขียนโปรแกรม",
        "บริการอนุมานบนคลาวด์ของ Cerebras ที่ใช้ฮาร์ดแวร์ระดับเวเฟอร์เพื่อสร้างคำตอบจากโมเดลภาษาอย่างรวดเร็ว"
    ],
    "tr": [
        "Google’ın AI geliştirme ortamı, yazılım oluşturmak ve test etmek için ajanları editör ve terminalle bir araya getirir.",
        "Gemini modellerini denemek, istemleri iyileştirmek ve AI uygulamalarının prototiplerini oluşturmak için Google’ın çalışma alanı.",
        "SpaceXAI’ın kodlama ajanı, kod tabanlarını incelemek, dosyaları düzenlemek ve terminaldeki geliştirme işlerini otomatikleştirmek için Grok kullanır.",
        "SpaceXAI’ın geliştirici platformu, sohbet, akıl yürütme ve programlama uygulamaları için Grok modelleri sunar.",
        "OpenAI’ın kodlama ajanı, geliştirme süreçlerinde depoları anlamaya, değişiklikleri uygulamaya ve kodu incelemeye yardımcı olur.",
        "OpenAI’ın geliştirici platformu, uygulama ve ajan oluşturmak için GPT ve akıl yürütme modelleri sunar.",
        "Anthropic’in kodlama asistanı projeleri inceler, dosyaları düzenler, hataları giderir ve geliştirme komutlarını çalıştırır.",
        "Anthropic’in geliştirici platformu, dil anlama, akıl yürütme ve kod üretme gereken uygulamalara Claude’u entegre eder.",
        "Açık modelleri yerel olarak veya bulutta çalıştıran, sohbet ve kodlama için model kütüphanesi sunan bir araç.",
        "Moonshot AI’ın model platformu, akıl yürütme, programlama ve uzun bağlam işleme için Kimi modelleri sunar.",
        "Gereksinimleri tasarımlara, uygulama görevlerine ve koda dönüştüren, belirtim odaklı bir AI geliştirme ortamı.",
        "Cloudflare’ın sunucusuz model hizmeti, GPU işletmek zorunda kalmadan yönetilen altyapıda AI çıkarımı çalıştırır.",
        "NVIDIA’nın optimize edilmiş model çıkarım hizmetleri, geliştiricilerin GPU altyapısında AI dağıtmasına ve çalıştırmasına yardımcı olur.",
        "AI destekli geliştirme süreçleri için Zen ve Go model hizmetleri sunan açık kaynaklı bir kodlama ajanı.",
        "Modelleri ve ajanları kurumsal geliştirme süreçlerine entegre eden, yazılım mühendisliğine yönelik bir AI platformu.",
        "Kimchi Inference tabanlı, kodlama ajanlarını barındırılan açık modellerle birleştiren çok modelli bir kodlama platformu.",
        "Editör, terminal ve buluttaki ajanlar için birleşik model ağ geçidi sunan açık kaynaklı bir kodlama platformu.",
        "Meta’nın geliştirici platformu, sohbet, akıl yürütme ve programlama uygulamaları için Muse modelleri sunar.",
        "Meta’nın terminal tabanlı kodlama asistanı, projeleri incelemek ve yazılım geliştirme görevlerini yürütmek için Muse modellerini kullanır.",
        "Groq’un bulut çıkarım platformu, dil modellerini düşük gecikmeyle sunmak için özel donanım kullanır.",
        "DeepSeek’in model platformu; sohbet uygulamaları, akıl yürütme, kod üretme ve metin analizi için hizmet sunar.",
        "Mistral AI’ın modelleri denemek ve dil, akıl yürütme ile programlama uygulamaları oluşturmak için sunduğu geliştirme alanı.",
        "Cerebras’ın bulut çıkarım hizmeti, dil modeli yanıtlarını yüksek hızda üretmek için yonga plakası ölçeğinde donanım kullanır."
    ]
};
const PROVIDER_ENTRY_COPY = {
    "en": [
        "Enter API key",
        "Enter API token"
    ],
    "vi": [
        "Nhập khóa API",
        "Nhập token API"
    ],
    "zh-CN": [
        "输入 API 密钥",
        "输入 API 令牌"
    ],
    "zh-TW": [
        "輸入 API 金鑰",
        "輸入 API 權杖"
    ],
    "de": [
        "API-Schlüssel eingeben",
        "API-Token eingeben"
    ],
    "es": [
        "Introducir clave API",
        "Introducir token API"
    ],
    "fr": [
        "Saisir une clé API",
        "Saisir un jeton API"
    ],
    "id": [
        "Masukkan kunci API",
        "Masukkan token API"
    ],
    "it": [
        "Inserisci chiave API",
        "Inserisci token API"
    ],
    "ja": [
        "API キーを入力",
        "API トークンを入力"
    ],
    "ko": [
        "API 키 입력",
        "API 토큰 입력"
    ],
    "pt": [
        "Inserir chave API",
        "Inserir token API"
    ],
    "ru": [
        "Ввести API-ключ",
        "Ввести API-токен"
    ],
    "th": [
        "ป้อนคีย์ API",
        "ป้อนโทเค็น API"
    ],
    "tr": [
        "API anahtarı gir",
        "API belirteci gir"
    ]
};
for (const [locale, descriptions] of Object.entries(PROVIDER_PRODUCT_COPY)) {
    PROVIDER_DESCRIPTION_KEYS.forEach((key, index) => {
        PAGE_LOCALE_TRANSLATIONS[locale][key] = descriptions[index];
    });
    PAGE_LOCALE_TRANSLATIONS[locale]['provider.ui.enter_key'] = PROVIDER_ENTRY_COPY[locale][0];
    PAGE_LOCALE_TRANSLATIONS[locale]['provider.ui.enter_token'] = PROVIDER_ENTRY_COPY[locale][1];
}
