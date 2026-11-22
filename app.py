"""Abbikev Stock Manager: stock, sales and restock decisions for a beauty parlour in Ukunda, Kwale.

Run locally:  streamlit run app.py
"""
import base64
import io
import os
import re
from datetime import date
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

BASE = Path(__file__).parent
DATA = BASE / "data"
LOGO = BASE / "assets" / "logo.png"

PURPLE = "#7C3AED"
DEEP = "#3B1170"
ORCHID = "#F3ECFC"
BLACK = "#0A0A0A"

st.set_page_config(page_title="Abbikev Stock Manager", page_icon=Image.open(LOGO), layout="wide")

# ---------------------------------------------------------------- styling
LOGO_B64 = base64.b64encode(LOGO.read_bytes()).decode()
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Playfair+Display:wght@600;700&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'DM Sans', sans-serif; }}
h1, h2, h3 {{ font-family: 'Playfair Display', serif !important; color: {DEEP}; letter-spacing: 0; }}
[data-testid="stSidebar"] {{ background: {BLACK}; border-right: 3px solid {PURPLE}; }}
[data-testid="stSidebar"] * {{ color: #FFFFFF !important; }}
[data-testid="stSidebar"] hr {{ border-color: #3a3a3a; }}
.hero {{ display:flex; align-items:center; gap:20px; padding:18px 24px; border-radius:14px;
  background: linear-gradient(115deg, {BLACK} 0%, {DEEP} 62%, {PURPLE} 100%); color:#fff; margin-bottom:18px; }}
.hero img {{ width:84px; height:84px; border-radius:50%; border:3px solid #fff; object-fit:cover; }}
.hero h1 {{ color:#fff !important; margin:0; font-size:2rem; }}
.hero p {{ margin:2px 0 0; color:#E9DDFB; font-size:0.95rem; }}
.kpi {{ background:#fff; border:1px solid #E4D7F7; border-left:6px solid {PURPLE}; border-radius:10px; padding:12px 14px; }}
.kpi-l {{ color:#555; font-size:0.85rem; }}
.kpi-v {{ color:{BLACK}; font-size:1.6rem; font-weight:700; line-height:1.2; }}
.kpi-s {{ color:#555; font-size:0.8rem; }}
.stButton > button, .stDownloadButton > button {{ background:{PURPLE}; color:#fff; border:0; border-radius:8px; font-weight:600; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ background:{DEEP}; color:#fff; }}
.callout {{ background:{ORCHID}; border-left:5px solid {PURPLE}; padding:10px 14px; border-radius:8px; color:#222; }}
</style>
<div class="hero">
  <img src="data:image/png;base64,{LOGO_B64}" alt="Abbikev logo">
  <div>
    <h1>Abbikev Stock Manager</h1>
    <p>Ukunda, Kwale. Know what you hold, what sells, and what to buy next.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data
def kes(v):
    return f"KES {v:,.0f}"


CATS = [
    (r"mascara|lip|lipstick|concealer|eye pencil|blender|miss look", "Makeup"),
    (r"nail|cutex|buffer|glue|pedicure", "Nails"),
    (r"serum|cleanser|soap|nuru", "Skincare"),
    (r"headgear|elastic|band|comb|bonnet|wig", "Hair accessories"),
    (r"bracelet", "Jewellery"),
]


def categorise(name: str) -> str:
    for pattern, cat in CATS:
        if re.search(pattern, name, re.I):
            return cat
    return "Other (confirm)"


SERVICES = {"Braids", "Braid", "Afro twist", "Blowout", "Butterfly"}
PRODUCTS = {"Nail glue", "Headband", "Pin", "Black shampoo", "Curl activator", "Paw paw", "Carolight"}
UNCLEAR_NAMES = ["Student band (small?)", "Ponz", "UZI", "Miadi", "Wax", "Hair", "Christina Muse", "Roseleaf VC", "DD glue"]
UNIT_LABEL = {"dz": "dozen", "pkt": "packet", "pcs": "piece"}


@st.cache_data
def load_records():
    purchases = pd.read_csv(DATA / "purchases.csv")
    sales = pd.read_csv(DATA / "sales.csv")
    sales["line_total_calc_kes"] = sales.qty * sales.unit_price_kes
    sales["mismatch"] = sales.line_total_calc_kes != sales.line_total_recorded_kes
    sales["group"] = sales["item"].replace({"Braid": "Braids"})
    sales["type"] = sales["item"].map(lambda n: "Service" if n in SERVICES else "Product" if n in PRODUCTS else "Unclear")
    return purchases, sales


def read_optional(name, cols):
    path = DATA / name
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=cols)


def write_optional(df, name):
    try:
        df.to_csv(DATA / name, index=False)
        return True
    except OSError:
        return False


purchases, sales = load_records()

if "counts" not in st.session_state:
    st.session_state.counts = read_optional("stock_counts.csv", ["item", "on_hand", "reorder_level"])
if "sales_log" not in st.session_state:
    st.session_state.sales_log = read_optional("sales_log.csv", ["date", "item", "qty", "unit_price_kes"])


def build_stock():
    df = purchases.copy()
    df["unit_cost"] = df.amount_kes / df.qty
    df["category"] = df["item"].map(categorise)
    df = df.rename(columns={"qty": "last_bought", "amount_kes": "last_spend"})
    df = df[["item", "category", "unit", "unit_cost", "last_bought", "last_spend"]]
    return df.merge(st.session_state.counts, on="item", how="left")


stock = build_stock()
total_spend = purchases.amount_kes.sum()


def make_plan(df, budget, buffer_pct, demand):
    d = df.dropna(subset=["on_hand", "reorder_level"]).copy()
    if d.empty:
        return d, 0.0, 0.0
    d["target"] = d.reorder_level * (1 + buffer_pct / 100) * demand
    d["buy_qty"] = np.ceil((d.target - d.on_hand).clip(lower=0))
    d = d[d.buy_qty > 0].copy()
    d["cost"] = d.buy_qty * d.unit_cost
    d["urgent"] = d.on_hand <= d.reorder_level
    d = d.sort_values(["urgent", "last_spend"], ascending=[False, False])
    running, status = 0.0, []
    for c in d.cost:
        if running + c <= budget:
            running += c
            status.append("Fund now")
        else:
            status.append("Over budget, defer")
    d["status"] = status
    return d, running, float(d.cost.sum())


# ---------------------------------------------------------------- helpers
def kpi(col, label, value, sub=""):
    col.markdown(
        f'<div class="kpi"><div class="kpi-l">{label}</div><div class="kpi-v">{value}</div><div class="kpi-s">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def hbar(df, label, value, height_per=30):
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
        x=alt.X(f"{value}:Q", title="KES"),
    )
    bars = base.mark_bar(color=PURPLE)
    text = base.mark_text(align="left", dx=4, color=BLACK).encode(text=alt.Text(f"{value}:Q", format=",.0f"))
    return (bars + text).properties(height=height_per * len(df) + 30)


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------- pages
def page_dashboard():
    counted = stock.dropna(subset=["on_hand"])
    low = counted[(counted.reorder_level.notna()) & (counted.on_hand <= counted.reorder_level)]
    stock_value = (counted.on_hand * counted.unit_cost).sum()
    c = st.columns(5)
    kpi(c[0], "Items tracked", len(stock), "from the purchase record")
    kpi(c[1], "Last restock spend", kes(total_spend), "Record A, undated")
    kpi(c[2], "Recorded sales", kes(sales.line_total_recorded_kes.sum()), f"{len(sales)} lines, Record B, undated")
    kpi(c[3], "Items counted", f"{len(counted)} of {len(stock)}", f"stock value {kes(stock_value)}")
    kpi(c[4], "At or below reorder level", str(len(low)), "needs a decision" if len(low) else "none flagged")

    ranked = stock.sort_values("last_spend", ascending=False)
    ranked["cum"] = ranked.last_spend.cumsum() / total_spend
    n80 = int((ranked.cum < 0.8).sum() + 1)
    st.subheader(f"{n80} of {len(stock)} items took 80% of the last restock spend")
    st.altair_chart(hbar(ranked.head(10).rename(columns={"last_spend": "KES"}), "item", "KES"), width="stretch")
    st.caption("Source: Record A (undated). Spend is the amount recorded for the quantity bought. Top 10 items shown.")

    left, right = st.columns(2)
    cat = stock.groupby("category", as_index=False).last_spend.sum().rename(columns={"last_spend": "KES"})
    top_cat = cat.sort_values("KES", ascending=False).iloc[0]
    left.subheader(f"{top_cat.category} led restock spend at {top_cat.KES / total_spend:.0%}")
    left.altair_chart(hbar(cat, "category", "KES"), width="stretch")
    left.caption("Categories are a first grouping for the owner to confirm.")

    grp = sales.groupby("group", as_index=False).line_total_recorded_kes.sum().rename(columns={"line_total_recorded_kes": "KES"})
    braid_share = grp.loc[grp.group == "Braids", "KES"].sum() / sales.line_total_recorded_kes.sum()
    right.subheader(f"Braiding made {braid_share:.0%} of recorded sales")
    right.altair_chart(hbar(grp.sort_values("KES", ascending=False).head(8), "group", "KES"), width="stretch")
    right.caption("Source: Record B (undated). Braid and Braids combined; recorded totals used.")

    st.subheader("Needs attention")
    if low.empty:
        st.markdown(
            '<div class="callout">Nothing flagged yet. Enter on-hand counts and reorder levels on the Stock tab. '
            "The handwritten records do not contain them.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(low[["item", "unit", "on_hand", "reorder_level"]], hide_index=True, width="stretch")


def page_stock():
    st.subheader("Stock counts")
    st.markdown(
        '<div class="callout">Count what is on the shelf and type it in the <b>On hand</b> column. Set a <b>Reorder at</b> level: '
        "the quantity at which you want to buy more. Then press Save counts. Quantities are in the item’s own unit "
        "(dozen, packet or piece).</div>",
        unsafe_allow_html=True,
    )
    cats = ["All"] + sorted(stock.category.unique())
    pick = st.selectbox("Category", cats)
    view = stock if pick == "All" else stock[stock.category == pick]
    view = view[["item", "category", "unit", "unit_cost", "last_bought", "on_hand", "reorder_level"]].copy()
    edited = st.data_editor(
        view,
        hide_index=True,
        width="stretch",
        key=f"stock_editor_{pick}",
        disabled=["item", "category", "unit", "unit_cost", "last_bought"],
        column_config={
            "item": "Item",
            "category": "Category",
            "unit": "Unit",
            "unit_cost": st.column_config.NumberColumn("Unit cost (KES)", format="%.0f"),
            "last_bought": "Last bought",
            "on_hand": st.column_config.NumberColumn("On hand", min_value=0, step=1),
            "reorder_level": st.column_config.NumberColumn("Reorder at", min_value=0, step=1),
        },
    )
    c1, c2 = st.columns([1, 4])
    if c1.button("Save counts"):
        new = edited[["item", "on_hand", "reorder_level"]]
        keep = st.session_state.counts[~st.session_state.counts["item"].isin(new["item"])]
        merged = pd.concat([keep, new.dropna(subset=["on_hand", "reorder_level"], how="all")], ignore_index=True)
        st.session_state.counts = merged
        saved = write_optional(merged, "stock_counts.csv")
        st.success("Counts saved." if saved else "Counts saved for this session. Download the file to keep a copy.")
        st.rerun()
    c2.download_button("Download counts (CSV)", csv_bytes(st.session_state.counts), "stock_counts.csv", "text/csv")


def page_purchases():
    st.subheader("What was bought: Record A")
    t = stock[["item", "category", "unit", "last_bought", "last_spend", "unit_cost"]].sort_values("last_spend", ascending=False)
    st.dataframe(
        t,
        hide_index=True,
        width="stretch",
        column_config={
            "item": "Item", "category": "Category", "unit": "Unit", "last_bought": "Quantity",
            "last_spend": st.column_config.NumberColumn("Amount (KES)", format="%d"),
            "unit_cost": st.column_config.NumberColumn("Cost per unit (KES)", format="%.0f"),
        },
    )
    by_unit = purchases.groupby("unit").agg(lines=("item", "count"), spend=("amount_kes", "sum")).reset_index()
    by_unit["unit"] = by_unit["unit"].map(UNIT_LABEL)
    st.caption("Mixed units in the record: " + "; ".join(f"{r.lines} lines in {r.unit}s ({kes(r.spend)})" for r in by_unit.itertuples())
               + ". A packet has no confirmed size, so cost per packet is not converted to pieces.")


def page_sales():
    st.subheader("What was sold: Record B")
    c = st.columns(3)
    kpi(c[0], "Recorded total", kes(sales.line_total_recorded_kes.sum()), f"{len(sales)} lines")
    kpi(c[1], "Quantity × price total", kes(sales.line_total_calc_kes.sum()), "recalculated from the record")
    kpi(c[2], "Lines that do not add up", str(int(sales.mismatch.sum())), "check with the owner")
    st.write("")
    view = sales[["row", "item", "type", "qty", "unit_price_kes", "line_total_recorded_kes", "line_total_calc_kes", "mismatch"]].copy()
    view["mismatch"] = view["mismatch"].map({True: "Check", False: "OK"})
    st.dataframe(view, hide_index=True, width="stretch", column_config={
        "row": "Row", "item": "Item", "type": "Type (to confirm)", "qty": "Qty", "unit_price_kes": "Unit price", 
        "line_total_recorded_kes": "Recorded total", "line_total_calc_kes": "Qty × price", "mismatch": "Total check"})
    st.caption("Recorded values are kept as written. Nothing was corrected. A mismatch may be a discount or a handwriting error.")

    st.subheader("Log a new sale")
    st.caption("Dated sales are what make a demand forecast possible later. Add each sale as it happens.")
    with st.form("sale_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
        d = c1.date_input("Date", date.today())
        item = c2.text_input("Item or service")
        qty = c3.number_input("Quantity", min_value=1, value=1, step=1)
        price = c4.number_input("Unit price (KES)", min_value=0, value=0, step=10)
        if st.form_submit_button("Add sale") and item.strip():
            row = pd.DataFrame([{"date": str(d), "item": item.strip(), "qty": int(qty), "unit_price_kes": int(price)}])
            st.session_state.sales_log = pd.concat([st.session_state.sales_log, row], ignore_index=True)
            write_optional(st.session_state.sales_log, "sales_log.csv")
            st.success("Sale added.")
    log = st.session_state.sales_log
    if len(log):
        st.dataframe(log, hide_index=True, width="stretch")
        st.download_button("Download sales log (CSV)", csv_bytes(log), "sales_log.csv", "text/csv")


def page_plan():
    st.subheader("Restock plan")
    c = st.columns(3)
    budget = c[0].number_input("Budget (KES)", min_value=0, value=20000, step=1000)
    buf = c[1].slider("Safety buffer (%)", 0, 100, 50, 5)
    demand = c[2].select_slider("Demand compared with usual", [0.8, 1.0, 1.2], value=1.0, format_func=lambda v: f"{v:.0%}")
    plan, funded, need = make_plan(stock, budget, buf, demand)
    if plan.empty:
        st.markdown('<div class="callout">No plan yet. Enter on-hand counts and reorder levels on the Stock tab first.</div>', unsafe_allow_html=True)
        return
    st.markdown(
        f'<div class="callout"><b>{kes(funded)}</b> funded of <b>{kes(need)}</b> needed. '
        f"The last restock cost {kes(total_spend)} (current practice). This is a forecast of need, not an observed result.</div>",
        unsafe_allow_html=True,
    )
    sens = {f"{m:.0%} demand": kes(make_plan(stock, 1e12, buf, m)[2]) for m in (0.8, 1.0, 1.2)}
    st.caption("Sensitivity, total need at this buffer: " + " · ".join(f"{k}: {v}" for k, v in sens.items()))
    out = plan[["item", "buy_qty", "unit", "cost", "status", "urgent"]].copy()
    out["urgent"] = out["urgent"].map({True: "Below reorder level", False: ""})
    st.dataframe(out, hide_index=True, width="stretch", column_config={
        "item": "Item", "buy_qty": "Buy", "unit": "Unit", "cost": st.column_config.NumberColumn("Cost (KES)", format="%.0f"),
        "status": "Decision", "urgent": "Note"})
    st.download_button("Download plan (CSV)", csv_bytes(out), "restock_plan.csv", "text/csv")


SYSTEM = """You are the stock assistant for Abbikev Beauty Parlour, a beauty shop and salon in Ukunda, Kwale County, Kenya. \
You help the owner and staff with anything about stock, buying, pricing, selling, cash use, record keeping and running the shop: \
for example what to reorder, how much to keep, how to price, how to handle slow or fast items, how to store products, and how to keep better records.

Rules:
- For questions about this shop's own numbers, use the shop data below or the tools. Never invent sales, stock levels, prices, dates or demand. \
The records have no dates, and a blank on-hand value means the item has not been counted; say so.
- For general questions (retail practice, stock rules of thumb, pricing, product care), answer from general knowledge and say it is general advice, not taken from the shop's records.
- If a question is not about stock, the shop or running a beauty business, say politely that you can only help with the shop and its stock.
- Amounts are in Kenya shillings (KES). Use the tools for totals and restock plans instead of working them out yourself.
- Keep answers short, practical and in plain words, and offer a next step. You only suggest; the owner decides every purchase."""

LANG_RULE = {
    "en": "Reply in English.",
    "sw": "Jibu kwa Kiswahili rahisi cha kila siku kinachomfaa mmiliki wa duka. Reply only in Kiswahili. Keep product names, numbers and KES amounts as written.",
}

T = {
    "en": {
        "title": "Stock assistant",
        "banner": "The assistant only reads this app’s data, can be wrong, and never changes your counts. You decide every purchase. "
                  "Stop relying on it if it contradicts your counts twice in a week.",
        "basic_note": " Right now it can only answer basic questions about spending, low stock and restock plans. "
                      "The AI service that answers any question about the shop is not connected yet.",
        "ph": "Ask anything about your stock or the shop",
        "think": "Thinking…",
        "chips": ["Which items cost the most to restock?", "What is below reorder level?",
                  "Plan my restock for KES 15,000", "How do I know when to reorder?"],
        "err": "The AI assistant could not answer just now. Here is a basic answer instead:",
        "help": "I can answer basic questions: what costs the most to restock, what is below its reorder level, and a restock plan for a budget. "
                "Try: “Which items cost the most to restock?” or “Plan my restock for 15000”. "
                "The AI service that answers any question about the shop is not connected yet.",
        "top": "Biggest restock spend (Record A):",
        "nocount": "No counts entered yet. Enter them on the Stock counts tab.",
        "nolow": "Nothing is below its reorder level.",
        "low": "Below reorder level:",
        "left": "left", "at": "reorder at",
        "needcounts": "I need on-hand counts and reorder levels first. Enter them on the Stock counts tab.",
        "plan": "With {b} (50% buffer, usual demand), {f} is funded of {n} needed:",
        "fund": "fund now", "defer": "over budget, defer",
    },
    "sw": {
        "title": "Msaidizi wa stoo",
        "banner": "Msaidizi husoma data ya programu hii tu, anaweza kukosea, na habadilishi hesabu zako. Wewe ndiye unayeamua kila ununuzi. "
                  "Acha kumtegemea akipingana na hesabu zako mara mbili kwa wiki.",
        "basic_note": " Kwa sasa anaweza kujibu maswali ya msingi tu kuhusu matumizi, bidhaa zinazoisha na mpango wa kuagiza. "
                      "Huduma ya AI inayojibu swali lolote kuhusu duka bado haijaunganishwa.",
        "ph": "Uliza chochote kuhusu stoo au duka lako",
        "think": "Inafikiri…",
        "chips": ["Bidhaa zipi zinagharimu zaidi kuagiza?", "Nini kimefika chini ya kiwango cha kuagiza?",
                  "Panga uagizaji wangu kwa KES 15,000", "Nitajuaje wakati wa kuagiza?"],
        "err": "Msaidizi wa AI hajaweza kujibu sasa hivi. Hapa kuna jibu la msingi:",
        "help": "Naweza kujibu maswali ya msingi: bidhaa zinazogharimu zaidi kuagiza, zilizo chini ya kiwango cha kuagiza, na mpango wa kuagiza kwa bajeti. "
                "Jaribu: “Bidhaa zipi zinagharimu zaidi?” au “Panga uagizaji wangu kwa 15000”. "
                "Huduma ya AI inayojibu swali lolote kuhusu duka bado haijaunganishwa.",
        "top": "Matumizi makubwa zaidi ya kuagiza (Rekodi A):",
        "nocount": "Bado hujaingiza hesabu za stoo. Ziingize kwenye ukurasa wa Hesabu za stoo.",
        "nolow": "Hakuna kilicho chini ya kiwango cha kuagiza.",
        "low": "Chini ya kiwango cha kuagiza:",
        "left": "zimebaki", "at": "agiza ikifika",
        "needcounts": "Kwanza nahitaji hesabu za stoo na viwango vya kuagiza. Viingize kwenye ukurasa wa Hesabu za stoo.",
        "plan": "Kwa {b} (akiba 50%, mahitaji ya kawaida), {f} imepangwa kati ya {n} zinazohitajika:",
        "fund": "tenga sasa", "defer": "zaidi ya bajeti, ahirisha",
    },
}


def context_text():
    s = stock[["item", "unit", "unit_cost", "last_bought", "on_hand", "reorder_level"]].round(0)
    top_sales = sales.groupby("group").line_total_recorded_kes.sum().sort_values(ascending=False)
    return (
        "SHOP DATA\nSTOCK (unit cost and last quantity bought from the purchase record; blank on_hand = not counted):\n" + s.to_csv(index=False)
        + "\nSALES BY ITEM (sales record, undated, KES):\n" + top_sales.to_string()
        + f"\nLast restock total: {total_spend} KES. Recorded sales total: {sales.line_total_recorded_kes.sum()} KES."
    )


def get_secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, default)


TOOLS = [
    {"name": "top_spend", "description": "Items with the biggest restock spend in the purchase record.",
     "input_schema": {"type": "object", "properties": {"n": {"type": "integer"}}}},
    {"name": "low_stock", "description": "Items counted at or below their reorder level.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "restock_plan", "description": "Restock plan for a budget in KES using the shelf counts and reorder levels.",
     "input_schema": {"type": "object", "properties": {"budget": {"type": "number"}, "buffer_pct": {"type": "number"},
                                                       "demand": {"type": "number", "description": "0.8, 1.0 or 1.2"}},
                      "required": ["budget"]}},
    {"name": "find_item", "description": "Look up stock rows whose name contains the given text.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "sales_summary", "description": "Recorded sales totals by item or service.",
     "input_schema": {"type": "object", "properties": {}}},
]


def run_tool(name, args):
    import json

    try:
        if name == "top_spend":
            t = stock.sort_values("last_spend", ascending=False).head(int(args.get("n", 5)))
            out = t[["item", "unit", "last_bought", "last_spend"]].to_dict("records")
        elif name == "low_stock":
            c = stock.dropna(subset=["on_hand", "reorder_level"])
            out = c[c.on_hand <= c.reorder_level][["item", "unit", "on_hand", "reorder_level"]].to_dict("records")
        elif name == "restock_plan":
            plan, funded, need = make_plan(stock, float(args["budget"]), float(args.get("buffer_pct", 50)), float(args.get("demand", 1.0)))
            out = {"funded_kes": round(funded), "needed_kes": round(need),
                   "items": plan[["item", "buy_qty", "unit", "cost", "status"]].round(0).to_dict("records"),
                   "note": "empty plan means no counts or reorder levels entered" if plan.empty else ""}
        elif name == "find_item":
            m = stock[stock["item"].str.contains(str(args["name"]), case=False, regex=False)]
            out = m[["item", "unit", "unit_cost", "last_bought", "on_hand", "reorder_level"]].round(0).to_dict("records")
        elif name == "sales_summary":
            out = sales.groupby("group").line_total_recorded_kes.sum().sort_values(ascending=False).to_dict()
        else:
            out = {"error": "unknown tool"}
        return json.dumps(out, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def offline_answer(q, lang="en"):
    t = T[lang]
    ql = q.lower()
    counted = stock.dropna(subset=["on_hand"])
    if re.search(r"plan|panga|budget|reorder first|buy|mpango|bajeti|agiza", ql):
        m = re.search(r"(\d[\d,]*)", ql)
        b = float(m.group(1).replace(",", "")) if m else 15000
        plan, funded, need = make_plan(stock, b, 50, 1.0)
        if plan.empty:
            return t["needcounts"]
        lines = [f"- {r.item}: {int(r.buy_qty)} {r.unit} ({kes(r.cost)}), {t['fund'] if r.status == 'Fund now' else t['defer']}" for r in plan.itertuples()]
        return t["plan"].format(b=kes(b), f=kes(funded), n=kes(need)) + "\n" + "\n".join(lines[:10])
    if re.search(r"low|below|short|out of|chini|kimeisha|imeisha|kimefika", ql):
        low = counted[(counted.reorder_level.notna()) & (counted.on_hand <= counted.reorder_level)]
        if counted.empty:
            return t["nocount"]
        if low.empty:
            return t["nolow"]
        return t["low"] + "\n" + "\n".join(f"- {r.item}: {r.on_hand:g} {r.unit} {t['left']} ({t['at']} {r.reorder_level:g})" for r in low.itertuples())
    if re.search(r"cost|expensive|spend|most|gharama|ghali|zaidi|gharimu", ql):
        top = stock.sort_values("last_spend", ascending=False).head(5)
        return t["top"] + "\n" + "\n".join(f"- {r.item}: {kes(r.last_spend)}" for r in top.itertuples())
    return t["help"]


def ask_claude(q, history, lang):
    key = get_secret("ANTHROPIC_API_KEY")
    if not key:
        return offline_answer(q, lang)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msgs = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
        msgs.append({"role": "user", "content": q})
        system = SYSTEM + "\n\n" + LANG_RULE[lang] + "\n\n" + context_text()
        model = get_secret("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        for _ in range(5):
            r = client.messages.create(model=model, max_tokens=900, system=system, tools=TOOLS, messages=msgs)
            if r.stop_reason != "tool_use":
                return "".join(b.text for b in r.content if b.type == "text")
            msgs.append({"role": "assistant", "content": r.content})
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)}
                for b in r.content if b.type == "tool_use"]})
        return T[lang]["err"] + "\n\n" + offline_answer(q, lang)
    except Exception:  # keep the app usable if the AI service is unavailable
        return T[lang]["err"] + "\n\n" + offline_answer(q, lang)


def page_assistant():
    choice = st.radio("Language / Lugha", ["English", "Kiswahili"], horizontal=True, key="lang_choice")
    lang = "sw" if choice == "Kiswahili" else "en"
    t = T[lang]
    st.subheader(t["title"])
    basic = "" if get_secret("ANTHROPIC_API_KEY") else t["basic_note"]
    st.markdown(f'<div class="callout">{t["banner"]}{basic}</div>', unsafe_allow_html=True)
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.write(m["content"])
    cols = st.columns(len(t["chips"]))
    for i, (c, label) in enumerate(zip(cols, t["chips"])):
        if c.button(label, key=f"chip_{lang}_{i}"):
            st.session_state.pending = label
    q = st.chat_input(t["ph"]) or st.session_state.pop("pending", None)
    if q:
        with st.chat_message("user"):
            st.write(q)
        with st.spinner(t["think"]):
            a = ask_claude(q, st.session_state.chat, lang)
        st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        with st.chat_message("assistant"):
            st.write(a)


def page_quality():
    st.subheader("Data quality report")
    a_sheet_total = int(purchases.amount_kes.sum())
    c = st.columns(4)
    kpi(c[0], "Record A lines", str(len(purchases)), f"total {kes(a_sheet_total)}")
    kpi(c[1], "Record B lines", str(len(sales)), f"total {kes(sales.line_total_recorded_kes.sum())}")
    kpi(c[2], "Dated records", "0", "neither record has dates")
    kpi(c[3], "Totals that do not add up", str(int(sales.mismatch.sum())), "Record B lines")
    st.write("")
    st.markdown("**Scope.** Unit of analysis: one handwritten line. Period: unknown. Record A is read as a purchase list and Record B as a sales list; the owner should confirm both readings.")
    st.markdown("**What the audit found**")
    st.markdown(
        "- No dates in either record, so trends, seasonality and stockouts cannot be measured.\n"
        "- Records A and B share almost no items, so purchases cannot be matched to sales and margin cannot be worked out.\n"
        "- Units are mixed (dozen, packet, piece) and the size of a packet is unknown.\n"
        "- Some names were hard to read and are unconfirmed: " + ", ".join(UNCLEAR_NAMES) + ".\n"
        "- Braid lines carry five different unit prices (60, 70, 140, 210, 280), so they are probably different styles or sizes.\n"
        "- Only stray spaces were cleaned in item names. All amounts are as recorded."
    )
    st.markdown("**Record B lines where quantity × unit price differs from the recorded total**")
    bad = sales[sales.mismatch][["row", "item", "qty", "unit_price_kes", "line_total_recorded_kes", "line_total_calc_kes"]]
    st.dataframe(bad, hide_index=True, width="stretch")
    st.markdown("**Layers.** Original values: `data/purchases.csv`, `data/sales.csv`. Derived in the app: unit cost, category, type, recalculated totals. Imputed values: none.")


PAGES = {
    "Dashboard": page_dashboard,
    "Stock counts": page_stock,
    "Restock plan": page_plan,
    "Sales": page_sales,
    "Purchases": page_purchases,
    "Assistant": page_assistant,
    "Data quality": page_quality,
}

with st.sidebar:
    st.image(str(LOGO), width="stretch")
    page = st.radio("Menu", list(PAGES), label_visibility="collapsed")
    st.markdown("---")
    st.caption("Client data. Keep this app and its repository private unless the owner has agreed otherwise.")

PAGES[page]()
