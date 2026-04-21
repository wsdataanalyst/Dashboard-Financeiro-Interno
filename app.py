"""
Dashboard Financeiro e Resultados - Sistema de Cobrança
Versão 11.1 - Flexibilidade na alteração de status + indicadores de clientes/boletos
"""

import streamlit as st
import pandas as pd
import hashlib
import unicodedata
import sqlite3
from datetime import datetime, timedelta
import plotly.express as px

# ---------- CONFIGURAÇÃO DA PÁGINA ----------
st.set_page_config(page_title="Dashboard Financeiro", page_icon="💰", layout="wide")

st.markdown("""
<style>
    html, body, [class*="css"] { font-size: 18px; }
    h1 { font-size: 2.5rem !important; }
    h2 { font-size: 2rem !important; }
    h3 { font-size: 1.6rem !important; }
    [data-testid="stMetricValue"] { font-size: 2rem !important; }
    [data-testid="stMetricLabel"] { font-size: 1.1rem !important; }
    .stButton button { font-size: 1.1rem !important; padding: 0.5rem 1rem !important; }
</style>
""", unsafe_allow_html=True)

TAXA_JUROS_DIARIO = 0.002       # 0,20% ao dia
TAXA_JUROS_MENSAL = 0.06        # 6% ao mês

STATUS_MAP = {
    'pendente': '⏳ Pendente',
    'em_tratativa': '📞 Em Tratativa',
    'contatado_sem_exito': '❌ Sem Êxito',
    'acordo_finalizado': '✅ Acordo Finalizado',
    'acordo_pendente': '⏰ Acordo Pendente'
}

DB_PATH = "cobranca.db"

