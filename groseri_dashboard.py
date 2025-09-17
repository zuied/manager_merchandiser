# groseri_dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="Groseri Manager Dashboard (Streamlit)")

# -----------------------
# Helper functions
# -----------------------
def rag_emoji(value, thresholds):
    """Return emoji menurut thresholds dict {'green':x,'yellow':y} where x>=green threshold, y>=yellow threshold."""
    try:
        if pd.isna(value):
            return "⚪"
        if value >= thresholds["green"]:
            return "🟢"
        elif value >= thresholds["yellow"]:
            return "🟡"
        else:
            return "🔴"
    except Exception:
        return "⚪"

def load_sample_data():
    # Sample Sales Data: Tanggal, Produk, Qty, Harga, Total, Stok_Awal, Sisa_Stok
    sales = pd.DataFrame([
        ["2025-06-05","Susu UHT 1L",20,15000,20*15000,100,100-20],
        ["2025-06-12","Indomie Ayam",50,3000,50*3000,200,200-50],
        ["2025-06-25","Teh Botol",30,5000,30*5000,150,150-30],
        ["2025-07-10","Susu UHT 1L",25,15000,25*15000,100,100-25],
        ["2025-07-18","Indomie Ayam",80,3000,80*3000,200,200-80],
        ["2025-08-05","Teh Botol",60,5000,60*5000,150,150-60],
        ["2025-08-20","Susu UHT 1L",40,15000,40*15000,100,100-40],
        ["2025-09-10","Indomie Ayam",150,3000,150*3000,200,200-150],
        ["2025-09-15","Susu UHT 1L",70,15000,70*15000,100,100-70],
    ], columns=["Tanggal","Produk","Qty","Harga","Total","Stok_Awal","Sisa_Stok"])
    sales['Tanggal'] = pd.to_datetime(sales['Tanggal'], dayfirst=False)

    expiry = pd.DataFrame([
        ["Yogurt Cup","YG202509","2025-09-25",100],
        ["Yogurt Cup","YG202510","2025-10-15",200],
    ], columns=["Produk","Batch_No","Exp_Date","Qty_Stok"])
    expiry['Exp_Date'] = pd.to_datetime(expiry['Exp_Date'])

    pricing = pd.DataFrame([
        ["Beras 5kg",60000,72000],
    ], columns=["Produk","Harga_Beli","Harga_Jual"])

    promo = pd.DataFrame([
        ["Susu UHT 1L",100000000,115000000,10000000],
    ], columns=["Promosi","Target_Sales","Actual_Sales","Biaya_Promosi"])

    return sales, expiry, pricing, promo

def safe_convert_num(x):
    try:
        return float(x)
    except:
        return np.nan

# -----------------------
# UI: Upload file / use sample
# -----------------------
st.title("Groseri Manager Dashboard — Streamlit")
st.markdown("Upload file Excel (format: sheets `Sales Data`, `Expiry Data`, `Pricing Data`, `Promo Data`) atau gunakan data contoh.")

uploaded_file = st.file_uploader("Upload file Excel (.xlsx) (opsional)", type=["xlsx"])

if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        # Try read known sheet names variations
        sheet_names = {s.lower(): s for s in xls.sheet_names}
        def get_sheet(name_lower, default_df):
            if name_lower in sheet_names:
                return pd.read_excel(xls, sheet_names[name_lower])
            else:
                return default_df
        # Default placeholders if not present
        default_sales, default_expiry, default_pricing, default_promo = load_sample_data()
        sales = get_sheet("sales data", default_sales)
        expiry = get_sheet("expiry data", default_expiry)
        pricing = get_sheet("pricing data", default_pricing)
        promo = get_sheet("promo data", default_promo)
    except Exception as e:
        st.error(f"Gagal membaca file Excel: {e}")
        sales, expiry, pricing, promo = load_sample_data()
