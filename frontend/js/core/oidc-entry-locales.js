// Team sign-in entry and deployment guidance. Protocol names remain exact.
const OIDC_ENTRY_KEYS = [
    'oidc_entry.sign_in',
    'oidc_entry.retry_hint',
    'oidc_entry.setup_title',
    'oidc_entry.setup_help',
    'oidc_entry.access_help',
    'oidc_entry.setup_guide'
];

const OIDC_ENTRY_LOCALE_VALUES = {
    en: [
        'Sign in with a team account',
        'If team sign-in does not finish, retry or use your console password.',
        'Set up team sign-in',
        'Configure OIDC in the deployment environment using the guide, then restart Polaris. Keep your local-owner password for recovery.',
        'Grant access through an exact issuer and subject binding below, or an explicit role mapping. Verify readiness after restarting.',
        'OIDC setup guide'
    ],
    'zh-CN': [
        '使用团队账户登录',
        '如果团队登录未完成，请重试或使用控制台密码。',
        '设置团队登录',
        '按照指南在部署环境中配置 OIDC，然后重启 Polaris。请保留本地所有者密码以便恢复访问。',
        '通过下方精确的颁发者和主体绑定或明确的角色映射授予访问权限。重启后请确认就绪状态。',
        'OIDC 设置指南'
    ],
    'zh-TW': [
        '使用團隊帳戶登入',
        '如果團隊登入未完成，請重試或使用控制台密碼。',
        '設定團隊登入',
        '依照指南在部署環境中設定 OIDC，然後重新啟動 Polaris。請保留本機擁有者密碼以便復原存取權。',
        '透過下方精確的發行者與主體繫結，或明確的角色對應授予存取權。重新啟動後請確認就緒狀態。',
        'OIDC 設定指南'
    ],
    de: [
        'Mit einem Teamkonto anmelden',
        'Falls die Teamanmeldung nicht abgeschlossen wird, versuchen Sie es erneut oder nutzen Sie Ihr Konsolenpasswort.',
        'Teamanmeldung einrichten',
        'Konfigurieren Sie OIDC gemäß der Anleitung in der Bereitstellungsumgebung und starten Sie Polaris neu. Bewahren Sie das lokale Eigentümerpasswort zur Wiederherstellung auf.',
        'Gewähren Sie Zugriff über eine exakte Bindung von Aussteller und Subjekt unten oder eine ausdrückliche Rollenzuordnung. Prüfen Sie die Bereitschaft nach dem Neustart.',
        'OIDC-Einrichtungsanleitung'
    ],
    es: [
        'Iniciar sesión con una cuenta de equipo',
        'Si el inicio de sesión del equipo no se completa, reinténtalo o usa tu contraseña de consola.',
        'Configurar el inicio de sesión del equipo',
        'Configura OIDC en el entorno de despliegue siguiendo la guía y reinicia Polaris. Conserva la contraseña del propietario local para recuperar el acceso.',
        'Concede acceso mediante una vinculación exacta de emisor y sujeto abajo, o un mapeo de roles explícito. Verifica la preparación después de reiniciar.',
        'Guía de configuración de OIDC'
    ],
    fr: [
        'Se connecter avec un compte d’équipe',
        'Si la connexion d’équipe n’aboutit pas, réessayez ou utilisez votre mot de passe de console.',
        'Configurer la connexion d’équipe',
        'Configurez OIDC dans l’environnement de déploiement en suivant le guide, puis redémarrez Polaris. Conservez le mot de passe du propriétaire local pour récupérer l’accès.',
        'Accordez l’accès via une liaison exacte entre émetteur et sujet ci-dessous, ou un mappage explicite de rôles. Vérifiez l’état après le redémarrage.',
        'Guide de configuration OIDC'
    ],
    id: [
        'Masuk dengan akun tim',
        'Jika proses masuk tim tidak selesai, coba lagi atau gunakan kata sandi konsol Anda.',
        'Siapkan akses masuk tim',
        'Konfigurasikan OIDC di lingkungan penerapan sesuai panduan, lalu mulai ulang Polaris. Simpan kata sandi pemilik lokal untuk pemulihan.',
        'Berikan akses melalui pengikatan penerbit dan subjek yang tepat di bawah, atau pemetaan peran yang eksplisit. Periksa kesiapan setelah memulai ulang.',
        'Panduan penyiapan OIDC'
    ],
    it: [
        'Accedi con un account del team',
        'Se l’accesso del team non si completa, riprova o usa la password della console.',
        'Configura l’accesso del team',
        'Configura OIDC nell’ambiente di distribuzione seguendo la guida, poi riavvia Polaris. Conserva la password del proprietario locale per il ripristino.',
        'Concedi l’accesso tramite un’associazione esatta di emittente e soggetto qui sotto, o una mappatura esplicita dei ruoli. Verifica lo stato dopo il riavvio.',
        'Guida alla configurazione OIDC'
    ],
    ja: [
        'チームアカウントでサインイン',
        'チームのサインインが完了しない場合は、再試行するかコンソールのパスワードを使用してください。',
        'チームのサインインを設定',
        'ガイドに従ってデプロイ環境で OIDC を設定し、Polaris を再起動してください。復旧用にローカル所有者のパスワードを保管してください。',
        '以下で発行者とサブジェクトを正確に紐付けるか、明示的なロールマッピングでアクセスを許可します。再起動後に準備状態を確認してください。',
        'OIDC 設定ガイド'
    ],
    ko: [
        '팀 계정으로 로그인',
        '팀 로그인이 완료되지 않으면 다시 시도하거나 콘솔 비밀번호를 사용하세요.',
        '팀 로그인 설정',
        '가이드에 따라 배포 환경에서 OIDC를 설정한 다음 Polaris를 다시 시작하세요. 복구를 위해 로컬 소유자 비밀번호를 보관하세요.',
        '아래에서 발급자와 주체를 정확하게 연결하거나 명시적 역할 매핑으로 접근을 허용하세요. 다시 시작한 후 준비 상태를 확인하세요.',
        'OIDC 설정 가이드'
    ],
    pt: [
        'Entrar com uma conta da equipe',
        'Se o login da equipe não for concluído, tente novamente ou use a senha do console.',
        'Configurar o login da equipe',
        'Configure o OIDC no ambiente de implantação seguindo o guia e reinicie o Polaris. Guarde a senha do proprietário local para recuperação.',
        'Conceda acesso por uma vinculação exata de emissor e sujeito abaixo ou um mapeamento explícito de funções. Verifique a prontidão após reiniciar.',
        'Guia de configuração do OIDC'
    ],
    ru: [
        'Войти с учётной записью команды',
        'Если вход команды не завершён, повторите попытку или используйте пароль консоли.',
        'Настроить вход команды',
        'Настройте OIDC в среде развёртывания по руководству, затем перезапустите Polaris. Сохраните пароль локального владельца для восстановления доступа.',
        'Предоставьте доступ через точную привязку издателя и субъекта ниже или явное сопоставление ролей. Проверьте готовность после перезапуска.',
        'Руководство по настройке OIDC'
    ],
    th: [
        'เข้าสู่ระบบด้วยบัญชีทีม',
        'หากการเข้าสู่ระบบของทีมไม่เสร็จสิ้น ให้ลองอีกครั้งหรือใช้รหัสผ่านคอนโซล',
        'ตั้งค่าการเข้าสู่ระบบของทีม',
        'กำหนดค่า OIDC ในสภาพแวดล้อมการติดตั้งตามคู่มือ แล้วเริ่ม Polaris ใหม่ เก็บรหัสผ่านเจ้าของในเครื่องไว้เพื่อกู้คืนการเข้าถึง',
        'ให้สิทธิ์เข้าถึงโดยผูกผู้ออกและตัวระบุผู้ใช้ให้ตรงกันด้านล่าง หรือกำหนดการจับคู่บทบาทอย่างชัดเจน ตรวจสอบความพร้อมหลังเริ่มใหม่',
        'คู่มือการตั้งค่า OIDC'
    ],
    tr: [
        'Ekip hesabıyla giriş yap',
        'Ekip girişi tamamlanmazsa yeniden deneyin veya konsol parolanızı kullanın.',
        'Ekip girişini ayarla',
        'Kılavuzu izleyerek dağıtım ortamında OIDC yapılandırın, ardından Polaris’i yeniden başlatın. Kurtarma için yerel sahip parolasını saklayın.',
        'Aşağıda sağlayıcı ve özne değerlerini tam eşleştirerek veya açık bir rol eşlemesiyle erişim verin. Yeniden başlattıktan sonra hazırlık durumunu doğrulayın.',
        'OIDC kurulum kılavuzu'
    ],
    vi: [
        'Đăng nhập bằng tài khoản nhóm',
        'Nếu đăng nhập nhóm chưa hoàn tất, hãy thử lại hoặc dùng mật khẩu bảng điều khiển.',
        'Thiết lập đăng nhập nhóm',
        'Cấu hình OIDC trong môi trường triển khai theo hướng dẫn, rồi khởi động lại Polaris. Giữ mật khẩu chủ sở hữu cục bộ để khôi phục quyền truy cập.',
        'Cấp quyền bằng cách liên kết chính xác nhà phát hành và chủ thể bên dưới, hoặc ánh xạ vai trò tường minh. Kiểm tra mức sẵn sàng sau khi khởi động lại.',
        'Hướng dẫn thiết lập OIDC'
    ]
};

for (const [locale, values] of Object.entries(OIDC_ENTRY_LOCALE_VALUES)) {
    const messages = Object.fromEntries(OIDC_ENTRY_KEYS.map((key, index) => [key, values[index]]));
    Object.assign(PAGE_LOCALE_TRANSLATIONS[locale], messages);
    Object.assign(MESSAGE_CATALOGS[locale], messages);
    if (locale === 'en') {
        for (const [key, message] of Object.entries(messages)) {
            if (!ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.has(message)) {
                ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.set(message, key);
            }
        }
    }
}
