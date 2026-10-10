import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import date, datetime
import plotly.express as px

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "egg_monitoring.db"

REQUIRED_COLUMNS = [
    "Kode Toko", "Area Supervisor", "Area Manager", "Kode Barang", "singkatan",
    "Jenis Modul", "OTY Penerimaan Barang", "Rupiah Penerimaan Barang",
    "QTY retur Barang", "Rupiah Retur barang", "QTY Sales", "Rupiah Sales",
    "Rupiah Margin", "% Margin", "OTY Rusak", "Rupiah Rusak",
    "Nilai Barang Hilang", "Rupiah Barang Hilang", "Potongan Penjualan",
    "OTY Stock", "Rupiah Stock"
]
NUMERIC_COLUMNS = [
    "OTY Penerimaan Barang", "Rupiah Penerimaan Barang", "QTY retur Barang",
    "Rupiah Retur barang", "QTY Sales", "Rupiah Sales", "Rupiah Margin",
    "% Margin", "OTY Rusak", "Rupiah Rusak", "Nilai Barang Hilang",
    "Rupiah Barang Hilang", "Potongan Penjualan", "OTY Stock", "Rupiah Stock"
]
ALIASES = {
    "QTY Penerimaan Barang": "OTY Penerimaan Barang",
    "QTY Stock": "OTY Stock",
    "Rupiah Retur Barang": "Rupiah Retur barang",
    "Singkatan": "singkatan",
    "Jenis modul": "Jenis Modul",
    "Area supervisor": "Area Supervisor",
    "Area manager": "Area Manager",
}

