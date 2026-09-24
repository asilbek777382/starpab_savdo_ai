import "../styles.css";
import { ru } from "./ru";

type Lang = "uz" | "ru";
const STORAGE_KEY = "nv_lang";

// O'zbekcha matnlar HTML'dan olinadi, shunda qayta almashtirish mumkin
const uz: Record<string, string> = {};
document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
  uz[el.dataset.i18n!] ??= el.textContent!.trim();
});
uz["demo.typing"] = "yozmoqda…";
uz["demo.online"] = "onlayn";

function readLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "uz" || saved === "ru") return saved;
  } catch {
    /* localStorage yopiq bo'lishi mumkin */
  }
  return navigator.language?.startsWith("ru") ? "ru" : "uz";
}

let lang: Lang = readLang();
const dict = () => (lang === "ru" ? ru : uz);

function applyLang(next: Lang) {
  lang = next;
  document.documentElement.lang = next;
  document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    const text = dict()[el.dataset.i18n!];
    if (text) el.textContent = text;
  });
  document.querySelectorAll<HTMLButtonElement>(".lang-btn").forEach((b) => {
    const active = b.dataset.lang === next;
    b.classList.toggle("bg-brand-700", active);
    b.classList.toggle("text-white", active);
    b.classList.toggle("text-slate-500", !active);
    b.setAttribute("aria-pressed", String(active));
  });
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* e'tiborsiz */
  }
  startDemo();
}

document.querySelectorAll<HTMLButtonElement>(".lang-btn").forEach((b) =>
  b.addEventListener("click", () => applyLang(b.dataset.lang as Lang)),
);
document.getElementById("year")!.textContent = String(new Date().getFullYear());

// ---------- Demo suhbat ----------
type Line = { from: "client" | "ai" | "photo" | "order"; text: string };

const SCRIPTS: Record<Lang, Line[]> = {
  uz: [
    { from: "client", text: "Assalomu alaykum, qora ko'ylak 42 razmer bormi?" },
    { from: "ai", text: "Va alaykum assalom! Ha, bor 😊 Qora paxtali ko'ylak — 250 000 so'm. Rasmini yuboryapman." },
    { from: "photo", text: "Qora ko'ylak · 42, 46" },
    { from: "client", text: "Olaman. Chilonzor 9, Aziza, 90 123 45 67" },
    { from: "ai", text: "Ko'ylak (42) — 250 000 + yetkazish 20 000 = 270 000 so'm. Manzil: Chilonzor 9. Hammasi to'g'rimi?" },
    { from: "client", text: "Ha, to'g'ri" },
    { from: "order", text: "✅ Buyurtma #128 qabul qilindi. Ertaga yetkazamiz!" },
  ],
  ru: [
    { from: "client", text: "Здравствуйте, чёрное платье 42 размера есть?" },
    { from: "ai", text: "Здравствуйте! Да, есть 😊 Чёрное хлопковое платье — 250 000 сум. Отправляю фото." },
    { from: "photo", text: "Чёрное платье · 42, 46" },
    { from: "client", text: "Беру. Чиланзар 9, Азиза, 90 123 45 67" },
    { from: "ai", text: "Платье (42) — 250 000 + доставка 20 000 = 270 000 сум. Адрес: Чиланзар 9. Всё верно?" },
    { from: "client", text: "Да, верно" },
    { from: "order", text: "✅ Заказ #128 принят. Доставим завтра!" },
  ],
};

const chat = document.getElementById("demo-chat")!;
const status = document.getElementById("demo-status")!;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let runId = 0;

function bubble(line: Line): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = `pop-in flex ${line.from === "client" ? "justify-end" : "justify-start"}`;
  const b = document.createElement("div");
  if (line.from === "photo") {
    b.className = "w-44 overflow-hidden rounded-2xl rounded-bl-md bg-white shadow-sm";
    b.innerHTML =
      '<div class="flex h-28 items-end justify-center bg-gradient-to-b from-slate-700 to-ink pb-2">' +
      '<div class="h-20 w-14 rounded-t-[1.6rem] rounded-b-md bg-slate-900 ring-2 ring-slate-600"></div></div>';
    const cap = document.createElement("p");
    cap.className = "px-2.5 py-1.5 text-xs text-slate-600";
    cap.textContent = line.text;
    b.appendChild(cap);
  } else {
    const base = "max-w-[82%] rounded-2xl px-3 py-2 shadow-sm";
    b.className =
      line.from === "client"
        ? `${base} rounded-br-md bg-[#D9FDD3] text-slate-800`
        : line.from === "order"
          ? `${base} rounded-bl-md bg-brand-700 font-medium text-white`
          : `${base} rounded-bl-md bg-white text-slate-800`;
    b.textContent = line.text;
  }
  wrap.appendChild(b);
  return wrap;
}

function typing(): HTMLElement {
  const el = document.createElement("div");
  el.className = "pop-in flex justify-start";
  el.innerHTML =
    '<div class="typing flex gap-1 rounded-2xl rounded-bl-md bg-white px-3 py-3 shadow-sm">' +
    '<span class="h-1.5 w-1.5 rounded-full bg-slate-400"></span><span class="h-1.5 w-1.5 rounded-full bg-slate-400"></span>' +
    '<span class="h-1.5 w-1.5 rounded-full bg-slate-400"></span></div>';
  return el;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, reduceMotion ? 0 : ms));

async function startDemo() {
  const id = ++runId;
  const lines = SCRIPTS[lang];
  while (id === runId) {
    chat.replaceChildren();
    for (const line of lines) {
      if (id !== runId) return;
      if (line.from !== "client") {
        const t = typing();
        chat.appendChild(t);
        status.textContent = dict()["demo.typing"];
        await sleep(1100);
        t.remove();
        status.textContent = dict()["demo.online"];
      } else {
        await sleep(900);
      }
      if (id !== runId) return;
      chat.appendChild(bubble(line));
    }
    if (reduceMotion) return;
    await sleep(4500);
  }
}

applyLang(lang);
