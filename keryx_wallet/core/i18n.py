"""
i18n.py — lightweight translation layer for the Keryx wallet.

Supported languages: English (en), Russian (ru), Chinese (zh), Indonesian (id),
Korean (ko), Spanish (es), Dutch (nl).

Usage:
    from keryx_wallet.core import i18n
    i18n.set_language("es")
    label = i18n.t("connect")           # -> "Conectar"

Strings are looked up by a stable key. If a key is missing for the active
language, it falls back to English, then to the key itself — so the app never
crashes on a missing translation.
"""

from __future__ import annotations

LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "zh": "中文",
    "id": "Bahasa Indonesia",
    "ko": "한국어",
    "es": "Español",
    "nl": "Nederlands",
}

# Short labels for the compact top-right button (full names are used in the
# picker dialog). "Bahasa Indonesia" is too wide for a small button.
LANGUAGES_SHORT = {
    "en": "English",
    "ru": "Русский",
    "zh": "中文",
    "id": "Indonesia",
    "ko": "한국어",
    "es": "Español",
    "nl": "Nederlands",
}

_current = "en"

# Translation table: key -> {lang: text}. English is the source of truth.
_T = {
    # ── Connection screen ────────────────────────────────────────────────
    "connect_to_node": {
        "en": "Connect to a Keryx node",
        "ru": "Подключиться к узлу Keryx",
        "zh": "连接到 Keryx 节点",
        "id": "Hubungkan ke node Keryx",
        "ko": "Keryx 노드에 연결",
        "es": "Conectar a un nodo Keryx",
        "nl": "Verbinden met een Keryx-node",
    },
    "address": {
        "en": "Address:", "ru": "Адрес:", "zh": "地址：", "id": "Alamat:",
        "ko": "주소:", "es": "Dirección:", "nl": "Adres:",
    },
    "connect": {
        "en": "Connect", "ru": "Подключить", "zh": "连接", "id": "Hubungkan",
        "ko": "연결", "es": "Conectar", "nl": "Verbinden",
    },
    "network": {
        "en": "Network:", "ru": "Сеть:", "zh": "网络：", "id": "Jaringan:",
        "ko": "네트워크:", "es": "Red:", "nl": "Netwerk:",
    },
    # ── Wallet options screen ────────────────────────────────────────────
    "wallet_options": {
        "en": "Wallet Options", "ru": "Параметры кошелька", "zh": "钱包选项",
        "id": "Opsi Dompet", "ko": "지갑 옵션", "es": "Opciones de cartera",
        "nl": "Portemonnee-opties",
    },
    "choose": {
        "en": "Choose:", "ru": "Выберите:", "zh": "选择：", "id": "Pilih:",
        "ko": "선택:", "es": "Elegir:", "nl": "Kies:",
    },
    "open": {
        "en": "Open", "ru": "Открыть", "zh": "打开", "id": "Buka",
        "ko": "열기", "es": "Abrir", "nl": "Openen",
    },
    "create": {
        "en": "Create", "ru": "Создать", "zh": "创建", "id": "Buat",
        "ko": "만들기", "es": "Crear", "nl": "Aanmaken",
    },
    "import": {
        "en": "Import", "ru": "Импорт", "zh": "导入", "id": "Impor",
        "ko": "가져오기", "es": "Importar", "nl": "Importeren",
    },
    "name": {
        "en": "Name:", "ru": "Имя:", "zh": "名称：", "id": "Nama:",
        "ko": "이름:", "es": "Nombre:", "nl": "Naam:",
    },
    "back_to_connection": {
        "en": "← Back to connection", "ru": "← Назад к подключению",
        "zh": "← 返回连接", "id": "← Kembali ke koneksi",
        "ko": "← 연결로 돌아가기", "es": "← Volver a la conexión",
        "nl": "← Terug naar verbinding",
    },
    # ── Dashboard ────────────────────────────────────────────────────────
    "switch_wallet": {
        "en": "Switch wallet", "ru": "Сменить кошелёк", "zh": "切换钱包",
        "id": "Ganti dompet", "ko": "지갑 전환", "es": "Cambiar cartera",
        "nl": "Wissel portemonnee",
    },
    "account": {
        "en": "Account", "ru": "Счёт", "zh": "账户", "id": "Akun",
        "ko": "계정", "es": "Cuenta", "nl": "Account",
    },
    "rename": {
        "en": "Rename", "ru": "Переименовать", "zh": "重命名", "id": "Ganti nama",
        "ko": "이름 변경", "es": "Renombrar", "nl": "Hernoemen",
    },
    "new_account": {
        "en": "New account", "ru": "Новый счёт", "zh": "新建账户",
        "id": "Akun baru", "ko": "새 계정", "es": "Nueva cuenta",
        "nl": "Nieuw account",
    },
    "reorder_hint": {
        "en": "Drag accounts to reorder", "ru": "Перетащите счета для порядка",
        "zh": "拖动账户以重新排序", "id": "Seret akun untuk mengurutkan",
        "ko": "계정을 끌어 순서 변경", "es": "Arrastra las cuentas para reordenar",
        "nl": "Sleep accounts om te herschikken",
    },
    "enter_passphrase_prompt": {
        "en": "Enter your wallet's BIP39 passphrase",
        "ru": "Введите парольную фразу BIP39 вашего кошелька",
        "zh": "输入钱包的 BIP39 口令",
        "id": "Masukkan frasa sandi BIP39 dompet Anda",
        "ko": "지갑의 BIP39 암호문을 입력하세요",
        "es": "Introduce la frase de contraseña BIP39 de tu cartera",
        "nl": "Voer de BIP39-wachtwoordzin van je portemonnee in",
    },
    "create_passphrase_warning": {
        "en": "Keep your 12-word mnemonic and BIP39 passphrase secure — they "
              "cannot be recovered after creation. Your BIP39 passphrase will be "
              "used as a payment secret for transactions.",
        "ru": "Храните свою фразу из 12 слов и парольную фразу BIP39 в "
              "безопасности — их нельзя восстановить после создания. Ваша "
              "парольная фраза BIP39 будет использоваться как платёжный секрет "
              "для транзакций.",
        "zh": "请妥善保管您的 12 词助记词和 BIP39 口令——创建后无法恢复。您的 "
              "BIP39 口令将用作交易的支付密钥。",
        "id": "Simpan frasa 12 kata dan frasa sandi BIP39 Anda dengan aman — "
              "keduanya tidak dapat dipulihkan setelah dibuat. Frasa sandi BIP39 "
              "Anda akan digunakan sebagai rahasia pembayaran untuk transaksi.",
        "ko": "12단어 니모닉과 BIP39 암호문을 안전하게 보관하세요 — 생성 후에는 "
              "복구할 수 없습니다. BIP39 암호문은 거래의 결제 비밀로 사용됩니다.",
        "es": "Guarda de forma segura tu frase de 12 palabras y tu frase de "
              "contraseña BIP39: no se pueden recuperar tras la creación. Tu "
              "frase de contraseña BIP39 se usará como secreto de pago para las "
              "transacciones.",
        "nl": "Bewaar je 12-woorden mnemonic en BIP39-wachtwoordzin veilig — ze "
              "kunnen na het aanmaken niet worden hersteld. Je "
              "BIP39-wachtwoordzin wordt gebruikt als betalingsgeheim voor "
              "transacties.",
    },
    "max": {
        "en": "Max", "ru": "Макс", "zh": "全部", "id": "Maks",
        "ko": "최대", "es": "Máx", "nl": "Max",
    },
    "max_tip": {
        "en": "Send the entire balance (amount = balance minus the network fee)",
        "ru": "Отправить весь баланс (сумма = баланс минус комиссия сети)",
        "zh": "发送全部余额（金额 = 余额减去网络手续费）",
        "id": "Kirim seluruh saldo (jumlah = saldo dikurangi biaya jaringan)",
        "ko": "전체 잔액 보내기 (금액 = 잔액 − 네트워크 수수료)",
        "es": "Enviar todo el saldo (importe = saldo menos la comisión de red)",
        "nl": "Verstuur het volledige saldo (bedrag = saldo min netwerkkosten)",
    },
    "estimate_unavailable": {
        "en": "Couldn't estimate the fee. Make sure you're connected, then try "
              "again.",
        "ru": "Не удалось рассчитать комиссию. Убедитесь, что вы подключены, и "
              "повторите попытку.",
        "zh": "无法估算手续费。请确认已连接后重试。",
        "id": "Tidak dapat memperkirakan biaya. Pastikan Anda terhubung, lalu "
              "coba lagi.",
        "ko": "수수료를 추정할 수 없습니다. 연결되어 있는지 확인 후 다시 "
              "시도하세요.",
        "es": "No se pudo estimar la comisión. Asegúrate de estar conectado e "
              "inténtalo de nuevo.",
        "nl": "Kon de kosten niet schatten. Controleer of je verbonden bent en "
              "probeer het opnieuw.",
    },
    "insufficient_amount_fee": {
        "en": "Your total balance can't cover the sending amount plus network "
              "fees. Try a smaller amount.",
        "ru": "Вашего общего баланса не хватает на сумму отправки плюс сетевые "
              "комиссии. Попробуйте меньшую сумму.",
        "zh": "您的总余额无法支付发送金额加网络手续费。请尝试更小的金额。",
        "id": "Total saldo Anda tidak cukup untuk jumlah kirim ditambah biaya "
              "jaringan. Coba jumlah yang lebih kecil.",
        "ko": "전체 잔액으로 보내는 금액과 네트워크 수수료를 충당할 수 없습니다. "
              "더 적은 금액으로 시도하세요.",
        "es": "Tu saldo total no cubre el importe a enviar más las comisiones de "
              "red. Prueba con un importe menor.",
        "nl": "Je totale saldo dekt het verzendbedrag plus netwerkkosten niet. "
              "Probeer een kleiner bedrag.",
    },
    "estimating": {
        "en": "Estimating fee", "ru": "Расчёт комиссии", "zh": "正在估算手续费",
        "id": "Memperkirakan biaya", "ko": "수수료 추정 중",
        "es": "Estimando comisión", "nl": "Kosten schatten",
    },
    "account_name_prompt": {
        "en": "Account name", "ru": "Имя счёта", "zh": "账户名称",
        "id": "Nama akun", "ko": "계정 이름", "es": "Nombre de cuenta",
        "nl": "Accountnaam",
    },
    "account_recovery_warning": {
        "en": "Additional accounts do NOT auto-restore from your recovery "
              "phrase. To recover them you must recreate each account in the "
              "same order. Keep important funds in the main account. Continue?",
        "ru": "Дополнительные счета НЕ восстанавливаются автоматически из "
              "вашей фразы. Чтобы восстановить их, нужно заново создать каждый "
              "счёт в том же порядке. Храните важные средства на основном "
              "счёте. Продолжить?",
        "zh": "附加账户不会从助记词自动恢复。要恢复它们，您必须按相同顺序"
              "重新创建每个账户。请将重要资金保留在主账户中。是否继续？",
        "id": "Akun tambahan TIDAK dipulihkan otomatis dari frasa pemulihan "
              "Anda. Untuk memulihkannya, buat ulang setiap akun dengan urutan "
              "yang sama. Simpan dana penting di akun utama. Lanjutkan?",
        "ko": "추가 계정은 복구 문구로 자동 복원되지 않습니다. 복구하려면 "
              "동일한 순서로 각 계정을 다시 만들어야 합니다. 중요한 자금은 "
              "메인 계정에 보관하세요. 계속할까요?",
        "es": "Las cuentas adicionales NO se restauran automáticamente desde tu "
              "frase de recuperación. Para recuperarlas debes recrear cada "
              "cuenta en el mismo orden. Mantén los fondos importantes en la "
              "cuenta principal. ¿Continuar?",
        "nl": "Extra accounts worden NIET automatisch hersteld vanuit je "
              "herstelzin. Om ze te herstellen moet je elk account in dezelfde "
              "volgorde opnieuw aanmaken. Houd belangrijke tegoeden op het "
              "hoofdaccount. Doorgaan?",
    },
    "account_created": {
        "en": "Account created", "ru": "Счёт создан", "zh": "账户已创建",
        "id": "Akun dibuat", "ko": "계정이 생성됨", "es": "Cuenta creada",
        "nl": "Account aangemaakt",
    },
    "create_account_failed": {
        "en": "Could not create account", "ru": "Не удалось создать счёт",
        "zh": "无法创建账户", "id": "Gagal membuat akun",
        "ko": "계정을 만들 수 없음", "es": "No se pudo crear la cuenta",
        "nl": "Kon account niet aanmaken",
    },
    "rename_prompt": {
        "en": "New account name", "ru": "Новое имя счёта",
        "zh": "新账户名称", "id": "Nama akun baru", "ko": "새 계정 이름",
        "es": "Nuevo nombre de cuenta", "nl": "Nieuwe accountnaam",
    },
    "account_renamed": {
        "en": "Account renamed", "ru": "Счёт переименован", "zh": "账户已重命名",
        "id": "Akun diganti namanya", "ko": "계정 이름이 변경됨",
        "es": "Cuenta renombrada", "nl": "Account hernoemd",
    },
    "rename_failed": {
        "en": "Rename failed", "ru": "Не удалось переименовать",
        "zh": "重命名失败", "id": "Gagal mengganti nama", "ko": "이름 변경 실패",
        "es": "Error al renombrar", "nl": "Hernoemen mislukt",
    },
    "consolidate": {
        "en": "Consolidate", "ru": "Объединить", "zh": "整合", "id": "Konsolidasi",
        "ko": "통합", "es": "Consolidar", "nl": "Consolideren",
    },
    "consolidate_tip": {
        "en": "Consolidating high UTXO counts can speed up future transactions",
        "ru": "Объединение большого числа UTXO ускоряет будущие транзакции",
        "zh": "整合大量 UTXO 可以加快未来的交易",
        "id": "Mengonsolidasikan UTXO yang banyak dapat mempercepat transaksi",
        "ko": "많은 UTXO를 통합하면 향후 거래 속도가 빨라집니다",
        "es": "Consolidar muchos UTXO puede acelerar las transacciones futuras",
        "nl": "Het consolideren van veel UTXO's versnelt toekomstige transacties",
    },
    "export_phrase": {
        "en": "Export phrase", "ru": "Экспорт фразы", "zh": "导出助记词",
        "id": "Ekspor frasa", "ko": "구문 내보내기", "es": "Exportar frase",
        "nl": "Zin exporteren",
    },
    "balance": {
        "en": "Balance", "ru": "Баланс", "zh": "余额", "id": "Saldo",
        "ko": "잔액", "es": "Saldo", "nl": "Saldo",
    },
    "receive": {
        "en": "Receive", "ru": "Получить", "zh": "接收", "id": "Terima",
        "ko": "받기", "es": "Recibir", "nl": "Ontvangen",
    },
    "send": {
        "en": "Send", "ru": "Отправить", "zh": "发送", "id": "Kirim",
        "ko": "보내기", "es": "Enviar", "nl": "Verzenden",
    },
    "copy_address": {
        "en": "Copy address", "ru": "Копировать адрес", "zh": "复制地址",
        "id": "Salin alamat", "ko": "주소 복사", "es": "Copiar dirección",
        "nl": "Adres kopiëren",
    },
    "copied": {
        "en": "Copied ✓", "ru": "Скопировано ✓", "zh": "已复制 ✓",
        "id": "Disalin ✓", "ko": "복사됨 ✓", "es": "Copiado ✓", "nl": "Gekopieerd ✓",
    },
    "copy_phrase": {
        "en": "Copy phrase", "ru": "Копировать фразу", "zh": "复制助记词",
        "id": "Salin frasa", "ko": "구문 복사", "es": "Copiar frase",
        "nl": "Zin kopiëren",
    },
    "transactions": {
        "en": "Transactions", "ru": "Транзакции", "zh": "交易", "id": "Transaksi",
        "ko": "거래", "es": "Transacciones", "nl": "Transacties",
    },
    "hide_txs_under": {
        "en": "Hide txs under:", "ru": "Скрыть транзакции меньше:",
        "zh": "隐藏小于此值的交易：", "id": "Sembunyikan tx di bawah:",
        "ko": "이 금액 미만 거래 숨기기:", "es": "Ocultar tx bajo:",
        "nl": "Verberg tx onder:",
    },
    "to": {
        "en": "To:", "ru": "Кому:", "zh": "收款人：", "id": "Ke:",
        "ko": "받는 사람:", "es": "Para:", "nl": "Naar:",
    },
    "amount": {
        "en": "Amount:", "ru": "Сумма:", "zh": "金额：", "id": "Jumlah:",
        "ko": "금액:", "es": "Cantidad:", "nl": "Bedrag:",
    },
    "fee": {
        "en": "Fee:", "ru": "Комиссия:", "zh": "手续费：", "id": "Biaya:",
        "ko": "수수료:", "es": "Comisión:", "nl": "Kosten:",
    },
    # ── Common buttons / dialogs ─────────────────────────────────────────
    "proceed": {
        "en": "Proceed", "ru": "Продолжить", "zh": "继续", "id": "Lanjutkan",
        "ko": "진행", "es": "Continuar", "nl": "Doorgaan",
    },
    "cancel": {
        "en": "Cancel", "ru": "Отмена", "zh": "取消", "id": "Batal",
        "ko": "취소", "es": "Cancelar", "nl": "Annuleren",
    },
    "ok": {
        "en": "OK", "ru": "ОК", "zh": "确定", "id": "OK", "ko": "확인",
        "es": "Aceptar", "nl": "OK",
    },
    "enter_password": {
        "en": "Enter password", "ru": "Введите пароль", "zh": "输入密码",
        "id": "Masukkan kata sandi", "ko": "비밀번호 입력",
        "es": "Introduzca la contraseña", "nl": "Voer wachtwoord in",
    },
    "wrong_password": {
        "en": "Wrong password.", "ru": "Неверный пароль.", "zh": "密码错误。",
        "id": "Kata sandi salah.", "ko": "비밀번호가 틀렸습니다.",
        "es": "Contraseña incorrecta.", "nl": "Verkeerd wachtwoord.",
    },
    # ── Consolidate dialog ───────────────────────────────────────────────
    "consolidate_title": {
        "en": "Consolidate UTXOs?", "ru": "Объединить UTXO?", "zh": "整合 UTXO？",
        "id": "Konsolidasi UTXO?", "ko": "UTXO를 통합하시겠습니까?",
        "es": "¿Consolidar UTXO?", "nl": "UTXO's consolideren?",
    },
    # ── Language picker ──────────────────────────────────────────────────
    "choose_language": {
        "en": "Choose your language", "ru": "Выберите язык", "zh": "选择语言",
        "id": "Pilih bahasa Anda", "ko": "언어를 선택하세요",
        "es": "Elija su idioma", "nl": "Kies uw taal",
    },
    "language": {
        "en": "Language", "ru": "Язык", "zh": "语言", "id": "Bahasa",
        "ko": "언어", "es": "Idioma", "nl": "Taal",
    },
    # ── Pagination ───────────────────────────────────────────────────────
    "prev": {
        "en": "‹ Prev", "ru": "‹ Назад", "zh": "‹ 上一页", "id": "‹ Sebelumnya",
        "ko": "‹ 이전", "es": "‹ Anterior", "nl": "‹ Vorige",
    },
    "next": {
        "en": "Next ›", "ru": "Вперёд ›", "zh": "下一页 ›", "id": "Berikutnya ›",
        "ko": "다음 ›", "es": "Siguiente ›", "nl": "Volgende ›",
    },
    # ── Network field + placeholders ─────────────────────────────────────
    "network_label": {
        "en": "Network:", "ru": "Сеть:", "zh": "网络：", "id": "Jaringan:",
        "ko": "네트워크:", "es": "Red:", "nl": "Netwerk:",
    },
    "address_placeholder": {
        "en": "Nodes wRPC address (e.g. host:port)",
        "ru": "wRPC-адрес узла (например, host:port)",
        "zh": "节点 wRPC 地址（例如 host:port）",
        "id": "Alamat wRPC node (mis. host:port)",
        "ko": "노드 wRPC 주소 (예: host:port)",
        "es": "Dirección wRPC del nodo (p. ej. host:port)",
        "nl": "wRPC-adres van node (bijv. host:poort)",
    },
    "wallet_name_placeholder": {
        "en": "new wallet name (letters, digits, _ -)",
        "ru": "имя нового кошелька (буквы, цифры, _ -)",
        "zh": "新钱包名称（字母、数字、_ -）",
        "id": "nama dompet baru (huruf, angka, _ -)",
        "ko": "새 지갑 이름 (문자, 숫자, _ -)",
        "es": "nombre de cartera nueva (letras, dígitos, _ -)",
        "nl": "nieuwe portemonneenaam (letters, cijfers, _ -)",
    },
    "destination_placeholder": {
        "en": "destination address", "ru": "адрес получателя",
        "zh": "目标地址", "id": "alamat tujuan", "ko": "받는 주소",
        "es": "dirección de destino", "nl": "bestemmingsadres",
    },
    "show_all": {
        "en": "0 (show all)", "ru": "0 (показать все)", "zh": "0（全部显示）",
        "id": "0 (tampilkan semua)", "ko": "0 (모두 표시)",
        "es": "0 (mostrar todo)", "nl": "0 (toon alles)",
    },
    # ── Buttons that take arguments / actions ────────────────────────────
    "open_btn": {
        "en": "Open…", "ru": "Открыть…", "zh": "打开…", "id": "Buka…",
        "ko": "열기…", "es": "Abrir…", "nl": "Openen…",
    },
    "create_btn": {
        "en": "Create…", "ru": "Создать…", "zh": "创建…", "id": "Buat…",
        "ko": "만들기…", "es": "Crear…", "nl": "Aanmaken…",
    },
    "import_btn": {
        "en": "Import…", "ru": "Импорт…", "zh": "导入…", "id": "Impor…",
        "ko": "가져오기…", "es": "Importar…", "nl": "Importeren…",
    },
    "send_btn": {
        "en": "Send", "ru": "Отправить", "zh": "发送", "id": "Kirim",
        "ko": "보내기", "es": "Enviar", "nl": "Verzenden",
    },
    "priority_fee": {
        "en": "Priority fee:", "ru": "Приоритетная комиссия:",
        "zh": "优先手续费：", "id": "Biaya prioritas:", "ko": "우선 수수료:",
        "es": "Comisión prioritaria:", "nl": "Prioriteitskosten:",
    },
    # ── Transaction directions ───────────────────────────────────────────
    "incoming": {
        "en": "Incoming", "ru": "Входящая", "zh": "收入", "id": "Masuk",
        "ko": "입금", "es": "Entrante", "nl": "Inkomend",
    },
    "outgoing": {
        "en": "Outgoing", "ru": "Исходящая", "zh": "支出", "id": "Keluar",
        "ko": "출금", "es": "Saliente", "nl": "Uitgaand",
    },
    "external": {
        "en": "External", "ru": "Внешняя", "zh": "外部", "id": "Eksternal",
        "ko": "외부", "es": "Externa", "nl": "Extern",
    },
    "no_transactions": {
        "en": "No transactions found.", "ru": "Транзакции не найдены.",
        "zh": "未找到交易。", "id": "Tidak ada transaksi.",
        "ko": "거래를 찾을 수 없습니다.", "es": "No se encontraron transacciones.",
        "nl": "Geen transacties gevonden.",
    },
    "loading_transactions": {
        "en": "Loading transactions…", "ru": "Загрузка транзакций…",
        "zh": "正在加载交易…", "id": "Memuat transaksi…",
        "ko": "거래 불러오는 중…", "es": "Cargando transacciones…",
        "nl": "Transacties laden…",
    },
    "loading_address": {
        "en": "Loading address…", "ru": "Загрузка адреса…", "zh": "正在加载地址…",
        "id": "Memuat alamat…", "ko": "주소 불러오는 중…",
        "es": "Cargando dirección…", "nl": "Adres laden…",
    },
    "tx_count": {  # used with .format(n=...)
        "en": "{n} transactions", "ru": "{n} транзакций", "zh": "{n} 笔交易",
        "id": "{n} transaksi", "ko": "{n}건의 거래", "es": "{n} transacciones",
        "nl": "{n} transacties",
    },
    # ── Send dialog ──────────────────────────────────────────────────────
    "confirm_send": {
        "en": "Confirm Send", "ru": "Подтвердить отправку", "zh": "确认发送",
        "id": "Konfirmasi Kirim", "ko": "전송 확인", "es": "Confirmar envío",
        "nl": "Verzending bevestigen",
    },
    "send_warning": {
        "en": "Review carefully. Once you enter your password the transaction is broadcast immediately and cannot be reversed.",
        "ru": "Внимательно проверьте. После ввода пароля транзакция немедленно отправляется и не может быть отменена.",
        "zh": "请仔细核对。输入密码后，交易将立即广播且无法撤销。",
        "id": "Periksa dengan teliti. Setelah memasukkan kata sandi, transaksi langsung disiarkan dan tidak dapat dibatalkan.",
        "ko": "신중히 확인하세요. 비밀번호를 입력하면 거래가 즉시 전송되며 되돌릴 수 없습니다.",
        "es": "Revise con cuidado. Una vez que introduzca su contraseña, la transacción se transmite de inmediato y no se puede revertir.",
        "nl": "Controleer zorgvuldig. Zodra u uw wachtwoord invoert, wordt de transactie direct verzonden en kan deze niet worden teruggedraaid.",
    },
    "confirm_sign": {
        "en": "Confirm && Sign", "ru": "Подтвердить и подписать",
        "zh": "确认并签名", "id": "Konfirmasi && Tanda Tangani",
        "ko": "확인 및 서명", "es": "Confirmar y firmar",
        "nl": "Bevestig && Onderteken",
    },
    "enter_pw_broadcast": {
        "en": "Enter wallet password to broadcast:",
        "ru": "Введите пароль кошелька для отправки:",
        "zh": "输入钱包密码以广播：",
        "id": "Masukkan kata sandi dompet untuk menyiarkan:",
        "ko": "전송하려면 지갑 비밀번호를 입력하세요:",
        "es": "Introduzca la contraseña de la cartera para transmitir:",
        "nl": "Voer portemonneewachtwoord in om te verzenden:",
    },
    "broadcast_tx": {
        "en": "Broadcast Transaction", "ru": "Отправить транзакцию",
        "zh": "广播交易", "id": "Siarkan Transaksi", "ko": "거래 전송",
        "es": "Transmitir transacción", "nl": "Transactie verzenden",
    },
    "estimated_fee": {
        "en": "Estimated fee:", "ru": "Оценочная комиссия:", "zh": "预估手续费：",
        "id": "Estimasi biaya:", "ko": "예상 수수료:", "es": "Comisión estimada:",
        "nl": "Geschatte kosten:",
    },
    "estimated_total": {
        "en": "Estimated total:", "ru": "Оценочная сумма:", "zh": "预估总额：",
        "id": "Estimasi total:", "ko": "예상 합계:", "es": "Total estimado:",
        "nl": "Geschat totaal:",
    },
    # ── Consolidate dialog details ───────────────────────────────────────
    "utxos_label": {
        "en": "UTXOs", "ru": "UTXO", "zh": "UTXO", "id": "UTXO", "ko": "UTXO",
        "es": "UTXO", "nl": "UTXO's",
    },
    "batches_label": {
        "en": "Batches", "ru": "Пакеты", "zh": "批次", "id": "Batch",
        "ko": "배치", "es": "Lotes", "nl": "Batches",
    },
    "batch_fee": {
        "en": "Batch fee", "ru": "Комиссия за пакет", "zh": "每批手续费",
        "id": "Biaya batch", "ko": "배치 수수료", "es": "Comisión por lote",
        "nl": "Batchkosten",
    },
    "total_fee": {
        "en": "Total consolidation fee", "ru": "Общая комиссия за объединение",
        "zh": "总整合手续费", "id": "Total biaya konsolidasi",
        "ko": "총 통합 수수료", "es": "Comisión total de consolidación",
        "nl": "Totale consolidatiekosten",
    },
    "wallet_label": {
        "en": "Wallet:", "ru": "Кошелёк:", "zh": "钱包：", "id": "Dompet:",
        "ko": "지갑:", "es": "Cartera:", "nl": "Portemonnee:",
    },
    "total": {
        "en": "Total:", "ru": "Итого:", "zh": "总计：", "id": "Total:",
        "ko": "합계:", "es": "Total:", "nl": "Totaal:",
    },
    "sent": {
        "en": "Sent", "ru": "Отправлено", "zh": "已发送", "id": "Terkirim",
        "ko": "전송됨", "es": "Enviado", "nl": "Verzonden",
    },
    "send_uncertain": {
        "en": "Send result uncertain", "ru": "Результат отправки неизвестен",
        "zh": "发送结果不确定", "id": "Hasil pengiriman tidak pasti",
        "ko": "전송 결과 불확실", "es": "Resultado de envío incierto",
        "nl": "Verzendresultaat onzeker",
    },
    "first_page": {
        "en": "« First", "ru": "« Первая", "zh": "« 首页", "id": "« Pertama",
        "ko": "« 처음", "es": "« Primera", "nl": "« Eerste",
    },
    "last_page": {
        "en": "Last »", "ru": "Последняя »", "zh": "末页 »", "id": "Terakhir »",
        "ko": "마지막 »", "es": "Última »", "nl": "Laatste »",
    },
    "showing_range": {  # .format(a=, b=)
        "en": "showing {a}–{b}", "ru": "показаны {a}–{b}",
        "zh": "显示 {a}–{b}", "id": "menampilkan {a}–{b}",
        "ko": "{a}–{b} 표시", "es": "mostrando {a}–{b}",
        "nl": "tonen {a}–{b}",
    },
    "consolidation_complete": {
        "en": "Consolidation complete", "ru": "Объединение завершено",
        "zh": "整合完成", "id": "Konsolidasi selesai", "ko": "통합 완료",
        "es": "Consolidación completa", "nl": "Consolidatie voltooid",
    },
    "consolidation_failed": {
        "en": "Consolidation failed", "ru": "Объединение не удалось",
        "zh": "整合失败", "id": "Konsolidasi gagal", "ko": "통합 실패",
        "es": "Consolidación fallida", "nl": "Consolidatie mislukt",
    },
    "nothing_to_consolidate": {
        "en": "Nothing to consolidate", "ru": "Нечего объединять",
        "zh": "无需整合", "id": "Tidak ada yang dikonsolidasi",
        "ko": "통합할 항목 없음", "es": "Nada que consolidar",
        "nl": "Niets te consolideren",
    },
    "no_wallet": {
        "en": "No wallet", "ru": "Нет кошелька", "zh": "无钱包",
        "id": "Tidak ada dompet", "ko": "지갑 없음", "es": "Sin cartera",
        "nl": "Geen portemonnee",
    },
    "open_wallet_first": {
        "en": "Open a wallet first.", "ru": "Сначала откройте кошелёк.",
        "zh": "请先打开钱包。", "id": "Buka dompet terlebih dahulu.",
        "ko": "먼저 지갑을 여세요.", "es": "Abra una cartera primero.",
        "nl": "Open eerst een portemonnee.",
    },
    "export_phrase_title": {
        "en": "Export recovery phrase", "ru": "Экспорт фразы восстановления",
        "zh": "导出助记词", "id": "Ekspor frasa pemulihan",
        "ko": "복구 구문 내보내기", "es": "Exportar frase de recuperación",
        "nl": "Herstelzin exporteren",
    },
    "export_pw_prompt": {
        "en": "Enter your wallet password to reveal the recovery phrase:",
        "ru": "Введите пароль кошелька, чтобы показать фразу восстановления:",
        "zh": "输入钱包密码以显示助记词：",
        "id": "Masukkan kata sandi dompet untuk menampilkan frasa pemulihan:",
        "ko": "복구 구문을 표시하려면 지갑 비밀번호를 입력하세요:",
        "es": "Introduzca la contraseña de su cartera para revelar la frase de recuperación:",
        "nl": "Voer uw portemonneewachtwoord in om de herstelzin te tonen:",
    },
    "recovery_phrase": {
        "en": "Recovery phrase", "ru": "Фраза восстановления", "zh": "助记词",
        "id": "Frasa pemulihan", "ko": "복구 구문", "es": "Frase de recuperación",
        "nl": "Herstelzin",
    },
    "wallet_name_exists": {
        "en": "Wallet name already exists", "ru": "Имя кошелька уже существует",
        "zh": "钱包名称已存在", "id": "Nama dompet sudah ada",
        "ko": "지갑 이름이 이미 존재합니다", "es": "El nombre de la cartera ya existe",
        "nl": "Portemonneenaam bestaat al",
    },
    "import_failed": {
        "en": "Import failed — check the recovery phrase",
        "ru": "Импорт не удался — проверьте фразу восстановления",
        "zh": "导入失败 — 请检查助记词",
        "id": "Impor gagal — periksa frasa pemulihan",
        "ko": "가져오기 실패 — 복구 구문을 확인하세요",
        "es": "Importación fallida — verifique la frase de recuperación",
        "nl": "Importeren mislukt — controleer de herstelzin",
    },
    "create_failed": {
        "en": "Create failed", "ru": "Создание не удалось", "zh": "创建失败",
        "id": "Pembuatan gagal", "ko": "생성 실패", "es": "Creación fallida",
        "nl": "Aanmaken mislukt",
    },
    "connect_failed": {
        "en": "Connect failed", "ru": "Подключение не удалось", "zh": "连接失败",
        "id": "Koneksi gagal", "ko": "연결 실패", "es": "Conexión fallida",
        "nl": "Verbinding mislukt",
    },
    "name_required": {
        "en": "Name required", "ru": "Требуется имя", "zh": "需要名称",
        "id": "Nama diperlukan", "ko": "이름 필요", "es": "Nombre requerido",
        "nl": "Naam vereist",
    },
    "select_enter_name": {
        "en": "Select or enter a wallet name.",
        "ru": "Выберите или введите имя кошелька.",
        "zh": "选择或输入钱包名称。", "id": "Pilih atau masukkan nama dompet.",
        "ko": "지갑 이름을 선택하거나 입력하세요.",
        "es": "Seleccione o introduzca un nombre de cartera.",
        "nl": "Selecteer of voer een portemonneenaam in.",
    },
    "not_connected": {
        "en": "Not connected", "ru": "Не подключено", "zh": "未连接",
        "id": "Tidak terhubung", "ko": "연결되지 않음", "es": "No conectado",
        "nl": "Niet verbonden",
    },
    "connect_before_send": {
        "en": "Connect to a node before sending.",
        "ru": "Подключитесь к узлу перед отправкой.",
        "zh": "发送前请先连接节点。", "id": "Hubungkan ke node sebelum mengirim.",
        "ko": "보내기 전에 노드에 연결하세요.",
        "es": "Conéctese a un nodo antes de enviar.",
        "nl": "Maak verbinding met een node voordat u verzendt.",
    },
    # ── Create / Import / Export dialogs ─────────────────────────────────
    "create_wallet": {
        "en": "Create wallet", "ru": "Создать кошелёк", "zh": "创建钱包",
        "id": "Buat dompet", "ko": "지갑 만들기", "es": "Crear cartera",
        "nl": "Portemonnee aanmaken",
    },
    "import_wallet": {
        "en": "Import wallet", "ru": "Импорт кошелька", "zh": "导入钱包",
        "id": "Impor dompet", "ko": "지갑 가져오기", "es": "Importar cartera",
        "nl": "Portemonnee importeren",
    },
    "wallet_name": {
        "en": "Wallet name:", "ru": "Имя кошелька:", "zh": "钱包名称：",
        "id": "Nama dompet:", "ko": "지갑 이름:", "es": "Nombre de cartera:",
        "nl": "Portemonneenaam:",
    },
    "account_title": {
        "en": "Account title:", "ru": "Название счёта:", "zh": "账户名称：",
        "id": "Judul akun:", "ko": "계정 제목:", "es": "Título de cuenta:",
        "nl": "Accounttitel:",
    },
    "phishing_hint": {
        "en": "Phishing hint:", "ru": "Анти-фишинг подсказка:", "zh": "防钓鱼提示：",
        "id": "Petunjuk anti-phishing:", "ko": "피싱 방지 힌트:",
        "es": "Pista antiphishing:", "nl": "Antiphishing-hint:",
    },
    "encryption_password": {
        "en": "Encryption password:", "ru": "Пароль шифрования:",
        "zh": "加密密码：", "id": "Kata sandi enkripsi:", "ko": "암호화 비밀번호:",
        "es": "Contraseña de cifrado:", "nl": "Versleutelingswachtwoord:",
    },
    "new_password": {
        "en": "New password:", "ru": "Новый пароль:", "zh": "新密码：",
        "id": "Kata sandi baru:", "ko": "새 비밀번호:", "es": "Nueva contraseña:",
        "nl": "Nieuw wachtwoord:",
    },
    "confirm_password": {
        "en": "Confirm password:", "ru": "Подтвердите пароль:", "zh": "确认密码：",
        "id": "Konfirmasi kata sandi:", "ko": "비밀번호 확인:",
        "es": "Confirmar contraseña:", "nl": "Bevestig wachtwoord:",
    },
    "bip39_passphrase": {
        "en": "BIP39 passphrase:", "ru": "BIP39 парольная фраза:",
        "zh": "BIP39 密码短语：", "id": "Frasa sandi BIP39:", "ko": "BIP39 암호:",
        "es": "Frase de contraseña BIP39:", "nl": "BIP39-wachtwoordzin:",
    },
    "recovery_phrase_label": {
        "en": "Recovery phrase (12 or 24 words, space-separated):",
        "ru": "Фраза восстановления (12 или 24 слова через пробел):",
        "zh": "助记词（12 或 24 个单词，用空格分隔）：",
        "id": "Frasa pemulihan (12 atau 24 kata, dipisahkan spasi):",
        "ko": "복구 구문 (12 또는 24단어, 공백으로 구분):",
        "es": "Frase de recuperación (12 o 24 palabras, separadas por espacios):",
        "nl": "Herstelzin (12 of 24 woorden, gescheiden door spaties):",
    },
    "mnemonic_label": {
        "en": "Recovery phrase (mnemonic):", "ru": "Фраза восстановления (мнемоника):",
        "zh": "助记词：", "id": "Frasa pemulihan (mnemonik):",
        "ko": "복구 구문 (니모닉):", "es": "Frase de recuperación (mnemónica):",
        "nl": "Herstelzin (mnemonic):",
    },
    "xpub_label": {
        "en": "Extended public key (xpub):", "ru": "Расширенный публичный ключ (xpub):",
        "zh": "扩展公钥 (xpub)：", "id": "Kunci publik diperluas (xpub):",
        "ko": "확장 공개키 (xpub):", "es": "Clave pública extendida (xpub):",
        "nl": "Uitgebreide publieke sleutel (xpub):",
    },
    "deposit_address": {
        "en": "Deposit address:", "ru": "Адрес для пополнения:", "zh": "存款地址：",
        "id": "Alamat setoran:", "ko": "입금 주소:", "es": "Dirección de depósito:",
        "nl": "Stortingsadres:",
    },
    "exported_phrase_title": {
        "en": "Exported recovery phrase", "ru": "Экспортированная фраза восстановления",
        "zh": "已导出的助记词", "id": "Frasa pemulihan yang diekspor",
        "ko": "내보낸 복구 구문", "es": "Frase de recuperación exportada",
        "nl": "Geëxporteerde herstelzin",
    },
    "backup_phrase_title": {
        "en": "Back up your recovery phrase", "ru": "Сохраните фразу восстановления",
        "zh": "备份您的助记词", "id": "Cadangkan frasa pemulihan Anda",
        "ko": "복구 구문을 백업하세요", "es": "Respalde su frase de recuperación",
        "nl": "Maak een back-up van uw herstelzin",
    },
    "done": {
        "en": "Done", "ru": "Готово", "zh": "完成", "id": "Selesai",
        "ko": "완료", "es": "Hecho", "nl": "Klaar",
    },
    "continue_btn": {
        "en": "Continue", "ru": "Продолжить", "zh": "继续", "id": "Lanjutkan",
        "ko": "계속", "es": "Continuar", "nl": "Doorgaan",
    },
    "optional": {
        "en": "optional", "ru": "необязательно", "zh": "可选", "id": "opsional",
        "ko": "선택 사항", "es": "opcional", "nl": "optioneel",
    },
    "phrase_word_count_error": {  # .format(n=)
        "en": "Phrase must be 12 or 24 words (got {n})",
        "ru": "Фраза должна содержать 12 или 24 слова (получено {n})",
        "zh": "助记词必须为 12 或 24 个单词（实际 {n} 个）",
        "id": "Frasa harus 12 atau 24 kata (dapat {n})",
        "ko": "구문은 12 또는 24단어여야 합니다 ({n}개 입력됨)",
        "es": "La frase debe tener 12 o 24 palabras (se obtuvieron {n})",
        "nl": "Zin moet 12 of 24 woorden bevatten ({n} ontvangen)",
    },
    "passwords_no_match": {
        "en": "Passwords do not match.", "ru": "Пароли не совпадают.",
        "zh": "密码不匹配。", "id": "Kata sandi tidak cocok.",
        "ko": "비밀번호가 일치하지 않습니다.", "es": "Las contraseñas no coinciden.",
        "nl": "Wachtwoorden komen niet overeen.",
    },
    "password_required": {
        "en": "Encryption password is required.",
        "ru": "Требуется пароль шифрования.", "zh": "需要加密密码。",
        "id": "Kata sandi enkripsi diperlukan.", "ko": "암호화 비밀번호가 필요합니다.",
        "es": "Se requiere una contraseña de cifrado.",
        "nl": "Versleutelingswachtwoord is vereist.",
    },
    "create_intro": {
        "en": "// new wallet — always named, never overwrites an existing one",
        "ru": "// новый кошелёк — всегда с именем, не перезаписывает существующий",
        "zh": "// 新钱包 — 始终命名，绝不覆盖现有钱包",
        "id": "// dompet baru — selalu diberi nama, tidak menimpa yang sudah ada",
        "ko": "// 새 지갑 — 항상 이름이 지정되며 기존 지갑을 덮어쓰지 않음",
        "es": "// cartera nueva — siempre con nombre, nunca sobrescribe una existente",
        "nl": "// nieuwe portemonnee — altijd benoemd, overschrijft nooit een bestaande",
    },
    "import_intro": {
        "en": "// import an existing wallet from its 12 or 24-word recovery phrase",
        "ru": "// импорт существующего кошелька из фразы восстановления 12 или 24 слов",
        "zh": "// 通过 12 或 24 个助记词导入现有钱包",
        "id": "// impor dompet yang ada dari frasa pemulihan 12 atau 24 kata",
        "ko": "// 12 또는 24단어 복구 구문으로 기존 지갑 가져오기",
        "es": "// importar una cartera existente desde su frase de recuperación de 12 o 24 palabras",
        "nl": "// importeer een bestaande portemonnee via de herstelzin van 12 of 24 woorden",
    },
    "ph_optional_skip": {
        "en": "optional (press create to skip)",
        "ru": "необязательно (нажмите «создать», чтобы пропустить)",
        "zh": "可选（点击创建以跳过）",
        "id": "opsional (tekan buat untuk melewati)",
        "ko": "선택 사항 (건너뛰려면 만들기를 누르세요)",
        "es": "opcional (pulse crear para omitir)",
        "nl": "optioneel (druk op aanmaken om over te slaan)",
    },
    "ph_antiphishing": {
        "en": "optional anti-phishing word/phrase",
        "ru": "необязательное анти-фишинг слово/фраза",
        "zh": "可选的防钓鱼词/短语",
        "id": "kata/frasa anti-phishing opsional",
        "ko": "선택적 피싱 방지 단어/구문",
        "es": "palabra/frase antiphishing opcional",
        "nl": "optioneel antiphishing-woord/zin",
    },
    "ph_bip39_create": {
        "en": "optional — REQUIRED to spend if set",
        "ru": "необязательно — ОБЯЗАТЕЛЬНО для траты, если задано",
        "zh": "可选 — 一旦设置，花费时必填",
        "id": "opsional — WAJIB untuk membelanjakan jika diatur",
        "ko": "선택 사항 — 설정 시 사용에 필수",
        "es": "opcional — OBLIGATORIA para gastar si se establece",
        "nl": "optioneel — VEREIST om uit te geven indien ingesteld",
    },
    "ph_bip39_import": {
        "en": "only if the original wallet used one",
        "ru": "только если оригинальный кошелёк её использовал",
        "zh": "仅当原钱包使用了密码短语时",
        "id": "hanya jika dompet asli menggunakannya",
        "ko": "원래 지갑이 사용한 경우에만",
        "es": "solo si la cartera original usó una",
        "nl": "alleen als de oorspronkelijke portemonnee er een gebruikte",
    },
    "ph_letters_digits": {
        "en": "letters, digits, _ -", "ru": "буквы, цифры, _ -",
        "zh": "字母、数字、_ -", "id": "huruf, angka, _ -",
        "ko": "문자, 숫자, _ -", "es": "letras, dígitos, _ -",
        "nl": "letters, cijfers, _ -",
    },
    "ph_word_list": {
        "en": "word1 word2 word3 …", "ru": "слово1 слово2 слово3 …",
        "zh": "单词1 单词2 单词3 …", "id": "kata1 kata2 kata3 …",
        "ko": "단어1 단어2 단어3 …", "es": "palabra1 palabra2 palabra3 …",
        "nl": "woord1 woord2 woord3 …",
    },
    "create_pw_note": {
        "en": "The encryption password is required. If you set a BIP39 passphrase, you will need it to spend and to recover — losing it means losing the wallet.",
        "ru": "Пароль шифрования обязателен. Если вы зададите BIP39-фразу, она понадобится для траты и восстановления — её потеря означает потерю кошелька.",
        "zh": "加密密码为必填项。如果您设置了 BIP39 密码短语，则花费和恢复时都需要它 — 丢失它意味着丢失钱包。",
        "id": "Kata sandi enkripsi wajib diisi. Jika Anda mengatur frasa sandi BIP39, Anda memerlukannya untuk membelanjakan dan memulihkan — kehilangannya berarti kehilangan dompet.",
        "ko": "암호화 비밀번호는 필수입니다. BIP39 암호를 설정하면 사용 및 복구에 필요하며, 분실하면 지갑을 잃게 됩니다.",
        "es": "La contraseña de cifrado es obligatoria. Si establece una frase de contraseña BIP39, la necesitará para gastar y recuperar — perderla significa perder la cartera.",
        "nl": "Het versleutelingswachtwoord is vereist. Als u een BIP39-wachtwoordzin instelt, hebt u die nodig om uit te geven en te herstellen — kwijtraken betekent de portemonnee kwijtraken.",
    },
    "import_pw_note": {
        "en": "If the original wallet used a BIP39 passphrase, you must enter the same one above or a different key will be derived. The new password encrypts this wallet on this machine.",
        "ru": "Если оригинальный кошелёк использовал BIP39-фразу, введите ту же самую выше, иначе будет получен другой ключ. Новый пароль шифрует этот кошелёк на этом компьютере.",
        "zh": "如果原钱包使用了 BIP39 密码短语，您必须在上方输入相同的短语，否则将派生出不同的密钥。新密码用于在本机加密此钱包。",
        "id": "Jika dompet asli menggunakan frasa sandi BIP39, Anda harus memasukkan yang sama di atas atau kunci yang berbeda akan diturunkan. Kata sandi baru mengenkripsi dompet ini di mesin ini.",
        "ko": "원래 지갑이 BIP39 암호를 사용했다면 위에 동일한 것을 입력해야 하며, 그렇지 않으면 다른 키가 파생됩니다. 새 비밀번호는 이 컴퓨터에서 이 지갑을 암호화합니다.",
        "es": "Si la cartera original usó una frase de contraseña BIP39, debe introducir la misma arriba o se derivará una clave diferente. La nueva contraseña cifra esta cartera en esta máquina.",
        "nl": "Als de oorspronkelijke portemonnee een BIP39-wachtwoordzin gebruikte, moet u dezelfde hierboven invoeren, anders wordt een andere sleutel afgeleid. Het nieuwe wachtwoord versleutelt deze portemonnee op deze machine.",
    },
    "export_warning": {
        "en": "This is your wallet's recovery phrase. Anyone who sees it can take your funds. Make sure no one is watching your screen. This app does not store it.",
        "ru": "Это фраза восстановления вашего кошелька. Любой, кто её увидит, может забрать ваши средства. Убедитесь, что никто не смотрит на экран. Это приложение её не хранит.",
        "zh": "这是您钱包的助记词。任何看到它的人都能取走您的资金。请确保无人窥视您的屏幕。本应用不会存储它。",
        "id": "Ini adalah frasa pemulihan dompet Anda. Siapa pun yang melihatnya dapat mengambil dana Anda. Pastikan tidak ada yang melihat layar Anda. Aplikasi ini tidak menyimpannya.",
        "ko": "이것은 지갑의 복구 구문입니다. 이를 보는 사람은 누구나 자금을 가져갈 수 있습니다. 화면을 보는 사람이 없는지 확인하세요. 이 앱은 이를 저장하지 않습니다.",
        "es": "Esta es la frase de recuperación de su cartera. Cualquiera que la vea puede tomar sus fondos. Asegúrese de que nadie esté mirando su pantalla. Esta aplicación no la almacena.",
        "nl": "Dit is de herstelzin van uw portemonnee. Iedereen die het ziet, kan uw geld nemen. Zorg ervoor dat niemand naar uw scherm kijkt. Deze app slaat het niet op.",
    },
    "backup_warning": {
        "en": "Write this recovery phrase down and store it offline. Anyone with it controls your funds. It will NOT be shown again and is not saved by this app.",
        "ru": "Запишите эту фразу восстановления и храните её офлайн. Любой, у кого она есть, контролирует ваши средства. Она НЕ будет показана снова и не сохраняется этим приложением.",
        "zh": "请将此助记词写下并离线保存。任何持有它的人都能控制您的资金。它不会再次显示，本应用也不会保存。",
        "id": "Tuliskan frasa pemulihan ini dan simpan secara offline. Siapa pun yang memilikinya mengendalikan dana Anda. Frasa ini TIDAK akan ditampilkan lagi dan tidak disimpan oleh aplikasi ini.",
        "ko": "이 복구 구문을 적어서 오프라인에 보관하세요. 이를 가진 사람은 누구나 자금을 통제합니다. 다시 표시되지 않으며 이 앱에 저장되지 않습니다.",
        "es": "Anote esta frase de recuperación y guárdela sin conexión. Cualquiera que la tenga controla sus fondos. NO se mostrará de nuevo y esta aplicación no la guarda.",
        "nl": "Schrijf deze herstelzin op en bewaar deze offline. Iedereen die het heeft, beheert uw geld. Het wordt NIET opnieuw getoond en wordt niet door deze app opgeslagen.",
    },
    "ack_written": {
        "en": "I have written down my recovery phrase and stored it safely.",
        "ru": "Я записал(а) свою фразу восстановления и надёжно её сохранил(а).",
        "zh": "我已写下助记词并妥善保管。",
        "id": "Saya telah menuliskan frasa pemulihan saya dan menyimpannya dengan aman.",
        "ko": "복구 구문을 적어 안전하게 보관했습니다.",
        "es": "He anotado mi frase de recuperación y la he guardado de forma segura.",
        "nl": "Ik heb mijn herstelzin opgeschreven en veilig opgeborgen.",
    },
    "ph_amount": {
        "en": "amount (KRX)", "ru": "сумма (KRX)", "zh": "金额 (KRX)",
        "id": "jumlah (KRX)", "ko": "금액 (KRX)", "es": "cantidad (KRX)",
        "nl": "bedrag (KRX)",
    },
    "connected": {
        "en": "Connected", "ru": "Подключено", "zh": "已连接",
        "id": "Terhubung", "ko": "연결됨", "es": "Conectado", "nl": "Verbonden",
    },
    "disconnected": {
        "en": "Disconnected", "ru": "Отключено", "zh": "未连接",
        "id": "Terputus", "ko": "연결 끊김", "es": "Desconectado",
        "nl": "Niet verbonden",
    },
    "connection_failed": {
        "en": "Connection failed", "ru": "Не удалось подключиться",
        "zh": "连接失败", "id": "Koneksi gagal", "ko": "연결 실패",
        "es": "Conexión fallida", "nl": "Verbinding mislukt",
    },
    "insufficient_funds": {
        "en": "Insufficient funds", "ru": "Недостаточно средств",
        "zh": "余额不足", "id": "Dana tidak cukup", "ko": "잔액 부족",
        "es": "Fondos insuficientes", "nl": "Onvoldoende saldo",
    },
    "ph_priority_fee": {
        "en": "priority fee (KRX)", "ru": "приоритетная комиссия (KRX)",
        "zh": "优先手续费 (KRX)", "id": "biaya prioritas (KRX)",
        "ko": "우선 수수료 (KRX)", "es": "comisión prioritaria (KRX)",
        "nl": "prioriteitskosten (KRX)",
    },
    "address_book": {
        "en": "Address book", "ru": "Адресная книга", "zh": "地址簿",
        "id": "Buku alamat", "ko": "주소록", "es": "Libreta de direcciones",
        "nl": "Adresboek",
    },
    "ab_label": {
        "en": "label", "ru": "метка", "zh": "标签", "id": "label",
        "ko": "레이블", "es": "etiqueta", "nl": "label",
    },
    "ab_address": {
        "en": "keryx address", "ru": "адрес keryx", "zh": "keryx 地址",
        "id": "alamat keryx", "ko": "keryx 주소", "es": "dirección keryx",
        "nl": "keryx-adres",
    },
    "ab_save": {
        "en": "Save", "ru": "Сохранить", "zh": "保存", "id": "Simpan",
        "ko": "저장", "es": "Guardar", "nl": "Opslaan",
    },
    "ab_delete": {
        "en": "Delete", "ru": "Удалить", "zh": "删除", "id": "Hapus",
        "ko": "삭제", "es": "Eliminar", "nl": "Verwijderen",
    },
    "ab_use": {
        "en": "Use", "ru": "Выбрать", "zh": "使用", "id": "Gunakan",
        "ko": "사용", "es": "Usar", "nl": "Gebruiken",
    },
    "amount_zero": {
        "en": "Amount cannot be zero", "ru": "Сумма не может быть нулевой",
        "zh": "金额不能为零", "id": "Jumlah tidak boleh nol",
        "ko": "금액은 0일 수 없습니다", "es": "La cantidad no puede ser cero",
        "nl": "Bedrag kan niet nul zijn",
    },
    "invalid_address": {
        "en": "Invalid address", "ru": "Неверный адрес", "zh": "无效地址",
        "id": "Alamat tidak valid", "ko": "잘못된 주소",
        "es": "Dirección no válida", "nl": "Ongeldig adres",
    },
    "amount_too_small": {
        "en": "Amount is too small", "ru": "Сумма слишком мала",
        "zh": "金额太小", "id": "Jumlah terlalu kecil",
        "ko": "금액이 너무 적습니다", "es": "La cantidad es demasiado pequeña",
        "nl": "Bedrag is te klein",
    },
    "missing_fields": {
        "en": "Missing fields", "ru": "Незаполненные поля", "zh": "缺少字段",
        "id": "Bidang yang hilang", "ko": "누락된 필드",
        "es": "Campos faltantes", "nl": "Ontbrekende velden",
    },
    "fields_required": {
        "en": "Destination, amount, and priority fee are required.",
        "ru": "Требуются адрес получателя, сумма и приоритетная комиссия.",
        "zh": "需要填写收款地址、金额和优先手续费。",
        "id": "Alamat tujuan, jumlah, dan biaya prioritas wajib diisi.",
        "ko": "받는 주소, 금액, 우선 수수료가 필요합니다.",
        "es": "Se requieren dirección de destino, cantidad y comisión prioritaria.",
        "nl": "Bestemmingsadres, bedrag en prioriteitskosten zijn vereist.",
    },
    "swept_result": {  # .format(u=, b=, fees=)
        "en": "Swept {u} UTXOs in {b} batches.\nFees: {fees} KRX",
        "ru": "Объединено {u} UTXO в {b} пакетах.\nКомиссия: {fees} KRX",
        "zh": "已在 {b} 个批次中整合 {u} 个 UTXO。\n手续费：{fees} KRX",
        "id": "Menyapu {u} UTXO dalam {b} batch.\nBiaya: {fees} KRX",
        "ko": "{b}개 배치로 {u}개의 UTXO를 통합했습니다.\n수수료: {fees} KRX",
        "es": "Se consolidaron {u} UTXO en {b} lotes.\nComisión: {fees} KRX",
        "nl": "{u} UTXO's geconsolideerd in {b} batches.\nKosten: {fees} KRX",
    },
}


def set_language(lang: str):
    global _current
    if lang in LANGUAGES:
        _current = lang


def get_language() -> str:
    return _current


def t(key: str, **kwargs) -> str:
    """Translate a key to the active language, falling back to English then key.
    Supports str.format kwargs (e.g. t('tx_count', n=5))."""
    entry = _T.get(key)
    if not entry:
        return key
    text = entry.get(_current) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