# ---------- CONEXÃO COM SQLITE ----------
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_cliente TEXT NOT NULL,
                numero_titulo TEXT NOT NULL,
                razao_social TEXT,
                valor_original REAL,
                juros REAL,
                valor_atualizado REAL,
                valor_acordo REAL,
                tempo_atraso INTEGER,
                emissao TEXT,
                vencimento TEXT,
                parcela TEXT,
                tipo_faturamento TEXT,
                vendedor TEXT,
                situacao TEXT,
                historico_contato TEXT,
                canal TEXT,
                assistente_responsavel TEXT,
                status_tratativa TEXT DEFAULT 'pendente',
                observacao TEXT DEFAULT '',
                data_pagamento_programado TEXT,
                data_ultima_atualizacao TIMESTAMP,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(codigo_cliente, numero_titulo)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS historico_tratativas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER REFERENCES clientes(id),
                assistente TEXT,
                acao TEXT,
                status_anterior TEXT,
                status_novo TEXT,
                observacao TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS solicitacoes_reabertura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                assistente TEXT NOT NULL,
                motivo TEXT,
                status TEXT DEFAULT 'pendente',
                data_solicitacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_resposta TIMESTAMP,
                admin_responsavel TEXT
            )
        ''')
        conn.commit()

def criar_usuarios_iniciais():
    usuarios = [
        ("Edvanison Muniz", "edvanison@empresa.com", "admin123", "admin"),
        ("Jane Xavier", "jane@empresa.com", "jane123", "assistente"),
        ("Renata Kelly", "renata@empresa.com", "renata123", "assistente")
    ]
    with get_connection() as conn:
        for nome, email, senha, perfil in usuarios:
            senha_hash = hashlib.sha256(senha.encode()).hexdigest()
            cur = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            if cur.fetchone() is None:
                conn.execute(
                    "INSERT INTO usuarios (nome, email, senha_hash, perfil) VALUES (?, ?, ?, ?)",
                    (nome, email, senha_hash, perfil)
                )
        conn.commit()

def verificar_login(email, senha):
    senha_hash = hashlib.sha256(senha.encode()).hexdigest()
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT nome, perfil FROM usuarios WHERE email = ? AND senha_hash = ?",
            conn, params=(email, senha_hash)
        )
    if not df.empty:
        return df.iloc[0]['nome'], df.iloc[0]['perfil']
    return None

def processar_upload_excel(arquivo, modo="atualizar"):
    # (mantido sem alterações)
    try:
        xl = pd.ExcelFile(arquivo)
        abas = xl.sheet_names
    except Exception as e:
        st.error(f"Erro ao ler o arquivo Excel: {e}")
        return None
    if not abas:
        st.error("A planilha não contém nenhuma aba.")
        return None
    aba_selecionada = st.selectbox("Selecione a aba da planilha:", abas)
    linha_cabecalho = st.number_input("Linha do cabeçalho (0 = primeira):", min_value=0, value=4, step=1)
    try:
        df = pd.read_excel(arquivo, sheet_name=aba_selecionada, header=linha_cabecalho)
    except Exception as e:
        st.error(f"Erro ao ler a aba '{aba_selecionada}': {e}")
        return None
    df = df.dropna(how='all')
    def normalizar_texto(texto):
        if not isinstance(texto, str):
            return ""
        texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
        texto = texto.lower()
        texto = ' '.join(texto.split())
        return texto
    colunas_originais = df.columns.tolist()
    colunas_normalizadas = [normalizar_texto(col) for col in colunas_originais]
    mapa_esperado = {
        normalizar_texto('Nome Cliente'): 'Nome Cliente',
        normalizar_texto('Cliente'): 'Cliente',
        normalizar_texto('No. Titulo'): 'No. Titulo',
        normalizar_texto('Vlr.Titulo'): 'Vlr.Titulo',
        normalizar_texto('Vlr Baixado'): 'Vlr Baixado',
        normalizar_texto('SALDO'): 'SALDO',
        normalizar_texto('Atraso(D)'): 'Atraso(D)',
        normalizar_texto('Valor Juros'): 'Valor Juros',
        normalizar_texto('Vlr a pagar'): 'Vlr a pagar',
        normalizar_texto('Emissao'): 'Emissao',
        normalizar_texto('Vencimento'): 'Vencimento',
        normalizar_texto('Vendedor'): 'Vendedor',
        normalizar_texto('Parcela'): 'Parcela',
        normalizar_texto('Tipo'): 'Tipo',
        normalizar_texto('SITUACAO'): 'SITUACAO',
        normalizar_texto('N_VEND'): 'N_VEND',
        normalizar_texto('CANAL'): 'CANAL',
        normalizar_texto('Observações'): 'Observações',
    }
    renomear = {}
    for i, col_norm in enumerate(colunas_normalizadas):
        if col_norm in mapa_esperado:
            renomear[colunas_originais[i]] = mapa_esperado[col_norm]
    if not renomear:
        st.error("Nenhuma coluna mapeada.")
        return None
    df.rename(columns=renomear, inplace=True)
    colunas_obrigatorias = [
        'Nome Cliente', 'Cliente', 'No. Titulo', 'Vlr.Titulo', 'SALDO',
        'Atraso(D)', 'Valor Juros', 'Vlr a pagar', 'Emissao', 'Vencimento',
        'Vendedor', 'Parcela', 'Tipo', 'SITUACAO'
    ]
    faltantes = [col for col in colunas_obrigatorias if col not in df.columns]
    if faltantes:
        st.error(f"Colunas obrigatórias ausentes: {', '.join(faltantes)}")
        return None
    for col in ['Vlr.Titulo', 'Vlr Baixado', 'SALDO', 'Valor Juros', 'Vlr a pagar']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    if 'Atraso(D)' in df.columns:
        df['Atraso(D)'] = pd.to_numeric(df['Atraso(D)'], errors='coerce').fillna(0).astype(int)
    df['assistente_responsavel'] = df['Atraso(D)'].apply(
        lambda x: 'Jane Xavier' if x <= 30 else 'Renata Kelly'
    )
    with get_connection() as conn:
        if modo == "substituir":
            conn.execute("DELETE FROM clientes")
            conn.execute("DELETE FROM historico_tratativas")
            conn.execute("DELETE FROM solicitacoes_reabertura")
            conn.commit()
            st.warning("Base antiga removida. Inserindo novos dados...")
        total = len(df)
        progress = st.progress(0, f"Processando {total} registros...")
        batch_size = 50
        for i, (_, row) in enumerate(df.iterrows()):
            codigo = str(row['Cliente']).strip()
            titulo = str(row['No. Titulo']).strip()
            if not codigo or not titulo:
                continue
            emissao_str = row['Emissao'].strftime('%Y-%m-%d') if hasattr(row['Emissao'], 'strftime') else str(row['Emissao'])
            vencimento_str = row['Vencimento'].strftime('%Y-%m-%d') if hasattr(row['Vencimento'], 'strftime') else str(row['Vencimento'])
            valor_original = float(row['Vlr.Titulo'])
            juros = float(row['Valor Juros'])
            valor_atualizado = float(row['Vlr a pagar'])
            tempo_atraso = int(row['Atraso(D)'])
            razao = str(row['Nome Cliente'])
            vendedor = str(row['Vendedor'])
            situacao = str(row['SITUACAO'])
            hist_contato = str(row.get('Observações', '')) if pd.notna(row.get('Observações', '')) else ''
            canal = str(row.get('CANAL', '')) if pd.notna(row.get('CANAL', '')) else ''
            parcela = str(row['Parcela']).strip()
            tipo_fat = str(row['Tipo'])
            assistente = row['assistente_responsavel']
            conn.execute('''
                INSERT INTO clientes (
                    codigo_cliente, numero_titulo, razao_social, valor_original, juros, valor_atualizado,
                    tempo_atraso, emissao, vencimento, parcela, tipo_faturamento, vendedor, situacao,
                    historico_contato, canal, assistente_responsavel, status_tratativa, observacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente', '')
                ON CONFLICT(codigo_cliente, numero_titulo) DO UPDATE SET
                    razao_social = excluded.razao_social,
                    valor_original = excluded.valor_original,
                    juros = excluded.juros,
                    valor_atualizado = excluded.valor_atualizado,
                    tempo_atraso = excluded.tempo_atraso,
                    emissao = excluded.emissao,
                    vencimento = excluded.vencimento,
                    parcela = excluded.parcela,
                    tipo_faturamento = excluded.tipo_faturamento,
                    vendedor = excluded.vendedor,
                    situacao = excluded.situacao,
                    historico_contato = excluded.historico_contato,
                    canal = excluded.canal,
                    assistente_responsavel = excluded.assistente_responsavel,
                    data_ultima_atualizacao = CURRENT_TIMESTAMP
            ''', (
                codigo, titulo, razao, valor_original, juros, valor_atualizado,
                tempo_atraso, emissao_str, vencimento_str, parcela, tipo_fat, vendedor, situacao,
                hist_contato, canal, assistente
            ))
            if i % batch_size == 0:
                conn.commit()
                progress.progress((i+1)/total)
        conn.commit()
        progress.empty()
        st.success(f"Upload concluído! {total} registros processados.")
        st.cache_data.clear()
        return df

def atualizar_status_cliente(cliente_id, novo_status, observacao, assistente, data_pagamento=None, valor_acordo=None):
    try:
        with get_connection() as conn:
            cur = conn.execute("SELECT status_tratativa FROM clientes WHERE id = ?", (cliente_id,))
            row = cur.fetchone()
            if not row:
                return False
            status_anterior = row[0]
            set_parts = ["status_tratativa = ?", "observacao = ?", "data_ultima_atualizacao = CURRENT_TIMESTAMP"]
            params = [novo_status, observacao]
            if data_pagamento:
                set_parts.append("data_pagamento_programado = ?")
                params.append(data_pagamento)
            if valor_acordo is not None:
                set_parts.append("valor_acordo = ?")
                params.append(valor_acordo)
            params.append(cliente_id)
            conn.execute(f"UPDATE clientes SET {', '.join(set_parts)} WHERE id = ?", params)
            conn.execute('''
                INSERT INTO historico_tratativas (cliente_id, assistente, acao, status_anterior, status_novo, observacao)
                VALUES (?, ?, 'atualizacao_status', ?, ?, ?)
            ''', (cliente_id, assistente, status_anterior, novo_status, observacao))
            conn.commit()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar status: {e}")
        return False

@st.cache_data(ttl=600)
def carregar_clientes_assistente_cached(nome):
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM clientes WHERE assistente_responsavel = ?",
            conn, params=(nome,)
        )
    return df

def carregar_clientes_assistente(nome):
    return carregar_clientes_assistente_cached(nome)

def calcular_juros_projetado(valor_original, data_vencimento, data_futura):
    if data_vencimento is None or valor_original == 0:
        return valor_original
    try:
        venc = datetime.strptime(data_vencimento, '%Y-%m-%d')
        fut = datetime.strptime(data_futura, '%Y-%m-%d')
        dias = (fut - venc).days
        if dias <= 0:
            return valor_original
        if dias < 30:
            return valor_original * (1 + TAXA_JUROS_DIARIO * dias)
        else:
            meses = dias // 30
            resto_dias = dias % 30
            valor_com_meses = valor_original * ((1 + TAXA_JUROS_MENSAL) ** meses)
            if resto_dias > 0:
                valor_com_meses *= (1 + TAXA_JUROS_DIARIO * resto_dias)
            return valor_com_meses
    except:
        return valor_original

# ---------- DASHBOARD AGREGADO ----------
def aplicar_filtro_periodo(df, campo_data, data_inicio, data_fim):
    if data_inicio and data_fim and campo_data in df.columns:
        df[campo_data] = pd.to_datetime(df[campo_data], errors='coerce')
        mask = (df[campo_data] >= pd.to_datetime(data_inicio)) & (df[campo_data] <= pd.to_datetime(data_fim))
        return df[mask]
    return df

def is_inadimplente(row):
    return row['tempo_atraso'] > 0 and row['status_tratativa'] != 'acordo_finalizado'

@st.cache_data(ttl=300)
def get_dashboard_data(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT valor_atualizado, tempo_atraso, vencimento, emissao, status_tratativa FROM clientes
        ''', conn)
    df = aplicar_filtro_periodo(df, campo_filtro, data_inicio, data_fim)
    total_titulos = len(df)
    valor_total = df['valor_atualizado'].sum()
    df_inad = df[df.apply(is_inadimplente, axis=1)]
    valor_inadimplente = df_inad['valor_atualizado'].sum()
    return pd.Series({
        'total_titulos': total_titulos,
        'valor_total': valor_total,
        'valor_inadimplente': valor_inadimplente,
        'df_inad': df_inad
    })