else:
    sales, expiry, pricing, promo = load_sample_data()
    st.info("Menggunakan data contoh. Upload file Excel untuk memakai data nyata.")

# -----------------------
# Normalize sales table columns (best effort)
# -----------------------
# Ensure datetime, numeric columns
if 'Tanggal' in sales.columns:
    sales['Tanggal'] = pd.to_datetime(sales['Tanggal'], errors='coerce')
else:
    st.error("Sheet Sales Data harus punya kolom 'Tanggal'.")
if 'Produk' not in sales.columns:
    st.error("Sheet Sales Data harus punya kolom 'Produk'.")

# numeric conversions
for col in ['Qty','Harga','Total','Stok_Awal','Sisa_Stok']:
    if col in sales.columns:
        sales[col] = sales[col].apply(safe_convert_num)

# ensure Total column (compute if missing)
if 'Total' not in sales.columns or sales['Total'].isnull().all():
    sales['Total'] = sales['Qty'] * sales['Harga']

# If Stok_Awal or Sisa_Stok missing, leave NaN
# Add Year column to help baseline mapping
sales['Year'] = sales['Tanggal'].dt.year

# -----------------------
# Compute Baseline Juni per product per year
# -----------------------
# sum totals where month==6 grouped by (Produk, Year)
june_totals = (sales[sales['Tanggal'].dt.month == 6]
               .groupby(['Produk','Year'], as_index=False)
               .agg({'Total':'sum'})
               .rename(columns={'Total':'JuneTotal'}))

# Merge back to sales
sales = sales.merge(june_totals, on=['Produk','Year'], how='left')

# Trend vs Juni per row: safe
def compute_trend(row):
    jt = row.get('JuneTotal', np.nan)
    total = row.get('Total', np.nan)
    try:
        if pd.isna(jt) or jt == 0:
            return np.nan
        else:
            return (total / jt) - 1
    except Exception:
        return np.nan

sales['Trend_vs_Juni'] = sales.apply(compute_trend, axis=1)

# -----------------------
# KPI calculations
# -----------------------
# Promo KPI
promo['Target_Sales'] = promo['Target_Sales'].apply(safe_convert_num)
promo['Actual_Sales'] = promo['Actual_Sales'].apply(safe_convert_num)
promo['Biaya_Promosi'] = promo['Biaya_Promosi'].apply(safe_convert_num)

total_actual = promo['Actual_Sales'].sum() if 'Actual_Sales' in promo.columns else 0.0
total_target = promo['Target_Sales'].sum() if 'Target_Sales' in promo.columns else 0.0
pencapaian = (total_actual / total_target) if total_target and total_target!=0 else np.nan

# Pricing margin (per product)
if 'Harga_Beli' in pricing.columns and 'Harga_Jual' in pricing.columns:
    pricing['Margin_pct'] = (pricing['Harga_Jual'] - pricing['Harga_Beli']) / pricing['Harga_Jual']
else:
    pricing['Margin_pct'] = np.nan

# ROI per promo row and combined
if 'Biaya_Promosi' in promo.columns and 'Actual_Sales' in promo.columns and 'Target_Sales' in promo.columns:
    promo['ROI'] = promo.apply(lambda r: (r['Actual_Sales'] - r['Target_Sales'])/r['Biaya_Promosi'] if (r['Biaya_Promosi'] and r['Biaya_Promosi']!=0) else np.nan, axis=1)
else:
    promo['ROI'] = np.nan
combined_roi = promo['ROI'].mean() if 'ROI' in promo.columns else np.nan

# -----------------------
# Dashboard display
# -----------------------
st.header("KPI Ringkasan")
col1, col2, col3 = st.columns(3)

# thresholds (you can expose UI later to edit)
sales_thresholds = {"green":1.0, "yellow":0.8}      # pencapaian: >=100% green, >=80% amber
margin_thresholds = {"green":0.20, "yellow":0.15}  # margin: >=20% green, >=15% amber
roi_thresholds = {"green":1.0, "yellow":0.5}       # ROI: >=100% green, >=50% amber

