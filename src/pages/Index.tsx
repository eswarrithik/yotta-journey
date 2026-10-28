import { useMemo, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bot, CalendarDays,
  Check, ChevronDown, CircleAlert, Download, Filter, Fingerprint,
  LayoutDashboard, Menu, MousePointer2, PackageCheck, Search, ShieldCheck,
  Smartphone, Sparkles, Users, X,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import "../App.css";
import "../JourneyIQ.css";

type StageName = "Session started" | "Product viewed" | "Added to cart" | "Checkout started" | "Purchase completed";
type Session = {
  id: number; customerId: string | null; anonymousId: string; channel: "Website" | "Mobile app";
  device: "Desktop" | "Mobile" | "Tablet"; productId: string; startedAt: Date;
  consent: boolean; bot: boolean;
};
type EventRow = {
  id: string; sessionId: number; customerId: string | null; type: string; occurredAt: Date;
  ingestedAt: Date; channel: Session["channel"]; device: Session["device"];
  page: string | null; productId: string; orderId: string | null; botSignal: boolean;
};
type DemoData = { sessions: Session[]; events: EventRow[]; orders: { id: string; sessionId: number; productId: string }[]; support: number[] };

const STAGES: StageName[] = ["Session started", "Product viewed", "Added to cart", "Checkout started", "Purchase completed"];
const SECTIONS = ["Executive Overview", "Customer Journey Funnel", "Friction Analysis", "Channel Analysis", "Anomaly Monitoring", "Data Quality"];
const icons = [LayoutDashboard, MousePointer2, Activity, Smartphone, Bot, ShieldCheck];
const moneyless = new Intl.NumberFormat("en-US");

function seeded(seed: number) {
  let state = seed >>> 0;
  return () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 4294967296; };
}
function makeDemoData(anchor = Date.now()): DemoData {
  const random = seeded(20261022);
  const now = anchor;
  const sessions: Session[] = [];
  const events: EventRow[] = [];
  const orders: DemoData["orders"] = [];
  const support: number[] = [];
  for (let id = 1; id <= 100; id++) {
    const consent = random() > 0.2;
    const channel = random() < 0.68 ? "Website" : "Mobile app";
    const device = random() < 0.53 ? "Mobile" : random() < 0.76 ? "Desktop" : "Tablet";
    const bot = [9, 31, 68, 94].includes(id) || random() < 0.02;
    const customerId = consent && random() < 0.76 ? `CUS-${String(1 + Math.floor(random() * 70)).padStart(6, "0")}` : null;
    const productId = `PRD-${String(1 + Math.floor(random() * 12)).padStart(6, "0")}`;
    const startedAt = new Date(now - Math.floor(random() * 30 * 86400000));
    const hasSupport = !bot && (id % 12 === 0 || random() < 0.04);
    const session: Session = { id, customerId, anonymousId: `AN-${String(1 + Math.floor(random() * 56)).padStart(6, "0")}`, channel, device, productId, startedAt, consent, bot };
    sessions.push(session);
    const types: string[] = ["Session started"];
    if (bot) {
      types.push(...Array.from({ length: 12 + Math.floor(random() * 9) }, () => "Page viewed"));
    } else {
      if (random() < 0.86) {
        types.push("Product viewed");
        if (random() < 0.59) {
          types.push("Added to cart");
          if (random() < 0.68) {
            types.push("Checkout started", "Payment attempted");
            types.push(random() < 0.72 ? "Purchase completed" : "Purchase failed");
          }
        }
      }
      types.push(...Array.from({ length: 12 + Math.floor(random() * 9) }, () => "Page viewed"));
    }
    if (hasSupport) types.push("Support contacted");
    const orderId = types.includes("Purchase completed") ? `ORD-${String(id).padStart(6, "0")}` : null;
    types.forEach((type, index) => {
      const occurredAt = new Date(startedAt.getTime() + (index + 1) * 45_000);
      const delay = 10 + Math.floor(random() * 180);
      events.push({
        id: `EVT-SES-2026-${String(id).padStart(6, "0")}-${String(index + 1).padStart(6, "0")}`,
        sessionId: id,
        customerId,
        type,
        occurredAt,
        ingestedAt: new Date(occurredAt.getTime() + delay * 1000),
        channel,
        device,
        page: pageFor(type),
        productId,
        orderId: type === "Purchase completed" ? orderId : null,
        botSignal: bot,
      });
    });
    if (orderId) orders.push({ id: orderId, sessionId: id, productId });
    if (hasSupport) support.push(id);
  }

  const firstPurchase = events.find((event) => event.type === "Purchase completed");
  if (firstPurchase) {
    events.push({ ...firstPurchase, id: `EVT-SES-2026-${String(firstPurchase.sessionId).padStart(6, "0")}-999999`, ingestedAt: new Date(firstPurchase.occurredAt.getTime() + 35_000) });
  }
  const firstProductView = events.find((event) => event.type === "Product viewed");
  if (firstProductView) firstProductView.ingestedAt = new Date(firstProductView.occurredAt.getTime() + 1_240_000);
  const orderEvents = events.filter((event) => event.sessionId === 1).sort((a, b) => a.occurredAt.getTime() - b.occurredAt.getTime());
  if (orderEvents.length > 1) {
    orderEvents[0].ingestedAt = new Date(orderEvents[0].occurredAt.getTime() + 1_800_000);
    orderEvents[1].ingestedAt = new Date(orderEvents[1].occurredAt.getTime() + 2_000);
  }
  const identitySession = sessions.find((session) => session.id === 2);
  const identityEvent = events.find((event) => event.sessionId === 2);
  if (identitySession && identityEvent) {
    identitySession.customerId = null;
    identitySession.consent = false;
    identityEvent.customerId = "CUS-000001";
  }
  return { sessions, events, orders, support };
}
function pageFor(type: string) {
  if (type === "Session started" || type === "Page viewed") return "Home";
  if (type === "Product viewed") return "Product details";
  if (type === "Added to cart") return "Cart";
  if (type === "Checkout started") return "Checkout";
  if (type.startsWith("Payment") || type.startsWith("Purchase")) return "Payment";
  if (type === "Support contacted") return "Help";
  return null;
}
const DEMO_ANCHOR = Date.now();
const SOURCE = makeDemoData(DEMO_ANCHOR);
const REPEAT_SOURCE = makeDemoData(DEMO_ANCHOR);
const REPRODUCIBILITY = {
  compared: "Two independently generated full demo source datasets with seed 20261022",
  rows: SOURCE.events.length,
  matches: JSON.stringify(SOURCE) === JSON.stringify(REPEAT_SOURCE),
};
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
const format = (value: number) => moneyless.format(value);
function downloadEvents(events: EventRow[], filters = { channel: "see active dashboard filter", device: "see active dashboard filter", range: "see active dashboard filter", filteredSessions: new Set(events.map((event) => event.sessionId)).size }) {
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const metadata = [`# JourneyIQ DEMO DATA`, `# Filters: ${filters.range}; ${filters.channel}; ${filters.device}`, `# Filtered sessions: ${filters.filteredSessions}/${SOURCE.sessions.length}; filtered events: ${events.length}/${SOURCE.events.length}`];
  const columns = ["event_id", "session_id", "event_type", "event_timestamp", "ingestion_timestamp", "channel", "device_type", "product_id", "order_id"];
  const lines = [columns.join(","), ...events.map((event) => [event.id, `SES-2026-${String(event.sessionId).padStart(6, "0")}`, event.type, event.occurredAt.toISOString(), event.ingestedAt.toISOString(), event.channel, event.device, event.productId, event.orderId ?? ""].map(escape).join(","))];
  const url = URL.createObjectURL(new Blob([[...metadata, ...lines].join("\n")], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = "journeyiq_demo_filtered_events.csv"; anchor.click(); URL.revokeObjectURL(url);
}
function distinct<T>(items: T[]) { return new Set(items); }

export default function Index() {
  const [page, setPage] = useState(SECTIONS[0]);
  const [channel, setChannel] = useState("All channels");
  const [device, setDevice] = useState("All devices");
  const [range, setRange] = useState("Last 30 days");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [reviewedAnomalies, setReviewedAnomalies] = useState<Set<string>>(() => new Set());
  const choosePage = (next: string) => { setPage(next); setMobileOpen(false); };
  const days = Number(range.match(/\d+/)?.[0] ?? 30);
  const cutoff = Date.now() - days * 86400000;
  const sessions = useMemo(() => SOURCE.sessions.filter((session) => session.startedAt.getTime() >= cutoff && (channel === "All channels" || session.channel === channel) && (device === "All devices" || session.device === device)), [cutoff, channel, device]);
  const ids = new Set(sessions.map((session) => session.id));
  const events = SOURCE.events.filter((event) => ids.has(event.sessionId));
  const sessionById = new Map(sessions.map((session) => [session.id, session]));
  const funnelEntryIds = new Set(events.filter((event) => event.type === "Session started" && !sessionById.get(event.sessionId)?.bot).map((event) => event.sessionId));
  const eligibleEvents = events.filter((event) => funnelEntryIds.has(event.sessionId));
  const orders = SOURCE.orders.filter((order) => funnelEntryIds.has(order.sessionId));
  const purchaseSessions = distinct(orders.map((order) => order.sessionId));
  const stageCounts = STAGES.map((stage) => distinct(eligibleEvents.filter((event) => event.type === stage).map((event) => event.sessionId)).size);
  const funnel = STAGES.map((stage, index) => ({ stage, count: stageCounts[index], drop: index ? stageCounts[index - 1] - stageCounts[index] : 0, dropRate: index && stageCounts[index - 1] ? (stageCounts[index - 1] - stageCounts[index]) / stageCounts[index - 1] : 0 }));
  const cartSessions = distinct(eligibleEvents.filter((event) => event.type === "Added to cart").map((event) => event.sessionId));
  const asOf = Math.max(Date.now(), ...events.map((event) => event.ingestedAt.getTime()));
  const matureCartSessions = new Set([...cartSessions].filter((sessionId) => {
    const lastActivity = events.filter((event) => event.sessionId === sessionId).reduce((latest, event) => Math.max(latest, event.occurredAt.getTime()), 0);
    return asOf - lastActivity >= SESSION_TIMEOUT_MS;
  }));
  const abandonedCartSessions = [...matureCartSessions].filter((sessionId) => !purchaseSessions.has(sessionId)).length;
  const customers = distinct(sessions.flatMap((session) => session.customerId ? [session.customerId] : []));
  const conversion = funnelEntryIds.size ? [...purchaseSessions].filter((sessionId) => funnelEntryIds.has(sessionId)).length / funnelEntryIds.size : 0;
  const abandonment = matureCartSessions.size ? abandonedCartSessions / matureCartSessions.size : 0;
  const supportSessions = distinct(SOURCE.support.filter((id) => ids.has(id)));
  const funnelByChannel = ["Website", "Mobile app"].map((name) => {
    const cohort = sessions.filter((session) => session.channel === name);
    const cohortEntries = new Set([...funnelEntryIds].filter((id) => sessionById.get(id)?.channel === name));
    const cohortIds = new Set(cohort.map((session) => session.id));
    return { name, sessions: cohort.length, eligible: cohortEntries.size, conversion: cohortEntries.size ? distinct(orders.filter((order) => cohortEntries.has(order.sessionId)).map((order) => order.sessionId)).size / cohortEntries.size : 0, stages: STAGES.map((stage) => distinct(eligibleEvents.filter((event) => cohortIds.has(event.sessionId) && event.type === stage).map((event) => event.sessionId)).size) };
  });
  const anomalyRows = useMemo(() => {
    const rows: { issue: string; id: string; eventId: string; severity: string; detail: string; icon: typeof CircleAlert; tone: string }[] = [];
    const purchasesBySession = new Map<number, EventRow[]>();
    for (const event of events.filter((row) => row.type === "Purchase completed")) purchasesBySession.set(event.sessionId, [...(purchasesBySession.get(event.sessionId) ?? []), event]);
    for (const [id, group] of purchasesBySession) if (group.length > 1) rows.push({ issue: "Duplicate conversion", id: `SES-2026-${String(id).padStart(6, "0")}`, eventId: group[1].id, severity: "Critical", detail: `${group.length} purchase events share a conversion session`, icon: CircleAlert, tone: "red" });
    for (const session of sessions.filter((row) => row.bot)) rows.push({ issue: "Bot traffic", id: `SES-2026-${String(session.id).padStart(6, "0")}`, eventId: events.find((event) => event.sessionId === session.id)?.id ?? "—", severity: "Medium", detail: `Automated ${session.channel.toLowerCase()} browsing signals`, icon: Bot, tone: "violet" });
    for (const event of events.filter((row) => row.ingestedAt.getTime() - row.occurredAt.getTime() > 600_000)) rows.push({ issue: "Delayed event", id: `SES-2026-${String(event.sessionId).padStart(6, "0")}`, eventId: event.id, severity: "Medium", detail: `${event.type} arrived ${Math.round((event.ingestedAt.getTime() - event.occurredAt.getTime()) / 60000)} minutes after occurrence`, icon: Activity, tone: "blue" });
    for (const event of events) { const owner = sessions.find((session) => session.id === event.sessionId); if (owner && (!owner.consent && event.customerId || (owner.customerId && event.customerId && owner.customerId !== event.customerId))) rows.push({ issue: "Identity stitching", id: `SES-2026-${String(event.sessionId).padStart(6, "0")}`, eventId: event.id, severity: "High", detail: "Customer identity attached without valid session consent", icon: Fingerprint, tone: "amber" }); }
    const bySession = new Map<number, EventRow[]>();
    for (const event of events) bySession.set(event.sessionId, [...(bySession.get(event.sessionId) ?? []), event]);
    for (const [id, group] of bySession) { const timeOrder = [...group].sort((a, b) => a.occurredAt.getTime() - b.occurredAt.getTime()).map((event) => event.id); const arrivalOrder = [...group].sort((a, b) => a.ingestedAt.getTime() - b.ingestedAt.getTime()).map((event) => event.id); const mismatch = timeOrder.findIndex((eventId, i) => eventId !== arrivalOrder[i]); if (mismatch !== -1) rows.push({ issue: "Out-of-order arrival", id: `SES-2026-${String(id).padStart(6, "0")}`, eventId: timeOrder[mismatch], severity: "Low", detail: "Arrival sequence differs from occurrence sequence", icon: Activity, tone: "blue" }); }
    return rows;
  }, [events, sessions]);
  const visibleAnomalies = anomalyRows.filter((row) => !search || `${row.issue} ${row.id} ${row.eventId} ${row.detail}`.toLowerCase().includes(search.toLowerCase()));
  const customerIds = new Set(Array.from({ length: 70 }, (_, index) => `CUS-${String(index + 1).padStart(6, "0")}`));
  const validationChecks = [
    { label: "Session primary keys are unique", pass: new Set(SOURCE.sessions.map((session) => session.id)).size === SOURCE.sessions.length },
    { label: "Event primary keys are unique", pass: new Set(SOURCE.events.map((event) => event.id)).size === SOURCE.events.length },
    { label: "Event-to-session references resolve", pass: SOURCE.events.every((event) => SOURCE.sessions.some((session) => session.id === event.sessionId)) },
    { label: "Order-to-session references resolve", pass: SOURCE.orders.every((order) => SOURCE.sessions.some((session) => session.id === order.sessionId)) },
    { label: "Customer references resolve", pass: SOURCE.events.every((event) => !event.customerId || customerIds.has(event.customerId)) },
    { label: "Event and ingestion timestamps are valid", pass: SOURCE.events.every((event) => event.ingestedAt >= event.occurredAt && Number.isFinite(event.occurredAt.getTime())) },
    { label: "Funnel stage counts are monotonic", pass: stageCounts.every((count, index) => index === 0 || stageCounts[index - 1] >= count) },
  ];
  const goodChecks = validationChecks.filter((check) => check.pass).length;
  const trend = useMemo(() => Array.from({ length: 14 }, (_, index) => {
    const day = new Date(Date.now() - (13 - index) * 86400000); const key = day.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const daily = sessions.filter((session) => new Date(session.startedAt).toDateString() === day.toDateString()); const dailyIds = new Set(daily.map((session) => session.id));
    return { day: key, sessions: daily.length, purchases: distinct(orders.filter((order) => dailyIds.has(order.sessionId)).map((order) => order.sessionId)).size };
  }), [sessions, orders]);
  const pageSignals = [
    { page: "Home", entry: "Session started", next: "Product viewed" },
    { page: "Product details", entry: "Product viewed", next: "Added to cart" },
    { page: "Cart", entry: "Added to cart", next: "Checkout started" },
    { page: "Checkout", entry: "Checkout started", next: "Purchase completed" },
    { page: "Payment", entry: "Payment attempted", next: "Purchase completed" },
  ].map((item) => { const entrants = distinct(events.filter((event) => event.type === item.entry).map((event) => event.sessionId)); const progressed = new Set(events.filter((event) => event.type === item.next).map((event) => event.sessionId)); const relevant = events.filter((event) => event.page === item.page); const latencies = relevant.map((event) => (event.ingestedAt.getTime() - event.occurredAt.getTime()) / 1000).sort((a, b) => a - b); return { ...item, views: relevant.length, sessions: entrants.size, dropRate: entrants.size ? [...entrants].filter((id) => !progressed.has(id)).length / entrants.size : 0, medianLatency: latencies.length ? latencies[Math.floor(latencies.length / 2)] : 0 }; });

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-mark"><svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M7 28c4.8 0 4.8-16 9.6-16s4.8 16 9.6 16S31 12 36 12" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/><circle cx="7" cy="28" r="3" fill="currentColor"/><circle cx="36" cy="12" r="3" fill="currentColor"/></svg></div><div className="brand-copy"><strong>Journey<span>IQ</span></strong><small>JOURNEY ANALYTICS</small></div><button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={19}/></button></div>
      <div className="workspace-label">WORKSPACE</div><div className="workspace-select"><div className="workspace-icon">J</div><div className="workspace-copy"><b>Demo workspace</b><small>Customer analytics</small></div><ChevronDown size={16}/></div>
      <div className="nav-heading">ANALYTICS</div><nav aria-label="Analytics navigation">{SECTIONS.map((label, index) => { const Icon = icons[index]; return <button key={label} className={`nav-link ${page === label ? "active" : ""}`} onClick={() => choosePage(label)} aria-current={page === label ? "page" : undefined}><Icon size={18}/><span>{label}</span>{label === "Anomaly Monitoring" && anomalyRows.length > 0 && <i className="nav-alert">{anomalyRows.length}</i>}</button>; })}</nav>
      <div className="sidebar-bottom"><div className="pipeline-status"><span className="status-dot"/><div><b>DEMO DATA</b><small>Seed 20261022 · {events.length} events</small></div><span className="live-pulse"/></div><div className="profile"><div className="avatar">JI</div><div className="profile-copy"><b>JourneyIQ</b><small>Analytics preview</small></div><ChevronDown size={15}/></div></div>
    </aside>
    {mobileOpen && <button className="mobile-overlay" onClick={() => setMobileOpen(false)} aria-label="Close navigation"/>}
    <main className="main-area"><header className="topbar"><div className="topbar-left"><button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20}/></button><div className="topbar-title"><span>JourneyIQ · DEMO DATA</span><b>{page}</b></div></div><div className="topbar-controls"><label className="header-select" title="Filter by date range"><CalendarDays size={15}/><select value={range} onChange={(event) => setRange(event.target.value)} aria-label="Date range"><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option></select><ChevronDown size={13}/></label><label className="header-select" title="Filter by channel"><Filter size={15}/><select value={channel} onChange={(event) => setChannel(event.target.value)} aria-label="Channel"><option>All channels</option><option>Website</option><option>Mobile app</option></select><ChevronDown size={13}/></label><div className={`header-status ${goodChecks === validationChecks.length ? "" : "review"}`} title={`${goodChecks} of ${validationChecks.length} sample validation checks pass`}><i/>{goodChecks === validationChecks.length ? "Data quality good" : "Data review"}</div>{page === "Anomaly Monitoring" && <div className="searchbox"><Search size={15}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search issues..." aria-label="Search anomaly issues"/></div>}<div className="user-menu-wrap"><button className="user-menu-button" onClick={() => setUserMenuOpen((open) => !open)} aria-expanded={userMenuOpen} aria-label="Open JourneyIQ demo profile"><div className="top-avatar">JI</div><ChevronDown size={14}/></button>{userMenuOpen && <div className="user-menu-popover"><b>JourneyIQ analyst</b><span>Demo workspace · Read-only sample</span><small>Profile menu is a local demo control. No account or backend connection is active.</small></div>}</div></div></header>
      <div className="content"><div className="demo-banner"><span>DEMO DATA</span><p>Understand every journey. Eliminate every friction.</p></div>
        <div className="heading-row"><div><div className="eyebrow"><span className="eyebrow-line"/> JOURNEYIQ ANALYTICS</div><h1>{page}</h1><p className="subhead">Understand every journey. Eliminate every friction.</p></div><div className="heading-actions"><button className="export-button" onClick={() => downloadEvents(events, { channel, device, range, filteredSessions: sessions.length })}><Download size={16}/> Export events</button></div></div>
        <div className="filters"><span className="filter-title"><Filter size={15}/> Active filters</span><label><select value={device} onChange={(event) => setDevice(event.target.value)} aria-label="Device"><option>All devices</option><option>Desktop</option><option>Mobile</option><option>Tablet</option></select><ChevronDown size={14}/></label><span className="filter-meta" title="Filtered rows compared with the full generated demo dataset">Filtered {format(sessions.length)} / {format(SOURCE.sessions.length)} sessions · {format(events.length)} / {format(SOURCE.events.length)} events</span><button className="clear-filter" onClick={() => { setChannel("All channels"); setDevice("All devices"); setRange("Last 30 days"); }}>Reset filters</button></div>
        {sessions.length === 0 && <div className="empty-filter-state"><CalendarDays size={18}/><span><b>No sessions match these filters.</b> Widen the date range or reset channel and device filters.</span></div>}
        <section className="kpi-grid" aria-label="Key performance indicators">{[
          { label: "Total sessions", value: format(sessions.length), note: `${format(events.length)} filtered events`, icon: Users, tone: "teal" },
          { label: "Unique customers", value: format(customers.size), note: "consent-linked identities", icon: Fingerprint, tone: "lavender" },
          { label: "Purchases", value: format(purchaseSessions.size), note: "distinct converting sessions", icon: PackageCheck, tone: "peach" },
          { label: "Conversion rate", value: `${(conversion * 100).toFixed(1)}%`, note: `${format([...purchaseSessions].filter((id) => funnelEntryIds.has(id)).length)} purchases ÷ ${format(funnelEntryIds.size)} eligible human entries`, icon: Sparkles, tone: "mint" },
          { label: "Abandonment rate", value: `${(abandonment * 100).toFixed(1)}%`, note: `${format(abandonedCartSessions)} ÷ ${format(matureCartSessions.size)} carts idle ≥30 min`, icon: ArrowDownRight, tone: "amber" },
          { label: "Support contact rate", value: `${(sessions.length ? supportSessions.size / sessions.length * 100 : 0).toFixed(1)}%`, note: supportSessions.size ? `${format(supportSessions.size)} support sessions ÷ ${format(sessions.length)} filtered sessions` : "No support events in this filtered cohort", icon: Activity, tone: "lavender" },
        ].map((metric) => { const Icon = metric.icon; return <article className="kpi-card" key={metric.label}><div className="kpi-top"><span>{metric.label}</span><i className={`kpi-icon ${metric.tone}`}><Icon size={18}/></i></div><div className="kpi-value">{metric.value}</div><div className="kpi-note">{metric.note}</div></article>; })}</section>

        {page === "Executive Overview" && <>
          <div className="dashboard-grid"><section className="panel chart-panel"><div className="panel-heading"><div><h2>Journey activity</h2><p>Daily filtered sessions and distinct purchase sessions</p></div><span className="panel-tag">Last 14 days</span></div><div className="chart-legend"><span><i className="legend-dot teal-dot"/> Sessions</span><span><i className="legend-dot lilac-dot"/> Purchases</span></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend} margin={{ top: 12, right: 12, left: -18, bottom: 0 }}><defs><linearGradient id="sessionFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#087f8c" stopOpacity={0.18}/><stop offset="100%" stopColor="#087f8c" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#eaf0f1"/><XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#839097" }} interval={2}/><YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#839097" }}/><Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #e3eaec" }}/><Area type="monotone" dataKey="sessions" stroke="#087f8c" strokeWidth={2.5} fill="url(#sessionFill)"/><Area type="monotone" dataKey="purchases" stroke="#8178c8" strokeWidth={2} fill="transparent"/></AreaChart></ResponsiveContainer></div></section>
            <section className="panel funnel-panel"><div className="panel-heading"><div><h2>Conversion funnel</h2><p>Unique sessions reaching each stage</p></div></div><div className="funnel-list">{funnel.map((row, index) => <div className="funnel-stage" key={row.stage}><div className="funnel-label"><span><i className={`stage-dot dot-${index}`}/>{row.stage}</span><b>{format(row.count)}</b></div><div className="funnel-track"><div className={`funnel-fill fill-${index}`} style={{ width: `${funnelEntryIds.size ? Math.max(row.count / funnelEntryIds.size * 100, 2) : 0}%` }}/></div><div className="funnel-meta"><span>{funnelEntryIds.size ? (row.count / funnelEntryIds.size * 100).toFixed(0) : 0}% of eligible entries</span>{index > 0 && <span className="drop-label"><ArrowDownRight size={13}/>{(row.dropRate * 100).toFixed(0)}% drop</span>}</div></div>)}</div></section></div>
          <div className="lower-grid"><section className="panel"><div className="panel-heading"><div><h2>Channel performance</h2><p>Conversion rate calculated per channel cohort</p></div><button className="text-action" onClick={() => choosePage("Channel Analysis")}>Explore channels <ArrowUpRight size={15}/></button></div><div className="channel-rows">{funnelByChannel.map((row) => <div className="channel-row" key={row.name}><div className="channel-name"><span className={`channel-symbol ${row.name === "Website" ? "website" : "mobile"}`}>{row.name === "Website" ? <MousePointer2 size={18}/> : <Smartphone size={18}/>}</span><div><b>{row.name}</b><small>{format(row.sessions)} sessions · {format(row.eligible)} eligible</small></div></div><div className="channel-progress"><span style={{ width: `${sessions.length ? row.sessions / sessions.length * 100 : 0}%` }}/></div><strong>{(row.conversion * 100).toFixed(1)}% <small>convert</small></strong></div>)}</div></section>
            <section className="panel quality-panel"><div className="panel-heading"><div><h2>Data quality</h2><p>Integrity validations from current demo rows</p></div><button className="text-action" onClick={() => choosePage("Data Quality")}>View checks <ArrowUpRight size={15}/></button></div><div className={`quality-summary ${goodChecks === validationChecks.length ? "good" : "review"}`}><span className="quality-symbol">{goodChecks === validationChecks.length ? <Check size={20}/> : <AlertTriangle size={20}/>}</span><div><b>{goodChecks === validationChecks.length ? "All checks passed" : `${goodChecks} of ${validationChecks.length} checks passed`}</b><p>Known anomalies are retained and shown for review.</p></div></div><div className="quality-counts"><span><b>{anomalyRows.length}</b> anomaly signals</span><span><b>{events.length}</b> source events</span></div></section></div>
        </>}

        {page === "Customer Journey Funnel" && <section className="panel detail-panel"><div className="panel-heading"><div><h2>Stage conversion and drop-off</h2><p>Stage-to-stage conversion denominator is the preceding stage.</p></div><span className="panel-tag">{sessions.length} filtered sessions</span></div><div className="detail-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={funnel} layout="vertical" margin={{ top: 8, right: 32, left: 20, bottom: 8 }}><CartesianGrid horizontal={false} stroke="#edf0f2"/><XAxis type="number" tickLine={false} axisLine={false} allowDecimals={false} tick={{ fill: "#839097", fontSize: 11 }}/><YAxis type="category" dataKey="stage" width={155} tickLine={false} axisLine={false} tick={{ fill: "#586970", fontSize: 12 }}/><Tooltip/><Bar dataKey="count" name="Sessions" fill="#087f8c" radius={[0, 7, 7, 0]} barSize={27}/></BarChart></ResponsiveContainer></div><div className="stage-card-grid">{funnel.map((row, index) => <article className="stage-card" key={row.stage}><small>0{index + 1} · {row.stage}</small><b>{format(row.count)}</b><span>{index ? `${(row.count / Math.max(1, funnel[index - 1].count) * 100).toFixed(1)}% stage conversion` : "100% of eligible sessions"}</span></article>)}</div></section>}

        {page === "Friction Analysis" && <div className="detail-grid"><section className="panel detail-panel"><div className="panel-heading"><div><h2>High-friction pages</h2><p>Drop-off from page-stage entrants to the next journey stage</p></div></div><div className="friction-list">{pageSignals.map((signal, index) => <div className="friction-row" key={signal.page}><div className={`friction-badge ${index < 2 ? "warning" : "neutral"}`}><ArrowDownRight size={18}/></div><div className="friction-info"><b>{signal.page}</b><small>{format(signal.sessions)} entrants · {format(signal.views)} events · median delay {Math.round(signal.medianLatency)}s</small></div><strong>{(signal.dropRate * 100).toFixed(1)}%</strong></div>)}</div><p className="method-note">Page drop-off counts sessions that entered the page stage but did not reach its next funnel milestone.</p></section><section className="panel detail-panel"><h2>Checkout signals</h2><div className="signal-stat"><span>Payment failures</span><b>{events.filter((event) => event.type === "Purchase failed").length}</b></div><div className="signal-stat"><span>Delayed events · &gt;10 min</span><b>{events.filter((event) => event.ingestedAt.getTime() - event.occurredAt.getTime() > 600_000).length}</b></div><div className="signal-stat"><span>Cart abandonment</span><b>{(abandonment * 100).toFixed(1)}%</b></div><div className="method-note">All friction and failure counts use the currently filtered source events.</div></section></div>}

        {page === "Channel Analysis" && <div className="panel detail-panel"><div className="panel-heading"><div><h2>Channel journey comparison</h2><p>Stage reach as a share of each filtered channel cohort</p></div></div><div className="channel-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={STAGES.map((stage, index) => ({ stage, Website: funnelByChannel.find((row) => row.name === "Website")?.eligible ? funnelByChannel.find((row) => row.name === "Website")!.stages[index] / funnelByChannel.find((row) => row.name === "Website")!.eligible * 100 : 0, "Mobile app": funnelByChannel.find((row) => row.name === "Mobile app")?.eligible ? funnelByChannel.find((row) => row.name === "Mobile app")!.stages[index] / funnelByChannel.find((row) => row.name === "Mobile app")!.eligible * 100 : 0 }))} margin={{ top: 16, right: 20, left: 4, bottom: 18 }}><CartesianGrid vertical={false} stroke="#edf0f2"/><XAxis dataKey="stage" tickLine={false} axisLine={false} interval={0} tick={{ fill: "#586970", fontSize: 11 }}/><YAxis tickLine={false} axisLine={false} unit="%" tick={{ fill: "#839097", fontSize: 11 }}/><Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`}/><Bar dataKey="Website" fill="#087f8c" radius={[5, 5, 0, 0]}/><Bar dataKey="Mobile app" fill="#8178c8" radius={[5, 5, 0, 0]}/></BarChart></ResponsiveContainer></div><div className="channel-card-grid">{funnelByChannel.map((row) => <article className="channel-card" key={row.name}><span className={`channel-symbol ${row.name === "Website" ? "website" : "mobile"}`}>{row.name === "Website" ? <MousePointer2/> : <Smartphone/>}</span><h3>{row.name}</h3><b>{format(row.sessions)}</b><small>filtered sessions</small><div>Conversion rate <strong>{(row.conversion * 100).toFixed(1)}%</strong></div></article>)}</div><div className="identity-banner"><Fingerprint size={19}/><div><b>Consent-aware identity</b><p>{format(customers.size)} known identities and {format(sessions.length - customers.size)} anonymous sessions in this view. Unconsented linkage is flagged in anomaly monitoring.</p></div></div></div>}

        {page === "Anomaly Monitoring" && <><section className="anomaly-kpis">{[
          { label: "Duplicate conversions", count: anomalyRows.filter((row) => row.issue === "Duplicate conversion").length, tone: "peach", icon: CircleAlert },
          { label: "Bot sessions", count: sessions.filter((session) => session.bot).length, tone: "lavender", icon: Bot },
          { label: "Delayed events", count: events.filter((event) => event.ingestedAt.getTime() - event.occurredAt.getTime() > 600_000).length, tone: "teal", icon: Activity },
          { label: "Identity exceptions", count: anomalyRows.filter((row) => row.issue === "Identity stitching").length, tone: "amber", icon: Fingerprint },
        ].map((item) => { const Icon = item.icon; return <article className="anomaly-kpi" key={item.label}><span className={`kpi-icon ${item.tone}`}><Icon size={18}/></span><div><small>{item.label}</small><b>{format(item.count)}</b></div></article>; })}</section><section className="panel detail-panel"><div className="panel-heading"><div><h2>Anomaly monitoring</h2><p>Issues are detected from source events, arrival latency, consent, and bot signals.</p></div><span className="panel-tag">{visibleAnomalies.length} results</span></div><div className="anomaly-table-wrap"><table className="anomaly-table"><thead><tr><th>Issue type</th><th>Affected event ID</th><th>Severity</th><th>Investigation</th></tr></thead><tbody>{visibleAnomalies.map((row, index) => { const Icon = row.icon; const key = `${row.issue}-${row.eventId}`; const reviewed = reviewedAnomalies.has(key); return <tr key={`${key}-${index}`}><td><span className="issue-cell"><i className={`anomaly-icon ${row.tone}`}><Icon size={16}/></i><span><b>{row.issue}</b><small>{row.detail}</small></span></span></td><td><code>{row.eventId}</code><small className="event-session">{row.id}</small></td><td><span className={`severity-pill ${row.tone}`}>{row.severity}</span></td><td><button className={`review-button ${reviewed ? "reviewed" : ""}`} onClick={() => setReviewedAnomalies((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; })}>{reviewed ? <><Check size={13}/> Reviewed</> : "Mark reviewed"}</button></td></tr>; })}</tbody></table>{visibleAnomalies.length === 0 && <div className="empty-state"><ShieldCheck size={23}/><b>No anomalies in this selection</b><span>Try broadening the date, channel, or device filter.</span></div>}</div><div className="truth-note"><ShieldCheck size={17}/><span>DEMO signals are derived from source records; the injected exceptions remain traceable and searchable.</span></div></section></>}

        {page === "Data Quality" && <><section className="quality-status-card"><span className={`quality-symbol ${validationChecks.every((check) => check.pass) ? "good" : "review"}`}>{validationChecks.every((check) => check.pass) ? <Check size={21}/> : <AlertTriangle size={21}/>}</span><div><b>{validationChecks.every((check) => check.pass) ? "Integrity checks passed" : "Validation review required"}</b><p>{goodChecks} of {validationChecks.length} sample checks pass. Injected anomalies remain visible and do not alter unrelated source rows.</p></div><span className="panel-tag">DEMO DATA</span></section><div className="detail-grid"><section className="panel detail-panel"><div className="panel-heading"><div><h2>Validation results</h2><p>Structural integrity checks on full generated demo rows; detected anomalies are evaluated separately</p></div></div>{validationChecks.map((check) => <div className="check-row" key={check.label}><span>{check.label}</span><b className={check.pass ? "pass-label" : "fail-label"}>{check.pass ? <Check size={14}/> : <AlertTriangle size={14}/>} {check.pass ? "Pass" : "Review"}</b></div>)}</section><section className="panel detail-panel"><h2>Reproducibility & sample inventory</h2><div className="reproducibility-row"><div><b>Deterministic source dataset comparison</b><small>{REPRODUCIBILITY.compared} · {format(REPRODUCIBILITY.rows)} events in each run</small></div><span className={REPRODUCIBILITY.matches ? "pass-label" : "fail-label"}>{REPRODUCIBILITY.matches ? <Check size={14}/> : <AlertTriangle size={14}/>} {REPRODUCIBILITY.matches ? "Repeatable" : "Mismatch"}</span></div>{[{ name: "Customers", value: customers.size }, { name: "Sessions", value: sessions.length }, { name: "Journey events", value: events.length }, { name: "Products", value: distinct(sessions.map((session) => session.productId)).size }, { name: "Paid orders", value: purchaseSessions.size }, { name: "Support sessions", value: supportSessions.size }].map((row) => <div className="entity-row" key={row.name}><span><i className="entity-bullet"/>{row.name}</span><b>{format(row.value)}</b><span className="entity-state"><i/>Measured</span></div>)}<button className="export-wide" onClick={() => downloadEvents(events, { channel, device, range, filteredSessions: sessions.length })}><Download size={16}/> Download filtered event CSV</button></section></div></>}
        <footer className="page-footer"><span>JourneyIQ <i/> Understand every journey. Eliminate every friction.</span><span><i className="status-dot"/> Demo preview</span></footer>
      </div>
    </main>
  </div>;
}