@st.cache_data(ttl=300)
def get_status_counts(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT status_tratativa, valor_atualizado, vencimento, emissao FROM clientes
        ''', conn)
    df = aplicar_filtro_periodo(df, campo_filtro, data_inicio, data_fim)
    return df.groupby('status_tratativa').agg(
        qtd=('status_tratativa', 'count'),
        total=('valor_atualizado', 'sum')
    ).reset_index()

@st.cache_data(ttl=300)
def get_assistente_comparativo(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT assistente_responsavel, valor_atualizado, tempo_atraso, vencimento, emissao, status_tratativa FROM clientes
        ''', conn)
    df = aplicar_filtro_periodo(df, campo_filtro, data_inicio, data_fim)
    df['inad'] = df.apply(is_inadimplente, axis=1)
    return df.groupby('assistente_responsavel').agg(
        valor_total=('valor_atualizado', 'sum'),
        clientes_em_atraso=('inad', 'sum'),
        clientes_total=('assistente_responsavel', 'count')
    ).reset_index()

@st.cache_data(ttl=300)
def get_acordos_ontem():
    ontem = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total
            FROM clientes
            WHERE status_tratativa IN ('acordo_finalizado', 'acordo_pendente')
              AND DATE(data_ultima_atualizacao) = ?
        ''', conn, params=(ontem,))
    if df.empty:
        return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

@st.cache_data(ttl=300)
def get_acordos_hoje():
    hoje = datetime.now().strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total
            FROM clientes
            WHERE data_pagamento_programado = ?
        ''', conn, params=(hoje,))
    if df.empty:
        return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