with col1:
    st.subheader("Sales")
    st.metric("Actual Sales", f"Rp {int(total_actual):,}", delta=f"{pencapaian:.0%}" if not pd.isna(pencapaian) else "N/A")
    st.markdown(f"**Status**: {rag_emoji(pencapaian, sales_thresholds)}", unsafe_allow_html=True)

with col2:
    st.subheader("Margin (sample)")
    # show average margin or first product margin
    avg_margin = pricing['Margin_pct'].mean() if not pricing['Margin_pct'].isna().all() else np.nan
    st.metric("Avg Margin", f"{avg_margin:.2%}" if not pd.isna(avg_margin) else "N/A")
    st.markdown(f"**Status**: {rag_emoji(avg_margin, margin_thresholds)}", unsafe_allow_html=True)

with col3:
    st.subheader("ROI Promo")
    st.metric("Avg ROI", f"{combined_roi:.2%}" if not pd.isna(combined_roi) else "N/A")
    st.markdown(f"**Status**: {rag_emoji(combined_roi, roi_thresholds)}", unsafe_allow_html=True)

# -----------------------
# Visual: Trend by product (monthly sum)
# -----------------------
st.header("Grafik Tren Penjualan (per bulan — sum Total)")

# create month-year column
sales['MonthYear'] = sales['Tanggal'].dt.to_period('M').astype(str)
monthly = sales.groupby(['MonthYear','Produk'], as_index=False).agg({'Total':'sum'})
fig = px.line(monthly, x='MonthYear', y='Total', color='Produk', markers=True, title="Tren Penjualan per Produk (bulanan)")
st.plotly_chart(fig, use_container_width=True)

# -----------------------
# Table: Sales Data with Trend coloring
# -----------------------
st.header("Sales Data (detail)")
# Prepare display table
display_sales = sales.copy()
# Friendly formatting
display_sales['Total'] = display_sales['Total'].fillna(0).astype(float)
display_sales['Trend_vs_Juni_pct'] = display_sales['Trend_vs_Juni'].map(lambda x: f"{x:.2%}" if not pd.isna(x) else "-")

# Conditional color function for styler
def color_trend(val):
    try:
        if pd.isna(val):
            return ''
        v = float(val)
        if v > 0:
            return 'background-color: #C6EFCE'  # light green
        elif v < 0:
            return 'background-color: #F4CCCC'  # light red
        else:
            return 'background-color: #FFF2CC'  # light yellow
    except:
        return ''

# color low stock
def color_stock(val):
    try:
        v = float(val)
        if v <= 50:
            return 'background-color: #F4CCCC'  # red
        else:
            return ''
    except:
        return ''

# Build styler
sty = display_sales[['Tanggal','Produk','Qty','Harga','Total','Stok_Awal','Sisa_Stok','Trend_vs_Juni_pct']].style.format({
    'Harga': '{:,.0f}',
    'Total': '{:,.0f}',
}).applymap(lambda v: '', subset=['Tanggal','Produk','Qty','Harga','Total']) \
  .applymap(lambda v: color_stock(v), subset=['Sisa_Stok']) \
  .applymap(lambda v: '', subset=['Trend_vs_Juni_pct'])  # trend coloring below

# For trend coloring we need to apply on numeric column Trend_vs_Juni
# Create a style for trend column separately
def style_trend_col(df):
    return [color_trend(x) for x in df['Trend_vs_Juni'].values]

try:
    sty = sty.apply(lambda df: style_trend_col(display_sales), axis=0, subset=['Trend_vs_Juni_pct'])
except Exception:
    # fallback: no style for trend
    pass

st.write("Keterangan: baris berwarna merah = stok rendah; hijau = tren naik vs Juni; kuning = sama; merah = turun.")
st.dataframe(display_sales[['Tanggal','Produk','Qty','Harga','Total','Sisa_Stok','Trend_vs_Juni_pct']].sort_values(['Produk','Tanggal']), height=360)

