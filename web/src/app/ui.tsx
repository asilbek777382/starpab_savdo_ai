import {
  useEffect,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { useI18n } from "./i18n";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "gold";
  size?: "sm" | "md";
  loading?: boolean;
};

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: "bg-brand-700 text-white hover:bg-brand-900 shadow-sm",
    gold: "bg-gold-500 text-brand-900 hover:bg-gold-400 shadow-sm",
    secondary: "bg-white text-brand-900 ring-1 ring-slate-200 hover:ring-brand-500",
    ghost: "text-slate-600 hover:bg-slate-100",
    danger: "bg-white text-red-700 ring-1 ring-red-200 hover:bg-red-50",
  }[variant];
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm",
        styles,
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      className={cx(
        "inline-block animate-spin rounded-full border-2 border-current border-r-transparent",
        small ? "h-3.5 w-3.5" : "h-6 w-6 text-brand-700",
      )}
      aria-hidden
    />
  );
}

export function Field({ label, hint, children, id }: { label: string; hint?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-slate-500">{hint}</p>}
    </div>
  );
}

const inputCls =
  "block w-full rounded-lg border-0 bg-white px-3 py-2.5 text-sm text-slate-900 ring-1 ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none";

export function Input({ label, hint, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: ReactNode }) {
  const id = useId();
  const input = <input id={id} className={cx(inputCls, className)} {...rest} />;
  return label ? (
    <Field label={label} hint={hint} id={id}>
      {input}
    </Field>
  ) : (
    input
  );
}

export function Textarea({ label, hint, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; hint?: ReactNode }) {
  const id = useId();
  const el = <textarea id={id} rows={4} className={cx(inputCls, "leading-relaxed", className)} {...rest} />;
  return label ? (
    <Field label={label} hint={hint} id={id}>
      {el}
    </Field>
  ) : (
    el
  );
}

export function Select({ label, className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  const id = useId();
  const el = (
    <select id={id} className={cx(inputCls, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
  return label ? (
    <Field label={label} id={id}>
      {el}
    </Field>
  ) : (
    el
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cx("relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition", checked ? "bg-brand-600" : "bg-slate-300")}
      >
        <span className={cx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition", checked ? "left-5.5" : "left-0.5")} />
      </button>
      <span>
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}

export function Card({
  children,
  className,
  title,
  actions,
  flush = false,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  actions?: ReactNode;
  /** Ichki padding'siz (jadval yoki chat to'liq kenglikda) */
  flush?: boolean;
}) {
  return (
    <section className={cx("rounded-2xl bg-white shadow-sm ring-1 ring-slate-100", !flush && "p-5 sm:p-6", className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-brand-900">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const BADGE_TONES = {
  gray: "bg-slate-100 text-slate-700",
  brand: "bg-brand-50 text-brand-700 ring-1 ring-brand-100",
  gold: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  green: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  red: "bg-red-50 text-red-700 ring-1 ring-red-200",
  blue: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
};

export function Badge({ tone = "gray", children }: { tone?: keyof typeof BADGE_TONES; children: ReactNode }) {
  return <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", BADGE_TONES[tone])}>{children}</span>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const { t } = useI18n();
  if (!error) return null;
  return (
    <div role="alert" className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-red-200">
      {error instanceof Error ? error.message : t("common.error")}
    </div>
  );
}

export function Loading() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-slate-500">
      <Spinner /> {t("common.loading")}
    </div>
  );
}

export function Empty({ children }: { children?: ReactNode }) {
  const { t } = useI18n();
  return <div className="rounded-xl border border-dashed border-slate-200 py-10 text-center text-sm text-slate-500">{children ?? t("common.empty")}</div>;
}

/** Saqlangandan keyin qisqa "Saqlandi" belgisi. */
export function SavedFlash({ show }: { show: boolean }) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!show) return;
    setVisible(true);
    const id = setTimeout(() => setVisible(false), 2200);
    return () => clearTimeout(id);
  }, [show]);
  return visible ? <span className="text-sm font-medium text-emerald-700">✓ {t("common.saved")}</span> : null;
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-2xl sm:rounded-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-brand-900">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Yopish">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export { cx };