@st.cache_data(ttl=300)
def get_acordos_futuros():
    hoje = datetime.now().strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total
            FROM clientes
            WHERE data_pagamento_programado > ?
        ''', conn, params=(hoje,))
    if df.empty:
        return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

def criar_solicitacao_reabertura(cliente_id, assistente, motivo):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO solicitacoes_reabertura (cliente_id, assistente, motivo, status)
            VALUES (?, ?, ?, 'pendente')
        ''', (cliente_id, assistente, motivo))
        conn.commit()

def listar_solicitacoes_pendentes():
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT s.id, s.cliente_id, c.codigo_cliente, c.razao_social, s.assistente, s.motivo, s.data_solicitacao
            FROM solicitacoes_reabertura s
            JOIN clientes c ON s.cliente_id = c.id
            WHERE s.status = 'pendente'
            ORDER BY s.data_solicitacao
        ''', conn)
    return df

def processar_solicitacao(solicitacao_id, aprovado, admin_nome):
    with get_connection() as conn:
        novo_status = 'aprovada' if aprovado else 'rejeitada'
        conn.execute('''
            UPDATE solicitacoes_reabertura
            SET status = ?, data_resposta = CURRENT_TIMESTAMP, admin_responsavel = ?
            WHERE id = ?
        ''', (novo_status, admin_nome, solicitacao_id))
        if aprovado:
            cur = conn.execute("SELECT cliente_id FROM solicitacoes_reabertura WHERE id = ?", (solicitacao_id,))
            row = cur.fetchone()
            if row:
                cliente_id = row[0]
                conn.execute("UPDATE clientes SET status_tratativa = 'em_tratativa', data_ultima_atualizacao = CURRENT_TIMESTAMP WHERE id = ?", (cliente_id,))
                conn.execute('''
                    INSERT INTO historico_tratativas (cliente_id, assistente, acao, status_anterior, status_novo, observacao)
                    VALUES (?, 'Sistema', 'reabertura_aprovada', 'acordo_finalizado', 'em_tratativa', ?)
                ''', (cliente_id, f"Reabertura aprovada por {admin_nome}"))
        conn.commit()
    st.cache_data.clear()

def transferir_cliente(codigo_cliente, nova_assistente):
    with get_connection() as conn:
        conn.execute('''
            UPDATE clientes SET assistente_responsavel = ?, data_ultima_atualizacao = CURRENT_TIMESTAMP
            WHERE codigo_cliente = ?
        ''', (nova_assistente, codigo_cliente))
        conn.commit()
    st.cache_data.clear()
    return True

# ========== INICIALIZAÇÃO ==========
init_db()
criar_usuarios_iniciais()

# ========== AUTENTICAÇÃO ==========
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = None
    st.session_state.perfil = None

if not st.session_state.autenticado:
    st.title("🔐 Login")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        email = st.text_input("Email")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = verificar_login(email, senha)
            if user:
                st.session_state.autenticado = True
                st.session_state.usuario = user[0]
                st.session_state.perfil = user[1]
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

# ========== INTERFACE PRINCIPAL ==========
st.sidebar.title(f"👤 {st.session_state.usuario}")
st.sidebar.write(f"Perfil: **{st.session_state.perfil}**")

if st.sidebar.button("🚪 Sair"):
    st.cache_data.clear()
    st.session_state.autenticado = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Filtro de Período")
usar_filtro = st.sidebar.checkbox("Ativar filtro")
if usar_filtro:
    campo_filtro = st.sidebar.selectbox("Filtrar por:", ["Data de Vencimento", "Data de Emissão"])
    campo_db = "vencimento" if campo_filtro == "Data de Vencimento" else "emissao"
    col1, col2 = st.sidebar.columns(2)
    with col1:
        data_inicio = st.date_input("Data inicial", value=datetime.now() - timedelta(days=30))
    with col2:
        data_fim = st.date_input("Data final", value=datetime.now())
else:
    campo_db = "vencimento"
    data_inicio = None
    data_fim = None

if st.session_state.perfil == "admin":
    menu = st.sidebar.radio("Menu", ["📤 Upload", "📊 Dashboard Geral", "🔄 Solicitações de Reabertura", "📥 Exportar Dados", "🔄 Transferir Cliente"])
else:
    menu = st.sidebar.radio("Menu", ["📋 Meus Clientes", "📊 Meu Dashboard"])

# ========== ADMIN ==========
if st.session_state.perfil == "admin":
    if menu == "📤 Upload":
        st.header("Upload da Planilha")
        modo_upload = st.radio("Modo de upload:", ["Atualizar base (recomendado)", "Substituir base (apaga tudo)"])
        arquivo = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls"])
        if arquivo:
            modo = "atualizar" if "Atualizar" in modo_upload else "substituir"
            if modo == "substituir":
                if not st.checkbox("CONFIRMO que desejo apagar todos os dados existentes"):
                    st.warning("Marque a confirmação para prosseguir.")
                    st.stop()
            df = processar_upload_excel(arquivo, modo=modo)
            if df is not None:
                st.cache_data.clear()

    elif menu == "📊 Dashboard Geral":
        st.header("Dashboard Gerencial")
        metricas = get_dashboard_data(data_inicio, data_fim, campo_db)
        total_clientes = int(metricas['total_titulos'])
        total_valor = float(metricas['valor_total'])
        inad_valor = float(metricas['valor_inadimplente'])
        percent_inad = (inad_valor / total_valor * 100) if total_valor else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Títulos", total_clientes)
        col2.metric("Valor Total em Aberto", f"R$ {total_valor:,.2f}")
        col3.metric("Inadimplência (%)", f"{percent_inad:.2f}%",
                   delta=f"{percent_inad-3:.2f} p.p." if percent_inad > 3 else "✅ Dentro da meta")

        st.subheader("📅 Acordos")
        col_a, col_b, col_c = st.columns(3)
        qtd_ontem, val_ontem = get_acordos_ontem()
        with col_a:
            st.metric("Acordos Fechados Ontem", f"{qtd_ontem} títulos", f"R$ {val_ontem:,.2f}")
        qtd_hoje, val_hoje = get_acordos_hoje()
        with col_b:
            st.metric("Acordos Programados Hoje", f"{qtd_hoje} títulos", f"R$ {val_hoje:,.2f}")
        qtd_fut, val_fut = get_acordos_futuros()
        with col_c:
            st.metric("Acordos Programados Futuros", f"{qtd_fut} títulos", f"R$ {val_fut:,.2f}")

        st.subheader("📈 Status das Tratativas (Global)")
        df_status = get_status_counts(data_inicio, data_fim, campo_db)
        cols = st.columns(len(df_status))
        for i, (_, row) in enumerate(df_status.iterrows()):
            status = row['status_tratativa']
            with cols[i]:
                st.metric(STATUS_MAP.get(status, status), f"{row['qtd']} títulos", f"R$ {row['total']:,.2f}")

        st.subheader("📊 Análise Comparativa por Assistente")
        df_ass = get_assistente_comparativo(data_inicio, data_fim, campo_db)
        if not df_ass.empty:
            df_ass['Taxa_Inadimplencia'] = (df_ass['clientes_em_atraso'] / df_ass['clientes_total'] * 100).fillna(0)
            fig = px.bar(df_ass, x='assistente_responsavel', y='valor_total', text='clientes_em_atraso',
                         color='Taxa_Inadimplencia', color_continuous_scale='RdYlGn_r',
                         labels={'valor_total': 'Valor Total (R$)', 'assistente_responsavel': 'Assistente'})
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("🔴 Top 10 Inadimplentes")
        with get_connection() as conn:
            top_inad = pd.read_sql_query('''
                SELECT razao_social, valor_atualizado, tempo_atraso, assistente_responsavel
                FROM clientes WHERE tempo_atraso > 0 AND status_tratativa != 'acordo_finalizado'
                ORDER BY valor_atualizado DESC
                LIMIT 10
            ''', conn)
        st.dataframe(top_inad, use_container_width=True)

    elif menu == "🔄 Solicitações de Reabertura":
        st.header("Solicitações de Reabertura")
        df_solic = listar_solicitacoes_pendentes()
        if df_solic.empty:
            st.info("Nenhuma solicitação pendente.")
        else:
            for _, row in df_solic.iterrows():
                with st.expander(f"Cliente {row['codigo_cliente']} - {row['razao_social']} (Solicitado por {row['assistente']})"):
                    st.write(f"Motivo: {row['motivo']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"✅ Aprovar", key=f"apr_{row['id']}"):
                            processar_solicitacao(row['id'], True, st.session_state.usuario)
                            st.success("Aprovada!")
                            st.rerun()
                    with col2:
                        if st.button(f"❌ Rejeitar", key=f"rej_{row['id']}"):
                            processar_solicitacao(row['id'], False, st.session_state.usuario)
                            st.success("Rejeitada.")
                            st.rerun()

    elif menu == "📥 Exportar Dados":
        st.header("Exportar Base Completa")
        with get_connection() as conn:
            df_export = pd.read_sql_query("SELECT * FROM clientes ORDER BY assistente_responsavel, status_tratativa", conn)
        if df_export.empty:
            st.warning("Sem dados.")
        else:
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Clientes')
            st.download_button("📥 Baixar Excel", data=output.getvalue(),
                               file_name=f"base_cobranca_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")

    elif menu == "🔄 Transferir Cliente":
        st.header("Transferir Cliente entre Assistentes")
        codigo = st.text_input("Código do Cliente")
        nova = st.selectbox("Nova Assistente", ["Jane Xavier", "Renata Kelly"])
        if st.button("Transferir"):
            if codigo:
                transferir_cliente(codigo, nova)
                st.success(f"Cliente {codigo} transferido para {nova}.")
            else:
                st.warning("Informe o código.")

# ========== ASSISTENTE ==========
else:
    st.sidebar.subheader("🔍 Consulta Manual")
    codigo_manual = st.sidebar.text_input("Código do Cliente")
    if st.sidebar.button("Buscar"):
        if codigo_manual:
            with get_connection() as conn:
                df_manual = pd.read_sql_query(
                    "SELECT * FROM clientes WHERE codigo_cliente = ?",
                    conn, params=(codigo_manual,)
                )
            if not df_manual.empty:
                st.sidebar.success(f"Cliente: {df_manual.iloc[0]['razao_social']}")
                st.session_state.cliente_selecionado = codigo_manual
                st.rerun()
            else:
                st.sidebar.warning("Código não encontrado.")

    if menu == "📋 Meus Clientes":
        st.header(f"Clientes de {st.session_state.usuario}")

        df_clientes = carregar_clientes_assistente(st.session_state.usuario)
        if df_clientes.empty:
            st.info("Nenhum título atribuído.")
            st.stop()

        # Cards de status
        st.subheader("📊 Status das Tratativas")
        status_list = list(STATUS_MAP.keys())
        cols = st.columns(len(status_list))
        if 'filtro_status' not in st.session_state:
            st.session_state.filtro_status = None

        cores_card = {
            'pendente': '#6B7280',
            'em_tratativa': '#2563EB',
            'contatado_sem_exito': '#DC2626',
            'acordo_finalizado': '#059669',
            'acordo_pendente': '#D97706'
        }

        for i, status in enumerate(status_list):
            df_status = df_clientes[df_clientes['status_tratativa'] == status]
            qtd = len(df_status)
            valor = df_status['valor_atualizado'].sum()
            with cols[i]:
                card_html = f"""
                <div style="background-color:{cores_card[status]}; padding:15px; border-radius:15px; text-align:center; margin-bottom:5px;">
                    <h4 style="color:white; margin:0;">{STATUS_MAP[status]}</h4>
                    <h2 style="color:white; margin:5px 0;">{qtd}</h2>
                    <p style="color:#FDE047; margin:0;">R$ {valor:,.2f}</p>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                if st.button("Filtrar", key=f"card_{status}"):
                    st.session_state.filtro_status = status
                    st.rerun()

        if st.session_state.filtro_status:
            st.info(f"Filtrando por: {STATUS_MAP[st.session_state.filtro_status]}")
            if st.button("❌ Limpar filtro"):
                st.session_state.filtro_status = None
                st.rerun()
            df_filtrado = df_clientes[df_clientes['status_tratativa'] == st.session_state.filtro_status]
        else:
            df_filtrado = df_clientes

        st.subheader("📋 Lista de Clientes")
        if not df_filtrado.empty:
            codigos = df_filtrado['codigo_cliente'].unique().tolist()
            if 'cliente_selecionado' in st.session_state and st.session_state.cliente_selecionado in codigos:
                default_idx = codigos.index(st.session_state.cliente_selecionado)
            else:
                default_idx = 0

            codigo_sel = st.selectbox(
                "Selecione um cliente:",
                codigos,
                index=default_idx,
                format_func=lambda c: f"{c} - {df_filtrado[df_filtrado['codigo_cliente']==c]['razao_social'].iloc[0]}"
            )

            if codigo_sel:
                with get_connection() as conn:
                    titulos_df = pd.read_sql_query(
                        "SELECT * FROM clientes WHERE codigo_cliente = ? AND assistente_responsavel = ?",
                        conn, params=(codigo_sel, st.session_state.usuario)
                    )
                if titulos_df.empty:
                    st.error("Cliente não encontrado.")
                else:
                    cliente_nome = titulos_df.iloc[0]['razao_social']
                    st.write(f"**{cliente_nome}** possui {len(titulos_df)} título(s).")

                    # Tabela editável com checkboxes
                    titulos_df['Selecionar'] = False
                    edited_df = st.data_editor(
                        titulos_df[['Selecionar', 'numero_titulo', 'vencimento', 'valor_atualizado', 'status_tratativa', 'observacao']],
                        column_config={"Selecionar": st.column_config.CheckboxColumn("Selecionar")},
                        hide_index=True,
                        use_container_width=True,
                        key=f"editor_{codigo_sel}"
                    )
                    ids_selecionados = titulos_df[edited_df['Selecionar'] == True]['id'].tolist()

                    if ids_selecionados:
                        st.write(f"{len(ids_selecionados)} título(s) selecionado(s).")

                        # Filtrar apenas títulos que não são acordo_finalizado para ação em lote
                        ids_validos = [tid for tid in ids_selecionados if titulos_df[titulos_df['id']==tid]['status_tratativa'].iloc[0] != 'acordo_finalizado']
                        if len(ids_validos) < len(ids_selecionados):
                            st.warning("Alguns títulos com 'Acordo Finalizado' não serão alterados.")

                        if ids_validos:
                            with st.form("form_tratativa_lote"):
                                novo_status = st.selectbox("Novo Status", options=list(STATUS_MAP.keys()), format_func=lambda x: STATUS_MAP[x])
                                motivo = st.selectbox("Motivo (opcional)", ['', 'Vencimento fim de semana', 'Repasse de verba', 'Problemas financeiros', 'Erro de programação', 'Mudança de Pessoal', 'Contato não atende!'])
                                obs = st.text_area("Observações")
                                data_pag = st.date_input("Data de Pagamento Programado (opcional)", value=None, min_value=datetime.today())
                                valor_acordo = None
                                if data_pag:
                                    ex = titulos_df[titulos_df['id'] == ids_validos[0]].iloc[0]
                                    valor_proj = calcular_juros_projetado(ex['valor_original'], ex['vencimento'], data_pag.strftime('%Y-%m-%d'))
                                    st.write(f"💡 Valor projetado (exemplo): R$ {valor_proj:,.2f}")
                                    valor_acordo = st.number_input("Valor do Acordo (R$)", value=float(valor_proj), step=0.01)
                                if st.form_submit_button("Aplicar aos selecionados"):
                                    obs_completa = f"{motivo}: {obs}" if motivo else obs
                                    data_str = data_pag.strftime('%Y-%m-%d') if data_pag else None
                                    for tid in ids_validos:
                                        atualizar_status_cliente(tid, novo_status, obs_completa, st.session_state.usuario, data_str, valor_acordo)
                                    st.success(f"{len(ids_validos)} título(s) atualizado(s)!")
                                    st.rerun()

                    # Detalhes de título individual com possibilidade de alteração (exceto acordo_finalizado)
                    with st.expander("🔎 Ver/Editar título específico"):
                        titulo_det = st.selectbox("Número do título:", titulos_df['numero_titulo'].tolist())
                        if titulo_det:
                            titulo = titulos_df[titulos_df['numero_titulo'] == titulo_det].iloc[0]
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Nº Título:** {titulo['numero_titulo']}")
                                st.write(f"**Emissão:** {titulo['emissao']}")
                                st.write(f"**Vencimento:** {titulo['vencimento']}")
                                st.write(f"**Parcela:** {titulo['parcela']}")
                                st.write(f"**Valor Original:** R$ {titulo['valor_original']:,.2f}")
                            with col2:
                                st.write(f"**Juros:** R$ {titulo['juros']:,.2f}")
                                st.write(f"**Valor a Pagar:** R$ {titulo['valor_atualizado']:,.2f}")
                                st.write(f"**Situação:** {titulo['situacao']}")
                                st.write(f"**Canal:** {titulo['canal']}")
                                st.write(f"**Status:** {STATUS_MAP.get(titulo['status_tratativa'], titulo['status_tratativa'])}")
                                if titulo['data_pagamento_programado']:
                                    st.write(f"**Pagamento Programado:** {titulo['data_pagamento_programado']}")

                            status_atual = titulo['status_tratativa']
                            if status_atual != 'acordo_finalizado':
                                with st.form(f"form_edit_{titulo['id']}"):
                                    novo_status = st.selectbox("Alterar para:", options=list(STATUS_MAP.keys()), format_func=lambda x: STATUS_MAP[x], key=f"status_{titulo['id']}")
                                    motivo = st.selectbox("Motivo (opcional)", ['', 'Vencimento fim de semana', 'Repasse de verba', 'Problemas financeiros', 'Erro de programação', 'Mudança de Pessoal', 'Contato não atende!'], key=f"motivo_{titulo['id']}")
                                    obs = st.text_area("Observações", key=f"obs_{titulo['id']}")
                                    data_pag = st.date_input("Data de Pagamento Programado (opcional)", value=None, min_value=datetime.today(), key=f"data_{titulo['id']}")
                                    valor_acordo = None
                                    if data_pag:
                                        valor_proj = calcular_juros_projetado(titulo['valor_original'], titulo['vencimento'], data_pag.strftime('%Y-%m-%d'))
                                        st.write(f"💡 Valor projetado: R$ {valor_proj:,.2f}")
                                        valor_acordo = st.number_input("Valor do Acordo (R$)", value=float(valor_proj), step=0.01, key=f"valor_{titulo['id']}")
                                    if st.form_submit_button("Atualizar"):
                                        obs_completa = f"{motivo}: {obs}" if motivo else obs
                                        data_str = data_pag.strftime('%Y-%m-%d') if data_pag else None
                                        if atualizar_status_cliente(titulo['id'], novo_status, obs_completa, st.session_state.usuario, data_str, valor_acordo):
                                            st.success("Título atualizado!")
                                            st.rerun()
                            else:
                                st.warning("Títulos com 'Acordo Finalizado' não podem ser alterados diretamente. Solicite reabertura se necessário.")

        else:
            st.info("Nenhum cliente com este status.")

    elif menu == "📊 Meu Dashboard":
        st.header("Meu Desempenho")
        df_clientes = carregar_clientes_assistente(st.session_state.usuario)
        if df_clientes.empty:
            st.info("Sem dados.")
            st.stop()

        df_clientes_filtrado = aplicar_filtro_periodo(df_clientes.copy(), campo_db, data_inicio, data_fim)

        metricas_global = get_dashboard_data(data_inicio, data_fim, campo_db)
        total_global = float(metricas_global['valor_total'])
        inad_global = float(metricas_global['valor_inadimplente'])
        percent_global = (inad_global / total_global * 100) if total_global else 0
        st.metric("🌍 Inadimplência Global", f"{percent_global:.2f}%", delta="Meta ≤3%" if percent_global <=3 else "Acima da meta")

        total_ind = df_clientes_filtrado['valor_atualizado'].sum()
        df_inad_ind = df_clientes_filtrado[df_clientes_filtrado.apply(is_inadimplente, axis=1)]
        inad_ind = df_inad_ind['valor_atualizado'].sum()
        percent_ind = (inad_ind / total_ind * 100) if total_ind else 0
        qtd_inad = len(df_inad_ind)

        # NOVOS INDICADORES
        clientes_unicos = df_clientes_filtrado['codigo_cliente'].nunique()
        total_boletos = len(df_clientes_filtrado)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Meu Valor Aberto", f"R$ {total_ind:,.2f}")
        col2.metric("Minha Inadimplência", f"{percent_ind:.2f}%")
        col3.metric("Clientes Únicos", clientes_unicos)
        col4.metric("Total de Boletos", total_boletos)

        qtd_hoje, val_hoje = get_acordos_hoje()
        if qtd_hoje > 0:
            st.warning(f"🔔 **Fique atento!** Você tem **{qtd_hoje}** acordo(s) programado(s) para hoje, totalizando **R$ {val_hoje:,.2f}**.")

        st.subheader("📅 Meus Acordos")
        col_a, col_b, col_c = st.columns(3)
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        hoje_str = hoje.strftime('%Y-%m-%d')
        ontem_str = ontem.strftime('%Y-%m-%d')

        df_ass = df_clientes_filtrado
        qtd_ontem = len(df_ass[(df_ass['status_tratativa'].isin(['acordo_finalizado', 'acordo_pendente'])) & (pd.to_datetime(df_ass['data_ultima_atualizacao']).dt.date == ontem)])
        val_ontem = df_ass[(df_ass['status_tratativa'].isin(['acordo_finalizado', 'acordo_pendente'])) & (pd.to_datetime(df_ass['data_ultima_atualizacao']).dt.date == ontem)]['valor_acordo'].sum()
        with col_a:
            st.metric("Acordos Fechados Ontem", f"{qtd_ontem} títulos", f"R$ {val_ontem:,.2f}")

        df_hoje = df_ass[df_ass['data_pagamento_programado'] == hoje_str]
        qtd_hoje_ass = len(df_hoje)
        val_hoje_ass = df_hoje['valor_acordo'].sum()
        with col_b:
            st.metric("Acordos Programados Hoje", f"{qtd_hoje_ass} títulos", f"R$ {val_hoje_ass:,.2f}")

        df_fut = df_ass[df_ass['data_pagamento_programado'] > hoje_str]
        qtd_fut = len(df_fut)
        val_fut = df_fut['valor_acordo'].sum()
        with col_c:
            st.metric("Acordos Programados Futuros", f"{qtd_fut} títulos", f"R$ {val_fut:,.2f}")

        # Forecast
        df_pendentes = df_ass[df_ass['status_tratativa'] == 'acordo_pendente']
        if not df_pendentes.empty:
            valor_pendente = df_pendentes['valor_atualizado'].sum()
            nova_inad = inad_ind - valor_pendente
            nova_taxa = (nova_inad / total_ind * 100) if total_ind else 0
            st.subheader("🔮 Projeção")
            st.write(f"Se todos os **acordos pendentes** (R$ {valor_pendente:,.2f}) forem finalizados, sua inadimplência cairá para **{nova_taxa:.2f}%**.")

        # Meta para 3%
        if percent_ind > 3:
            valor_necessario = inad_ind - (0.03 * total_ind)
            st.subheader("🎯 Meta para 3%")
            st.write(f"Para atingir **3%** de inadimplência, você precisa recuperar **R$ {valor_necessario:,.2f}** em títulos inadimplentes.")
            if qtd_inad > 0:
                valor_medio = inad_ind / qtd_inad
                qtd_necessaria = int(valor_necessario / valor_medio) + 1
                st.write(f"Isso equivale a aproximadamente **{qtd_necessaria}** títulos (valor médio R$ {valor_medio:,.2f}).")

        st.subheader("📊 Status das Minhas Tratativas")
        status_list = list(STATUS_MAP.keys())
        cols = st.columns(len(status_list))
        cores = {'pendente':'#6B7280','em_tratativa':'#2563EB','contatado_sem_exito':'#DC2626','acordo_finalizado':'#059669','acordo_pendente':'#D97706'}
        for i, status in enumerate(status_list):
            df_status = df_ass[df_ass['status_tratativa'] == status]
            with cols[i]:
                st.markdown(f"""
                <div style="background-color:{cores[status]}; padding:15px; border-radius:15px; text-align:center;">
                    <h4 style="color:white; margin:0;">{STATUS_MAP[status]}</h4>
                    <h2 style="color:white; margin:5px 0;">{len(df_status)}</h2>
                    <p style="color:#FDE047; margin:0;">R$ {df_status['valor_atualizado'].sum():,.2f}</p>
                </div>
                """, unsafe_allow_html=True)

        st.subheader("Distribuição")
        status_counts = df_ass['status_tratativa'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Quantidade']
        status_counts['Status'] = status_counts['Status'].map(STATUS_MAP)
        fig = px.pie(status_counts, names='Status', values='Quantidade', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🔴 Meus Top 5 Inadimplentes")
        top5 = df_inad_ind.nlargest(5, 'valor_atualizado')[['razao_social', 'valor_atualizado', 'tempo_atraso']]
        st.dataframe(top5, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("Dashboard Financeiro v11.1")
