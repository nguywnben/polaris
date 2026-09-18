// Reviewed contextual backup copy. Every supported locale supplies every key.
const BACKUP_KEYS = [
    'title', 'description', 'create', 'passphrase', 'placeholder', 'confirm_passphrase',
    'confirm_placeholder', 'import', 'archive', 'policy', 'abort', 'replace', 'validate',
    'restore', 'confirm_restore', 'sanitized', 'sanitized_hint', 'loading', 'denied',
    'permissions_failed', 'passphrase_invalid', 'passphrase_mismatch', 'file_invalid',
    'unsupported', 'conflict', 'archive_invalid', 'failed', 'restore_unknown',
    'validating', 'plan_ready', 'plan_records', 'restoring', 'restored', 'downloading',
    'downloaded', 'coverage', 'import_placeholder'
].map(key => `backup.${key}`);
const BACKUP_LOCALE_VALUES = {
    en: [
        'Backup and restore', 'Encrypted system backups support SQLite only. Keep the archive and its passphrase safe; both are needed to restore.',
        'Download encrypted backup', 'Backup passphrase', 'Enter 12–256 characters', 'Confirm passphrase', 'Enter the same passphrase again',
        'Validate and restore', 'Encrypted archive (.ogb, up to 64 MiB)', 'Existing data', 'Abort if this instance contains data', 'Replace existing data',
        'Validate archive', 'Restore backup', 'Restore the validated archive? This can replace current configuration, credentials, identities, and usage records. Save a current backup first. You will need to sign in again.',
        'Download sanitized export', 'The sanitized export is for inspection and cannot be restored.', 'Checking backup permissions…', 'You do not have permission to use backups.',
        'Could not check backup permissions. Reopen Settings to try again.', 'Use a passphrase of 12–256 characters.', 'The passphrases must match.', 'Choose a nonempty encrypted archive no larger than 64 MiB.',
        'Backup and restore are unavailable with this storage backend. Only SQLite is supported.', 'This instance already contains data. Review the replacement policy before validating again.',
        'The archive, passphrase, or compatibility metadata is invalid. Check the file and passphrase.', 'The backup request failed. Check your connection and access before trying again.',
        'The restore outcome could not be confirmed. Do not retry automatically. Check the instance and sign in again before deciding what to do.',
        'Validating without changing data…', 'Validation passed. No data has been changed. Review the plan before restoring.', 'Records in the validated archive: {count}',
        'Restoring data. Keep this page open…', 'Restore completed. Sign in again to continue.', 'Preparing download…', 'Download started. Check your browser downloads.',
        'Includes configuration, credentials, identities, routes, keys, usage ledgers, audit, and traces. Excludes raw logs, legacy usage statistics, and earlier restore snapshots.', 'Enter the passphrase used to encrypt this archive'
    ],
    vi: [
        'Sao lưu và khôi phục', 'Sao lưu hệ thống có mã hóa chỉ hỗ trợ SQLite. Hãy giữ an toàn tệp sao lưu và mật khẩu; cần cả hai để khôi phục.',
        'Tải bản sao lưu mã hóa', 'Mật khẩu bản sao lưu', 'Nhập từ 12 đến 256 ký tự', 'Xác nhận mật khẩu', 'Nhập lại đúng mật khẩu',
        'Kiểm tra và khôi phục', 'Tệp mã hóa (.ogb, tối đa 64 MiB)', 'Dữ liệu hiện có', 'Dừng nếu máy chủ đã có dữ liệu', 'Thay thế dữ liệu hiện có',
        'Kiểm tra bản sao lưu', 'Khôi phục bản sao lưu', 'Khôi phục bản sao lưu đã kiểm tra? Thao tác có thể thay thế cấu hình, thông tin xác thực, danh tính và dữ liệu sử dụng hiện tại. Hãy sao lưu dữ liệu hiện tại trước. Bạn sẽ cần đăng nhập lại.',
        'Tải bản xuất đã loại dữ liệu nhạy cảm', 'Bản xuất đã loại dữ liệu nhạy cảm chỉ dùng để kiểm tra, không thể khôi phục.', 'Đang kiểm tra quyền sao lưu…', 'Bạn không có quyền sử dụng chức năng sao lưu.',
        'Không thể kiểm tra quyền sao lưu. Mở lại Cài đặt để thử lại.', 'Dùng mật khẩu dài từ 12 đến 256 ký tự.', 'Hai mật khẩu phải trùng nhau.', 'Chọn tệp sao lưu mã hóa không rỗng, tối đa 64 MiB.',
        'Hệ lưu trữ này không hỗ trợ sao lưu và khôi phục. Chỉ SQLite được hỗ trợ.', 'Máy chủ đã có dữ liệu. Xem lại chính sách thay thế trước khi kiểm tra lại.',
        'Tệp sao lưu, mật khẩu hoặc thông tin tương thích không hợp lệ. Kiểm tra lại tệp và mật khẩu.', 'Yêu cầu sao lưu thất bại. Kiểm tra kết nối và quyền truy cập trước khi thử lại.',
        'Chưa xác nhận được kết quả khôi phục. Không tự động thử lại. Kiểm tra máy chủ và đăng nhập lại trước khi quyết định bước tiếp theo.',
        'Đang kiểm tra, không thay đổi dữ liệu…', 'Kiểm tra thành công. Chưa thay đổi dữ liệu. Xem kế hoạch trước khi khôi phục.', 'Số bản ghi trong tệp đã kiểm tra: {count}',
        'Đang khôi phục dữ liệu. Giữ trang này mở…', 'Đã khôi phục. Đăng nhập lại để tiếp tục.', 'Đang chuẩn bị tải xuống…', 'Đã bắt đầu tải. Kiểm tra danh sách tải xuống của trình duyệt.',
        'Bao gồm cấu hình, thông tin xác thực, danh tính, tuyến, khóa, sổ sử dụng, kiểm toán và dấu vết. Không gồm nhật ký thô, thống kê sử dụng cũ và ảnh chụp trước các lần khôi phục.', 'Nhập mật khẩu đã dùng để mã hóa tệp này'
    ],
    'zh-CN': [
        '备份与恢复', '加密系统备份仅支持 SQLite。请妥善保存备份文件和口令，恢复时两者缺一不可。',
        '下载加密备份', '备份口令', '输入 12–256 个字符', '确认口令', '再次输入相同的口令', '验证与恢复', '加密文件（.ogb，最大 64 MiB）', '现有数据', '实例已有数据时中止', '替换现有数据',
        '验证备份文件', '恢复备份', '恢复已验证的备份？这可能替换当前配置、凭据、身份和用量记录。请先备份当前数据。之后需要重新登录。',
        '下载脱敏导出', '脱敏导出仅供检查，不能用于恢复。', '正在检查备份权限…', '您没有使用备份功能的权限。', '无法检查备份权限。请重新打开设置后重试。',
        '口令长度必须为 12–256 个字符。', '两次输入的口令必须相同。', '请选择不为空且不超过 64 MiB 的加密备份文件。', '此存储后端不支持备份与恢复，仅支持 SQLite。', '此实例已有数据。请先检查替换策略，再次验证。',
        '备份文件、口令或兼容性信息无效。请检查文件和口令。', '备份请求失败。请检查连接和访问权限后重试。', '无法确认恢复结果。请勿自动重试。请检查实例并重新登录，再决定下一步。',
        '正在验证，不会修改数据…', '验证通过，尚未修改数据。请在恢复前检查计划。', '已验证备份中的记录数：{count}', '正在恢复数据，请保持页面打开…', '恢复完成，请重新登录后继续。', '正在准备下载…', '下载已开始，请查看浏览器的下载列表。',
        '包含配置、凭据、身份、路由、密钥、用量账本、审计和跟踪。不包含原始日志、旧用量统计和此前的恢复快照。', '输入加密此文件时使用的口令'
    ],
    'zh-TW': [
        '備份與還原', '加密系統備份僅支援 SQLite。請妥善保存備份檔案和密碼，還原時兩者缺一不可。',
        '下載加密備份', '備份密碼', '輸入 12–256 個字元', '確認密碼', '再次輸入相同的密碼', '驗證與還原', '加密檔案（.ogb，最大 64 MiB）', '現有資料', '執行個體已有資料時中止', '取代現有資料',
        '驗證備份檔案', '還原備份', '還原已驗證的備份？這可能取代目前的設定、憑證、身分和用量紀錄。請先備份目前的資料。之後需要重新登入。',
        '下載去識別化匯出', '移除敏感資料的匯出僅供檢查，無法用於還原。', '正在檢查備份權限…', '您沒有使用備份功能的權限。', '無法檢查備份權限。請重新開啟設定後再試。',
        '密碼長度必須為 12–256 個字元。', '兩次輸入的密碼必須相同。', '請選擇非空且不超過 64 MiB 的加密備份檔案。', '此儲存後端不支援備份與還原，僅支援 SQLite。', '此執行個體已有資料。請先檢查取代原則，再次驗證。',
        '備份檔案、密碼或相容性資訊無效。請檢查檔案和密碼。', '備份要求失敗。請檢查連線和存取權限後再試。', '無法確認還原結果。請勿自動重試。請檢查執行個體並重新登入，再決定下一步。',
        '正在驗證，不會變更資料…', '驗證通過，尚未變更資料。請在還原前檢查計畫。', '已驗證備份中的紀錄數：{count}', '正在還原資料，請保持頁面開啟…', '還原完成，請重新登入後繼續。', '正在準備下載…', '下載已開始，請查看瀏覽器的下載清單。',
        '包含設定、憑證、身分、路由、金鑰、用量帳本、稽核和追蹤。不包含原始日誌、舊用量統計和先前的還原快照。', '輸入加密此檔案時使用的密碼'
    ],
    de: [
        'Sichern und wiederherstellen', 'Verschlüsselte Systemsicherungen unterstützen nur SQLite. Archiv und Passphrase sicher aufbewahren; zur Wiederherstellung werden beide benötigt.',
        'Verschlüsselte Sicherung herunterladen', 'Passphrase der Sicherung', '12–256 Zeichen eingeben', 'Passphrase bestätigen', 'Dieselbe Passphrase erneut eingeben', 'Prüfen und wiederherstellen', 'Verschlüsseltes Archiv (.ogb, bis 64 MiB)', 'Vorhandene Daten', 'Bei vorhandenen Daten abbrechen', 'Vorhandene Daten ersetzen',
        'Archiv prüfen', 'Sicherung wiederherstellen', 'Das geprüfte Archiv wiederherstellen? Dabei können Konfiguration, Zugangsdaten, Identitäten und Nutzungsdaten ersetzt werden. Sichern Sie zuerst den aktuellen Stand. Danach ist eine erneute Anmeldung erforderlich.',
        'Bereinigten Export herunterladen', 'Der bereinigte Export dient zur Prüfung und kann nicht wiederhergestellt werden.', 'Sicherungsberechtigungen werden geprüft…', 'Sie haben keine Berechtigung für Sicherungen.', 'Berechtigungen konnten nicht geprüft werden. Öffnen Sie die Einstellungen erneut.',
        'Verwenden Sie eine Passphrase mit 12–256 Zeichen.', 'Die Passphrasen müssen übereinstimmen.', 'Wählen Sie ein nicht leeres verschlüsseltes Archiv mit höchstens 64 MiB.', 'Dieses Speicherbackend unterstützt keine Sicherung und Wiederherstellung. Nur SQLite wird unterstützt.', 'Diese Instanz enthält bereits Daten. Prüfen Sie vor der erneuten Validierung die Ersetzungsrichtlinie.',
        'Archiv, Passphrase oder Kompatibilitätsdaten sind ungültig. Prüfen Sie Datei und Passphrase.', 'Sicherungsanfrage fehlgeschlagen. Prüfen Sie Verbindung und Zugriffsrechte vor einem neuen Versuch.', 'Das Ergebnis der Wiederherstellung ist unbestätigt. Nicht automatisch wiederholen. Prüfen Sie die Instanz und melden Sie sich erneut an, bevor Sie fortfahren.',
        'Prüfung ohne Datenänderung läuft…', 'Prüfung erfolgreich. Keine Daten wurden geändert. Prüfen Sie den Plan vor der Wiederherstellung.', 'Datensätze im geprüften Archiv: {count}', 'Daten werden wiederhergestellt. Lassen Sie diese Seite geöffnet…', 'Wiederherstellung abgeschlossen. Melden Sie sich erneut an.', 'Download wird vorbereitet…', 'Download gestartet. Prüfen Sie die Downloads Ihres Browsers.',
        'Enthält Konfiguration, Zugangsdaten, Identitäten, Routen, Schlüssel, Nutzungsbücher, Audit und Traces. Rohprotokolle, alte Nutzungsstatistiken und frühere Wiederherstellungssnapshots sind ausgeschlossen.', 'Passphrase eingeben, mit der dieses Archiv verschlüsselt wurde'
    ],
    es: [
        'Copia de seguridad y restauración', 'Las copias cifradas del sistema solo admiten SQLite. Guarda el archivo y su frase de contraseña de forma segura; necesitas ambos para restaurar.',
        'Descargar copia cifrada', 'Frase de contraseña de la copia', 'Introduce entre 12 y 256 caracteres', 'Confirmar frase de contraseña', 'Vuelve a introducir la misma frase', 'Validar y restaurar', 'Archivo cifrado (.ogb, hasta 64 MiB)', 'Datos existentes', 'Cancelar si la instancia contiene datos', 'Reemplazar datos existentes',
        'Validar archivo', 'Restaurar copia', '¿Restaurar el archivo validado? Puede reemplazar la configuración, credenciales, identidades y registros de uso actuales. Crea primero una copia del estado actual. Tendrás que iniciar sesión de nuevo.',
        'Descargar exportación sin datos sensibles', 'La exportación sin datos sensibles sirve para inspección y no se puede restaurar.', 'Comprobando permisos de copia…', 'No tienes permiso para usar copias de seguridad.', 'No se pudieron comprobar los permisos. Vuelve a abrir Configuración.',
        'Usa una frase de contraseña de entre 12 y 256 caracteres.', 'Las frases de contraseña deben coincidir.', 'Elige un archivo cifrado no vacío de hasta 64 MiB.', 'Este almacenamiento no admite copias ni restauración. Solo se admite SQLite.', 'Esta instancia ya contiene datos. Revisa la política de reemplazo antes de validar de nuevo.',
        'El archivo, la frase de contraseña o los metadatos de compatibilidad no son válidos. Comprueba el archivo y la frase.', 'La solicitud de copia falló. Comprueba la conexión y el acceso antes de reintentar.', 'No se pudo confirmar el resultado de la restauración. No reintentes automáticamente. Comprueba la instancia e inicia sesión de nuevo antes de decidir cómo continuar.',
        'Validando sin modificar datos…', 'Validación correcta. No se han modificado datos. Revisa el plan antes de restaurar.', 'Registros del archivo validado: {count}', 'Restaurando datos. Mantén esta página abierta…', 'Restauración completada. Inicia sesión de nuevo.', 'Preparando descarga…', 'Descarga iniciada. Comprueba las descargas del navegador.',
        'Incluye configuración, credenciales, identidades, rutas, claves, registros de uso, auditoría y trazas. Excluye registros sin procesar, estadísticas antiguas y capturas de restauraciones anteriores.', 'Introduce la frase usada para cifrar este archivo'
    ],
    fr: [
        'Sauvegarde et restauration', 'Les sauvegardes système chiffrées prennent uniquement en charge SQLite. Conservez l’archive et sa phrase secrète en lieu sûr ; les deux sont nécessaires pour restaurer.',
        'Télécharger la sauvegarde chiffrée', 'Phrase secrète de la sauvegarde', 'Saisissez 12 à 256 caractères', 'Confirmer la phrase secrète', 'Saisissez à nouveau la même phrase', 'Valider et restaurer', 'Archive chiffrée (.ogb, 64 MiB maximum)', 'Données existantes', 'Abandonner si l’instance contient des données', 'Remplacer les données existantes',
        'Valider l’archive', 'Restaurer la sauvegarde', 'Restaurer l’archive validée ? La configuration, les identifiants, les identités et les données d’utilisation actuels peuvent être remplacés. Sauvegardez d’abord l’état actuel. Vous devrez vous reconnecter.',
        'Télécharger l’export sans données sensibles', 'L’export sans données sensibles sert à l’inspection et ne peut pas être restauré.', 'Vérification des droits de sauvegarde…', 'Vous n’avez pas le droit d’utiliser les sauvegardes.', 'Impossible de vérifier les droits. Rouvrez les paramètres pour réessayer.',
        'Utilisez une phrase secrète de 12 à 256 caractères.', 'Les phrases secrètes doivent être identiques.', 'Choisissez une archive chiffrée non vide de 64 MiB maximum.', 'Ce stockage ne permet pas la sauvegarde et la restauration. Seul SQLite est pris en charge.', 'Cette instance contient déjà des données. Vérifiez la règle de remplacement avant de valider à nouveau.',
        'L’archive, la phrase secrète ou les métadonnées de compatibilité sont invalides. Vérifiez le fichier et la phrase.', 'La demande de sauvegarde a échoué. Vérifiez la connexion et les droits avant de réessayer.', 'Le résultat de la restauration n’a pas pu être confirmé. Ne relancez pas automatiquement. Vérifiez l’instance et reconnectez-vous avant de décider de la suite.',
        'Validation sans modification des données…', 'Validation réussie. Aucune donnée modifiée. Vérifiez le plan avant de restaurer.', 'Enregistrements dans l’archive validée : {count}', 'Restauration en cours. Gardez cette page ouverte…', 'Restauration terminée. Reconnectez-vous pour continuer.', 'Préparation du téléchargement…', 'Téléchargement lancé. Consultez les téléchargements du navigateur.',
        'Inclut configuration, identifiants, identités, routes, clés, registres d’utilisation, audit et traces. Exclut journaux bruts, anciennes statistiques et instantanés de restaurations antérieures.', 'Saisissez la phrase utilisée pour chiffrer cette archive'
    ],
    id: [
        'Pencadangan dan pemulihan', 'Cadangan sistem terenkripsi hanya mendukung SQLite. Simpan arsip dan frasa sandinya dengan aman; keduanya diperlukan untuk pemulihan.',
        'Unduh cadangan terenkripsi', 'Frasa sandi cadangan', 'Masukkan 12–256 karakter', 'Konfirmasi frasa sandi', 'Masukkan frasa sandi yang sama lagi', 'Validasi dan pulihkan', 'Arsip terenkripsi (.ogb, hingga 64 MiB)', 'Data yang ada', 'Batalkan jika instans berisi data', 'Ganti data yang ada',
        'Validasi arsip', 'Pulihkan cadangan', 'Pulihkan arsip yang telah divalidasi? Konfigurasi, kredensial, identitas, dan catatan penggunaan saat ini dapat diganti. Cadangkan keadaan saat ini terlebih dahulu. Anda perlu masuk kembali.',
        'Unduh ekspor tanpa data sensitif', 'Ekspor tanpa data sensitif hanya untuk pemeriksaan dan tidak dapat dipulihkan.', 'Memeriksa izin pencadangan…', 'Anda tidak memiliki izin menggunakan cadangan.', 'Izin pencadangan tidak dapat diperiksa. Buka ulang Pengaturan untuk mencoba lagi.',
        'Gunakan frasa sandi sepanjang 12–256 karakter.', 'Kedua frasa sandi harus sama.', 'Pilih arsip terenkripsi yang tidak kosong dan tidak lebih dari 64 MiB.', 'Penyimpanan ini tidak mendukung pencadangan dan pemulihan. Hanya SQLite yang didukung.', 'Instans ini sudah berisi data. Tinjau kebijakan penggantian sebelum memvalidasi lagi.',
        'Arsip, frasa sandi, atau metadata kompatibilitas tidak valid. Periksa berkas dan frasa sandi.', 'Permintaan pencadangan gagal. Periksa koneksi dan akses sebelum mencoba lagi.', 'Hasil pemulihan tidak dapat dipastikan. Jangan mencoba ulang otomatis. Periksa instans dan masuk kembali sebelum menentukan langkah selanjutnya.',
        'Memvalidasi tanpa mengubah data…', 'Validasi berhasil. Data belum berubah. Tinjau rencana sebelum memulihkan.', 'Catatan dalam arsip tervalidasi: {count}', 'Memulihkan data. Biarkan halaman ini terbuka…', 'Pemulihan selesai. Masuk kembali untuk melanjutkan.', 'Menyiapkan unduhan…', 'Unduhan dimulai. Periksa unduhan peramban Anda.',
        'Mencakup konfigurasi, kredensial, identitas, rute, kunci, buku penggunaan, audit, dan jejak. Tidak mencakup log mentah, statistik lama, dan snapshot pemulihan sebelumnya.', 'Masukkan frasa sandi yang digunakan untuk mengenkripsi arsip ini'
    ],
    it: [
        'Backup e ripristino', 'I backup di sistema cifrati supportano solo SQLite. Conserva al sicuro archivio e passphrase: servono entrambi per il ripristino.',
        'Scarica backup cifrato', 'Passphrase del backup', 'Inserisci da 12 a 256 caratteri', 'Conferma passphrase', 'Inserisci di nuovo la stessa passphrase', 'Convalida e ripristina', 'Archivio cifrato (.ogb, fino a 64 MiB)', 'Dati esistenti', 'Interrompi se l’istanza contiene dati', 'Sostituisci i dati esistenti',
        'Convalida archivio', 'Ripristina backup', 'Ripristinare l’archivio convalidato? Configurazione, credenziali, identità e registri di utilizzo attuali possono essere sostituiti. Esegui prima un backup dello stato attuale. Dovrai accedere nuovamente.',
        'Scarica esportazione senza dati sensibili', 'L’esportazione senza dati sensibili serve per l’ispezione e non può essere ripristinata.', 'Verifica dei permessi di backup…', 'Non hai il permesso di usare i backup.', 'Impossibile verificare i permessi. Riapri le impostazioni per riprovare.',
        'Usa una passphrase da 12 a 256 caratteri.', 'Le passphrase devono coincidere.', 'Scegli un archivio cifrato non vuoto di massimo 64 MiB.', 'Questo sistema di archiviazione non supporta backup e ripristino. È supportato solo SQLite.', 'Questa istanza contiene già dati. Controlla la politica di sostituzione prima di convalidare di nuovo.',
        'Archivio, passphrase o metadati di compatibilità non validi. Controlla il file e la passphrase.', 'Richiesta di backup non riuscita. Controlla connessione e accesso prima di riprovare.', 'Impossibile confermare l’esito del ripristino. Non riprovare automaticamente. Controlla l’istanza e accedi nuovamente prima di decidere come procedere.',
        'Convalida senza modificare i dati…', 'Convalida riuscita. Nessun dato modificato. Controlla il piano prima del ripristino.', 'Record nell’archivio convalidato: {count}', 'Ripristino dei dati. Lascia aperta questa pagina…', 'Ripristino completato. Accedi nuovamente per continuare.', 'Preparazione del download…', 'Download avviato. Controlla i download del browser.',
        'Include configurazione, credenziali, identità, percorsi, chiavi, registri di utilizzo, audit e tracce. Esclude log grezzi, vecchie statistiche e istantanee di ripristini precedenti.', 'Inserisci la passphrase usata per cifrare questo archivio'
    ],
    ja: [
        'バックアップと復元', '暗号化システムバックアップは SQLite のみ対応です。復元にはアーカイブとパスフレーズの両方が必要なため、安全に保管してください。',
        '暗号化バックアップをダウンロード', 'バックアップのパスフレーズ', '12～256 文字を入力', 'パスフレーズの確認', '同じパスフレーズをもう一度入力', '検証と復元', '暗号化アーカイブ（.ogb、最大 64 MiB）', '既存のデータ', 'データが存在する場合は中止', '既存のデータを置換',
        'アーカイブを検証', 'バックアップを復元', '検証済みアーカイブを復元しますか？現在の設定、認証情報、ID、使用量記録が置き換わる可能性があります。先に現在のバックアップを保存してください。再ログインが必要になります。',
        '機密情報を除いたデータをダウンロード', '機密情報を除いたエクスポートは確認用で、復元には使用できません。', 'バックアップ権限を確認中…', 'バックアップを使用する権限がありません。', 'バックアップ権限を確認できませんでした。設定を開き直してください。',
        'パスフレーズは 12～256 文字にしてください。', 'パスフレーズが一致している必要があります。', '空でない、64 MiB 以下の暗号化アーカイブを選択してください。', 'このストレージではバックアップと復元を利用できません。SQLite のみ対応しています。', 'このインスタンスには既にデータがあります。置換方針を確認してから再検証してください。',
        'アーカイブ、パスフレーズ、または互換性情報が無効です。ファイルとパスフレーズを確認してください。', 'バックアップ要求に失敗しました。接続とアクセス権を確認してから再試行してください。', '復元結果を確認できませんでした。自動で再試行しないでください。インスタンスを確認し、再ログインしてから次の操作を判断してください。',
        'データを変更せずに検証中…', '検証に成功しました。データは変更されていません。復元前に計画を確認してください。', '検証済みアーカイブのレコード数：{count}', 'データを復元中です。このページを開いたままにしてください…', '復元が完了しました。再ログインしてください。', 'ダウンロードを準備中…', 'ダウンロードを開始しました。ブラウザーのダウンロード一覧を確認してください。',
        '設定、認証情報、ID、ルート、キー、使用量台帳、監査、トレースを含みます。生ログ、旧使用量統計、過去の復元スナップショットは含みません。', 'このアーカイブの暗号化に使ったパスフレーズを入力'
    ],
    ko: [
        '백업 및 복원', '암호화된 시스템 백업은 SQLite만 지원합니다. 복원에는 아카이브와 암호가 모두 필요하므로 안전하게 보관하세요.',
        '암호화된 백업 다운로드', '백업 암호', '12~256자 입력', '암호 확인', '동일한 암호를 다시 입력', '검증 및 복원', '암호화된 아카이브 (.ogb, 최대 64 MiB)', '기존 데이터', '인스턴스에 데이터가 있으면 중단', '기존 데이터 교체',
        '아카이브 검증', '백업 복원', '검증된 아카이브를 복원할까요? 현재 구성, 자격 증명, ID 및 사용량 기록이 교체될 수 있습니다. 먼저 현재 상태를 백업하세요. 다시 로그인해야 합니다.',
        '민감 정보 제거 내보내기 다운로드', '민감 정보를 제거한 내보내기는 검토용이며 복원할 수 없습니다.', '백업 권한 확인 중…', '백업을 사용할 권한이 없습니다.', '백업 권한을 확인할 수 없습니다. 설정을 다시 열어 재시도하세요.',
        '12~256자의 암호를 사용하세요.', '암호가 일치해야 합니다.', '비어 있지 않은 64 MiB 이하의 암호화된 아카이브를 선택하세요.', '이 저장소에서는 백업 및 복원을 사용할 수 없습니다. SQLite만 지원합니다.', '이 인스턴스에 이미 데이터가 있습니다. 교체 정책을 검토한 후 다시 검증하세요.',
        '아카이브, 암호 또는 호환성 정보가 올바르지 않습니다. 파일과 암호를 확인하세요.', '백업 요청이 실패했습니다. 연결과 접근 권한을 확인한 후 다시 시도하세요.', '복원 결과를 확인할 수 없습니다. 자동으로 재시도하지 마세요. 인스턴스를 확인하고 다시 로그인한 후 다음 작업을 결정하세요.',
        '데이터를 변경하지 않고 검증 중…', '검증에 성공했습니다. 데이터는 변경되지 않았습니다. 복원 전에 계획을 확인하세요.', '검증된 아카이브의 레코드 수: {count}', '데이터 복원 중입니다. 이 페이지를 열어 두세요…', '복원이 완료되었습니다. 다시 로그인하세요.', '다운로드 준비 중…', '다운로드를 시작했습니다. 브라우저 다운로드 목록을 확인하세요.',
        '구성, 자격 증명, ID, 경로, 키, 사용량 원장, 감사 및 추적을 포함합니다. 원시 로그, 이전 사용량 통계 및 과거 복원 스냅샷은 제외합니다.', '이 아카이브를 암호화할 때 사용한 암호 입력'
    ],
    pt: [
        'Backup e restauração', 'Backups de sistema criptografados só oferecem suporte ao SQLite. Guarde o arquivo e a frase secreta com segurança; ambos são necessários para restaurar.',
        'Baixar backup criptografado', 'Frase secreta do backup', 'Digite de 12 a 256 caracteres', 'Confirmar frase secreta', 'Digite a mesma frase novamente', 'Validar e restaurar', 'Arquivo criptografado (.ogb, até 64 MiB)', 'Dados existentes', 'Interromper se a instância contiver dados', 'Substituir dados existentes',
        'Validar arquivo', 'Restaurar backup', 'Restaurar o arquivo validado? Isso pode substituir configurações, credenciais, identidades e registros de uso atuais. Faça um backup do estado atual primeiro. Será necessário entrar novamente.',
        'Baixar exportação sem dados sensíveis', 'A exportação sem dados sensíveis é para inspeção e não pode ser restaurada.', 'Verificando permissões de backup…', 'Você não tem permissão para usar backups.', 'Não foi possível verificar as permissões. Abra as Configurações novamente.',
        'Use uma frase secreta de 12 a 256 caracteres.', 'As frases secretas devem ser iguais.', 'Escolha um arquivo criptografado não vazio de até 64 MiB.', 'Este armazenamento não permite backup e restauração. Apenas SQLite é compatível.', 'Esta instância já contém dados. Revise a política de substituição antes de validar novamente.',
        'O arquivo, a frase secreta ou os metadados de compatibilidade são inválidos. Verifique o arquivo e a frase.', 'A solicitação de backup falhou. Verifique a conexão e o acesso antes de tentar novamente.', 'Não foi possível confirmar o resultado da restauração. Não repita automaticamente. Verifique a instância e entre novamente antes de decidir como prosseguir.',
        'Validando sem alterar dados…', 'Validação concluída. Nenhum dado foi alterado. Revise o plano antes de restaurar.', 'Registros no arquivo validado: {count}', 'Restaurando dados. Mantenha esta página aberta…', 'Restauração concluída. Entre novamente para continuar.', 'Preparando download…', 'Download iniciado. Verifique os downloads do navegador.',
        'Inclui configurações, credenciais, identidades, rotas, chaves, registros de uso, auditoria e rastros. Exclui logs brutos, estatísticas antigas e instantâneos de restaurações anteriores.', 'Digite a frase usada para criptografar este arquivo'
    ],
    ru: [
        'Резервное копирование и восстановление', 'Зашифрованные системные копии поддерживают только SQLite. Храните архив и пароль в безопасном месте: для восстановления нужны оба.',
        'Скачать зашифрованную копию', 'Пароль резервной копии', 'Введите от 12 до 256 символов', 'Подтвердите пароль', 'Введите тот же пароль повторно', 'Проверка и восстановление', 'Зашифрованный архив (.ogb, до 64 MiB)', 'Существующие данные', 'Прервать, если экземпляр содержит данные', 'Заменить существующие данные',
        'Проверить архив', 'Восстановить копию', 'Восстановить проверенный архив? Текущие настройки, учётные данные, идентификаторы и записи использования могут быть заменены. Сначала сохраните текущую резервную копию. Потребуется повторный вход.',
        'Скачать экспорт без секретных данных', 'Экспорт без секретных данных предназначен для проверки и не подходит для восстановления.', 'Проверка прав резервного копирования…', 'У вас нет прав на работу с резервными копиями.', 'Не удалось проверить права. Откройте настройки заново.',
        'Используйте пароль длиной от 12 до 256 символов.', 'Пароли должны совпадать.', 'Выберите непустой зашифрованный архив размером не более 64 MiB.', 'Это хранилище не поддерживает резервное копирование и восстановление. Поддерживается только SQLite.', 'Экземпляр уже содержит данные. Проверьте политику замены перед повторной проверкой.',
        'Архив, пароль или сведения о совместимости недействительны. Проверьте файл и пароль.', 'Запрос резервного копирования завершился ошибкой. Проверьте соединение и права перед повтором.', 'Результат восстановления не подтверждён. Не повторяйте автоматически. Проверьте экземпляр и войдите заново, прежде чем решать, что делать дальше.',
        'Проверка без изменения данных…', 'Проверка пройдена. Данные не изменены. Просмотрите план перед восстановлением.', 'Записей в проверенном архиве: {count}', 'Восстановление данных. Оставьте страницу открытой…', 'Восстановление завершено. Войдите заново.', 'Подготовка скачивания…', 'Скачивание началось. Проверьте загрузки браузера.',
        'Включает настройки, учётные данные, идентификаторы, маршруты, ключи, реестры использования, аудит и трассировки. Не включает исходные логи, старую статистику и снимки прошлых восстановлений.', 'Введите пароль, использованный для шифрования архива'
    ],
    th: [
        'สำรองและกู้คืนข้อมูล', 'การสำรองระบบแบบเข้ารหัสรองรับเฉพาะ SQLite เก็บไฟล์และวลีรหัสผ่านให้ปลอดภัย เพราะต้องใช้ทั้งสองอย่างในการกู้คืน',
        'ดาวน์โหลดข้อมูลสำรองแบบเข้ารหัส', 'วลีรหัสผ่านข้อมูลสำรอง', 'ป้อน 12–256 อักขระ', 'ยืนยันวลีรหัสผ่าน', 'ป้อนวลีรหัสผ่านเดิมอีกครั้ง', 'ตรวจสอบและกู้คืน', 'ไฟล์เข้ารหัส (.ogb ไม่เกิน 64 MiB)', 'ข้อมูลที่มีอยู่', 'ยกเลิกหากอินสแตนซ์มีข้อมูล', 'แทนที่ข้อมูลที่มีอยู่',
        'ตรวจสอบไฟล์สำรอง', 'กู้คืนข้อมูลสำรอง', 'กู้คืนไฟล์ที่ตรวจสอบแล้วหรือไม่ การตั้งค่า ข้อมูลรับรอง ตัวตน และบันทึกการใช้งานปัจจุบันอาจถูกแทนที่ สำรองข้อมูลปัจจุบันก่อน คุณจะต้องเข้าสู่ระบบอีกครั้ง',
        'ดาวน์โหลดข้อมูลส่งออกที่ลบข้อมูลอ่อนไหว', 'ข้อมูลส่งออกที่ลบข้อมูลอ่อนไหวใช้เพื่อตรวจสอบเท่านั้นและกู้คืนไม่ได้', 'กำลังตรวจสอบสิทธิ์สำรองข้อมูล…', 'คุณไม่มีสิทธิ์ใช้การสำรองข้อมูล', 'ตรวจสอบสิทธิ์ไม่ได้ เปิดการตั้งค่าอีกครั้งเพื่อลองใหม่',
        'ใช้วลีรหัสผ่านยาว 12–256 อักขระ', 'วลีรหัสผ่านต้องตรงกัน', 'เลือกไฟล์เข้ารหัสที่ไม่ว่างและไม่เกิน 64 MiB', 'ที่เก็บข้อมูลนี้ไม่รองรับการสำรองและกู้คืน รองรับเฉพาะ SQLite', 'อินสแตนซ์นี้มีข้อมูลอยู่แล้ว ตรวจสอบนโยบายแทนที่ก่อนตรวจสอบอีกครั้ง',
        'ไฟล์ วลีรหัสผ่าน หรือข้อมูลความเข้ากันได้ไม่ถูกต้อง ตรวจสอบไฟล์และวลีรหัสผ่าน', 'คำขอสำรองข้อมูลล้มเหลว ตรวจสอบการเชื่อมต่อและสิทธิ์ก่อนลองใหม่', 'ยืนยันผลการกู้คืนไม่ได้ อย่าลองซ้ำอัตโนมัติ ตรวจสอบอินสแตนซ์และเข้าสู่ระบบอีกครั้งก่อนตัดสินใจดำเนินการต่อ',
        'กำลังตรวจสอบโดยไม่เปลี่ยนข้อมูล…', 'ตรวจสอบผ่านแล้ว ยังไม่มีการเปลี่ยนข้อมูล ตรวจสอบแผนก่อนกู้คืน', 'จำนวนรายการในไฟล์ที่ตรวจสอบแล้ว: {count}', 'กำลังกู้คืนข้อมูล เปิดหน้านี้ไว้…', 'กู้คืนเสร็จแล้ว เข้าสู่ระบบอีกครั้งเพื่อดำเนินการต่อ', 'กำลังเตรียมดาวน์โหลด…', 'เริ่มดาวน์โหลดแล้ว ตรวจสอบรายการดาวน์โหลดของเบราว์เซอร์',
        'รวมการตั้งค่า ข้อมูลรับรอง ตัวตน เส้นทาง คีย์ บัญชีการใช้งาน การตรวจสอบ และการติดตาม ไม่รวมบันทึกดิบ สถิติเก่า และสแนปช็อตการกู้คืนก่อนหน้า', 'ป้อนวลีรหัสผ่านที่ใช้เข้ารหัสไฟล์นี้'
    ],
    tr: [
        'Yedekleme ve geri yükleme', 'Şifreli sistem yedekleri yalnızca SQLite ile kullanılabilir. Arşivi ve parolasını güvenle saklayın; geri yükleme için ikisi de gerekir.',
        'Şifreli yedeği indir', 'Yedek parolası', '12–256 karakter girin', 'Parolayı doğrulayın', 'Aynı parolayı tekrar girin', 'Doğrula ve geri yükle', 'Şifreli arşiv (.ogb, en fazla 64 MiB)', 'Mevcut veriler', 'Sunucuda veri varsa iptal et', 'Mevcut verileri değiştir',
        'Arşivi doğrula', 'Yedeği geri yükle', 'Doğrulanmış arşiv geri yüklensin mi? Mevcut yapılandırma, kimlik bilgileri, kimlikler ve kullanım kayıtları değiştirilebilir. Önce mevcut durumu yedekleyin. Yeniden giriş yapmanız gerekir.',
        'Hassas verileri çıkarılmış dışa aktarımı indir', 'Hassas verileri çıkarılmış dışa aktarım inceleme içindir ve geri yüklenemez.', 'Yedekleme izinleri kontrol ediliyor…', 'Yedekleri kullanma izniniz yok.', 'Yedekleme izinleri kontrol edilemedi. Tekrar denemek için Ayarları yeniden açın.',
        '12–256 karakter uzunluğunda bir parola kullanın.', 'Parolalar eşleşmelidir.', 'Boş olmayan, en fazla 64 MiB boyutunda şifreli bir arşiv seçin.', 'Bu depolama sistemi yedekleme ve geri yüklemeyi desteklemiyor. Yalnızca SQLite desteklenir.', 'Bu sunucuda zaten veri var. Yeniden doğrulamadan önce değiştirme ilkesini gözden geçirin.',
        'Arşiv, parola veya uyumluluk bilgileri geçersiz. Dosyayı ve parolayı kontrol edin.', 'Yedekleme isteği başarısız oldu. Tekrar denemeden önce bağlantınızı ve erişiminizi kontrol edin.', 'Geri yükleme sonucu doğrulanamadı. Otomatik olarak tekrar denemeyin. Sonraki adıma karar vermeden önce sunucuyu kontrol edip yeniden giriş yapın.',
        'Veriler değiştirilmeden doğrulanıyor…', 'Doğrulama başarılı. Veriler değiştirilmedi. Geri yüklemeden önce planı gözden geçirin.', 'Doğrulanmış arşivdeki kayıt sayısı: {count}', 'Veriler geri yükleniyor. Bu sayfayı açık tutun…', 'Geri yükleme tamamlandı. Devam etmek için yeniden giriş yapın.', 'İndirme hazırlanıyor…', 'İndirme başladı. Tarayıcınızın indirmelerini kontrol edin.',
        'Yapılandırma, kimlik bilgileri, kimlikler, rotalar, anahtarlar, kullanım defterleri, denetim ve izleri içerir. Ham günlükler, eski istatistikler ve önceki geri yükleme anlık görüntüleri hariçtir.', 'Bu arşivi şifrelemek için kullanılan parolayı girin'
    ]
};
const BACKUP_ARCHIVE_CHOOSER_VALUES = {
    en: ['Choose encrypted archive', 'No archive selected'],
    vi: ['Chọn tệp sao lưu mã hóa', 'Chưa chọn tệp sao lưu'],
    'zh-CN': ['选择加密备份文件', '尚未选择备份文件'],
    'zh-TW': ['選擇加密備份檔案', '尚未選擇備份檔案'],
    de: ['Verschlüsseltes Archiv auswählen', 'Kein Archiv ausgewählt'],
    es: ['Elegir archivo cifrado', 'No se ha elegido un archivo'],
    fr: ['Choisir une archive chiffrée', 'Aucune archive sélectionnée'],
    id: ['Pilih arsip terenkripsi', 'Belum ada arsip yang dipilih'],
    it: ['Scegli archivio cifrato', 'Nessun archivio selezionato'],
    ja: ['暗号化アーカイブを選択', 'アーカイブが選択されていません'],
    ko: ['암호화된 아카이브 선택', '선택된 아카이브 없음'],
    pt: ['Escolher arquivo criptografado', 'Nenhum arquivo selecionado'],
    ru: ['Выбрать зашифрованный архив', 'Архив не выбран'],
    th: ['เลือกไฟล์สำรองที่เข้ารหัส', 'ยังไม่ได้เลือกไฟล์สำรอง'],
    tr: ['Şifreli arşiv seç', 'Arşiv seçilmedi']
};
for (const [locale, values] of Object.entries(BACKUP_LOCALE_VALUES)) {
    if (values.length !== BACKUP_KEYS.length) throw new Error(`Invalid backup locale: ${locale}`);
    const messages = Object.fromEntries(BACKUP_KEYS.map((key, index) => [key, values[index]]));
    messages['backup.choose_archive'] = BACKUP_ARCHIVE_CHOOSER_VALUES[locale][0];
    messages['backup.no_archive'] = BACKUP_ARCHIVE_CHOOSER_VALUES[locale][1];
    Object.assign(PAGE_LOCALE_TRANSLATIONS[locale], messages);
    Object.assign(MESSAGE_CATALOGS[locale], messages);
}
for (const [index, message] of BACKUP_LOCALE_VALUES.en.entries()) {
    if (!ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.has(message)) ENGLISH_SEMANTIC_KEYS_BY_MESSAGE.set(message, BACKUP_KEYS[index]);
}
