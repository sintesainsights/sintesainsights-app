"""
dashboard.py
------------
Dashboard interaktif untuk memantau perubahan kepemilikan saham BEI per bulan,
berdasarkan data yang sudah digabung oleh parse_balancepos.py, dilengkapi
dengan chart perbandingan Harga Penutupan Akhir Bulan vs Volume KSEI 
(Lokal / Asing / Total sesuai filter) serta narasi interpretasi otomatis.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

DATA_FILE = "data_kepemilikan.csv"

st.set_page_config(page_title="Dashboard Kepemilikan Saham BEI", layout="wide")


@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"])
    df["Bulan"] = df["Date"].dt.to_period("M").astype(str)
    return df


@st.cache_data
def load_stock_market_data(ticker_code: str) -> pd.DataFrame:
    """Mengambil data historis bulanan dari Yahoo Finance untuk saham BEI (suffix .JK)"""
    yf_ticker = f"{ticker_code}.JK"
    df_mkt = yf.download(yf_ticker, period="2y", interval="1mo", progress=False)
    
    if df_mkt.empty:
        return pd.DataFrame()
    
    if isinstance(df_mkt.columns, pd.MultiIndex):
        df_mkt.columns = df_mkt.columns.get_level_values(0)
        
    df_mkt = df_mkt.reset_index()
    if "Date" in df_mkt.columns:
        df_mkt["Bulan"] = pd.to_datetime(df_mkt["Date"]).dt.to_period("M").astype(str)
    elif "Datetime" in df_mkt.columns:
        df_mkt["Bulan"] = pd.to_datetime(df_mkt["Datetime"]).dt.to_period("M").astype(str)
        
    return df_mkt


try:
    df = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(
        f"File '{DATA_FILE}' tidak ditemukan. Jalankan dulu:\n\n"
        "`python parse_balancepos.py --input-dir <folder_txt> --output data_kepemilikan.csv`"
    )
    st.stop()

st.title("📊 Dashboard Kepemilikan Saham BEI")
st.caption("Data kepemilikan saham per jenis investor, sumber: KSEI Balance Position & Yahoo Finance")

# ---------------- Sidebar filter ----------------
st.sidebar.header("Filter")

all_codes = sorted(df["Code"].unique())
selected_code = st.sidebar.selectbox("Pilih Kode Saham", all_codes)

kepemilikan_option = st.sidebar.radio(
    "Tampilkan kepemilikan", ["Lokal", "Asing", "Total (Lokal + Asing)"], index=2
)

label_map = df.drop_duplicates("JenisInvestor").set_index("JenisInvestor")["JenisInvestorLabel"].to_dict()
all_investor_codes = sorted(label_map.keys())
selected_investors = st.sidebar.multiselect(
    "Jenis Investor",
    options=all_investor_codes,
    default=all_investor_codes,
    format_func=lambda c: f"{c} - {label_map[c]}",
)

if not selected_investors:
    st.warning("Pilih minimal satu jenis investor di sidebar.")
    st.stop()

# ---------------- Siapkan data saham terpilih ----------------
stock_df = df[(df["Code"] == selected_code) & (df["JenisInvestor"].isin(selected_investors))].copy()

if kepemilikan_option == "Total (Lokal + Asing)":
    plot_df = (
        stock_df.groupby(["Bulan", "JenisInvestor", "JenisInvestorLabel"], as_index=False)["Jumlah"].sum()
    )
    # Agregasi total volume kepemilikan per bulan untuk chart kanan
    vol_ksei_df = stock_df.groupby("Bulan", as_index=False)["Jumlah"].sum()
    bar_name = "Volume Total (Lokal + Asing)"
    bar_color = "rgba(55, 128, 191, 0.6)"
else:
    plot_df = stock_df[stock_df["Kepemilikan"] == kepemilikan_option]
    vol_ksei_df = plot_df.groupby("Bulan", as_index=False)["Jumlah"].sum()
    bar_name = f"Volume Kepemilikan {kepemilikan_option}"
    bar_color = "rgba(44, 160, 44, 0.6)" if kepemilikan_option == "Lokal" else "rgba(255, 127, 14, 0.6)"

pivot = plot_df.pivot_table(
    index="Bulan", columns="JenisInvestorLabel", values="Jumlah", aggfunc="sum"
).fillna(0)
pivot = pivot.sort_index()

st.subheader(f"Saham: {selected_code} — {kepemilikan_option}")

if len(pivot) < 2:
    st.info(
        "Baru ada 1 periode bulan di dataset. Tambahkan file Balancepos bulan lain lalu "
        "jalankan ulang parser untuk melihat tren perubahan dari waktu ke waktu."
    )

col1, col2 = st.columns(2)

# ---------------- Line chart: tren kepemilikan per bulan ----------------
with col1:
    st.markdown("**Tren Kepemilikan per Bulan (Line Chart)**")
    fig_line = go.Figure()
    for col in pivot.columns:
        fig_line.add_trace(go.Scatter(x=pivot.index, y=pivot[col], mode="lines+markers", name=col))
    fig_line.update_layout(
        xaxis_title="Bulan", yaxis_title="Jumlah Saham", legend=dict(orientation="h", y=-0.3), height=450
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ---------------- Dual-Axis Chart: Harga Penutupan vs Volume KSEI (Dinamis Sesuai Filter) ----------------
with col2:
    st.markdown(f"**Harga Penutupan vs {bar_name}**")
    
    mkt_df = load_stock_market_data(selected_code)
    fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
    
    if not mkt_df.empty and "Close" in mkt_df.columns:
        mkt_filtered = mkt_df[mkt_df["Bulan"].isin(pivot.index)].sort_values("Bulan")
        
        # Gabungkan data market (Close) dengan volume KSEI berdasarkan bulan
        merged_chart_df = pd.merge(mkt_filtered, vol_ksei_df, on="Bulan", how="inner")
        
        if not merged_chart_df.empty:
            # 1. Bar Chart untuk Volume KSEI (Dinamis: Lokal / Asing / Total)
            fig_dual.add_trace(
                go.Bar(
                    x=merged_chart_df["Bulan"],
                    y=merged_chart_df["Jumlah"],
                    name=bar_name,
                    marker_color=bar_color,
                ),
                secondary_y=False,
            )
            
            # 2. Line Chart untuk Harga Penutupan (Close)
            fig_dual.add_trace(
                go.Scatter(
                    x=merged_chart_df["Bulan"],
                    y=merged_chart_df["Close"],
                    name="Harga Penutupan (Close)",
                    mode="lines+markers",
                    line=dict(color="gold", width=3),
                ),
                secondary_y=True,
            )
    
    fig_dual.update_layout(
        xaxis_title="Bulan",
        legend=dict(orientation="h", y=-0.3),
        height=450,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    fig_dual.update_yaxes(title_text="<b>Jumlah Saham (Volume KSEI)</b>", secondary_y=False, showgrid=True)
    fig_dual.update_yaxes(title_text="<b>Harga Penutupan (IDR)</b>", secondary_y=True, showgrid=False)
    
    st.plotly_chart(fig_dual, use_container_width=True)

# ---------------- Tabel perubahan bulan-ke-bulan (MoM) ----------------
st.subheader("Perubahan Bulan ke Bulan (MoM)")
change_df = pivot.diff().round(0)
pct_df = pivot.pct_change().round(4) * 100

if len(pivot) >= 2:
    latest = pivot.index[-1]
    prev = pivot.index[-2]
    summary = pd.DataFrame(
        {
            f"Jumlah ({prev})": pivot.loc[prev],
            f"Jumlah ({latest})": pivot.loc[latest],
            "Perubahan": change_df.loc[latest],
            "Perubahan (%)": pct_df.loc[latest],
        }
    )
    st.dataframe(summary.style.format({
        f"Jumlah ({prev})": "{:,.0f}",
        f"Jumlah ({latest})": "{:,.0f}",
        "Perubahan": "{:+,.0f}",
        "Perubahan (%)": "{:+.2f}%",
    }), use_container_width=True)

    # ---------------- Narasi / Interpretasi Otomatis Perubahan MoM ----------------
    st.markdown("### 📝 Analisis & Interpretasi Perubahan MoM")
    
    sig_changes = summary[summary["Perubahan"].abs() > 0]
    if not sig_changes.empty:
        top_movers_mom = summary.reindex(summary["Perubahan"].abs().sort_values(ascending=False).index)
        
        st.info(f"**Periode Analisis:** Perbandingan antara **{prev}** dan **{latest}** untuk emiten **{selected_code}** (Segmen: **{kepemilikan_option}**).")
        
        narration_bullets = []
        for inv_label, row in top_movers_mom.iterrows():
            chg = row["Perubahan"]
            pct = row["Perubahan (%)"]
            
            if abs(chg) == 0:
                continue
                
            direction = "meningkat" if chg > 0 else "menurun"
            
            context_hint = ""
            inv_lower = inv_label.lower()
            if "foreign" in inv_lower or kepemilikan_option == "Asing":
                if chg > 0:
                    context_hint = "Indikasi masuknya aliran modal asing (*foreign inflow*), merefleksikan optimisme investor institusi global."
                else:
                    context_hint = "Indikasi keluarnya aliran modal asing (*foreign outflow*), mengindikasikan rotasi portofolio."
            elif "corporate" in inv_lower or "perusahaan" in inv_lower:
                if chg > 0:
                    context_hint = "Potensi aksi korporasi strategis atau akumulasi oleh pengendali."
                else:
                    context_hint = "Potensi pelepasan kepemilikan atau divestasi korporasi."
            elif "retail" in inv_lower or "individual" in inv_lower or "perorangan" in inv_lower:
                if chg > 0:
                    context_hint = "Menunjukkan tingginya antusiasme serta akumulasi oleh investor ritel."
                else:
                    context_hint = "Menandakan kejenuhan atau aksi realisasi keuntungan (*profit-taking*) ritel."
            elif "mutual fund" in inv_lower or "reksa dana" in inv_lower or "pension" in inv_lower or "dana pensiun" in inv_lower:
                if chg > 0:
                    context_hint = "Penyesuaian bobot portofolio (*rebalancing*) institusional atau manajer investasi."
                else:
                    context_hint = "Pencairan atau pengurangan alokasi dana kelolaan institusi."
            else:
                context_hint = "Mencerminkan dinamika likuiditas pada tipe investor ini."

            bullet_text = (
                f"- **{inv_label}**: Kepemilikan {direction} sebesar **{chg:+,.0f} saham** "
                f"({pct:+.2f}%). *Interpretasi:* {context_hint}"
            )
            narration_bullets.append(bullet_text)

        for b in narration_bullets:
            st.markdown(b)
            
        st.markdown("---")
        total_net_change = summary["Perubahan"].sum()
        if kepemilikan_option == "Total (Lokal + Asing)":
            if total_net_change > 0:
                st.success(f"**Kesimpulan Agregat:** Total volume kepemilikan mengalami penambahan bersih sebesar **{total_net_change:+,.0f} saham** pada periode ini.")
            elif total_net_change < 0:
                st.warning(f"**Kesimpulan Agregat:** Total volume kepemilikan mengalami pengurangan bersih sebesar **{total_net_change:+,.0f} saham** pada periode ini.")
            else:
                st.info("**Kesimpulan Agregat:** Total volume kepemilikan relatif stabil.")
    else:
        st.write("Tidak ada perubahan kepemilikan yang tercatat antara kedua periode tersebut.")
else:
    st.dataframe(pivot.style.format("{:,.0f}"), use_container_width=True)

# ---------------- Top movers lintas semua saham (bulan terakhir) ----------------
st.subheader("Top Perubahan Kepemilikan Lintas Semua Saham (Bulan Terakhir)")
mover_investor = st.selectbox(
    "Jenis investor untuk analisis top movers",
    options=all_investor_codes,
    format_func=lambda c: f"{c} - {label_map[c]}",
    key="mover_investor",
)
mover_owner = st.radio("Kepemilikan", ["Lokal", "Asing"], horizontal=True, key="mover_owner")

mover_df = df[(df["JenisInvestor"] == mover_investor) & (df["Kepemilikan"] == mover_owner)]
mover_pivot = mover_df.pivot_table(index="Code", columns="Bulan", values="Jumlah", aggfunc="sum").fillna(0)
mover_pivot = mover_pivot.reindex(sorted(mover_pivot.columns), axis=1)

if mover_pivot.shape[1] >= 2:
    last_col, prev_col = mover_pivot.columns[-1], mover_pivot.columns[-2]
    movers = pd.DataFrame(
        {
            "Perubahan": mover_pivot[last_col] - mover_pivot[prev_col],
        }
    ).sort_values("Perubahan", ascending=False)
    top_n = st.slider("Jumlah saham ditampilkan", 5, 30, 10)
    st.bar_chart(movers.head(top_n))
else:
    st.info("Perlu minimal 2 bulan data untuk menghitung top movers.")