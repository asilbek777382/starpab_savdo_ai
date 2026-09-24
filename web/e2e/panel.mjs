// Panel E2E: node e2e/panel.mjs <base_url> <out_dir>
// Oldindan: backend (8000) va `vite preview` (4173) ishlab turishi kerak.
import { execFileSync } from "node:child_process";
import { chromium } from "playwright";

const [base = "http://localhost:4173", out = "."] = process.argv.slice(2);
const phone = `9${Math.floor(10_000_000 + Math.random() * 89_999_999)}`;
const password = "e2e-parol-123";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
page.on("pageerror", (e) => console.error("PAGE ERROR:", e.message));
const step = (name) => console.log("✓", name);
const nav = (name) => page.getByRole("navigation").getByRole("link", { name, exact: true }).click();
const shot = (name) => page.screenshot({ path: `${out}/panel-${name}.png`, fullPage: true });

// 1. Landing → ro'yxatdan o'tish
await page.addInitScript(() => localStorage.setItem("nv_lang", "uz"));
await page.goto(base + "/");
await page.getByRole("link", { name: "Bepul boshlash" }).first().click();
await page.waitForURL("**/app/register");
await page.getByLabel("Ismingiz").fill("Dilnoza");
await page.getByLabel("Do'kon nomi").fill("Dilnoza Style");
await page.getByLabel("Telefon raqam").fill(phone);
await page.getByLabel("Parol").fill(password);
await shot("register");
await page.getByRole("button", { name: "Ro'yxatdan o'tish" }).click();
await page.getByRole("heading", { name: "Bosh sahifa" }).waitFor();
await page.getByText("Ishga tushirish").waitFor();
await page.getByText("Bepul sinov:").waitFor();
await page.getByText("Oylik limit").waitFor();
await shot("dashboard-new");
step("register → dashboard (checklist, trial banner)");

// 2. Katalog: mahsulot qo'shish
await nav("Katalog");
await page.getByRole("button", { name: "+ Mahsulot qo'shish" }).click();
const dialog = page.getByRole("dialog");
await dialog.getByLabel("Nomi").fill("Qora ko'ylak");
await dialog.getByLabel("Narx (so'm)").fill("250000");
await dialog.getByLabel("Kategoriya").fill("Ko'ylaklar");
await dialog.getByRole("button", { name: "+ Variant qo'shish" }).click();
await dialog.getByPlaceholder("Razmer").fill("42");
await dialog.getByPlaceholder("Rang").fill("qora");
await dialog.getByPlaceholder("Qoldiq").fill("3");
await shot("product-editor");
await dialog.getByRole("button", { name: "Saqlash" }).click();
await dialog.waitFor({ state: "detached" });
await page.getByText("250 000 so'm").waitFor();
await shot("catalog");
step("catalog: product created");

// 3. Do'kon ma'lumotlari
await nav("Do'kon ma'lumotlari");
await page.getByLabel("Manzil").fill("Toshkent, Chilonzor 9");
await page.getByLabel("To'lov usullari").fill("Naqd, Click, Payme");
await page.getByRole("button", { name: "+ Hudud qo'shish" }).click();
await page.getByLabel("Hudud").fill("Toshkent shahri");
await page.getByLabel("Kalit so'zlar (vergul bilan)").fill("toshkent, chilonzor");
await page.getByLabel("Narx", { exact: true }).fill("20000");
await page.getByRole("button", { name: "Saqlash" }).click();
await page.getByText("✓ Saqlandi").waitFor();
await shot("shop-settings");
step("shop settings saved");

