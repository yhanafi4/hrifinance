import git
import streamlit as st
import sqlite3
import pandas as pd
import datetime
import google.generativeai as genai

# ==========================================
# 1. PENGATURAN HALAMAN & KONFIGURASI
# ==========================================
st.set_page_config(page_title="HRI Finance", page_icon="💼", layout="wide")

# Masukkan API Key Gemini Anda di sini
GEMINI_API_KEY = ""

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. PENGATURAN DATABASE (SQLite)
# ==========================================
DB_NAME = "hri_finance.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Tabel Pelanggan
    c.execute('''CREATE TABLE IF NOT EXISTS customers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, term INTEGER)''')
    # Tabel Jobcode
    c.execute('''CREATE TABLE IF NOT EXISTS jobcodes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, jobcode TEXT, nama_pekerjaan TEXT, type TEXT, lokasi TEXT)''')
    # Tabel Progress
    c.execute('''CREATE TABLE IF NOT EXISTS progresses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, project TEXT, jobcode TEXT, amount REAL, created_at TEXT)''')
    # Tabel Invoice
    c.execute('''CREATE TABLE IF NOT EXISTS invoices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, no_invoice TEXT, customer_name TEXT, date TEXT,
                  tgl_jatuh_tempo TEXT, desc TEXT, type TEXT, jobcode TEXT, periode_progress TEXT,
                  harga_jual REAL, pengurang_sblm REAL, ppn REAL, pph23 REAL, pengurang_stlh REAL,
                  total_tagihan REAL, dana_masuk REAL, tgl_pembayaran TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def run_query(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def execute_query(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

# ==========================================
# 3. FUNGSI UTILITAS & AI
# ==========================================
def format_idr(value):
    if pd.isna(value): return "Rp 0"
    return f"Rp {value:,.0f}".replace(",", ".")

def call_gemini(prompt):
    if not GEMINI_API_KEY:
        return "API Key Gemini belum diatur di dalam kode Python."
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gagal memanggil AI: {str(e)}"

# ==========================================
# 4. TAMPILAN DASHBOARD
# ==========================================
def show_dashboard():
    st.title("📊 Dashboard Monitoring")

    # Filter Tahun
    current_year = datetime.datetime.now().year
    years = list(range(2025, max(2025, current_year) + 2))
    selected_year = st.selectbox("Pilih Tahun Analisis:", years, index=years.index(current_year))

    # Ambil Data
    df_inv = run_query("SELECT * FROM invoices WHERE status != 'BATAL'")
    df_prog = run_query("SELECT * FROM progresses")

    # Perhitungan Metrik
    total_tagihan = df_inv['total_tagihan'].sum() if not df_inv.empty else 0
    total_dana_masuk = df_inv.loc[df_inv['tgl_pembayaran'].str.startswith(str(selected_year), na=False), 'dana_masuk'].sum() if not df_inv.empty else 0
    total_piutang = (df_inv['total_tagihan'] - df_inv['dana_masuk']).sum() if not df_inv.empty else 0
    outstanding_count = len(df_inv[df_inv['status'] == 'OUTSTANDING']) if not df_inv.empty else 0

    total_prog_diakui = df_prog['amount'].sum() if not df_prog.empty else 0
    total_billed_dpp = df_inv['harga_jual'].sum() if not df_inv.empty else 0
    total_unbilled = total_prog_diakui - total_billed_dpp

    # Tampilkan Metrik
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Progress (Unbilled)", format_idr(total_unbilled))
    col2.metric("Tagihan Terbit", format_idr(total_tagihan))
    col3.metric("Dana Masuk", format_idr(total_dana_masuk))
    col4.metric("Sisa Piutang", format_idr(total_piutang), f"{outstanding_count} Invoice", delta_color="inverse")

    st.divider()

    # Grafik Progress vs Invoice
    st.subheader(f"📈 Grafik Progress vs Invoice ({selected_year})")

    chart_data = {"Bulan": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
                  "Progress Diakui": [0]*12, "Invoice Terbit": [0]*12}

    if not df_prog.empty:
        for _, row in df_prog.iterrows():
            if str(selected_year) in str(row['period']):
                # Pencarian bulan sederhana
                for i, m in enumerate(["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]):
                    if m.lower() in str(row['period']).lower():
                        chart_data["Progress Diakui"][i] += row['amount']

    if not df_inv.empty:
        for _, row in df_inv.iterrows():
            if str(row['date']).startswith(str(selected_year)):
                month_idx = int(str(row['date']).split('-')[1]) - 1
                chart_data["Invoice Terbit"][month_idx] += row['harga_jual']

    df_chart = pd.DataFrame(chart_data).set_index("Bulan")
    st.bar_chart(df_chart, color=["#60a5fa", "#4f46e5"]) # Biru dan Indigo

    # Analisis AI
    st.subheader("✨ Analisis Arus Kas AI")
    if st.button("Generate Analisis Keuangan"):
        with st.spinner("AI sedang menganalisis data..."):
            prompt = f"Buatkan analisis singkat arus kas tahun {selected_year}: Progress Belum Ditagih: {format_idr(total_unbilled)}, Invoice Terbit: {format_idr(total_tagihan)}, Dana Masuk: {format_idr(total_dana_masuk)}, Sisa Piutang: {format_idr(total_piutang)} ({outstanding_count} inv). Berikan ringkasan 2 paragraf dan rekomendasi."
            insight = call_gemini(prompt)
            st.info(insight)

# ==========================================
# 5. TAMPILAN INVOICE & PIUTANG
# ==========================================
def show_invoices():
    st.title("🧾 Manajemen Invoice & Piutang")

    tab1, tab2 = st.tabs(["Daftar Invoice", "Buat Invoice Baru"])

    with tab1:
        df_inv = run_query("SELECT id, no_invoice, customer_name, date, tgl_jatuh_tempo, total_tagihan, dana_masuk, (total_tagihan - dana_masuk) as sisa_piutang, status FROM invoices ORDER BY id DESC")
        if not df_inv.empty:
            df_inv['total_tagihan'] = df_inv['total_tagihan'].apply(format_idr)
            df_inv['dana_masuk'] = df_inv['dana_masuk'].apply(format_idr)
            df_inv['sisa_piutang'] = df_inv['sisa_piutang'].apply(format_idr)
            st.dataframe(df_inv, use_container_width=True, hide_index=True)

            st.subheader("💳 Update Pembayaran")
            col_sel, col_val, col_btn = st.columns([2, 2, 1])
            with col_sel:
                inv_list = df_inv[df_inv['status'] == 'OUTSTANDING']['no_invoice'].tolist()
                selected_inv = st.selectbox("Pilih Invoice:", inv_list)
            with col_val:
                nominal_masuk = st.number_input("Nominal Dana Masuk (Rp):", min_value=0)
            with col_btn:
                st.write("") # spacing
                st.write("")
                if st.button("Simpan Pembayaran", type="primary"):
                    if selected_inv and nominal_masuk > 0:
                        tgl_bayar = datetime.datetime.now().strftime("%Y-%m-%d")
                        # Cek apakah lunas
                        inv_data = run_query("SELECT total_tagihan FROM invoices WHERE no_invoice=?", (selected_inv,))
                        tagihan = inv_data.iloc[0]['total_tagihan']
                        status = "PAID" if nominal_masuk >= tagihan else "OUTSTANDING"

                        execute_query("UPDATE invoices SET dana_masuk=?, tgl_pembayaran=?, status=? WHERE no_invoice=?",
                                      (nominal_masuk, tgl_bayar, status, selected_inv))
                        st.success("Pembayaran berhasil diupdate!")
                        st.rerun()
        else:
            st.info("Belum ada data invoice.")

    with tab2:
        df_cust = run_query("SELECT name, term FROM customers")
        df_jobs = run_query("SELECT jobcode, nama_pekerjaan, type FROM jobcodes")

        if df_cust.empty or df_jobs.empty:
            st.warning("⚠️ Harap isi Data Pelanggan dan Jobcode di menu Master Data terlebih dahulu.")
            return

        with st.form("form_invoice"):
            st.subheader("Informasi Dokumen")
            col1, col2 = st.columns(2)
            no_inv = col1.text_input("No. Invoice", placeholder="HRI-INV-...")
            tgl_terbit = col2.date_input("Tgl Terbit")

            pelanggan = col1.selectbox("Pelanggan", df_cust['name'].tolist())
            pekerjaan = col2.selectbox("Pekerjaan (Lookup)", df_jobs['nama_pekerjaan'].tolist())

            desc = st.text_area("Deskripsi Pekerjaan")

            st.subheader("Kalkulasi Finansial")
            col3, col4 = st.columns(2)
            dpp = col3.number_input("Harga Jual / DPP (Rp)", min_value=0.0, step=100000.0)
            pengurang_sblm = col4.number_input("Pengurang Sblm PPN (Rp)", min_value=0.0, step=100000.0)

            # Auto-calculate
            jenis_job = df_jobs[df_jobs['nama_pekerjaan'] == pekerjaan]['type'].iloc[0]
            jobcode_val = df_jobs[df_jobs['nama_pekerjaan'] == pekerjaan]['jobcode'].iloc[0]

            tarif_ppn = 0.11
            ppn = (dpp - pengurang_sblm) * tarif_ppn
            pph23 = 0 if jenis_job in ['PENJUALAN ASSET', 'SPAREPART'] else (dpp * 0.02)
            total_tagihan = (dpp - pengurang_sblm) + ppn - pph23

            st.info(f"Kalkulasi Otomatis: PPN = {format_idr(ppn)} | PPh 23 = {format_idr(pph23)} | **TOTAL = {format_idr(total_tagihan)}**")

            submitted = st.form_submit_button("Simpan Invoice", type="primary")
            if submitted:
                term = df_cust[df_cust['name'] == pelanggan]['term'].iloc[0]
                jatuh_tempo = tgl_terbit + datetime.timedelta(days=int(term))

                execute_query('''INSERT INTO invoices (no_invoice, customer_name, date, tgl_jatuh_tempo, desc, type, jobcode,
                                 harga_jual, pengurang_sblm, ppn, pph23, total_tagihan, dana_masuk, status)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                              (no_inv, pelanggan, tgl_terbit.strftime("%Y-%m-%d"), jatuh_tempo.strftime("%Y-%m-%d"),
                               desc, jenis_job, jobcode_val, dpp, pengurang_sblm, ppn, pph23, total_tagihan, 0, "OUTSTANDING"))
                st.success("Invoice berhasil disimpan!")
                st.rerun()