# -----------------------
# Expiry monitoring
# -----------------------
st.header("Monitoring Expiry")
expiry['Exp_Date'] = pd.to_datetime(expiry['Exp_Date'], errors='coerce')
expiry['Days_to_Expiry'] = (expiry['Exp_Date'] - pd.Timestamp.today()).dt.days
expiry['Status'] = expiry['Days_to_Expiry'].apply(lambda d: 'Expired' if d < 0 else ('Almost expired' if d <= 30 else 'OK'))

# show table with highlights
st.dataframe(expiry[['Produk','Batch_No','Exp_Date','Qty_Stok','Days_to_Expiry','Status']])

# -----------------------
# Pricing & Promo tables
# -----------------------
st.header("Pricing Data")
if not pricing.empty:
    pricing_display = pricing.copy()
    pricing_display['Margin_pct'] = pricing_display['Margin_pct'].map(lambda x: f"{x:.2%}" if not pd.isna(x) else "-")
    st.table(pricing_display)
else:
    st.write("Tidak ada data pricing.")

st.header("Promo Data")
if not promo.empty:
    promo_display = promo.copy()
    promo_display['ROI'] = promo_display['ROI'].map(lambda x: f"{x:.2%}" if not pd.isna(x) else "-")
    st.table(promo_display)
else:
    st.write("Tidak ada data promo.")

# -----------------------
# Download processed data (CSV)
# -----------------------
st.header("Export / Unduh")
@st.cache_data
def to_csv_bytes(df):
    return df.to_csv(index=False).encode('utf-8')

colA, colB = st.columns(2)
with colA:
    st.download_button("Unduh Sales Data (diproses) CSV", to_csv_bytes(sales), "sales_processed.csv", "text/csv")
with colB:
    st.download_button("Unduh Expiry Data CSV", to_csv_bytes(expiry), "expiry_processed.csv", "text/csv")

st.sidebar.header("Pengaturan")
safety_stock = st.sidebar.number_input("Threshold stok rendah (Sisa_Stok)", min_value=0, value=50)
show_only_low_stock = st.sidebar.checkbox("Tunjukkan hanya stok rendah di tabel", value=False)

if show_only_low_stock:
    low = sales[sales['Sisa_Stok'] <= safety_stock]
    st.subheader(f"Produk dengan Sisa_Stok ≤ {safety_stock}")
    st.dataframe(low[['Tanggal','Produk','Qty','Total','Sisa_Stok','Trend_vs_Juni_pct']])

#import streamlit as st
#import pandas as pd

# Load data dari Excel
#file_path = "Groseri_Database_100Items.xlsx"
#xls = pd.ExcelFile(file_path)

#sales = pd.read_excel(xls, "Sales Data")
#pricing = pd.read_excel(xls, "Pricing Data")
#promo = pd.read_excel(xls, "Promo Data")
#expiry = pd.read_excel(xls, "Expiry Data")

# Hitung KPI
#total_sales = sales["Total"].sum()
#avg_margin = ((pricing["Harga_Jual"] - pricing["Harga_Beli"]) / pricing["Harga_Jual"]).mean()
#roi = (promo["Actual_Sales"].sum() - promo["Target_Sales"].sum()) / promo["Biaya_Promosi"].sum()
#stok_avail = sales["Sisa_Stok"].sum() / sales["Stok_Awal"].sum()
#expiry_risk = expiry.loc[expiry["Exp_Date"] <= pd.Timestamp.today() + pd.Timedelta(days=30), "Qty_Stok"].sum()

# Tampilkan KPI
#st.title("📊 Dashboard KPI Groseri")