// 4. AI sozlamalari: lid rejimi + vazifalar
await nav("AI sozlamalari");
await page.getByRole("radio", { name: /Lid yig'ish/ }).click();
await page.getByLabel("Vazifalar (ssenariy)").fill("Avval yangi kolleksiyani tanishtir, keyin telefon raqamini so'ra.");
await page.getByRole("button", { name: "Saqlash" }).click();
await page.getByText("✓ Saqlandi").waitFor();
await shot("ai-settings");
await page.reload();
if (!(await page.getByRole("radio", { name: /Lid yig'ish/ }).getAttribute("aria-checked")).includes("true"))
  throw new Error("AI rejimi saqlanmadi");
step("ai settings (lead mode, tasks) persisted");

// 5. Test chat (LLM kaliti yo'q → zaxira javob)
await nav("Test chat");
await page.getByLabel(/Masalan/).fill("Qora ko'ylak 42 razmer bormi?");
await page.getByRole("button", { name: "Yuborish" }).click();
await page.getByText("Xabaringiz qabul qilindi", { exact: false }).waitFor({ timeout: 60_000 });
await shot("test-chat");
step("test chat round-trip");

// 6. Suhbatlar, buyurtmalar, lidlar, ulash
await nav("Suhbatlar");
await page.getByRole("button", { name: /Test mijoz/ }).click();
await page.getByText("Qora ko'ylak 42 razmer bormi?").waitFor();
await shot("conversations");
await nav("Buyurtmalar");
await page.getByText("Hozircha hech narsa yo'q").waitFor();
await nav("Lidlar");
await page.getByRole("heading", { name: "Lidlar" }).waitFor();
await nav("Ulash");
await page.getByText("shop_").first().waitFor();
await shot("connect");
step("conversations / orders / leads / connect pages");

// 7. Dashboard (grafik) va rus tili
await nav("Bosh sahifa");
await page.getByText("Kunlar bo'yicha").waitFor();
await page.getByText("Oylik limit").waitFor();
await page.locator("figure svg").first().waitFor();
await shot("dashboard");
await page.getByRole("button", { name: "RU", exact: true }).first().click();
await page.getByRole("heading", { name: "Главная" }).waitFor();
await page.getByText("Месячный лимит").waitFor();
await shot("dashboard-ru");
await page.getByRole("button", { name: "UZ", exact: true }).first().click();
step("dashboard + language switch");

// 8. Chiqish → kirish
await page.getByRole("button", { name: "Chiqish" }).click();
await page.waitForURL("**/app/login");
await page.getByLabel("Telefon raqam").fill(phone);
await page.getByLabel("Parol").fill("noto'g'ri-parol");
await page.getByRole("button", { name: "Kirish" }).click();
await page.getByRole("alert").waitFor();
await page.getByLabel("Parol").fill(password);
await page.getByRole("button", { name: "Kirish" }).click();
await page.getByRole("heading", { name: "Bosh sahifa" }).waitFor();
step("logout → wrong password → login");

// 9. Platforma admini
execFileSync("uv", ["run", "python", "-m", "app.cli", "make-admin", phone], { cwd: "../backend", stdio: "inherit" });
await page.goto(base + "/app/admin");
await page.getByRole("heading", { name: "Platforma admini" }).waitFor();
await page.getByRole("cell", { name: "Dilnoza Style" }).first().click(); // eng yangisi yuqorida
await page.getByRole("dialog").getByLabel("Izoh (chek raqami)").fill("chek #1");
await page.getByRole("dialog").getByRole("button", { name: "To'lov qo'shish" }).click();
await page.getByRole("dialog").getByText("299 000 so'm").waitFor();
await page.keyboard.press("Escape");
await page.getByRole("cell", { name: "business" }).first().waitFor();
await shot("admin");
step("platform admin: manual payment → plan business");

// 10. Telefon kengligi
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(base + "/app/");
await page.getByRole("heading", { name: "Bosh sahifa" }).waitFor();
await page.getByText("Oylik limit").waitFor();
await shot("mobile-dashboard");
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
if (overflow > 1) throw new Error(`mobil gorizontal overflow: ${overflow}px`);
await page.getByRole("button", { name: "Menyu" }).click();
await shot("mobile-menu");
step("mobile layout");

await browser.close();
console.log("E2E OK");
