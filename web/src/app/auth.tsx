import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, get, getShopId, post, setShopId } from "./api";
import { useI18n } from "./i18n";
import type { Account } from "./types";
import { Loading } from "./ui";

export function useMe() {
  return useQuery<Account | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await get<Account>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export function useCurrentShop() {
  const { data: me } = useMe();
  const stored = Number(getShopId());
  return me?.shops.find((s) => s.id === stored) ?? me?.shops[0] ?? null;
}

export function useLogout() {
  const qc = useQueryClient();
  return async () => {
    await post("/api/auth/logout");
    setShopId(null);
    qc.clear();
    window.location.href = "/app/login";
  };
}

/** Kirmagan foydalanuvchini login sahifasiga yuboradi; akkaunt tilini qo'llaydi; do'konni tanlaydi. */
export function RequireAuth({ children, admin = false, needShop = true }: { children: ReactNode; admin?: boolean; needShop?: boolean }) {
  const { data: me, isLoading } = useMe();
  const { lang, setLang } = useI18n();
  const location = useLocation();

  useEffect(() => {
    if (me && me.lang !== lang) setLang(me.lang);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id]);

  useEffect(() => {
    if (!me) return;
    const stored = Number(getShopId());
    if (!me.shops.some((s) => s.id === stored)) setShopId(me.shops[0]?.id ?? null);
  }, [me]);

  if (isLoading) return <Loading />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (admin && !me.is_platform_admin) return <Navigate to="/" replace />;
  if (!admin && needShop && me.shops.length === 0) return <Navigate to={me.is_platform_admin ? "/admin" : "/login"} replace />;
  return <>{children}</>;
}
