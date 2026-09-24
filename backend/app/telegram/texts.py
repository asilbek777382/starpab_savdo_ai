ONBOARDING = (
    "Assalomu alaykum! <b>{shop}</b> do'koni uchun Navbatchi AI yaratildi. 14 kunlik bepul sinov boshlandi.\n\n"
    "Ishga tushirish:\n"
    "1. Katalog va do'kon ma'lumotlarini (manzil, yetkazib berish, to'lov) kiriting.\n"
    "2. Telegram Business'ga ulang: Sozlamalar → Telegram Business → Chatbots → <code>@{bot}</code>. "
    '"Xabarlarga javob berish" ruxsatini yoqing.\n'
    "3. Business'siz ishlash uchun mijozlarga havola bering: {link}\n\n"
    "Buyruqlar: /status — holat, /mode — AI rejimi (sotish yoki lid yig'ish), /tasks — AI vazifalari, "
    "/ai_off — AI'ni to'xtatish, /ai_on — yoqish, /help — yordam."
)
HELP = (
    "Buyruqlar:\n/status — do'kon holati\n"
    "/mode sell — AI buyurtmagacha sotadi\n/mode lead — AI tanishtiradi, telefon raqamini olib operatorga beradi\n"
    "/tasks <matn> — AI uchun vazifalar (ssenariy)\n"
    "/leads_here — operatorlar guruhida yozing: lidlar shu guruhga keladi\n"
    "/ai_on — AI'ni yoqish\n/ai_off — AI'ni to'xtatish\n\n"
    "Sotuvchi o'zi mijozga yozsa, AI shu suhbatda 30 daqiqa jim turadi."
)
CUSTOMER_WELCOME = "Assalomu alaykum! {shop} do'koniga xush kelibsiz. Savolingizni yozing."
CUSTOMER_NO_SHOP = "Iltimos, do'kon bergan havola orqali kiring."
BUSINESS_CONNECTED = "✅ Telegram Business ulandi. Navbatchi AI endi <b>{shop}</b> nomidan mijozlarga javob beradi."
BUSINESS_NO_REPLY = (
    "⚠️ Bot ulandi, lekin \"xabarlarga javob berish\" ruxsati yo'q. Telegram Business → Chatbots bo'limida "
    "ruxsatni yoqing, aks holda AI javob bera olmaydi."
)
BUSINESS_DISCONNECTED = "ℹ️ Telegram Business ulanishi o'chirildi. Navbatchi AI shaxsiy chatlarda javob bermaydi."
ORDER_CONFIRMED_CUSTOMER = "Buyurtmangiz #{number} tasdiqlandi. Tez orada siz bilan bog'lanamiz. Rahmat!"
ORDER_CANCELLED_CUSTOMER = "Afsuski, buyurtmangiz #{number} bekor qilindi. Savollar bo'lsa, shu yerga yozing."
ORDER_SHIPPED_CUSTOMER = "Buyurtmangiz #{number} yo'lga chiqdi."
