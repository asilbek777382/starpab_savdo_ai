export type Lang = "uz" | "ru";

export interface ShopBrief {
  id: number;
  name: string;
  role: string;
  plan: string;
  status: string;
}

export interface Account {
  id: number;
  name: string;
  phone: string | null;
  lang: Lang;
  telegram_linked: boolean;
  has_password: boolean;
  is_platform_admin: boolean;
  shops: ShopBrief[];
}

export interface Shop {
  id: number;
  name: string;
  type: string;
  language_default: string;
  status: string;
  plan: string;
  trial_ends_at: string | null;
}

export interface DeliveryZone {
  name: string;
  keywords: string[];
  fee: number;
  eta: string | null;
  center?: [number, number] | null;
  radius_km?: number | null;
}

export interface HandoffRules {
  silence_minutes: number;
  handoff_hours: number;
  allow_discounts: boolean;
  keywords: string[];
}

export interface Settings {
  faq_text: string;
  rules_text: string;
  address: string;
  delivery_zones: DeliveryZone[];
  payment_methods: string;
  working_hours: string;
  tone: string;
  handoff_rules: HandoffRules;
  ai_enabled: boolean;
  ai_mode: "sell" | "lead";
  ai_tasks: string;
  lead_chat_id: number | null;
  handoff_after_lead: boolean;
  voice_mode: "off" | "on_voice" | "always";
  voice_gender: "female" | "male";
  voice_available: boolean;
}

export interface Variant {
  id?: number | null;
  sku?: string | null;
  attrs: Record<string, string>;
  price_override?: number | null;
  stock?: number | null;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  price: number;
  currency: string;
  category_id: number | null;
  is_active: boolean;
  variants: Variant[];
  images: { id: number; url: string }[];
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
}

export interface OrderItem {
  name: string;
  attrs: Record<string, string>;
  qty: number;
  price: number;
  line_total: number;
}

export interface Order {
  id: number;
  number: number;
  status: "new" | "confirmed" | "shipped" | "cancelled";
  items: OrderItem[];
  subtotal: number;
  delivery_fee: number;
  total: number;
  customer_name: string | null;
  phone: string | null;
  address: string | null;
  location: { latitude: number; longitude: number } | null;
  comment: string | null;
  source: string;
  created_at: string;
}

export interface Lead {
  id: number;
  channel_type: string;
  name: string | null;
  phone: string;
  interest: string;
  note: string | null;
  status: "new" | "contacted" | "won" | "lost";
  created_at: string;
  conversation_id: number | null;
}

export interface Conversation {
  id: number;
  customer_id: number;
  customer_name: string | null;
  channel_type: string | null;
  status: "ai" | "human" | "closed";
  stage: string;
  human_until: string | null;
  last_message_at: string | null;
}

export interface ChatMessage {
  id: number;
  role: "customer" | "ai" | "staff";
  content: string;
  created_at: string;
  tokens_in: number;
  tokens_out: number;
  cost: string;
}

export interface Stats {
  days: number;
  conversations: number;
  orders: number;
  conversion: number;
  ai_orders_revenue: number;
  handoffs: number;
  leads: number;
  ai_cost: string;
  month_conversations: number;
  month_limit: number;
}

export interface DailyPoint {
  date: string;
  conversations: number;
  orders: number;
  leads: number;
}

export interface ChannelInfo {
  id: number;
  type: string;
  can_reply: boolean;
  is_enabled: boolean;
  display_name: string | null;
  token_expires_at: string | null;
}

export interface Channels {
  channels: ChannelInfo[];
  bot_username: string;
  bot_link: string;
  business_connected: boolean;
  instagram_configured: boolean;
  instagram_allowed: boolean;
  instagram: ChannelInfo | null;
}

export interface TestChatResult {
  status: string;
  replies: {
    type: "text" | "photos" | "voice";
    text?: string;
    photos?: string[];
    caption?: string | null;
    audio_b64?: string;
    mime?: string;
  }[];
  order_number: number | null;
  lead_id: number | null;
  voice: boolean;
  handed_off: boolean;
  tools: { tool: string; input: unknown; result: unknown }[];
}

export interface AdminShopRow {
  id: number;
  name: string;
  owner_name: string | null;
  owner_phone: string | null;
  plan: string;
  status: string;
  trial_ends_at: string | null;
  paid_until: string | null;
  month_conversations: number;
  month_cost: string;
  orders_30d: number;
  leads_30d: number;
  business_connected: boolean;
  instagram_connected: boolean;
  created_at: string;
}

export interface AdminOverview {
  shops: number;
  trials_active: number;
  paying: number;
  mrr: number;
  month_conversations: number;
  month_ai_cost: string;
  month_revenue: number;
}

export interface AdminShopDetail {
  shop: AdminShopRow;
  payments: { id: number; amount: number; provider: string; provider_txn_id: string | null; status: string; created_at: string }[];
  channels: { id: number; type: string; can_reply: boolean; is_enabled: boolean }[];
}

export interface PaymentRow {
  id: number;
  amount: number;
  provider: string;
  provider_txn_id: string | null;
  status: string;
  plan: string | null;
  months: number;
  created_at: string;
}

export interface PlanInfo {
  code: "start" | "business" | "pro";
  price: number;
  conversations: number;
  max_products: number | null;
  instagram: boolean;
}

export interface Billing {
  plan: string;
  status: string;
  trial_ends_at: string | null;
  paid_until: string | null;
  month_conversations: number;
  month_limit: number;
  plans: PlanInfo[];
  providers: ("payme" | "click")[];
  yearly_discount: number;
  payments: PaymentRow[];
}

export interface StaffMember {
  id: number;
  name: string;
  phone: string | null;
  role: "owner" | "operator";
  notify: boolean;
  telegram_linked: boolean;
  pending: boolean;
  is_me: boolean;
  invite_url: string | null;
}