#st.metric("Sales", f"Rp {total_sales:,.0f}")
#st.metric("Margin", f"{avg_margin:.1%}")
#st.metric("ROI Promo", f"{roi:.1%}")
#st.metric("Stok Availability", f"{stok_avail:.1%}")
#st.metric("Expiry Risk", f"{expiry_risk} unit")


import streamlit as st
import pandas as pd

# Load data
file_path = "Groseri_Database_100Items.xlsx"
xls = pd.ExcelFile(file_path)

sales = pd.read_excel(xls, "Sales Data")
pricing = pd.read_excel(xls, "Pricing Data")
promo = pd.read_excel(xls, "Promo Data")
expiry = pd.read_excel(xls, "Expiry Data")

# Hitung KPI
total_sales = sales["Total"].sum()
avg_margin = ((pricing["Harga_Jual"] - pricing["Harga_Beli"]) / pricing["Harga_Jual"]).mean()
roi = (promo["Actual_Sales"].sum() - promo["Target_Sales"].sum()) / promo["Biaya_Promosi"].sum()
stok_avail = sales["Sisa_Stok"].sum() / sales["Stok_Awal"].sum()
expiry_risk = expiry.loc[expiry["Exp_Date"] <= pd.Timestamp.today() + pd.Timedelta(days=30), "Qty_Stok"].sum()

# Fungsi indikator warna
def rag_indicator(value, green_thr, yellow_thr, reverse=False):
    if reverse:  # contoh: expiry risk (semakin kecil semakin bagus)
        if value <= green_thr: return "🟢"
        elif value <= yellow_thr: return "🟡"
        else: return "🔴"
    else:
        if value >= green_thr: return "🟢"
        elif value >= yellow_thr: return "🟡"
        else: return "🔴"

# Dashboard
st.title("📊 Dashboard KPI Groseri")

# KPI Cards dengan expander penjelasan
with st.expander(f"{rag_indicator(total_sales, 1e8, 5e7)} Sales: Rp {total_sales:,.0f}"):
    st.write("Mengukur total penjualan. Hijau jika ≥ target.")

with st.expander(f"{rag_indicator(avg_margin, 0.25, 0.15)} Margin: {avg_margin:.1%}"):
    st.write("Profitabilitas. Kuning artinya cukup tapi harus diawasi.")

with st.expander(f"{rag_indicator(roi, 1.0, 0.0)} ROI Promosi: {roi:.1%}"):
    st.write("Efektivitas promosi. Hijau artinya promosi menguntungkan.")

with st.expander(f"{rag_indicator(stok_avail, 0.7, 0.4)} Stok Availability: {stok_avail:.1%}"):
    st.write("Ketersediaan stok. Hijau jika aman.")

with st.expander(f"{rag_indicator(expiry_risk, 100, 500, reverse=True)} Expiry Risk: {expiry_risk} unit"):
    st.write("Produk dekat expired. Merah = risiko tinggi.")


#import streamlit as st
#import pandas as pd

# Load data
#file_path = "Groseri_Database_100Items.xlsx"
#xls = pd.ExcelFile(file_path)

#promo = pd.read_excel(xls, "Promo Data")

# Buat kolom perhitungan dasar
#promo["Total_Sales"] = promo["Actual_Sales"]
#promo["Selisih"] = promo["Actual_Sales"] - promo["Target_Sales"]
#promo["Status"] = promo["Selisih"].apply(lambda x: "✅ Tercapai" if x >= 0 else "❌ Tidak")

# Tentukan kolom yang tersedia
#kolom_tampil = ["Target_Sales", "Actual_Sales", "Total_Sales", "Selisih", "Status"]

#if "Produk" in promo.columns:
    #kolom_tampil = ["Produk"] + kolom_tampil
#if "Sales_Normal" in promo.columns:
    #kolom_tampil.insert(3, "Sales_Normal")  # sisipkan sebelum Total_Sales

# Tampilkan tabel
#st.subheader("📊 Perbandingan Target vs Actual Sales")
#st.dataframe(promo[kolom_tampil])