st.set_page_config(page_title="Egg Monitoring System", page_icon="🥚", layout="wide")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS egg_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            area_supervisor TEXT,
            area_manager TEXT,
            item_code TEXT NOT NULL,
            item_name TEXT,
            module_type TEXT,
            receipt_qty REAL DEFAULT 0,
            receipt_value REAL DEFAULT 0,
            return_qty REAL DEFAULT 0,
            return_value REAL DEFAULT 0,
            sales_qty REAL DEFAULT 0,
            sales_value REAL DEFAULT 0,
            margin_value REAL DEFAULT 0,
            margin_pct REAL DEFAULT 0,
            damaged_qty REAL DEFAULT 0,
            damaged_value REAL DEFAULT 0,
            lost_qty REAL DEFAULT 0,
            lost_value REAL DEFAULT 0,
            sales_deduction REAL DEFAULT 0,
            stock_qty REAL DEFAULT 0,
            stock_value REAL DEFAULT 0,
            imported_at TEXT NOT NULL,
            UNIQUE(report_date, store_code, item_code)
        )
    """)
    conn.commit()
    return conn

def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={c: ALIASES[c] for c in df.columns if c in ALIASES})
    # Common typo variants are supported, but the original file is not modified.
    return df

def parse_number(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    s = series.astype(str).str.strip().replace({"": None, "nan": None, "None": None, "-": "0"})
    # Supports plain numbers and Indonesian thousands/decimal notation.
    def one(v):
        if v is None or pd.isna(v):
            return 0.0
        v = str(v).strip().replace("Rp", "").replace(" ", "")
        if v in ("", "-", "nan", "None"):
            return 0.0
        # If both separators exist, last separator is treated as decimal separator.
        if "." in v and "," in v:
            if v.rfind(",") > v.rfind("."):
                v = v.replace(".", "").replace(",", ".")
            else:
                v = v.replace(",", "")
        elif "," in v:
            parts = v.split(",")
            v = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
        elif "." in v:
            parts = v.split(".")
            if len(parts) > 1 and len(parts[-1]) == 3:
                v = "".join(parts)
        try:
            return float(v)
        except ValueError:
            return float("nan")
    return s.map(one)

def prepare_upload(uploaded, report_date):
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, sep=None, engine="python", dtype=str)
    else:
        df = pd.read_excel(uploaded, dtype=str)
    df = normalize_columns(df)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(missing))
    df = df[REQUIRED_COLUMNS].copy()
    for c in ["Kode Toko", "Area Supervisor", "Area Manager", "Kode Barang", "singkatan", "Jenis Modul"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    for c in NUMERIC_COLUMNS:
        df[c] = parse_number(df[c])
    invalid_numeric = df[NUMERIC_COLUMNS].isna().sum().sum()
    df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].fillna(0)
    df["report_date"] = report_date.isoformat()
    df["imported_at"] = datetime.now().isoformat(timespec="seconds")
    df = df.rename(columns={
        "Kode Toko":"store_code", "Area Supervisor":"area_supervisor",
        "Area Manager":"area_manager", "Kode Barang":"item_code",
        "singkatan":"item_name", "Jenis Modul":"module_type",
        "OTY Penerimaan Barang":"receipt_qty", "Rupiah Penerimaan Barang":"receipt_value",
        "QTY retur Barang":"return_qty", "Rupiah Retur barang":"return_value",
        "QTY Sales":"sales_qty", "Rupiah Sales":"sales_value",
        "Rupiah Margin":"margin_value", "% Margin":"margin_pct",
        "OTY Rusak":"damaged_qty", "Rupiah Rusak":"damaged_value",
        "Nilai Barang Hilang":"lost_qty", "Rupiah Barang Hilang":"lost_value",
        "Potongan Penjualan":"sales_deduction", "OTY Stock":"stock_qty",
        "Rupiah Stock":"stock_value"
    })
    if (df["store_code"] == "").any():
        raise ValueError("Ada baris tanpa Kode Toko. Perbaiki file lalu unggah ulang.")
    if (df["item_code"] == "").any():
        raise ValueError("Ada baris tanpa Kode Barang. Perbaiki file lalu unggah ulang.")
    duplicate_mask = df.duplicated(["report_date", "store_code", "item_code"], keep=False)
    duplicates = int(duplicate_mask.sum())
    if duplicates:
        # Aggregate duplicate store-item rows so the unique database key remains valid.
        text_cols = ["area_supervisor", "area_manager", "item_name", "module_type"]
        agg = {c: "first" for c in text_cols}
        agg.update({c: "sum" for c in [
            "receipt_qty","receipt_value","return_qty","return_value","sales_qty","sales_value",
            "margin_value","damaged_qty","damaged_value","lost_qty","lost_value","sales_deduction",
            "stock_qty","stock_value"
        ]})
        agg["margin_pct"] = "mean"
        agg["imported_at"] = "max"
        df = df.groupby(["report_date","store_code","item_code"], as_index=False).agg(agg)
    return df, invalid_numeric, duplicates

def save_data(df, replace_day):
    conn = get_conn()
    d = str(df["report_date"].iloc[0])
    if replace_day:
        conn.execute("DELETE FROM egg_data WHERE report_date = ?", (d,))
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO egg_data ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, df[cols].itertuples(index=False, name=None))
    conn.commit()
    conn.close()

def load_data():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM egg_data", conn)
    conn.close()
    return df

def rupiah(x):
    return "Rp" + f"{float(x):,.0f}".replace(",", ".")

st.title("🥚 Egg Monitoring System")
st.caption("Monitoring performa telur • 514 toko • Fokus tindak lanjut Area Supervisor")
st.info("MVP awal: unggah file Excel/CSV, simpan histori harian, lalu analisis berdasarkan AS, AM, toko, dan periode.")

with st.sidebar:
    st.header("Impor data harian")
    upload = st.file_uploader("Pilih file Excel atau CSV", type=["xlsx", "xls", "csv"])
    selected_date = st.date_input("Tanggal laporan", value=date.today())
    replace_day = st.checkbox("Ganti seluruh data pada tanggal ini", value=True,
        help="Aktifkan jika file yang diunggah merupakan laporan lengkap untuk tanggal tersebut. Jika tidak, baris yang sama akan diperbarui.")
    if upload is not None:
        if st.button("Validasi & Simpan Data", type="primary", use_container_width=True):
            try:
                prepared, invalids, duplicates = prepare_upload(upload, selected_date)
                save_data(prepared, replace_day)
                st.success(f"Berhasil menyimpan {len(prepared):,} baris untuk {selected_date:%d-%m-%Y}.")
                st.caption(f"Baris numerik yang kosong/tidak terbaca: {invalids:,}. Baris duplikat yang digabung: {duplicates:,}.")
                st.rerun()
            except Exception as e:
                st.error(f"Impor gagal: {e}")
    st.divider()
    st.caption("Format kolom harus sesuai template sumber. Tanggal laporan ditentukan saat upload.")

data = load_data()
if data.empty:
    st.warning("Belum ada data tersimpan. Unggah file Excel/CSV dari sidebar untuk memulai.")
    st.markdown("""
    **Kolom yang dibutuhkan:** Kode Toko, Area Supervisor, Area Manager, Kode Barang, singkatan,
    Jenis Modul, OTY Penerimaan Barang, Rupiah Penerimaan Barang, QTY retur Barang,
    Rupiah Retur barang, QTY Sales, Rupiah Sales, Rupiah Margin, % Margin, OTY Rusak,
    Rupiah Rusak, Nilai Barang Hilang, Rupiah Barang Hilang, Potongan Penjualan, OTY Stock,
    Rupiah Stock.
    """)
    st.stop()

data["report_date"] = pd.to_datetime(data["report_date"], errors="coerce")
min_date = data["report_date"].min().date()
max_date = data["report_date"].max().date()

with st.sidebar:
    st.header("Filter dashboard")
    start_date = st.date_input("Dari tanggal", value=min_date, min_value=min_date, max_value=max_date, key="start")
    end_date = st.date_input("Sampai tanggal", value=max_date, min_value=min_date, max_value=max_date, key="end")
    if start_date > end_date:
        st.error("Tanggal awal tidak boleh melebihi tanggal akhir.")
        st.stop()
    all_as = sorted(data["area_supervisor"].dropna().astype(str).unique())
    chosen_as = st.multiselect("Area Supervisor", all_as, default=all_as)
    as_filtered = data[data["area_supervisor"].astype(str).isin(chosen_as)]
    all_am = sorted(as_filtered["area_manager"].dropna().astype(str).unique())
    chosen_am = st.multiselect("Area Manager", all_am, default=all_am)
    am_filtered = as_filtered[as_filtered["area_manager"].astype(str).isin(chosen_am)]
    all_stores = sorted(am_filtered["store_code"].astype(str).unique())
    chosen_stores = st.multiselect("Kode Toko", all_stores, default=[])
    product_options = sorted(am_filtered["item_code"].astype(str).unique())
    chosen_products = st.multiselect("Kode Barang", product_options, default=product_options)

period_data = data[
    (data["report_date"].dt.date >= start_date) &
    (data["report_date"].dt.date <= end_date) &
    (data["area_supervisor"].astype(str).isin(chosen_as)) &
    (data["area_manager"].astype(str).isin(chosen_am)) &
    (data["item_code"].astype(str).isin(chosen_products))
].copy()
if chosen_stores:
    period_data = period_data[period_data["store_code"].astype(str).isin(chosen_stores)]

if period_data.empty:
    st.warning("Tidak ada data sesuai filter yang dipilih.")
    st.stop()

# Sum daily flows; stock is a snapshot, so KPI stock uses the latest selected date per store-item.
latest_date = period_data["report_date"].max()
latest_stock = period_data[period_data["report_date"] == latest_date].copy()
sales = period_data["sales_value"].sum()
margin = period_data["margin_value"].sum()
receipt = period_data["receipt_value"].sum()
returns = period_data["return_value"].sum()
damage = period_data["damaged_value"].sum()
loss = period_data["lost_value"].sum()
stock_value = latest_stock["stock_value"].sum()
store_count = period_data["store_code"].nunique()
margin_rate = (margin / sales * 100) if sales else 0
loss_total = damage + loss

st.subheader("Ringkasan performa")
st.caption(f"Periode {start_date:%d %b %Y} – {end_date:%d %b %Y} • Snapshot stok: {latest_date:%d %b %Y}")
k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Toko terpantau", f"{store_count:,}")
k2.metric("Rupiah Sales", rupiah(sales))
k3.metric("Rupiah Margin", rupiah(margin), f"{margin_rate:.2f}% dari sales")
k4.metric("Nilai Stok terakhir", rupiah(stock_value))
k5.metric("Nilai Retur", rupiah(returns))
k6.metric("Rusak + Hilang", rupiah(loss_total))

st.subheader("Insight & prioritas tindak lanjut")
st.caption("Aturan awal berbasis indikator. Ambang batas dapat disesuaikan setelah baseline operasional disepakati.")

# Build per-store view from selected period; flows sum across days; latest stock snapshot.
store_flow = period_data.groupby(["store_code","area_supervisor","area_manager"], as_index=False).agg(
    sales_value=("sales_value","sum"), sales_qty=("sales_qty","sum"),
    margin_value=("margin_value","sum"), receipt_value=("receipt_value","sum"),
    return_value=("return_value","sum"), damaged_value=("damaged_value","sum"),
    lost_value=("lost_value","sum"), damaged_qty=("damaged_qty","sum"),
    lost_qty=("lost_qty","sum")
)
stock_by_store = latest_stock.groupby("store_code", as_index=False).agg(
    stock_value=("stock_value","sum"), stock_qty=("stock_qty","sum")
)
store_view = store_flow.merge(stock_by_store, on="store_code", how="left").fillna(0)
store_view["margin_rate"] = store_view.apply(lambda r: r["margin_value"] / r["sales_value"] * 100 if r["sales_value"] else 0, axis=1)
store_view["stock_to_sales"] = store_view.apply(lambda r: r["stock_value"] / r["sales_value"] if r["sales_value"] else None, axis=1)
store_view["loss_value"] = store_view["damaged_value"] + store_view["lost_value"]
store_view["loss_rate"] = store_view.apply(lambda r: r["loss_value"] / r["sales_value"] * 100 if r["sales_value"] else None, axis=1)

# Transparent rule-based insights: each row states measurable reason.
def make_reasons(r):
    reasons = []
    if r["sales_value"] == 0 and r["stock_value"] > 0:
        reasons.append("Stok bernilai ada, sales periode terpilih = 0")
    if r["sales_value"] > 0 and r["stock_to_sales"] is not None and r["stock_to_sales"] >= 2:
        reasons.append("Nilai stok terakhir ≥ 2x sales periode terpilih")
    if r["loss_value"] > 0:
        reasons.append("Ada nilai rusak/kehilangan")
    if r["return_value"] > 0:
        reasons.append("Ada nilai retur")
    if r["sales_value"] == 0 and r["stock_value"] == 0:
        reasons.append("Sales dan stok sama-sama nol")
    return reasons

store_view["indikator"] = store_view.apply(make_reasons, axis=1)
store_view["jumlah_indikator"] = store_view["indikator"].map(len)
store_view["prioritas"] = store_view["jumlah_indikator"].map(lambda n: "Perlu ditinjau" if n >= 2 else ("Pantau" if n == 1 else "Normal"))
store_view["alasan"] = store_view["indikator"].map(lambda x: "; ".join(x) if x else "Tidak ada indikator awal dari aturan yang tersedia")

c1,c2,c3 = st.columns(3)
c1.metric("Toko perlu ditinjau", int((store_view["prioritas"]=="Perlu ditinjau").sum()))
c2.metric("Toko pantau", int((store_view["prioritas"]=="Pantau").sum()))
c3.metric("Toko tanpa indikator awal", int((store_view["prioritas"]=="Normal").sum()))

left,right = st.columns(2)
with left:
    st.markdown("**10 toko dengan nilai rusak + hilang tertinggi**")
    top_loss = store_view.sort_values("loss_value", ascending=False).head(10)
    fig = px.bar(top_loss, x="store_code", y="loss_value", hover_data=["area_supervisor","area_manager","damaged_value","lost_value"], labels={"store_code":"Kode Toko","loss_value":"Nilai rusak + hilang"})
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown("**Sales vs nilai stok terakhir per toko**")
    scatter = store_view.copy()
    fig2 = px.scatter(scatter, x="sales_value", y="stock_value", color="prioritas", hover_name="store_code",
                      hover_data=["area_supervisor","area_manager","loss_value"],
                      labels={"sales_value":"Sales periode terpilih (Rp)","stock_value":"Nilai stok terakhir (Rp)","prioritas":"Status"})
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Daftar tindak lanjut per toko")
show_cols = ["store_code","area_supervisor","area_manager","sales_value","margin_value","margin_rate",
             "stock_value","stock_to_sales","return_value","damaged_value","lost_value","prioritas","alasan"]
table = store_view[show_cols].sort_values(["jumlah_indikator","loss_value","stock_value"], ascending=False).copy()
table = table.rename(columns={
    "store_code":"Kode Toko","area_supervisor":"Area Supervisor","area_manager":"Area Manager",
    "sales_value":"Sales (Rp)","margin_value":"Margin (Rp)","margin_rate":"Margin (%)",
    "stock_value":"Stok terakhir (Rp)","stock_to_sales":"Rasio stok/sales",
    "return_value":"Retur (Rp)","damaged_value":"Rusak (Rp)","lost_value":"Hilang (Rp)",
    "prioritas":"Prioritas","alasan":"Alasan indikator"
})
st.dataframe(table, use_container_width=True, hide_index=True,
             column_config={
                 "Sales (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Margin (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Stok terakhir (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Retur (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Rusak (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Hilang (Rp)": st.column_config.NumberColumn(format="Rp%.0f"),
                 "Margin (%)": st.column_config.NumberColumn(format="%.2f%%"),
                 "Rasio stok/sales": st.column_config.NumberColumn(format="%.2fx")
             })
csv = table.to_csv(index=False).encode("utf-8-sig")
st.download_button("Unduh hasil monitoring (CSV)", data=csv, file_name=f"egg_monitoring_{date.today().isoformat()}.csv", mime="text/csv")

st.subheader("Tren harian")
trend = period_data.groupby("report_date", as_index=False).agg(
    sales_value=("sales_value","sum"), margin_value=("margin_value","sum"),
    damaged_value=("damaged_value","sum"), lost_value=("lost_value","sum")
)
if len(trend) > 1:
    trend_long = trend.melt(id_vars="report_date", value_vars=["sales_value","margin_value"], var_name="indikator", value_name="rupiah")
    trend_long["indikator"] = trend_long["indikator"].map({"sales_value":"Sales","margin_value":"Margin"})
    fig3 = px.line(trend_long, x="report_date", y="rupiah", color="indikator", markers=True,
                   labels={"report_date":"Tanggal","rupiah":"Rupiah","indikator":"Indikator"})
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Tren akan tampil setelah tersedia lebih dari satu tanggal laporan.")

with st.expander("Lihat data sumber yang mendasari insight"):
    source = period_data.copy()
    source["report_date"] = source["report_date"].dt.strftime("%Y-%m-%d")
    st.dataframe(source, use_container_width=True, hide_index=True)
    st.download_button("Unduh data sumber terfilter", data=source.to_csv(index=False).encode("utf-8-sig"),
                       file_name="egg_monitoring_source.csv", mime="text/csv")

st.caption("Catatan: indikator adalah sinyal untuk pemeriksaan, bukan bukti otomatis adanya masalah. Rasio stok/sales hanya pembanding kasar dan perlu ditafsirkan sesuai periode, umur simpan, dan kebijakan stok telur.")
