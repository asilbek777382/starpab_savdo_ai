import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { patch, setShopId } from "./api";
import { useCurrentShop, useLogout, useMe } from "./auth";
import { useI18n } from "./i18n";
import type { MessageKey } from "./locales";
import type { Lang } from "./types";
import { cx } from "./ui";

const NAV: { to: string; key: MessageKey; icon: string }[] = [
  { to: "/", key: "nav.dashboard", icon: "🏠" },
  { to: "/orders", key: "nav.orders", icon: "🧾" },
  { to: "/leads", key: "nav.leads", icon: "📞" },
  { to: "/conversations", key: "nav.conversations", icon: "💬" },
  { to: "/catalog", key: "nav.catalog", icon: "📦" },
  { to: "/ai", key: "nav.ai", icon: "✨" },
  { to: "/shop", key: "nav.shop", icon: "🏪" },
  { to: "/connect", key: "nav.connect", icon: "🔗" },
  { to: "/test", key: "nav.test", icon: "🧪" },
  { to: "/billing", key: "nav.billing", icon: "💳" },
];

export function LangSwitch() {
  const { lang, setLang } = useI18n();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const change = async (l: Lang) => {
    setLang(l);
    if (me) {
      await patch("/api/auth/me", { lang: l });
      qc.invalidateQueries({ queryKey: ["me"] });
    }
  };
  return (
    <div className="flex rounded-full border border-slate-200 p-0.5 text-xs font-semibold" role="group" aria-label="Til">
      {(["uz", "ru"] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => change(l)}
          aria-pressed={lang === l}
          className={cx("rounded-full px-2.5 py-1", lang === l ? "bg-brand-700 text-white" : "text-slate-500")}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const { data: me } = useMe();
  const shop = useCurrentShop();
  const qc = useQueryClient();
  const logout = useLogout();
  const item = (to: string, label: string, icon: string) => (
    <NavLink
      key={to}
      to={to}
      end={to === "/"}
      onClick={onNavigate}
      className={({ isActive }) =>
        cx(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
          isActive ? "bg-brand-50 text-brand-900 ring-1 ring-brand-100" : "text-slate-600 hover:bg-slate-50",
        )
      }
    >
      <span aria-hidden>{icon}</span>
      {label}
    </NavLink>
  );
  return (
    <div className="flex h-full flex-col gap-4">
      {me && me.shops.length > 1 && (
        <select
          aria-label="Do'kon"
          value={shop?.id}
          onChange={(e) => {
            setShopId(Number(e.target.value));
            qc.invalidateQueries();
          }}
          className="rounded-lg border-0 bg-slate-50 px-3 py-2 text-sm font-medium ring-1 ring-slate-200"
        >
          {me.shops.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      )}
      {me && me.shops.length === 1 && <p className="truncate px-3 text-sm font-semibold text-slate-800">{shop?.name}</p>}
      <nav className="space-y-1">
        {me && me.shops.length > 0 && NAV.map((n) => item(n.to, t(n.key), n.icon))}
        {me?.is_platform_admin && item("/admin", t("nav.admin"), "🛡")}
      </nav>
      <div className="mt-auto space-y-1 border-t border-slate-100 pt-4">
        {item("/profile", t("nav.profile"), "👤")}
        <button onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
          <span aria-hidden>↩</span> {t("auth.logout")}
        </button>
      </div>
    </div>
  );
}

export function Layout({ children }: { children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <button onClick={() => setOpen(true)} className="rounded-lg p-2 text-slate-700 hover:bg-slate-100" aria-label="Menyu">
          ☰
        </button>
        <img src="/brand/navbatchi-logo.svg" alt="Navbatchi AI" className="h-8" />
        <div className="ml-auto">
          <LangSwitch />
        </div>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-72 bg-white p-4" onClick={(e) => e.stopPropagation()}>
            <img src="/brand/navbatchi-logo.svg" alt="Navbatchi AI" className="mb-6 h-9" />
            <SideNav onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white p-4 lg:block">
        <div className="mb-6 flex items-center justify-between">
          <img src="/brand/navbatchi-logo.svg" alt="Navbatchi AI" className="h-9" />
        </div>
        <div className="h-[calc(100%-4rem)]">
          <SideNav />
        </div>
      </aside>
      <main className="lg:pl-64">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:py-8">
          <div className="mb-4 hidden justify-end lg:flex">
            <LangSwitch />
          </div>
          {children ?? <Outlet />}
        </div>
      </main>
    </div>
  );
}
