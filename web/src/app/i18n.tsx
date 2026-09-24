import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { ru, uz, type MessageKey } from "./locales";
import type { Lang } from "./types";

const KEY = "nv_lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "uz" || saved === "ru") return saved;
  } catch {
    /* e'tiborsiz */
  }
  return navigator.language?.startsWith("ru") ? "ru" : "uz";
}

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  money: (n: number) => string;
  date: (iso: string, withTime?: boolean) => string;
};

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    document.documentElement.lang = l;
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* e'tiborsiz */
    }
  }, []);
  const value = useMemo<Ctx>(() => {
    const dict = lang === "ru" ? ru : uz;
    return {
      lang,
      setLang,
      t: (key, vars) => {
        let text: string = dict[key] ?? uz[key] ?? key;
        if (vars) for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, String(v));
        return text;
      },
      money: (n) => `${Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ")} ${dict["common.sum"]}`,
      // Brauzer locale'lari uz uchun turlicha format beradi — shuning uchun qat'iy DD.MM.YYYY HH:MM
      date: (iso, withTime = true) => {
        const d = new Date(iso);
        const p2 = (n: number) => String(n).padStart(2, "0");
        const day = `${p2(d.getDate())}.${p2(d.getMonth() + 1)}.${d.getFullYear()}`;
        return withTime ? `${day} ${p2(d.getHours())}:${p2(d.getMinutes())}` : day;
      },
    };
  }, [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("I18nProvider yo'q");
  return ctx;
}
