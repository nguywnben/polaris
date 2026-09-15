"""Request-scoped localization for console-facing API messages."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

from core.meta_provider_i18n import MESSAGES as META_PROVIDER_MESSAGES
from core.meta_provider_i18n import SOURCE_KEYS as META_SOURCE_KEYS
from core.provider_expansion_i18n import MESSAGES as PROVIDER_EXPANSION_MESSAGES
from fastapi.responses import JSONResponse

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = (
    "en",
    "zh-CN",
    "zh-TW",
    "de",
    "es",
    "fr",
    "id",
    "it",
    "ja",
    "ko",
    "pt",
    "ru",
    "th",
    "tr",
    "vi",
)

_current_locale: ContextVar[str] = ContextVar("request_locale", default=DEFAULT_LOCALE)
_localization_enabled: ContextVar[bool] = ContextVar("localization_enabled", default=False)


class LocalizedJSONResponse(JSONResponse):
    """Translate known console-facing values while preserving JSON field names."""

    def render(self, content: Any) -> bytes:
        return super().render(translate_payload(content))


@dataclass(frozen=True)
class _LocaleState:
    locale_token: Any
    enabled_token: Any


MESSAGES: dict[str, dict[str, str]] = {
    "auth.incorrect_password": {
        "en": "Incorrect password.",
        "zh-CN": "密码不正确。",
        "zh-TW": "密碼不正確。",
        "de": "Das Passwort ist falsch.",
        "es": "Contraseña incorrecta.",
        "fr": "Le mot de passe est incorrect.",
        "id": "Kata sandi salah.",
        "it": "La password non è corretta.",
        "ja": "パスワードが正しくありません。",
        "ko": "비밀번호가 올바르지 않습니다.",
        "pt": "A senha está incorreta.",
        "ru": "Неверный пароль.",
        "th": "รหัสผ่านไม่ถูกต้อง",
        "tr": "Parola yanlış.",
        "vi": "Mật khẩu không đúng.",
    },
    "credentials.model_unavailable": {
        "en": "Model {model} is not available for this credential.",
        "zh-CN": "此凭据无法使用模型 {model}。",
        "zh-TW": "此憑證無法使用模型 {model}。",
        "de": "Das Modell {model} ist für diesen Zugang nicht verfügbar.",
        "es": "El modelo {model} no está disponible con esta credencial.",
        "fr": "Le modèle {model} n’est pas disponible avec cet identifiant.",
        "id": "Model {model} tidak tersedia untuk kredensial ini.",
        "it": "Il modello {model} non è disponibile con questa credenziale.",
        "ja": "この認証情報ではモデル {model} を利用できません。",
        "ko": "이 자격 증명으로는 {model} 모델을 사용할 수 없습니다.",
        "pt": "O modelo {model} não está disponível para esta credencial.",
        "ru": "Модель {model} недоступна для этих учётных данных.",
        "th": "ข้อมูลรับรองนี้ไม่รองรับโมเดล {model}",
        "tr": "{model} modeli bu kimlik bilgisiyle kullanılamıyor.",
        "vi": "Thông tin xác thực này không hỗ trợ mô hình {model}.",
    },
}

_AUTH_MESSAGE_ROWS = {
    "en": {
        "auth.setup_required": "Initial setup is required before login.",
        "auth.signed_in": "Signed in.",
        "auth.setup_exists": "Initial setup has already been completed.",
        "auth.password_short": "Password must be at least 12 characters.",
        "auth.password_mismatch": "Passwords do not match.",
        "auth.password_weak": "Choose a less common password or a longer unique passphrase.",
        "auth.setup_complete": "Initial setup completed.",
        "auth.signed_out": "Signed out.",
        "auth.invalid_callback": "Please provide a valid callback URL.",
    },
    "zh-CN": {
        "auth.setup_required": "登录前必须先完成初始设置。",
        "auth.signed_in": "已登录。",
        "auth.setup_exists": "初始设置已经完成。",
        "auth.password_short": "密码必须至少包含 12 个字符。",
        "auth.password_mismatch": "两次输入的密码不一致。",
        "auth.password_weak": "请选择更不常见的密码，或使用更长的唯一密码短语。",
        "auth.setup_complete": "初始设置已完成。",
        "auth.signed_out": "已退出登录。",
        "auth.invalid_callback": "请提供有效的回调 URL。",
    },
    "zh-TW": {
        "auth.setup_required": "登入前必須先完成初始設定。",
        "auth.signed_in": "已登入。",
        "auth.setup_exists": "初始設定已經完成。",
        "auth.password_short": "密碼至少須包含 12 個字元。",
        "auth.password_mismatch": "兩次輸入的密碼不一致。",
        "auth.password_weak": "請選擇較不常見的密碼，或使用更長且獨特的密碼片語。",
        "auth.setup_complete": "初始設定已完成。",
        "auth.signed_out": "已登出。",
        "auth.invalid_callback": "請提供有效的回呼 URL。",
    },
    "de": {
        "auth.setup_required": "Vor der Anmeldung muss die Ersteinrichtung abgeschlossen werden.",
        "auth.signed_in": "Angemeldet.",
        "auth.setup_exists": "Die Ersteinrichtung wurde bereits abgeschlossen.",
        "auth.password_short": "Das Passwort muss mindestens 12 Zeichen lang sein.",
        "auth.password_mismatch": "Die Passwörter stimmen nicht überein.",
        "auth.password_weak": "Wählen Sie ein weniger häufiges Passwort oder eine längere, einzigartige Passphrase.",
        "auth.setup_complete": "Die Ersteinrichtung ist abgeschlossen.",
        "auth.signed_out": "Abgemeldet.",
        "auth.invalid_callback": "Geben Sie eine gültige Callback-URL an.",
    },
    "es": {
        "auth.setup_required": "Debes completar la configuración inicial antes de iniciar sesión.",
        "auth.signed_in": "Sesión iniciada.",
        "auth.setup_exists": "La configuración inicial ya se ha completado.",
        "auth.password_short": "La contraseña debe tener al menos 12 caracteres.",
        "auth.password_mismatch": "Las contraseñas no coinciden.",
        "auth.password_weak": "Elige una contraseña menos común o una frase de contraseña única y más larga.",
        "auth.setup_complete": "La configuración inicial se completó correctamente.",
        "auth.signed_out": "Sesión cerrada.",
        "auth.invalid_callback": "Proporciona una URL de retorno válida.",
    },
    "fr": {
        "auth.setup_required": "La configuration initiale doit être terminée avant la connexion.",
        "auth.signed_in": "Connexion réussie.",
        "auth.setup_exists": "La configuration initiale est déjà terminée.",
        "auth.password_short": "Le mot de passe doit comporter au moins 12 caractères.",
        "auth.password_mismatch": "Les mots de passe ne correspondent pas.",
        "auth.password_weak": "Choisissez un mot de passe moins courant ou une phrase secrète unique plus longue.",
        "auth.setup_complete": "La configuration initiale est terminée.",
        "auth.signed_out": "Déconnexion réussie.",
        "auth.invalid_callback": "Indiquez une URL de rappel valide.",
    },
    "id": {
        "auth.setup_required": "Penyiapan awal harus diselesaikan sebelum masuk.",
        "auth.signed_in": "Berhasil masuk.",
        "auth.setup_exists": "Penyiapan awal sudah selesai.",
        "auth.password_short": "Kata sandi harus berisi minimal 12 karakter.",
        "auth.password_mismatch": "Kata sandi tidak sama.",
        "auth.password_weak": "Pilih kata sandi yang tidak umum atau frasa sandi unik yang lebih panjang.",
        "auth.setup_complete": "Penyiapan awal selesai.",
        "auth.signed_out": "Berhasil keluar.",
        "auth.invalid_callback": "Masukkan URL callback yang valid.",
    },
    "it": {
        "auth.setup_required": "Prima di accedere è necessario completare la configurazione iniziale.",
        "auth.signed_in": "Accesso effettuato.",
        "auth.setup_exists": "La configurazione iniziale è già stata completata.",
        "auth.password_short": "La password deve contenere almeno 12 caratteri.",
        "auth.password_mismatch": "Le password non corrispondono.",
        "auth.password_weak": "Scegli una password meno comune o una passphrase univoca più lunga.",
        "auth.setup_complete": "Configurazione iniziale completata.",
        "auth.signed_out": "Disconnessione effettuata.",
        "auth.invalid_callback": "Specifica un URL di callback valido.",
    },
    "ja": {
        "auth.setup_required": "ログインする前に初期セットアップを完了してください。",
        "auth.signed_in": "ログインしました。",
        "auth.setup_exists": "初期セットアップはすでに完了しています。",
        "auth.password_short": "パスワードは 12 文字以上にしてください。",
        "auth.password_mismatch": "パスワードが一致しません。",
        "auth.password_weak": "より一般的でないパスワード、または長く固有のパスフレーズを選んでください。",
        "auth.setup_complete": "初期セットアップが完了しました。",
        "auth.signed_out": "ログアウトしました。",
        "auth.invalid_callback": "有効なコールバック URL を入力してください。",
    },
    "ko": {
        "auth.setup_required": "로그인하기 전에 초기 설정을 완료해야 합니다.",
        "auth.signed_in": "로그인했습니다.",
        "auth.setup_exists": "초기 설정이 이미 완료되었습니다.",
        "auth.password_short": "비밀번호는 12자 이상이어야 합니다.",
        "auth.password_mismatch": "비밀번호가 일치하지 않습니다.",
        "auth.password_weak": "덜 흔한 비밀번호나 더 길고 고유한 암호 문구를 선택하세요.",
        "auth.setup_complete": "초기 설정을 완료했습니다.",
        "auth.signed_out": "로그아웃했습니다.",
        "auth.invalid_callback": "올바른 콜백 URL을 입력하세요.",
    },
    "pt": {
        "auth.setup_required": "Conclua a configuração inicial antes de entrar.",
        "auth.signed_in": "Sessão iniciada.",
        "auth.setup_exists": "A configuração inicial já foi concluída.",
        "auth.password_short": "A senha deve ter pelo menos 12 caracteres.",
        "auth.password_mismatch": "As senhas não coincidem.",
        "auth.password_weak": "Escolha uma senha menos comum ou uma frase-senha única e mais longa.",
        "auth.setup_complete": "Configuração inicial concluída.",
        "auth.signed_out": "Sessão encerrada.",
        "auth.invalid_callback": "Informe uma URL de callback válida.",
    },
    "ru": {
        "auth.setup_required": "Перед входом необходимо завершить первоначальную настройку.",
        "auth.signed_in": "Вход выполнен.",
        "auth.setup_exists": "Первоначальная настройка уже завершена.",
        "auth.password_short": "Пароль должен содержать не менее 12 символов.",
        "auth.password_mismatch": "Пароли не совпадают.",
        "auth.password_weak": "Выберите менее распространённый пароль или более длинную уникальную парольную фразу.",
        "auth.setup_complete": "Первоначальная настройка завершена.",
        "auth.signed_out": "Вы вышли из системы.",
        "auth.invalid_callback": "Укажите корректный URL обратного вызова.",
    },
    "th": {
        "auth.setup_required": "ต้องตั้งค่าเริ่มต้นให้เสร็จก่อนเข้าสู่ระบบ",
        "auth.signed_in": "เข้าสู่ระบบแล้ว",
        "auth.setup_exists": "ตั้งค่าเริ่มต้นเรียบร้อยแล้ว",
        "auth.password_short": "รหัสผ่านต้องมีอย่างน้อย 12 ตัวอักษร",
        "auth.password_mismatch": "รหัสผ่านไม่ตรงกัน",
        "auth.password_weak": "เลือกรหัสผ่านที่คาดเดาได้ยากขึ้น หรือใช้วลีรหัสผ่านที่ยาวและไม่ซ้ำกัน",
        "auth.setup_complete": "ตั้งค่าเริ่มต้นเรียบร้อยแล้ว",
        "auth.signed_out": "ออกจากระบบแล้ว",
        "auth.invalid_callback": "โปรดระบุ URL callback ที่ถูกต้อง",
    },
    "tr": {
        "auth.setup_required": "Oturum açmadan önce ilk kurulum tamamlanmalıdır.",
        "auth.signed_in": "Oturum açıldı.",
        "auth.setup_exists": "İlk kurulum zaten tamamlanmış.",
        "auth.password_short": "Parola en az 12 karakter olmalıdır.",
        "auth.password_mismatch": "Parolalar eşleşmiyor.",
        "auth.password_weak": "Daha az yaygın bir parola veya daha uzun ve benzersiz bir parola ifadesi seçin.",
        "auth.setup_complete": "İlk kurulum tamamlandı.",
        "auth.signed_out": "Oturum kapatıldı.",
        "auth.invalid_callback": "Geçerli bir geri çağırma URL’si girin.",
    },
    "vi": {
        "auth.setup_required": "Bạn cần hoàn tất thiết lập ban đầu trước khi đăng nhập.",
        "auth.signed_in": "Đã đăng nhập.",
        "auth.setup_exists": "Thiết lập ban đầu đã được hoàn tất trước đó.",
        "auth.password_short": "Mật khẩu phải có ít nhất 12 ký tự.",
        "auth.password_mismatch": "Mật khẩu xác nhận không khớp.",
        "auth.password_weak": "Hãy chọn mật khẩu ít phổ biến hơn hoặc một cụm mật khẩu duy nhất và dài hơn.",
        "auth.setup_complete": "Đã hoàn tất thiết lập ban đầu.",
        "auth.signed_out": "Đã đăng xuất.",
        "auth.invalid_callback": "Vui lòng cung cấp URL callback hợp lệ.",
    },
}

for _locale, _messages in _AUTH_MESSAGE_ROWS.items():
    for _key, _message in _messages.items():
        MESSAGES.setdefault(_key, {})[_locale] = _message

_AUTH_INTERNAL_KEYS = (
    "auth.sign_in_internal_error",
    "auth.setup_status_internal_error",
    "auth.setup_internal_error",
)

_AUTH_INTERNAL_ROWS = {
    "en": (
        "Unable to sign in because of an internal service error.",
        "Unable to determine the initial setup status.",
        "Unable to complete initial setup because of an internal service error.",
    ),
    "zh-CN": (
        "由于服务内部错误，无法登录。",
        "无法确定初始设置状态。",
        "由于服务内部错误，无法完成初始设置。",
    ),
    "zh-TW": (
        "由於服務內部錯誤，無法登入。",
        "無法判斷初始設定狀態。",
        "由於服務內部錯誤，無法完成初始設定。",
    ),
    "de": (
        "Die Anmeldung ist wegen eines internen Dienstfehlers nicht möglich.",
        "Der Status der Ersteinrichtung konnte nicht ermittelt werden.",
        "Die Ersteinrichtung konnte wegen eines internen Dienstfehlers nicht abgeschlossen werden.",
    ),
    "es": (
        "No se pudo iniciar sesión debido a un error interno del servicio.",
        "No se pudo determinar el estado de la configuración inicial.",
        "No se pudo completar la configuración inicial debido a un error interno del servicio.",
    ),
    "fr": (
        "Connexion impossible en raison d’une erreur interne du service.",
        "Impossible de déterminer l’état de la configuration initiale.",
        "Impossible de terminer la configuration initiale en raison d’une erreur interne du service.",
    ),
    "id": (
        "Tidak dapat masuk karena terjadi kesalahan internal pada layanan.",
        "Status penyiapan awal tidak dapat ditentukan.",
        "Penyiapan awal tidak dapat diselesaikan karena terjadi kesalahan internal pada layanan.",
    ),
    "it": (
        "Impossibile accedere a causa di un errore interno del servizio.",
        "Impossibile determinare lo stato della configurazione iniziale.",
        "Impossibile completare la configurazione iniziale a causa di un errore interno del servizio.",
    ),
    "ja": (
        "サービス内部のエラーによりログインできませんでした。",
        "初期セットアップの状態を確認できませんでした。",
        "サービス内部のエラーにより初期セットアップを完了できませんでした。",
    ),
    "ko": (
        "서비스 내부 오류로 로그인할 수 없습니다.",
        "초기 설정 상태를 확인할 수 없습니다.",
        "서비스 내부 오류로 초기 설정을 완료할 수 없습니다.",
    ),
    "pt": (
        "Não foi possível entrar devido a um erro interno do serviço.",
        "Não foi possível determinar o estado da configuração inicial.",
        "Não foi possível concluir a configuração inicial devido a um erro interno do serviço.",
    ),
    "ru": (
        "Не удалось войти из-за внутренней ошибки сервиса.",
        "Не удалось определить состояние первоначальной настройки.",
        "Не удалось завершить первоначальную настройку из-за внутренней ошибки сервиса.",
    ),
    "th": (
        "ไม่สามารถเข้าสู่ระบบได้เนื่องจากเกิดข้อผิดพลาดภายในบริการ",
        "ไม่สามารถตรวจสอบสถานะการตั้งค่าเริ่มต้นได้",
        "ไม่สามารถตั้งค่าเริ่มต้นให้เสร็จได้เนื่องจากเกิดข้อผิดพลาดภายในบริการ",
    ),
    "tr": (
        "Dahili bir hizmet hatası nedeniyle oturum açılamadı.",
        "İlk kurulum durumu belirlenemedi.",
        "Dahili bir hizmet hatası nedeniyle ilk kurulum tamamlanamadı.",
    ),
    "vi": (
        "Không thể đăng nhập do dịch vụ gặp lỗi nội bộ.",
        "Không thể xác định trạng thái thiết lập ban đầu.",
        "Không thể hoàn tất thiết lập ban đầu do dịch vụ gặp lỗi nội bộ.",
    ),
}

for _locale, _messages in _AUTH_INTERNAL_ROWS.items():
    for _key, _message in zip(_AUTH_INTERNAL_KEYS, _messages):
        MESSAGES.setdefault(_key, {})[_locale] = _message

_OAUTH_MESSAGE_ROWS = {
    "en": {
        "oauth.failed_title": "{provider} Authentication Failed",
        "oauth.success_title": "{provider} Authentication Successful",
        "oauth.retry": "{provider} returned an authorization error. Return to Polaris and start the authentication flow again.",
        "oauth.internal_error": "Polaris could not finish {provider} authentication. Return to the Providers page and try again.",
        "oauth.copy_callback": "Copy this page URL from the browser address bar, return to the Providers page, paste it into the Callback URL field, and save the credential.",
    },
    "zh-CN": {
        "oauth.failed_title": "{provider} 身份验证失败",
        "oauth.success_title": "{provider} 身份验证成功",
        "oauth.retry": "{provider} 返回了授权错误。请返回 Polaris 并重新开始身份验证。",
        "oauth.internal_error": "Polaris 无法完成 {provider} 身份验证。请返回“提供商”页面后重试。",
        "oauth.copy_callback": "请复制浏览器地址栏中的完整页面 URL，返回“提供商”页面，将其粘贴到“回调 URL”字段中，然后保存凭据。",
    },
    "zh-TW": {
        "oauth.failed_title": "{provider} 驗證失敗",
        "oauth.success_title": "{provider} 驗證成功",
        "oauth.retry": "{provider} 傳回授權錯誤。請返回 Polaris 並重新開始驗證流程。",
        "oauth.internal_error": "Polaris 無法完成 {provider} 驗證。請返回「供應商」頁面後再試一次。",
        "oauth.copy_callback": "請複製瀏覽器網址列中的完整頁面 URL，返回「供應商」頁面，貼到「回呼 URL」欄位後儲存憑證。",
    },
    "de": {
        "oauth.failed_title": "{provider}-Authentifizierung fehlgeschlagen",
        "oauth.success_title": "{provider}-Authentifizierung erfolgreich",
        "oauth.retry": "{provider} hat einen Autorisierungsfehler gemeldet. Kehren Sie zu Polaris zurück und starten Sie die Authentifizierung erneut.",
        "oauth.internal_error": "Polaris konnte die {provider}-Authentifizierung nicht abschließen. Kehren Sie zur Seite „Provider“ zurück und versuchen Sie es erneut.",
        "oauth.copy_callback": "Kopieren Sie die vollständige URL aus der Adressleiste, kehren Sie zur Seite „Provider“ zurück, fügen Sie sie in das Feld „Callback-URL“ ein und speichern Sie den Zugang.",
    },
    "es": {
        "oauth.failed_title": "Error de autenticación con {provider}",
        "oauth.success_title": "Autenticación con {provider} completada",
        "oauth.retry": "{provider} devolvió un error de autorización. Vuelve a Polaris e inicia de nuevo el proceso de autenticación.",
        "oauth.internal_error": "Polaris no pudo completar la autenticación con {provider}. Vuelve a la página Proveedores e inténtalo de nuevo.",
        "oauth.copy_callback": "Copia la URL completa de la barra de direcciones, vuelve a la página Proveedores, pégala en el campo URL de retorno y guarda la credencial.",
    },
    "fr": {
        "oauth.failed_title": "Échec de l’authentification {provider}",
        "oauth.success_title": "Authentification {provider} réussie",
        "oauth.retry": "{provider} a renvoyé une erreur d’autorisation. Revenez dans Polaris et relancez l’authentification.",
        "oauth.internal_error": "Polaris n’a pas pu terminer l’authentification {provider}. Revenez à la page Fournisseurs et réessayez.",
        "oauth.copy_callback": "Copiez l’URL complète dans la barre d’adresse, revenez à la page Fournisseurs, collez-la dans le champ URL de rappel, puis enregistrez l’identifiant.",
    },
    "id": {
        "oauth.failed_title": "Autentikasi {provider} Gagal",
        "oauth.success_title": "Autentikasi {provider} Berhasil",
        "oauth.retry": "{provider} mengembalikan kesalahan otorisasi. Kembali ke Polaris dan mulai lagi proses autentikasi.",
        "oauth.internal_error": "Polaris tidak dapat menyelesaikan autentikasi {provider}. Kembali ke halaman Penyedia dan coba lagi.",
        "oauth.copy_callback": "Salin URL lengkap dari bilah alamat browser, kembali ke halaman Penyedia, tempelkan ke kolom URL Callback, lalu simpan kredensial.",
    },
    "it": {
        "oauth.failed_title": "Autenticazione {provider} non riuscita",
        "oauth.success_title": "Autenticazione {provider} riuscita",
        "oauth.retry": "{provider} ha restituito un errore di autorizzazione. Torna a Polaris e avvia di nuovo l’autenticazione.",
        "oauth.internal_error": "Polaris non ha potuto completare l’autenticazione {provider}. Torna alla pagina Provider e riprova.",
        "oauth.copy_callback": "Copia l’URL completo dalla barra degli indirizzi, torna alla pagina Provider, incollalo nel campo URL di callback e salva la credenziale.",
    },
    "ja": {
        "oauth.failed_title": "{provider} の認証に失敗しました",
        "oauth.success_title": "{provider} の認証が完了しました",
        "oauth.retry": "{provider} から認可エラーが返されました。Polaris に戻り、認証をやり直してください。",
        "oauth.internal_error": "Polaris は {provider} の認証を完了できませんでした。プロバイダーページに戻って、もう一度お試しください。",
        "oauth.copy_callback": "ブラウザーのアドレスバーからページの完全な URL をコピーし、プロバイダーページに戻ってコールバック URL 欄に貼り付け、認証情報を保存してください。",
    },
    "ko": {
        "oauth.failed_title": "{provider} 인증 실패",
        "oauth.success_title": "{provider} 인증 성공",
        "oauth.retry": "{provider}에서 인증 오류를 반환했습니다. Polaris로 돌아가 인증을 다시 시작하세요.",
        "oauth.internal_error": "Polaris에서 {provider} 인증을 완료하지 못했습니다. 공급자 페이지로 돌아가 다시 시도하세요.",
        "oauth.copy_callback": "브라우저 주소 표시줄의 전체 페이지 URL을 복사한 뒤 공급자 페이지로 돌아가 콜백 URL 필드에 붙여 넣고 자격 증명을 저장하세요.",
    },
    "pt": {
        "oauth.failed_title": "Falha na autenticação com {provider}",
        "oauth.success_title": "Autenticação com {provider} concluída",
        "oauth.retry": "{provider} retornou um erro de autorização. Volte ao Polaris e reinicie a autenticação.",
        "oauth.internal_error": "O Polaris não conseguiu concluir a autenticação com {provider}. Volte à página Provedores e tente novamente.",
        "oauth.copy_callback": "Copie a URL completa da barra de endereços, volte à página Provedores, cole-a no campo URL de callback e salve a credencial.",
    },
    "ru": {
        "oauth.failed_title": "Не удалось пройти аутентификацию {provider}",
        "oauth.success_title": "Аутентификация {provider} выполнена",
        "oauth.retry": "{provider} вернул ошибку авторизации. Вернитесь в Polaris и начните аутентификацию заново.",
        "oauth.internal_error": "Polaris не удалось завершить аутентификацию {provider}. Вернитесь на страницу «Провайдеры» и повторите попытку.",
        "oauth.copy_callback": "Скопируйте полный URL из адресной строки браузера, вернитесь на страницу «Провайдеры», вставьте его в поле URL обратного вызова и сохраните учётные данные.",
    },
    "th": {
        "oauth.failed_title": "การยืนยันตัวตน {provider} ไม่สำเร็จ",
        "oauth.success_title": "ยืนยันตัวตน {provider} สำเร็จ",
        "oauth.retry": "{provider} ส่งข้อผิดพลาดการอนุญาตกลับมา โปรดกลับไปที่ Polaris แล้วเริ่มการยืนยันตัวตนใหม่",
        "oauth.internal_error": "Polaris ไม่สามารถดำเนินการยืนยันตัวตน {provider} ให้เสร็จได้ โปรดกลับไปที่หน้าผู้ให้บริการแล้วลองอีกครั้ง",
        "oauth.copy_callback": "คัดลอก URL แบบเต็มจากแถบที่อยู่ของเบราว์เซอร์ กลับไปที่หน้าผู้ให้บริการ วาง URL ในช่อง Callback URL แล้วบันทึกข้อมูลรับรอง",
    },
    "tr": {
        "oauth.failed_title": "{provider} Kimlik Doğrulaması Başarısız",
        "oauth.success_title": "{provider} Kimlik Doğrulaması Başarılı",
        "oauth.retry": "{provider} bir yetkilendirme hatası döndürdü. Polaris’e dönüp kimlik doğrulamayı yeniden başlatın.",
        "oauth.internal_error": "Polaris, {provider} kimlik doğrulamasını tamamlayamadı. Sağlayıcılar sayfasına dönüp yeniden deneyin.",
        "oauth.copy_callback": "Tarayıcının adres çubuğundaki tam URL’yi kopyalayın, Sağlayıcılar sayfasına dönün, Geri Çağırma URL’si alanına yapıştırın ve kimlik bilgisini kaydedin.",
    },
    "vi": {
        "oauth.failed_title": "Xác thực {provider} không thành công",
        "oauth.success_title": "Xác thực {provider} thành công",
        "oauth.retry": "{provider} đã trả về lỗi cấp quyền. Hãy quay lại Polaris và bắt đầu lại quy trình xác thực.",
        "oauth.internal_error": "Polaris không thể hoàn tất xác thực {provider}. Hãy quay lại trang Nhà cung cấp và thử lại.",
        "oauth.copy_callback": "Sao chép toàn bộ URL trên thanh địa chỉ của trình duyệt, quay lại trang Nhà cung cấp, dán vào trường URL callback rồi lưu thông tin xác thực.",
    },
}

_OAUTH_NAVIGATION_ROWS = {
    "en": ("Return to Providers", "Open Providers in a new tab"),
    "zh-CN": ("返回提供商页面", "在新标签页中打开提供商页面"),
    "zh-TW": ("返回供應商頁面", "在新分頁開啟供應商頁面"),
    "de": ("Zurück zu den Providern", "Provider in neuem Tab öffnen"),
    "es": ("Volver a Proveedores", "Abrir Proveedores en una pestaña nueva"),
    "fr": ("Retour aux fournisseurs", "Ouvrir les fournisseurs dans un nouvel onglet"),
    "id": ("Kembali ke Penyedia", "Buka Penyedia di tab baru"),
    "it": ("Torna ai fornitori", "Apri i fornitori in una nuova scheda"),
    "ja": ("プロバイダーに戻る", "新しいタブでプロバイダーを開く"),
    "ko": ("공급자로 돌아가기", "새 탭에서 공급자 열기"),
    "pt": ("Voltar aos provedores", "Abrir provedores em uma nova guia"),
    "ru": ("Вернуться к провайдерам", "Открыть провайдеров в новой вкладке"),
    "th": ("กลับไปที่ผู้ให้บริการ", "เปิดหน้าผู้ให้บริการในแท็บใหม่"),
    "tr": ("Sağlayıcılara dön", "Sağlayıcıları yeni sekmede aç"),
    "vi": ("Quay lại Nhà cung cấp", "Mở Nhà cung cấp trong tab mới"),
}
for _locale, (_return_label, _new_tab_label) in _OAUTH_NAVIGATION_ROWS.items():
    _OAUTH_MESSAGE_ROWS[_locale].update(
        {
            "oauth.return_providers": _return_label,
            "oauth.open_providers_new_tab": _new_tab_label,
        }
    )

for _locale, _messages in _OAUTH_MESSAGE_ROWS.items():
    for _key, _message in _messages.items():
        MESSAGES.setdefault(_key, {})[_locale] = _message

_OAUTH_CREDENTIAL_SAVED_ROWS = {
    "en": "The {provider} credential for {account} was saved to the provider pool. You can close this tab and return to Polaris.",
    "zh-CN": "{account} 的 {provider} 凭据已保存到提供商凭据池。现在可以关闭此标签页并返回 Polaris。",
    "zh-TW": "{account} 的 {provider} 憑證已儲存到供應商憑證集區。現在可以關閉此分頁並返回 Polaris。",
    "de": "Die {provider}-Zugangsdaten für {account} wurden im Provider-Pool gespeichert. Sie können diesen Tab schließen und zu Polaris zurückkehren.",
    "es": "La credencial de {provider} para {account} se guardó en el pool de proveedores. Ya puedes cerrar esta pestaña y volver a Polaris.",
    "fr": "L’identifiant {provider} de {account} a été enregistré dans le pool de fournisseurs. Vous pouvez fermer cet onglet et revenir dans Polaris.",
    "id": "Kredensial {provider} untuk {account} telah disimpan ke pool penyedia. Anda dapat menutup tab ini dan kembali ke Polaris.",
    "it": "La credenziale {provider} di {account} è stata salvata nel pool dei provider. Puoi chiudere questa scheda e tornare a Polaris.",
    "ja": "{account} の {provider} 認証情報をプロバイダープールに保存しました。このタブを閉じて Polaris に戻れます。",
    "ko": "{account}의 {provider} 자격 증명을 공급자 풀에 저장했습니다. 이 탭을 닫고 Polaris로 돌아가세요.",
    "pt": "A credencial {provider} de {account} foi salva no pool de provedores. Você pode fechar esta guia e voltar ao Polaris.",
    "ru": "Учётные данные {provider} для {account} сохранены в пуле провайдеров. Эту вкладку можно закрыть и вернуться в Polaris.",
    "th": "บันทึกข้อมูลรับรอง {provider} ของ {account} ลงในพูลผู้ให้บริการแล้ว คุณสามารถปิดแท็บนี้และกลับไปที่ Polaris ได้",
    "tr": "{account} için {provider} kimlik bilgisi sağlayıcı havuzuna kaydedildi. Bu sekmeyi kapatıp Polaris’e dönebilirsiniz.",
    "vi": "Đã lưu thông tin xác thực {provider} của {account} vào kho nhà cung cấp. Bạn có thể đóng thẻ này và quay lại Polaris.",
}

for _locale, _message in _OAUTH_CREDENTIAL_SAVED_ROWS.items():
    MESSAGES.setdefault("oauth.credential_saved", {})[_locale] = _message

_CONSOLE_MESSAGE_KEYS = (
    "console.internal_error",
    "config.saved",
    "config.password_updated",
    "config.reset",
    "credentials.not_found",
    "credentials.file_not_found",
    "credentials.enabled",
    "credentials.disabled",
    "credentials.deleted",
    "credentials.credit_enabled",
    "credentials.credit_disabled",
    "logs.not_found",
    "logs.empty",
    "credentials.test_success",
    "credentials.test_failed",
    "models.catalog_failed",
    "models.pool_save_failed",
)

_CONSOLE_MESSAGE_ROWS = {
    "en": (
        "Internal server error.",
        "Configuration saved.",
        "Console password updated.",
        "System configuration reset to defaults. Access passwords and the generated API key were preserved.",
        "Credential does not exist.",
        "Credential file does not exist.",
        "Credential enabled.",
        "Credential disabled.",
        "Credential deleted. Historical usage was retained anonymously.",
        "Credit usage enabled.",
        "Credit usage disabled.",
        "Log file does not exist.",
        "Log file is empty.",
        "Model test completed successfully.",
        "Model test failed.",
        "The provider model catalog could not be loaded.",
        "The virtual model configuration could not be saved.",
    ),
    "zh-CN": (
        "服务器内部错误。",
        "配置已保存。",
        "控制台密码已更新。",
        "系统配置已恢复默认值。访问密码和生成的 API 密钥已保留。",
        "凭据不存在。",
        "凭据文件不存在。",
        "凭据已启用。",
        "凭据已禁用。",
        "凭据已删除，历史用量已匿名保留。",
        "额度使用已启用。",
        "额度使用已禁用。",
        "日志文件不存在。",
        "日志文件为空。",
        "模型测试已成功完成。",
        "模型测试失败。",
        "无法加载提供商模型目录。",
        "无法保存虚拟模型配置。",
    ),
    "zh-TW": (
        "伺服器內部錯誤。",
        "設定已儲存。",
        "主控台密碼已更新。",
        "系統設定已恢復預設值。存取密碼與產生的 API 金鑰已保留。",
        "憑證不存在。",
        "憑證檔案不存在。",
        "憑證已啟用。",
        "憑證已停用。",
        "憑證已刪除，歷史用量已匿名保留。",
        "額度使用已啟用。",
        "額度使用已停用。",
        "日誌檔案不存在。",
        "日誌檔案是空的。",
        "模型測試已成功完成。",
        "模型測試失敗。",
        "無法載入供應商模型目錄。",
        "無法儲存虛擬模型設定。",
    ),
    "de": (
        "Interner Serverfehler.",
        "Konfiguration gespeichert.",
        "Konsolenpasswort aktualisiert.",
        "Die Systemkonfiguration wurde zurückgesetzt. Zugangspasswörter und der generierte API-Schlüssel wurden beibehalten.",
        "Die Zugangsdaten sind nicht vorhanden.",
        "Die Zugangsdaten-Datei ist nicht vorhanden.",
        "Zugangsdaten aktiviert.",
        "Zugangsdaten deaktiviert.",
        "Zugangsdaten gelöscht. Historische Nutzungsdaten wurden anonymisiert beibehalten.",
        "Kontingentnutzung aktiviert.",
        "Kontingentnutzung deaktiviert.",
        "Die Protokolldatei ist nicht vorhanden.",
        "Die Protokolldatei ist leer.",
        "Der Modelltest wurde erfolgreich abgeschlossen.",
        "Der Modelltest ist fehlgeschlagen.",
        "Der Modellkatalog des Anbieters konnte nicht geladen werden.",
        "Die Konfiguration des virtuellen Modells konnte nicht gespeichert werden.",
    ),
    "es": (
        "Error interno del servidor.",
        "Configuración guardada.",
        "Contraseña de la consola actualizada.",
        "La configuración del sistema se restableció. Se conservaron las contraseñas de acceso y la clave API generada.",
        "La credencial no existe.",
        "El archivo de credenciales no existe.",
        "Credencial habilitada.",
        "Credencial deshabilitada.",
        "Credencial eliminada. El historial de uso se conservó de forma anónima.",
        "Uso de cuota habilitado.",
        "Uso de cuota deshabilitado.",
        "El archivo de registro no existe.",
        "El archivo de registro está vacío.",
        "La prueba del modelo se completó correctamente.",
        "La prueba del modelo falló.",
        "No se pudo cargar el catálogo de modelos del proveedor.",
        "No se pudo guardar la configuración del modelo virtual.",
    ),
    "fr": (
        "Erreur interne du serveur.",
        "Configuration enregistrée.",
        "Mot de passe de la console mis à jour.",
        "La configuration système a été réinitialisée. Les mots de passe d’accès et la clé API générée ont été conservés.",
        "L’identifiant n’existe pas.",
        "Le fichier d’identifiants n’existe pas.",
        "Identifiant activé.",
        "Identifiant désactivé.",
        "Identifiant supprimé. L’historique d’utilisation a été conservé de manière anonyme.",
        "Utilisation du quota activée.",
        "Utilisation du quota désactivée.",
        "Le fichier journal n’existe pas.",
        "Le fichier journal est vide.",
        "Le test du modèle s’est terminé correctement.",
        "Le test du modèle a échoué.",
        "Impossible de charger le catalogue de modèles du fournisseur.",
        "Impossible d’enregistrer la configuration du modèle virtuel.",
    ),
    "id": (
        "Terjadi kesalahan internal pada server.",
        "Konfigurasi disimpan.",
        "Kata sandi konsol diperbarui.",
        "Konfigurasi sistem direset ke nilai bawaan. Kata sandi akses dan kunci API yang dibuat tetap dipertahankan.",
        "Kredensial tidak ditemukan.",
        "File kredensial tidak ditemukan.",
        "Kredensial diaktifkan.",
        "Kredensial dinonaktifkan.",
        "Kredensial dihapus. Riwayat penggunaan disimpan secara anonim.",
        "Penggunaan kuota diaktifkan.",
        "Penggunaan kuota dinonaktifkan.",
        "File log tidak ditemukan.",
        "File log kosong.",
        "Pengujian model berhasil diselesaikan.",
        "Pengujian model gagal.",
        "Katalog model penyedia tidak dapat dimuat.",
        "Konfigurasi model virtual tidak dapat disimpan.",
    ),
    "it": (
        "Errore interno del server.",
        "Configurazione salvata.",
        "Password della console aggiornata.",
        "La configurazione di sistema è stata ripristinata. Le password di accesso e la chiave API generata sono state conservate.",
        "La credenziale non esiste.",
        "Il file della credenziale non esiste.",
        "Credenziale abilitata.",
        "Credenziale disabilitata.",
        "Credenziale eliminata. La cronologia di utilizzo è stata conservata in forma anonima.",
        "Utilizzo della quota abilitato.",
        "Utilizzo della quota disabilitato.",
        "Il file di log non esiste.",
        "Il file di log è vuoto.",
        "Il test del modello è stato completato.",
        "Il test del modello non è riuscito.",
        "Impossibile caricare il catalogo dei modelli del provider.",
        "Impossibile salvare la configurazione del modello virtuale.",
    ),
    "ja": (
        "サーバー内部エラーが発生しました。",
        "設定を保存しました。",
        "コンソールのパスワードを更新しました。",
        "システム設定を初期値に戻しました。アクセス用パスワードと生成済み API キーは保持されています。",
        "認証情報が存在しません。",
        "認証情報ファイルが存在しません。",
        "認証情報を有効にしました。",
        "認証情報を無効にしました。",
        "認証情報を削除しました。過去の使用履歴は匿名化して保持されています。",
        "割り当て使用を有効にしました。",
        "割り当て使用を無効にしました。",
        "ログファイルが存在しません。",
        "ログファイルは空です。",
        "モデルテストが完了しました。",
        "モデルテストに失敗しました。",
        "プロバイダーのモデルカタログを読み込めませんでした。",
        "仮想モデルの設定を保存できませんでした。",
    ),
    "ko": (
        "서버 내부 오류가 발생했습니다.",
        "설정을 저장했습니다.",
        "콘솔 비밀번호를 변경했습니다.",
        "시스템 설정을 기본값으로 되돌렸습니다. 접근 비밀번호와 생성된 API 키는 유지됩니다.",
        "자격 증명이 없습니다.",
        "자격 증명 파일이 없습니다.",
        "자격 증명을 활성화했습니다.",
        "자격 증명을 비활성화했습니다.",
        "자격 증명을 삭제했습니다. 이전 사용 기록은 익명으로 유지됩니다.",
        "할당량 사용을 활성화했습니다.",
        "할당량 사용을 비활성화했습니다.",
        "로그 파일이 없습니다.",
        "로그 파일이 비어 있습니다.",
        "모델 테스트를 완료했습니다.",
        "모델 테스트에 실패했습니다.",
        "공급자 모델 카탈로그를 불러오지 못했습니다.",
        "가상 모델 설정을 저장하지 못했습니다.",
    ),
    "pt": (
        "Erro interno do servidor.",
        "Configuração salva.",
        "Senha da console atualizada.",
        "A configuração do sistema foi redefinida. As senhas de acesso e a chave de API gerada foram preservadas.",
        "A credencial não existe.",
        "O arquivo de credenciais não existe.",
        "Credencial ativada.",
        "Credencial desativada.",
        "Credencial excluída. O histórico de uso foi preservado de forma anônima.",
        "Uso da cota ativado.",
        "Uso da cota desativado.",
        "O arquivo de log não existe.",
        "O arquivo de log está vazio.",
        "O teste do modelo foi concluído.",
        "O teste do modelo falhou.",
        "Não foi possível carregar o catálogo de modelos do provedor.",
        "Não foi possível salvar a configuração do modelo virtual.",
    ),
    "ru": (
        "Внутренняя ошибка сервера.",
        "Конфигурация сохранена.",
        "Пароль консоли обновлён.",
        "Системная конфигурация сброшена. Пароли доступа и сгенерированный ключ API сохранены.",
        "Учётные данные не существуют.",
        "Файл учётных данных не существует.",
        "Учётные данные включены.",
        "Учётные данные отключены.",
        "Учётные данные удалены. История использования сохранена в обезличенном виде.",
        "Использование квоты включено.",
        "Использование квоты отключено.",
        "Файл журнала не существует.",
        "Файл журнала пуст.",
        "Проверка модели успешно завершена.",
        "Проверка модели завершилась с ошибкой.",
        "Не удалось загрузить каталог моделей провайдера.",
        "Не удалось сохранить конфигурацию виртуальной модели.",
    ),
    "th": (
        "เกิดข้อผิดพลาดภายในเซิร์ฟเวอร์",
        "บันทึกการกำหนดค่าแล้ว",
        "อัปเดตรหัสผ่านคอนโซลแล้ว",
        "รีเซ็ตการกำหนดค่าระบบเป็นค่าเริ่มต้นแล้ว โดยเก็บรหัสผ่านการเข้าถึงและคีย์ API ที่สร้างไว้",
        "ไม่พบข้อมูลรับรอง",
        "ไม่พบไฟล์ข้อมูลรับรอง",
        "เปิดใช้งานข้อมูลรับรองแล้ว",
        "ปิดใช้งานข้อมูลรับรองแล้ว",
        "ลบข้อมูลรับรองแล้ว และเก็บประวัติการใช้งานในรูปแบบไม่ระบุตัวตน",
        "เปิดใช้งานโควตาแล้ว",
        "ปิดใช้งานโควตาแล้ว",
        "ไม่พบไฟล์บันทึก",
        "ไฟล์บันทึกว่างเปล่า",
        "ทดสอบโมเดลสำเร็จ",
        "ทดสอบโมเดลไม่สำเร็จ",
        "ไม่สามารถโหลดรายการโมเดลของผู้ให้บริการได้",
        "ไม่สามารถบันทึกการกำหนดค่าโมเดลเสมือนได้",
    ),
    "tr": (
        "Sunucu içi hata.",
        "Yapılandırma kaydedildi.",
        "Konsol parolası güncellendi.",
        "Sistem yapılandırması varsayılanlara sıfırlandı. Erişim parolaları ve oluşturulan API anahtarı korundu.",
        "Kimlik bilgisi mevcut değil.",
        "Kimlik bilgisi dosyası mevcut değil.",
        "Kimlik bilgisi etkinleştirildi.",
        "Kimlik bilgisi devre dışı bırakıldı.",
        "Kimlik bilgisi silindi. Geçmiş kullanım anonim olarak korundu.",
        "Kota kullanımı etkinleştirildi.",
        "Kota kullanımı devre dışı bırakıldı.",
        "Günlük dosyası mevcut değil.",
        "Günlük dosyası boş.",
        "Model testi başarıyla tamamlandı.",
        "Model testi başarısız oldu.",
        "Sağlayıcı model kataloğu yüklenemedi.",
        "Sanal model yapılandırması kaydedilemedi.",
    ),
    "vi": (
        "Máy chủ gặp lỗi nội bộ.",
        "Đã lưu cấu hình.",
        "Đã cập nhật mật khẩu bảng điều khiển.",
        "Đã khôi phục cấu hình hệ thống về mặc định. Mật khẩu truy cập và khóa API đã tạo vẫn được giữ nguyên.",
        "Thông tin xác thực không tồn tại.",
        "Tệp thông tin xác thực không tồn tại.",
        "Đã bật thông tin xác thực.",
        "Đã tắt thông tin xác thực.",
        "Đã xóa thông tin xác thực. Dữ liệu sử dụng trước đây được giữ lại ở dạng ẩn danh.",
        "Đã bật sử dụng hạn mức.",
        "Đã tắt sử dụng hạn mức.",
        "Tệp nhật ký không tồn tại.",
        "Tệp nhật ký đang trống.",
        "Đã kiểm tra mô hình thành công.",
        "Kiểm tra mô hình không thành công.",
        "Không thể tải danh mục mô hình của nhà cung cấp.",
        "Không thể lưu cấu hình mô hình ảo.",
    ),
}

for _locale, _messages in _CONSOLE_MESSAGE_ROWS.items():
    if len(_messages) != len(_CONSOLE_MESSAGE_KEYS):
        raise RuntimeError(f"Invalid console message catalog for {_locale}.")
    for _key, _message in zip(_CONSOLE_MESSAGE_KEYS, _messages):
        MESSAGES.setdefault(_key, {})[_locale] = _message

_PANEL_FAMILY_KEYS = (
    "panel.rate_limited",
    "panel.setup_token_required",
    "panel.managed_value",
    "panel.size_limit",
    "panel.invalid_value",
    "panel.unsupported_operation",
    "panel.duplicate_skipped",
    "panel.selection_required",
    "panel.resource_unavailable",
    "panel.operation_failed",
    "panel.operation_complete",
)

_PANEL_FAMILY_ROWS = {
    "en": (
        "Too many attempts were made. Wait a moment before trying again.",
        "Remote initial setup requires a strong SETUP_TOKEN configured by the operator.",
        "This value is managed by the runtime environment and cannot be changed from the console.",
        "The selected data exceeds the supported size or item limit.",
        "One or more submitted values are invalid. Review the field requirements and try again.",
        "This operation is not supported for the selected provider or credential type.",
        "The item was skipped because an equivalent or newer entry already exists.",
        "Select or enter the required information before continuing.",
        "The requested information is missing or currently unavailable.",
        "The operation could not be completed. Check the credential and provider configuration, then try again.",
        "The operation completed successfully.",
    ),
    "zh-CN": (
        "尝试次数过多，请稍后再试。",
        "远程初始设置需要运营者配置强 SETUP_TOKEN。",
        "此值由运行环境管理，无法在控制台中更改。",
        "所选数据超过支持的大小或数量限制。",
        "提交的一个或多个值无效。请检查字段要求后重试。",
        "所选提供商或凭据类型不支持此操作。",
        "已有相同或更新的条目，因此已跳过该项目。",
        "请先选择或输入必填信息。",
        "请求的信息缺失或暂时不可用。",
        "无法完成操作。请检查凭据和提供商配置后重试。",
        "操作已成功完成。",
    ),
    "zh-TW": (
        "嘗試次數過多，請稍後再試。",
        "遠端初始設定需要管理者設定強式 SETUP_TOKEN。",
        "此值由執行環境管理，無法在主控台中變更。",
        "所選資料超過支援的大小或數量限制。",
        "提交的一個或多個值無效。請檢查欄位要求後再試一次。",
        "所選供應商或憑證類型不支援此操作。",
        "已有相同或更新的項目，因此已略過。",
        "請先選擇或輸入必要資訊。",
        "要求的資訊遺失或目前無法使用。",
        "無法完成操作。請檢查憑證與供應商設定後再試一次。",
        "操作已成功完成。",
    ),
    "de": (
        "Es wurden zu viele Versuche durchgeführt. Warten Sie einen Moment und versuchen Sie es erneut.",
        "Die Remote-Ersteinrichtung erfordert ein starkes, vom Betreiber konfiguriertes SETUP_TOKEN.",
        "Dieser Wert wird von der Laufzeitumgebung verwaltet und kann nicht in der Konsole geändert werden.",
        "Die ausgewählten Daten überschreiten die unterstützte Größen- oder Mengenbegrenzung.",
        "Mindestens ein übermittelter Wert ist ungültig. Prüfen Sie die Feldanforderungen und versuchen Sie es erneut.",
        "Dieser Vorgang wird für den ausgewählten Anbieter oder Zugangstyp nicht unterstützt.",
        "Der Eintrag wurde übersprungen, da bereits ein gleichwertiger oder neuerer Eintrag vorhanden ist.",
        "Wählen Sie die erforderlichen Angaben aus oder geben Sie sie ein, bevor Sie fortfahren.",
        "Die angeforderten Informationen fehlen oder sind derzeit nicht verfügbar.",
        "Der Vorgang konnte nicht abgeschlossen werden. Prüfen Sie den Zugang und die Anbieterkonfiguration und versuchen Sie es erneut.",
        "Der Vorgang wurde erfolgreich abgeschlossen.",
    ),
    "es": (
        "Se han realizado demasiados intentos. Espera un momento antes de volver a intentarlo.",
        "La configuración inicial remota requiere un SETUP_TOKEN seguro configurado por el operador.",
        "Este valor lo administra el entorno de ejecución y no se puede cambiar desde la consola.",
        "Los datos seleccionados superan el límite de tamaño o cantidad admitido.",
        "Uno o varios valores enviados no son válidos. Revisa los requisitos de los campos e inténtalo de nuevo.",
        "Esta operación no es compatible con el proveedor o el tipo de credencial seleccionado.",
        "Se omitió el elemento porque ya existe una entrada equivalente o más reciente.",
        "Selecciona o introduce la información obligatoria antes de continuar.",
        "La información solicitada falta o no está disponible en este momento.",
        "No se pudo completar la operación. Comprueba la credencial y la configuración del proveedor e inténtalo de nuevo.",
        "La operación se completó correctamente.",
    ),
    "fr": (
        "Trop de tentatives ont été effectuées. Patientez un instant avant de réessayer.",
        "La configuration initiale à distance exige un SETUP_TOKEN robuste configuré par l’opérateur.",
        "Cette valeur est gérée par l’environnement d’exécution et ne peut pas être modifiée depuis la console.",
        "Les données sélectionnées dépassent la limite de taille ou de quantité prise en charge.",
        "Une ou plusieurs valeurs envoyées sont incorrectes. Vérifiez les exigences des champs et réessayez.",
        "Cette opération n’est pas prise en charge pour le fournisseur ou le type d’identifiant sélectionné.",
        "L’élément a été ignoré, car une entrée équivalente ou plus récente existe déjà.",
        "Sélectionnez ou saisissez les informations requises avant de continuer.",
        "Les informations demandées sont manquantes ou actuellement indisponibles.",
        "Impossible de terminer l’opération. Vérifiez l’identifiant et la configuration du fournisseur, puis réessayez.",
        "L’opération s’est terminée correctement.",
    ),
    "id": (
        "Terlalu banyak percobaan. Tunggu sebentar sebelum mencoba lagi.",
        "Penyiapan awal jarak jauh memerlukan SETUP_TOKEN kuat yang dikonfigurasi operator.",
        "Nilai ini dikelola oleh lingkungan runtime dan tidak dapat diubah dari konsol.",
        "Data yang dipilih melampaui batas ukuran atau jumlah yang didukung.",
        "Satu atau beberapa nilai yang dikirim tidak valid. Periksa persyaratan kolom lalu coba lagi.",
        "Operasi ini tidak didukung untuk penyedia atau jenis kredensial yang dipilih.",
        "Item dilewati karena entri yang setara atau lebih baru sudah ada.",
        "Pilih atau masukkan informasi yang diperlukan sebelum melanjutkan.",
        "Informasi yang diminta tidak ada atau sedang tidak tersedia.",
        "Operasi tidak dapat diselesaikan. Periksa kredensial dan konfigurasi penyedia, lalu coba lagi.",
        "Operasi berhasil diselesaikan.",
    ),
    "it": (
        "Sono stati effettuati troppi tentativi. Attendi un momento prima di riprovare.",
        "La configurazione iniziale da remoto richiede un SETUP_TOKEN robusto configurato dall’operatore.",
        "Questo valore è gestito dall’ambiente di esecuzione e non può essere modificato dalla console.",
        "I dati selezionati superano il limite di dimensione o quantità supportato.",
        "Uno o più valori inviati non sono validi. Controlla i requisiti dei campi e riprova.",
        "Questa operazione non è supportata per il provider o il tipo di credenziale selezionato.",
        "L’elemento è stato ignorato perché esiste già una voce equivalente o più recente.",
        "Seleziona o inserisci le informazioni richieste prima di continuare.",
        "Le informazioni richieste mancano o non sono al momento disponibili.",
        "Impossibile completare l’operazione. Controlla la credenziale e la configurazione del provider, quindi riprova.",
        "Operazione completata.",
    ),
    "ja": (
        "試行回数が多すぎます。しばらく待ってからもう一度お試しください。",
        "リモート初期セットアップには、運用者が設定した強力な SETUP_TOKEN が必要です。",
        "この値は実行環境で管理されているため、コンソールから変更できません。",
        "選択したデータが、対応しているサイズまたは件数の上限を超えています。",
        "送信された値の一部が無効です。各項目の要件を確認して、もう一度お試しください。",
        "選択したプロバイダーまたは認証情報の種類では、この操作を利用できません。",
        "同等または新しい項目がすでに存在するため、スキップしました。",
        "続行する前に、必要な情報を選択または入力してください。",
        "要求された情報がないか、現在利用できません。",
        "操作を完了できませんでした。認証情報とプロバイダー設定を確認して、もう一度お試しください。",
        "操作が完了しました。",
    ),
    "ko": (
        "시도 횟수가 너무 많습니다. 잠시 후 다시 시도하세요.",
        "원격 초기 설정에는 운영자가 구성한 강력한 SETUP_TOKEN이 필요합니다.",
        "이 값은 실행 환경에서 관리되므로 콘솔에서 변경할 수 없습니다.",
        "선택한 데이터가 지원되는 크기 또는 개수 제한을 초과했습니다.",
        "제출한 값 중 하나 이상이 올바르지 않습니다. 필드 요구 사항을 확인한 후 다시 시도하세요.",
        "선택한 공급자 또는 자격 증명 유형에서는 이 작업을 지원하지 않습니다.",
        "같거나 더 최신인 항목이 이미 있어 건너뛰었습니다.",
        "계속하기 전에 필요한 정보를 선택하거나 입력하세요.",
        "요청한 정보가 없거나 현재 사용할 수 없습니다.",
        "작업을 완료하지 못했습니다. 자격 증명과 공급자 설정을 확인한 후 다시 시도하세요.",
        "작업을 완료했습니다.",
    ),
    "pt": (
        "Foram feitas muitas tentativas. Aguarde um momento antes de tentar novamente.",
        "A configuração inicial remota exige um SETUP_TOKEN forte configurado pelo operador.",
        "Este valor é gerenciado pelo ambiente de execução e não pode ser alterado pela console.",
        "Os dados selecionados excedem o limite de tamanho ou quantidade permitido.",
        "Um ou mais valores enviados são inválidos. Confira os requisitos dos campos e tente novamente.",
        "Esta operação não é compatível com o provedor ou o tipo de credencial selecionado.",
        "O item foi ignorado porque já existe uma entrada equivalente ou mais recente.",
        "Selecione ou informe os dados obrigatórios antes de continuar.",
        "As informações solicitadas estão ausentes ou indisponíveis no momento.",
        "Não foi possível concluir a operação. Confira a credencial e a configuração do provedor e tente novamente.",
        "Operação concluída.",
    ),
    "ru": (
        "Слишком много попыток. Подождите немного и повторите действие.",
        "Для удалённой первоначальной настройки требуется надёжный SETUP_TOKEN, заданный оператором.",
        "Это значение управляется средой выполнения и не может быть изменено в консоли.",
        "Выбранные данные превышают допустимый размер или количество элементов.",
        "Одно или несколько значений недопустимы. Проверьте требования к полям и повторите попытку.",
        "Эта операция не поддерживается для выбранного провайдера или типа учётных данных.",
        "Элемент пропущен, поскольку уже существует эквивалентная или более новая запись.",
        "Перед продолжением выберите или введите необходимые сведения.",
        "Запрошенные сведения отсутствуют или временно недоступны.",
        "Не удалось завершить операцию. Проверьте учётные данные и настройки провайдера, затем повторите попытку.",
        "Операция успешно завершена.",
    ),
    "th": (
        "มีการลองหลายครั้งเกินไป โปรดรอสักครู่แล้วลองใหม่",
        "การตั้งค่าเริ่มต้นจากระยะไกลต้องใช้ SETUP_TOKEN ที่รัดกุมซึ่งผู้ดูแลกำหนดไว้",
        "ค่านี้จัดการโดยสภาพแวดล้อมรันไทม์และไม่สามารถเปลี่ยนจากคอนโซลได้",
        "ข้อมูลที่เลือกมีขนาดหรือจำนวนเกินขีดจำกัดที่รองรับ",
        "ค่าที่ส่งมาอย่างน้อยหนึ่งรายการไม่ถูกต้อง โปรดตรวจสอบข้อกำหนดของช่องแล้วลองใหม่",
        "ผู้ให้บริการหรือประเภทข้อมูลรับรองที่เลือกไม่รองรับการทำงานนี้",
        "ข้ามรายการนี้เนื่องจากมีรายการที่เหมือนกันหรือใหม่กว่าอยู่แล้ว",
        "โปรดเลือกหรือป้อนข้อมูลที่จำเป็นก่อนดำเนินการต่อ",
        "ข้อมูลที่ขอไม่มีอยู่หรือยังไม่พร้อมใช้งาน",
        "ไม่สามารถดำเนินการให้เสร็จได้ โปรดตรวจสอบข้อมูลรับรองและการตั้งค่าผู้ให้บริการแล้วลองใหม่",
        "ดำเนินการเสร็จเรียบร้อยแล้ว",
    ),
    "tr": (
        "Çok fazla deneme yapıldı. Yeniden denemeden önce kısa bir süre bekleyin.",
        "Uzaktan ilk kurulum, operatörün yapılandırdığı güçlü bir SETUP_TOKEN gerektirir.",
        "Bu değer çalışma ortamı tarafından yönetilir ve konsoldan değiştirilemez.",
        "Seçilen veri, desteklenen boyut veya adet sınırını aşıyor.",
        "Gönderilen değerlerden biri veya birkaçı geçersiz. Alan gereksinimlerini gözden geçirip yeniden deneyin.",
        "Bu işlem seçilen sağlayıcı veya kimlik bilgisi türü için desteklenmiyor.",
        "Aynı veya daha yeni bir kayıt bulunduğu için öğe atlandı.",
        "Devam etmeden önce gerekli bilgileri seçin veya girin.",
        "İstenen bilgiler eksik veya şu anda kullanılamıyor.",
        "İşlem tamamlanamadı. Kimlik bilgisini ve sağlayıcı ayarlarını kontrol edip yeniden deneyin.",
        "İşlem başarıyla tamamlandı.",
    ),
    "vi": (
        "Bạn đã thử quá nhiều lần. Hãy chờ một lúc rồi thử lại.",
        "Thiết lập ban đầu từ xa yêu cầu SETUP_TOKEN đủ mạnh do người vận hành cấu hình.",
        "Giá trị này do môi trường chạy quản lý nên không thể thay đổi trên bảng điều khiển.",
        "Dữ liệu đã chọn vượt quá giới hạn về kích thước hoặc số lượng được hỗ trợ.",
        "Một hoặc nhiều giá trị không hợp lệ. Hãy kiểm tra yêu cầu của từng trường rồi thử lại.",
        "Nhà cung cấp hoặc loại thông tin xác thực đã chọn không hỗ trợ thao tác này.",
        "Mục này đã được bỏ qua vì đã có một bản tương đương hoặc mới hơn.",
        "Hãy chọn hoặc nhập đầy đủ thông tin bắt buộc trước khi tiếp tục.",
        "Thông tin được yêu cầu đang thiếu hoặc hiện không khả dụng.",
        "Không thể hoàn tất thao tác. Hãy kiểm tra thông tin xác thực và cấu hình nhà cung cấp rồi thử lại.",
        "Đã hoàn tất thao tác.",
    ),
}

for _locale, _messages in _PANEL_FAMILY_ROWS.items():
    if len(_messages) != len(_PANEL_FAMILY_KEYS):
        raise RuntimeError(f"Invalid panel message family catalog for {_locale}.")
    for _key, _message in zip(_PANEL_FAMILY_KEYS, _messages):
        MESSAGES.setdefault(_key, {})[_locale] = _message

_SECURITY_BOUNDARY_KEYS = (
    "security.authentication_required",
    "security.setup_required_for_recovery",
    "security.loopback_recovery_required",
    "security.management_permission_denied",
)

_SECURITY_BOUNDARY_ROWS = {
    "en": (
        "Authentication required.",
        "Initial setup is required before recovery.",
        "Local-owner recovery is restricted to direct loopback access.",
        "Management permission denied.",
    ),
    "zh-CN": (
        "需要身份验证。",
        "恢复前必须完成初始设置。",
        "本地所有者恢复仅限直接回环访问。",
        "管理权限不足。",
    ),
    "zh-TW": (
        "需要驗證身分。",
        "復原前必須完成初始設定。",
        "本機擁有者復原僅限直接回送存取。",
        "管理權限不足。",
    ),
    "de": (
        "Authentifizierung erforderlich.",
        "Vor der Wiederherstellung muss die Ersteinrichtung abgeschlossen sein.",
        "Die Wiederherstellung des lokalen Besitzers ist auf direkten Loopback-Zugriff beschränkt.",
        "Die Verwaltungsberechtigung wurde verweigert.",
    ),
    "es": (
        "Se requiere autenticación.",
        "Debes completar la configuración inicial antes de la recuperación.",
        "La recuperación del propietario local se limita al acceso directo de bucle local.",
        "Permiso de administración denegado.",
    ),
    "fr": (
        "Authentification requise.",
        "La configuration initiale est requise avant la récupération.",
        "La récupération du propriétaire local est limitée à un accès direct en boucle locale.",
        "Autorisation de gestion refusée.",
    ),
    "id": (
        "Autentikasi diperlukan.",
        "Penyiapan awal harus diselesaikan sebelum pemulihan.",
        "Pemulihan pemilik lokal dibatasi untuk akses loopback langsung.",
        "Izin pengelolaan ditolak.",
    ),
    "it": (
        "Autenticazione richiesta.",
        "Prima del ripristino è necessario completare la configurazione iniziale.",
        "Il ripristino del proprietario locale è limitato all’accesso loopback diretto.",
        "Autorizzazione di gestione negata.",
    ),
    "ja": (
        "認証が必要です。",
        "復旧の前に初期設定を完了する必要があります。",
        "ローカル所有者の復旧は直接のループバックアクセスに限定されます。",
        "管理権限がありません。",
    ),
    "ko": (
        "인증이 필요합니다.",
        "복구하기 전에 초기 설정을 완료해야 합니다.",
        "로컬 소유자 복구는 직접 루프백 접근으로 제한됩니다.",
        "관리 권한이 거부되었습니다.",
    ),
    "pt": (
        "Autenticação obrigatória.",
        "A configuração inicial deve ser concluída antes da recuperação.",
        "A recuperação do proprietário local está restrita ao acesso loopback direto.",
        "Permissão de gerenciamento negada.",
    ),
    "ru": (
        "Требуется аутентификация.",
        "Перед восстановлением необходимо завершить первоначальную настройку.",
        "Восстановление локального владельца доступно только через прямое loopback-подключение.",
        "Нет разрешения на управление.",
    ),
    "th": (
        "ต้องยืนยันตัวตน",
        "ต้องตั้งค่าเริ่มต้นให้เสร็จก่อนการกู้คืน",
        "การกู้คืนเจ้าของภายในเครื่องจำกัดเฉพาะการเข้าถึงลูปแบ็กโดยตรง",
        "ไม่ได้รับอนุญาตให้จัดการ",
    ),
    "tr": (
        "Kimlik doğrulaması gerekli.",
        "Kurtarma işleminden önce ilk kurulum tamamlanmalıdır.",
        "Yerel sahip kurtarma işlemi yalnızca doğrudan geri döngü erişimiyle yapılabilir.",
        "Yönetim izni reddedildi.",
    ),
    "vi": (
        "Cần xác thực.",
        "Bạn phải hoàn tất thiết lập ban đầu trước khi khôi phục.",
        "Chỉ có thể khôi phục chủ sở hữu cục bộ qua kết nối loopback trực tiếp.",
        "Bạn không có quyền quản trị để thực hiện thao tác này.",
    ),
}

for _locale, _messages in _SECURITY_BOUNDARY_ROWS.items():
    if len(_messages) != len(_SECURITY_BOUNDARY_KEYS):
        raise RuntimeError(f"Invalid security boundary catalog for {_locale}.")
    for _key, _message in zip(_SECURITY_BOUNDARY_KEYS, _messages):
        MESSAGES.setdefault(_key, {})[_locale] = _message

_PANEL_MESSAGE_PATTERNS = (
    (
        re.compile(r"Credential belongs to a different provider\.$"),
        "provider.ext.wrong_import_provider",
    ),
    (
        re.compile(r"Import an API key credential for this provider\.$"),
        "provider.ext.import_api_key",
    ),
    (re.compile(r"too many .*attempts", re.IGNORECASE), "panel.rate_limited"),
    (re.compile(r"setup[\s_-]*token", re.IGNORECASE), "panel.setup_token_required"),
    (
        re.compile(r"managed by .*(?:environment|environment variable)", re.IGNORECASE),
        "panel.managed_value",
    ),
    (
        re.compile(
            r"(?:exceeds|up to \d+ files|between one and \d+ import files|limit must be|fewer)",
            re.IGNORECASE,
        ),
        "panel.size_limit",
    ),
    (
        re.compile(
            r"(?:must be|must identify|must be updated|cannot be empty|invalid(?:\s|\.)|incorrect|must be a valid|must be an integer|must be between|conflict|already exists|already uses)",
            re.IGNORECASE,
        ),
        "panel.invalid_value",
    ),
    (
        re.compile(
            r"(?:not supported|only available|can only be|cannot be edited|only .* are editable|does not expose|does not support)",
            re.IGNORECASE,
        ),
        "panel.unsupported_operation",
    ),
    (re.compile(r"(?:duplicate|skipped because)", re.IGNORECASE), "panel.duplicate_skipped"),
    (
        re.compile(
            r"^(?:select|enter|provide|refresh|run a fresh|an idempotency|no files selected)",
            re.IGNORECASE,
        ),
        "panel.selection_required",
    ),
    (
        re.compile(
            r"(?:does not exist|not found|no .* (?:were found|are (?:currently )?available|currently match)|not available|does not contain|unavailable)",
            re.IGNORECASE,
        ),
        "panel.resource_unavailable",
    ),
    (
        re.compile(r"(?:failed|unable|could not|was not deleted|rejected)", re.IGNORECASE),
        "panel.operation_failed",
    ),
    (
        re.compile(
            r"(?:saved|reset to defaults|verified|enabled|disabled|configured|retrieved|updated|complete|imported)",
            re.IGNORECASE,
        ),
        "panel.operation_complete",
    ),
)

MESSAGES.update(PROVIDER_EXPANSION_MESSAGES)
MESSAGES.update(META_PROVIDER_MESSAGES)

ENGLISH_TEXT_KEYS = {
    translations[DEFAULT_LOCALE]: key
    for key, translations in MESSAGES.items()
    if DEFAULT_LOCALE in translations
}


def _normalize_locale(candidate: str) -> str | None:
    normalized = candidate.strip().replace("_", "-").lower()
    if not normalized:
        return None
    if normalized.startswith("zh"):
        if any(marker in normalized for marker in ("-tw", "-hk", "-mo", "-hant")):
            return "zh-TW"
        return "zh-CN"
    language = normalized.split("-", 1)[0]
    return language if language in SUPPORTED_LOCALES else None


def resolve_locale(accept_language: str | None) -> str:
    """Select the best supported locale from an Accept-Language header."""
    weighted: list[tuple[float, int, str]] = []
    for position, raw_part in enumerate((accept_language or "").split(",")):
        part, *parameters = raw_part.strip().split(";")
        quality = 1.0
        for parameter in parameters:
            name, separator, value = parameter.strip().partition("=")
            if separator and name.lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        locale = _normalize_locale(part)
        if locale and quality > 0:
            weighted.append((quality, -position, locale))
    return max(weighted, default=(0.0, 0, DEFAULT_LOCALE))[2]


def get_locale() -> str:
    return _current_locale.get()


def localization_is_enabled() -> bool:
    return _localization_enabled.get()


@contextmanager
def locale_context(locale: str, *, enabled: bool = True) -> Iterator[None]:
    normalized = _normalize_locale(locale) or DEFAULT_LOCALE
    state = _LocaleState(
        locale_token=_current_locale.set(normalized),
        enabled_token=_localization_enabled.set(enabled),
    )
    try:
        yield
    finally:
        _localization_enabled.reset(state.enabled_token)
        _current_locale.reset(state.locale_token)


def translate(key: str, **values: Any) -> str:
    translations = MESSAGES.get(key, {})
    template = translations.get(get_locale()) or translations.get(DEFAULT_LOCALE) or key
    try:
        return template.format_map(values)
    except (KeyError, ValueError):
        return template


def panel_message_key(value: str) -> str | None:
    """Return the curated semantic family for a console-generated message."""
    exact_key = ENGLISH_TEXT_KEYS.get(value)
    if exact_key:
        return exact_key
    if value in META_SOURCE_KEYS:
        return META_SOURCE_KEYS[value]
    for pattern, key in _PANEL_MESSAGE_PATTERNS:
        if pattern.search(value):
            return key
    return None


def can_localize_text(value: str) -> bool:
    return panel_message_key(value) is not None


def translate_text(value: str) -> str:
    if not localization_is_enabled():
        return value
    key = panel_message_key(value)
    if get_locale() == DEFAULT_LOCALE and value not in ENGLISH_TEXT_KEYS:
        return value
    return translate(key) if key else value


def translate_payload(value: Any, *, message_context: bool = False) -> Any:
    """Localize known user-facing strings while preserving API field names and identifiers."""
    if not localization_is_enabled():
        return value
    if isinstance(value, str):
        return translate_text(value) if message_context else value
    if isinstance(value, list):
        return [translate_payload(item, message_context=message_context) for item in value]
    if isinstance(value, tuple):
        return tuple(translate_payload(item, message_context=message_context) for item in value)
    if isinstance(value, dict):
        message_keys = {"detail", "error", "message", "title", "restart_notice"}
        return {
            key: translate_payload(item, message_context=key in message_keys)
            for key, item in value.items()
        }
    return value
