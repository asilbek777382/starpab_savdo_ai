import "../styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "./api";
import { RequireAuth } from "./auth";
import { I18nProvider } from "./i18n";
import { Layout } from "./Layout";
import { AdminPage } from "./pages/admin/AdminPage";
import { AiSettingsPage } from "./pages/AiSettings";
import { LoginPage, MagicPage, RegisterPage } from "./pages/Auth";
import { CatalogPage } from "./pages/Catalog";
import { ConnectPage } from "./pages/Connect";
import { ConversationsPage } from "./pages/Conversations";
import { DashboardPage } from "./pages/Dashboard";
import { LeadsPage } from "./pages/Leads";
import { OrdersPage } from "./pages/Orders";
import { ProfilePage } from "./pages/Profile";
import { ShopSettingsPage } from "./pages/ShopSettings";
import { TestChatPage } from "./pages/TestChat";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

const shopPages = [
  { path: "/", el: <DashboardPage /> },
  { path: "/orders", el: <OrdersPage /> },
  { path: "/leads", el: <LeadsPage /> },
  { path: "/conversations", el: <ConversationsPage /> },
  { path: "/catalog", el: <CatalogPage /> },
  { path: "/ai", el: <AiSettingsPage /> },
  { path: "/shop", el: <ShopSettingsPage /> },
  { path: "/connect", el: <ConnectPage /> },
  { path: "/test", el: <TestChatPage /> },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter basename="/app">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/magic" element={<MagicPage />} />
            <Route element={<Layout />}>
              {shopPages.map((p) => (
                <Route key={p.path} path={p.path} element={<RequireAuth>{p.el}</RequireAuth>} />
              ))}
              <Route
                path="/profile"
                element={
                  <RequireAuth needShop={false}>
                    <ProfilePage />
                  </RequireAuth>
                }
              />
              <Route
                path="/admin"
                element={
                  <RequireAuth admin>
                    <AdminPage />
                  </RequireAuth>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
