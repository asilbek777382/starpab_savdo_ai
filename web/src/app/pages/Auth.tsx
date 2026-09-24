import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { get, post, setShopId } from "../api";
import { useMe } from "../auth";
import { useI18n } from "../i18n";
import { LangSwitch } from "../Layout";
import type { Account } from "../types";
import { Button, ErrorBox, Input, Loading } from "../ui";

function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="tile-pattern flex min-h-screen flex-col bg-cream">
      <div className="flex items-center justify-between px-4 py-4 sm:px-8">
        <a href="/">
          <img src="/brand/navbatchi-logo.svg" alt="Navbatchi AI" className="h-10" />
        </a>
        <LangSwitch />
      </div>
      <div className="flex flex-1 items-start justify-center px-4 pt-6 pb-16 sm:items-center sm:pt-0">
        <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl ring-1 ring-slate-100 sm:p-8">
          <h1 className="text-2xl font-bold text-brand-900">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}

function useAfterAuth() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  return (account: Account) => {
    qc.setQueryData(["me"], account);
    setShopId(account.shops[0]?.id ?? null);
    const from = (location.state as { from?: string } | null)?.from;
    navigate(from && from !== "/login" ? from : account.shops.length ? "/" : "/admin", { replace: true });
  };
}

export function LoginPage() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const done = useAfterAuth();
  const [phone, setPhone] = useState("+998 ");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      done(await post<Account>("/api/auth/login", { phone, password }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title={t("auth.login_title")}>
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("auth.phone")} type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
        <Input
          label={t("auth.password")}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <ErrorBox error={error} />
        <Button type="submit" loading={busy} className="w-full">
          {t("auth.login")}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        {t("auth.no_account")}{" "}
        <Link to="/register" className="font-semibold text-brand-700 hover:underline">
          {t("auth.register")}
        </Link>
      </p>
      <p className="mt-4 rounded-lg bg-brand-50 px-3 py-2.5 text-xs leading-relaxed text-brand-900">{t("auth.tg_hint")}</p>
    </AuthShell>
  );
}

export function RegisterPage() {
  const { t, lang } = useI18n();
  const { data: me } = useMe();
  const done = useAfterAuth();
  const [form, setForm] = useState({ name: "", phone: "+998 ", password: "", shop_name: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to="/" replace />;
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      done(await post<Account>("/api/auth/register", { ...form, lang }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title={t("auth.register_title")} subtitle={t("auth.trial")}>
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("auth.name")} autoComplete="name" value={form.name} onChange={set("name")} required />
        <Input label={t("auth.shop_name")} value={form.shop_name} onChange={set("shop_name")} required />
        <Input label={t("auth.phone")} type="tel" autoComplete="tel" value={form.phone} onChange={set("phone")} required />
        <Input
          label={t("auth.password")}
          hint={t("auth.password_hint")}
          type="password"
          autoComplete="new-password"
          minLength={8}
          value={form.password}
          onChange={set("password")}
          required
        />
        <ErrorBox error={error} />
        <Button type="submit" loading={busy} className="w-full">
          {t("auth.register")}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-600">
        {t("auth.have_account")}{" "}
        <Link to="/login" className="font-semibold text-brand-700 hover:underline">
          {t("auth.login")}
        </Link>
      </p>
    </AuthShell>
  );
}

export function MagicPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const done = useAfterAuth();
  const [error, setError] = useState<unknown>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return; // StrictMode'da ikki marta chaqirilmasin: token bir martalik
    started.current = true;
    post<Account>("/api/auth/magic", { token: params.get("token") ?? "" })
      .then(done)
      .catch(setError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <AuthShell title={t("auth.welcome")}>
      {error ? (
        <div className="space-y-4">
          <ErrorBox error={error} />
          <p className="text-sm text-slate-600">{t("auth.tg_hint")}</p>
          <Link to="/login" className="font-semibold text-brand-700 hover:underline">
            {t("auth.login")}
          </Link>
        </div>
      ) : (
        <>
          <p className="text-sm text-slate-500">{t("auth.magic_checking")}</p>
          <Loading />
        </>
      )}
    </AuthShell>
  );
}

/** Xodim taklifi: do'kon egasi bergan havola orqali parol o'rnatib kirish. */
export function InvitePage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const done = useAfterAuth();
  const [info, setInfo] = useState<{ name: string; phone: string | null; shops: string[] } | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    get<{ name: string; phone: string | null; shops: string[] }>(`/api/auth/invite?token=${encodeURIComponent(token)}`)
      .then(setInfo)
      .catch(setLoadError);
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      done(await post<Account>("/api/auth/invite", { token, password }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  if (loadError)
    return (
      <AuthShell title={t("invite.title")}>
        <div className="space-y-4">
          <ErrorBox error={loadError} />
          <Link to="/login" className="font-semibold text-brand-700 hover:underline">
            {t("auth.login")}
          </Link>
        </div>
      </AuthShell>
    );
  if (!info)
    return (
      <AuthShell title={t("invite.title")}>
        <Loading />
      </AuthShell>
    );
  return (
    <AuthShell title={t("invite.hello", { name: info.name })} subtitle={t("invite.subtitle", { shop: info.shops.join(", ") })}>
      <form onSubmit={submit} className="space-y-4">
        {info.phone && <Input label={t("auth.phone")} value={info.phone} disabled />}
        <Input
          label={t("invite.password")}
          hint={t("auth.password_hint")}
          type="password"
          autoComplete="new-password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <ErrorBox error={error} />
        <Button type="submit" loading={busy} className="w-full">
          {t("invite.submit")}
        </Button>
      </form>
    </AuthShell>
  );
}