# ==========================================
# 6. TAMPILAN MASTER DATA
# ==========================================
def show_master_data():
    st.title("⚙️ Master Data")
    tab1, tab2 = st.tabs(["Data Pelanggan", "Data Jobcode"])

    with tab1:
        with st.form("form_cust"):
            st.subheader("Tambah Pelanggan")
            c1, c2, c3 = st.columns([3, 1, 1])
            cust_name = c1.text_input("Nama PT/Pelanggan")
            cust_term = c2.number_input("Termin (Hari)", min_value=0, value=30)
            if c3.form_submit_button("Simpan"):
                execute_query("INSERT INTO customers (name, term) VALUES (?, ?)", (cust_name, cust_term))
                st.success("Tersimpan!")
                st.rerun()

        df_cust = run_query("SELECT * FROM customers")
        st.dataframe(df_cust, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("form_jobcode"):
            st.subheader("Tambah Jobcode")
            j1, j2, j3 = st.columns(3)
            jobcode = j1.text_input("Jobcode (Contoh: HRI-AHL)")
            nama_job = j2.text_input("Nama Pekerjaan")
            tipe_job = j3.selectbox("Jenis Pekerjaan", ["FULL PAKET", "HAULING", "MSP/MSC", "RENTAL", "PENJUALAN ASSET", "SPAREPART"])
            if st.form_submit_button("Simpan Jobcode"):
                execute_query("INSERT INTO jobcodes (jobcode, nama_pekerjaan, type, lokasi) VALUES (?, ?, ?, ?)",
                              (jobcode, nama_job, tipe_job, "-"))
                st.success("Tersimpan!")
                st.rerun()

        df_job = run_query("SELECT * FROM jobcodes")
        st.dataframe(df_job, use_container_width=True, hide_index=True)

# ==========================================
# 7. MENU NAVIGASI (SIDEBAR)
# ==========================================
st.sidebar.title("HRI FINANCE")
st.sidebar.caption("Sistem Monitoring Keuangan")
st.sidebar.divider()

menu = st.sidebar.radio("Navigasi Menu", ["Dashboard", "Invoice & Piutang", "Master Data"])

if menu == "Dashboard":
    show_dashboard()
elif menu == "Invoice & Piutang":
    show_invoices()
elif menu == "Master Data":
    show_master_data()