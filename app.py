"""
Dashboard Financeiro e Resultados - Sistema de Cobrança
Versão 13.0 - Bcrypt, sessão com timeout, troca de senha mensal, atualizar dados
"""

import streamlit as st
import pandas as pd
import hashlib
import unicodedata
import sqlite3
import shutil
import os
import time
import re
import json
import tempfile
from datetime import datetime, timedelta
import plotly.express as px
import bcrypt

SESSAO_TIMEOUT_SEGUNDOS = int(os.environ.get("STREAMLIT_SESSION_TIMEOUT", "1800"))
SENHA_MIN_LEN = 8
BACKUP_OBRIGATORIO_VALIDADE_MIN = int(os.environ.get("BACKUP_REQUIRED_VALID_MIN", "180"))

PERFIS_LABEL = {
    "supervisor": "Supervisor",
    "desenvolvedor": "Desenvolvedor",
    "assistente": "Assistente",
}

PERFIS_VISAO_GERAL = {"supervisor", "desenvolvedor"}

MAX_UPLOAD_MB_EXCEL = int(os.environ.get("MAX_UPLOAD_MB_EXCEL", "25"))
MAX_UPLOAD_MB_DB = int(os.environ.get("MAX_UPLOAD_MB_DB", "50"))
LOGIN_MAX_TENTATIVAS = int(os.environ.get("LOGIN_MAX_TENTATIVAS", "6"))
LOGIN_JANELA_SEG = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
LOGIN_COOLDOWN_SEG = int(os.environ.get("LOGIN_COOLDOWN_SECONDS", "120"))
REAUTH_TTL_SEG = int(os.environ.get("REAUTH_TTL_SECONDS", "600"))

# ---------- CONFIGURAÇÃO DA PÁGINA ----------
st.set_page_config(page_title="Dashboard Financeiro", page_icon="💰", layout="wide")

st.markdown("""
<style>
    :root{
        --base-font-size: 18px;
        --container-pad-top: 4.25rem;
        --container-pad-x: 2rem;
        --sidebar-width: 330px;
        --metric-value-size: 1.65rem;
        --metric-label-size: 0.78rem;
    }

    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');
    html, body, [class*="css"] { font-size: var(--base-font-size); font-family: 'DM Sans', system-ui, sans-serif !important; }
    .stApp {
        background: radial-gradient(1200px 800px at 10% -10%, rgba(99, 102, 241, 0.12), transparent 55%),
                    radial-gradient(900px 600px at 100% 0%, rgba(56, 189, 248, 0.08), transparent 50%),
                    linear-gradient(165deg, #0b0f14 0%, #0f1419 40%, #0a0d12 100%) !important;
    }
    [data-testid="stHeader"] { background: rgba(11, 15, 20, 0.85) !important; backdrop-filter: blur(8px); border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
    /* Dá folga para o header fixo não "cortar" títulos no topo */
    .block-container { padding-top: var(--container-pad-top) !important; max-width: 1400px; }
    .main .block-container { padding-left: var(--container-pad-x); padding-right: var(--container-pad-x); }

    h1 { font-size: 2.15rem !important; font-weight: 700 !important; letter-spacing: -0.03em !important; color: #f1f5f9 !important; }
    h2 { font-size: 1.65rem !important; font-weight: 600 !important; color: #e2e8f0 !important; letter-spacing: -0.02em; }
    h3 { font-size: 1.35rem !important; font-weight: 600 !important; color: #cbd5e1 !important; }

    [data-testid="stMetricValue"] {
        font-size: var(--metric-value-size) !important; font-weight: 600 !important; color: #f8fafc !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: var(--metric-label-size) !important; font-weight: 600 !important; color: #94a3b8 !important;
        text-transform: uppercase; letter-spacing: 0.06em !important;
    }
    [data-testid="stMetricDelta"] { font-size: 0.85rem !important; }

    div[data-testid="stMetricContainer"] {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.65) 100%);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 14px;
        padding: 1rem 1.1rem !important;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #0c1220 100%) !important;
        border-right: 1px solid rgba(99, 102, 241, 0.12) !important;
    }
    section[data-testid="stSidebar"] .stMarkdown strong { color: #c7d2fe !important; }
    section[data-testid="stSidebar"] label { color: #cbd5e1 !important; }

    /* Sidebar: manter largura confortável (sem espremer) */
    section[data-testid="stSidebar"] {
        width: var(--sidebar-width) !important;
        min-width: var(--sidebar-width) !important;
        max-width: var(--sidebar-width) !important;
    }
    /* Conteúdo da sidebar não estourar */
    section[data-testid="stSidebar"] .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    /* Evita quebra agressiva nos textos/labels do menu */
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {
        white-space: nowrap;
    }
    /* Se algum texto for longo demais, corta com reticências em vez de esmagar */
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span {
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Auto-responsivo (quando usuário escolhe "Auto") */
    @media (max-width: 1024px) {
        :root { --container-pad-x: 1.25rem; --sidebar-width: 305px; }
    }
    @media (max-width: 768px) {
        :root { --base-font-size: 16px; --container-pad-x: 1rem; --sidebar-width: 285px; --metric-value-size: 1.35rem; --metric-label-size: 0.72rem; }
        .block-container { max-width: 100% !important; }
    }
    @media (max-width: 480px) {
        :root { --base-font-size: 15.5px; --container-pad-x: 0.85rem; --metric-value-size: 1.25rem; }
        h1 { font-size: 1.85rem !important; }
        h2 { font-size: 1.35rem !important; }
    }

    .stButton > button {
        font-size: 1rem !important; font-weight: 600 !important; padding: 0.55rem 1.1rem !important;
        border-radius: 10px !important; border: none !important;
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 48%, #818cf8 100%) !important;
        color: #fff !important;
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35);
        transition: transform 0.15s ease, box-shadow 0.2s ease, filter 0.2s ease !important;
    }
    .stButton > button:hover {
        filter: brightness(1.06);
        box-shadow: 0 6px 22px rgba(129, 140, 248, 0.45);
    }
    .stButton > button:active { transform: scale(0.98); }

    .stTextInput > div > div > input, .stTextArea > div > div > textarea {
        font-size: 1rem !important; border-radius: 10px !important;
        background-color: rgba(30, 41, 59, 0.55) !important;
        color: #f1f5f9 !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
    }
    .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {
        border-color: rgba(129, 140, 248, 0.55) !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.22) !important;
    }
    .stTextInput label, .stTextArea label, .stSelectbox label, .stDateInput label, .stNumberInput label { color: #cbd5e1 !important; }

    div[data-baseweb="select"] > div {
        border-radius: 10px !important;
        background-color: rgba(30, 41, 59, 0.55) !important;
        border-color: rgba(148, 163, 184, 0.22) !important;
    }

    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border-radius: 12px !important;
        border: 1px solid rgba(148, 163, 184, 0.1) !important;
        overflow: hidden;
    }

    .stExpander { border: 1px solid rgba(148, 163, 184, 0.12) !important; border-radius: 12px !important; background: rgba(15, 23, 42, 0.35) !important; }
    .stExpander summary { font-weight: 600; color: #e2e8f0 !important; }

    div[data-testid="stRadio"] label { color: #e2e8f0 !important; }

    /* KPI cards (dashboard) */
    .kpi-grid{
        display: grid;
        grid-template-columns: repeat(12, 1fr);
        gap: 14px;
        margin: 0.75rem 0 1.15rem 0;
    }
    .kpi-card{
        grid-column: span 3;
        padding: 14px 14px 12px 14px;
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.14);
        background: linear-gradient(155deg, rgba(51, 65, 85, 0.35) 0%, rgba(15, 23, 42, 0.78) 100%);
        box-shadow: 0 18px 40px rgba(0,0,0,0.28);
        position: relative;
        overflow: hidden;
        min-height: 92px;
    }
    .kpi-card::before{
        content:"";
        position:absolute;
        inset:-2px;
        background: radial-gradient(420px 160px at 20% 0%, rgba(99,102,241,0.20), transparent 55%),
                    radial-gradient(360px 140px at 85% -10%, rgba(56,189,248,0.14), transparent 58%);
        pointer-events:none;
    }
    .kpi-top{
        display:flex;
        align-items:flex-start;
        justify-content:space-between;
        gap:12px;
        position:relative;
        z-index:1;
    }
    .kpi-label{
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(148, 163, 184, 0.95);
        margin: 0;
        line-height: 1.15;
    }
    .kpi-value{
        margin: 8px 0 0 0;
        font-size: 1.55rem;
        font-weight: 750;
        letter-spacing: -0.02em;
        color: #f8fafc;
        line-height: 1.15;
        position:relative;
        z-index:1;
    }
    .kpi-sub{
        margin: 6px 0 0 0;
        font-size: 0.92rem;
        font-weight: 600;
        color: rgba(226, 232, 240, 0.78);
        position:relative;
        z-index:1;
    }
    .kpi-icon{
        width: 40px;
        height: 40px;
        border-radius: 12px;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size: 1.15rem;
        color: #fff;
        background: rgba(99, 102, 241, 0.18);
        border: 1px solid rgba(129, 140, 248, 0.22);
        position:relative;
        z-index:1;
        flex: 0 0 auto;
    }
    .kpi-badge{
        display:inline-flex;
        align-items:center;
        gap:8px;
        margin-top: 10px;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 650;
        color: rgba(226, 232, 240, 0.92);
        background: rgba(2, 6, 23, 0.35);
        border: 1px solid rgba(148, 163, 184, 0.16);
        position:relative;
        z-index:1;
        width: fit-content;
    }
    .kpi-badge-dot{
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: rgba(99,102,241,0.9);
        box-shadow: 0 0 0 3px rgba(99,102,241,0.18);
    }
    .kpi-card[data-tone="ok"] .kpi-icon{ background: rgba(20,184,166,0.18); border-color: rgba(45,212,191,0.22); }
    .kpi-card[data-tone="ok"] .kpi-badge-dot{ background: rgba(20,184,166,0.95); box-shadow: 0 0 0 3px rgba(20,184,166,0.18); }
    .kpi-card[data-tone="warn"] .kpi-icon{ background: rgba(245,158,11,0.18); border-color: rgba(251,191,36,0.22); }
    .kpi-card[data-tone="warn"] .kpi-badge-dot{ background: rgba(245,158,11,0.95); box-shadow: 0 0 0 3px rgba(245,158,11,0.18); }
    .kpi-card[data-tone="danger"] .kpi-icon{ background: rgba(239,68,68,0.18); border-color: rgba(248,113,113,0.22); }
    .kpi-card[data-tone="danger"] .kpi-badge-dot{ background: rgba(239,68,68,0.95); box-shadow: 0 0 0 3px rgba(239,68,68,0.18); }

    @media (max-width: 1024px){ .kpi-card{ grid-column: span 4; } }
    @media (max-width: 768px){ .kpi-card{ grid-column: span 6; } .kpi-value{ font-size: 1.35rem; } }
    @media (max-width: 480px){ .kpi-card{ grid-column: span 12; } }

    /* Painéis (Assistentes): cards para lista/form */
    .panel-card{
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.14);
        background: linear-gradient(155deg, rgba(51, 65, 85, 0.22) 0%, rgba(15, 23, 42, 0.72) 100%);
        box-shadow: 0 18px 40px rgba(0,0,0,0.24);
        padding: 16px 16px 14px 16px;
        margin: 12px 0 16px 0;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
    }
    .panel-title{
        margin: 0 0 10px 0;
        font-weight: 700;
        color: rgba(241, 245, 249, 0.95);
        letter-spacing: -0.02em;
        font-size: 1.05rem;
        display:flex;
        align-items:center;
        gap:10px;
    }
    .panel-subtitle{
        margin: 0 0 14px 0;
        color: rgba(148, 163, 184, 0.95);
        font-weight: 600;
        font-size: 0.92rem;
    }

    /* Botões mais consistentes dentro de formulários */
    .panel-card .stButton>button{
        width: 100% !important;
    }

    /* Login — bloco visual (campos ficam abaixo; Streamlit não aninha widgets no HTML) */
    .login-hero-card {
        width: 100%; max-width: 420px; margin: 0 auto 1.5rem; padding: 2rem 1.75rem;
        background: linear-gradient(155deg, rgba(51, 65, 85, 0.42) 0%, rgba(15, 23, 42, 0.9) 100%);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: 22px;
        border: 1px solid rgba(165, 180, 252, 0.22);
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.04) inset;
    }
    .login-title {
        text-align: center; margin: 0 0 0.35rem 0; font-weight: 700; font-size: 1.75rem; letter-spacing: -0.03em;
        background: linear-gradient(110deg, #e0e7ff 0%, #c7d2fe 35%, #a5b4fc 70%, #93c5fd 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    }
    .login-subtitle {
        text-align: center; color: #94a3b8 !important; margin: 0 0 1.75rem 0; font-size: 0.95rem; font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

def _fmt_brl(v: float) -> str:
    try:
        return f"R$ {float(v):,.2f}"
    except Exception:
        return "R$ 0,00"


def _fmt_int(v) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return "0"


def render_kpi_card(label: str, value: str, subtitle: str = "", icon: str = "📌", badge: str = "", tone: str = "default"):
    label_html = (label or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value_html = (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    subtitle_html = (subtitle or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    badge_html = (badge or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    icon_html = (icon or "📌").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    badge_block = ""
    if badge_html:
        badge_block = f'<div class="kpi-badge"><span class="kpi-badge-dot"></span><span>{badge_html}</span></div>'
    sub_block = f'<p class="kpi-sub">{subtitle_html}</p>' if subtitle_html else ""
    # Não use indentação inicial: o Markdown pode interpretar como code-block.
    return (
        f'<div class="kpi-card" data-tone="{tone}">'
        f'<div class="kpi-top"><div>'
        f'<p class="kpi-label">{label_html}</p>'
        f'<p class="kpi-value">{value_html}</p>'
        f'{sub_block}'
        f'{badge_block}'
        f'</div><div class="kpi-icon">{icon_html}</div></div></div>'
    )


def render_kpi_grid(cards_html: list[str]) -> str:
    return f'<div class="kpi-grid">{"".join(cards_html)}</div>'

def _inject_device_profile_css(profile: str):
    """Aplica overrides de layout para diferentes dispositivos."""
    profile = (profile or "Auto").strip()
    if profile == "Auto":
        return
    presets = {
        "Smartphone": {
            "--base-font-size": "15.5px",
            "--container-pad-x": "0.85rem",
            "--container-pad-top": "4.75rem",
            "--sidebar-width": "285px",
            "--metric-value-size": "1.25rem",
            "--metric-label-size": "0.72rem",
        },
        "Tablet / iPad": {
            "--base-font-size": "16.8px",
            "--container-pad-x": "1.25rem",
            "--container-pad-top": "4.75rem",
            "--sidebar-width": "305px",
            "--metric-value-size": "1.45rem",
            "--metric-label-size": "0.75rem",
        },
        "Notebook / PC": {
            "--base-font-size": "18px",
            "--container-pad-x": "2rem",
            "--container-pad-top": "4.25rem",
            "--sidebar-width": "330px",
            "--metric-value-size": "1.65rem",
            "--metric-label-size": "0.78rem",
        },
    }
    vars_map = presets.get(profile)
    if not vars_map:
        return
    css_vars = "\n".join([f"      {k}: {v};" for k, v in vars_map.items()])
    st.markdown(
        f"""
        <style>
          :root {{
{css_vars}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

TAXA_JUROS_DIARIO = 0.002
TAXA_JUROS_MENSAL = 0.06

STATUS_MAP = {
    'pendente': '⏳ Pendente',
    'em_tratativa': '📞 Em Tratativa',
    'contatado_sem_exito': '❌ Sem Êxito',
    'acordo_finalizado': '✅ Acordo Finalizado',
    'acordo_pendente': '⏰ Acordo Pendente'
}

STATUS_CARD_THEMES = {
    'pendente': ('linear-gradient(152deg, #334155 0%, #475569 100%)', '#cbd5e1'),
    'em_tratativa': ('linear-gradient(152deg, #172554 0%, #1d4ed8 45%, #3b82f6 100%)', '#bfdbfe'),
    'contatado_sem_exito': ('linear-gradient(152deg, #450a0a 0%, #b91c1c 55%, #ef4444 100%)', '#fecaca'),
    'acordo_finalizado': ('linear-gradient(152deg, #042f2e 0%, #0f766e 45%, #14b8a6 100%)', '#ccfbf1'),
    'acordo_pendente': ('linear-gradient(152deg, #422006 0%, #c2410c 45%, #f59e0b 100%)', '#fde68a'),
}


def render_status_card(status_key, qtd, valor):
    """
    Card de status (Assistentes): mantém as cores/gradientes por status,
    porém com layout moderno e consistente com os KPI cards.
    """
    bg, val_color = STATUS_CARD_THEMES[status_key]
    label = STATUS_MAP.get(status_key, status_key)
    valor_str = _fmt_brl(valor)
    qtd_str = _fmt_int(qtd)

    label_html = (label or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    valor_html = (valor_str or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    qtd_html = (qtd_str or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    val_color_html = (val_color or "#e2e8f0").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Sem indentação inicial para não virar code-block no markdown
    return (
        f'<div class="kpi-card" data-tone="default" style="background:{bg};border:1px solid rgba(255,255,255,0.12);box-shadow:0 18px 40px rgba(0,0,0,0.28);min-height:108px;">'
        f'<div class="kpi-top"><div>'
        f'<p class="kpi-label" style="color:rgba(255,255,255,0.86)">{label_html}</p>'
        f'<p class="kpi-value" style="font-size:1.7rem">{qtd_html}</p>'
        f'<p class="kpi-sub" style="color:{val_color_html};font-weight:700">{valor_html}</p>'
        f'</div><div class="kpi-icon" style="background:rgba(0,0,0,0.18);border-color:rgba(255,255,255,0.18)">🏷️</div></div></div>'
    )


def aplicar_tema_plotly(fig, altura=None):
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(15, 23, 42, 0.5)',
        font=dict(color='#e2e8f0', family='DM Sans, system-ui, sans-serif'),
        margin=dict(t=52, b=52, l=56, r=32),
        title=dict(font=dict(size=15, color='#f1f5f9')),
        legend=dict(bgcolor='rgba(15,23,42,0.7)', bordercolor='rgba(148,163,184,0.2)', borderwidth=1),
        xaxis=dict(gridcolor='rgba(148,163,184,0.12)', zerolinecolor='rgba(148,163,184,0.15)', tickfont=dict(color='#94a3b8')),
        yaxis=dict(gridcolor='rgba(148,163,184,0.12)', zerolinecolor='rgba(148,163,184,0.15)', tickfont=dict(color='#94a3b8')),
    )
    if altura:
        fig.update_layout(height=altura)
    return fig


DB_PATH = os.environ.get("DB_PATH", "cobranca.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verificar_hash_armazenado(plain: str, stored: str):
    """Retorna (senha_ok, migrar_sha256_para_bcrypt)."""
    if not stored:
        return False, False
    if stored.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8")), False
        except Exception:
            return False, False
    leg = hashlib.sha256(plain.encode()).hexdigest()
    if leg.lower() == (stored or "").strip().lower():
        return True, True
    return False, False


def atualizar_senha_no_banco(email_db: str, nova_senha: str):
    nh = hash_password(nova_senha)
    hoje = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, ultima_troca_senha = ? WHERE email = ?",
            (nh, hoje, email_db),
        )
        conn.commit()
    st.cache_data.clear()


def obter_ultima_troca_senha(email: str):
    with get_connection() as conn:
        r = conn.execute(
            "SELECT ultima_troca_senha FROM usuarios WHERE email = ?",
            (email,),
        ).fetchone()
    return r[0] if r else None


def precisa_trocar_senha_mensal(email: str) -> bool:
    mes_atual = datetime.now().strftime("%Y-%m")
    ult = obter_ultima_troca_senha(email)
    if ult is None or len(str(ult)) < 7:
        return True
    return str(ult)[:7] < mes_atual


def verificar_senha_usuario(email: str, senha: str) -> bool:
    with get_connection() as conn:
        r = conn.execute("SELECT senha_hash FROM usuarios WHERE email = ?", (email,)).fetchone()
    if not r:
        return False
    ok, _ = verificar_hash_armazenado(senha, r[0])
    return ok


def validar_forca_senha(nova: str):
    if len(nova) < SENHA_MIN_LEN:
        return f"A nova senha deve ter pelo menos {SENHA_MIN_LEN} caracteres."
    if not re.search(r"[A-Za-z]", nova) or not re.search(r"\d", nova):
        return "Use letras e números na nova senha."
    return None


def limpar_sessao_auth():
    for k in ("_troca_senha_ui", "flash_reabertura", "flash_atualizar_dados", "flash_senha_ok", "cliente_selecionado"):
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.autenticado = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.email = None
    st.session_state.last_activity = None


def render_tela_trocar_senha(email: str, nome: str, obrigatoria_mes: bool):
    if obrigatoria_mes:
        st.markdown(
            '<style>section[data-testid="stSidebar"]{display:none!important;}</style>',
            unsafe_allow_html=True,
        )
        st.header("Renovação de senha (novo mês)")
        st.warning(
            "Por segurança, é **obrigatório** criar uma nova senha no primeiro acesso após o início de cada **mês calendário**."
        )
    else:
        st.header("Alterar minha senha")
    st.caption(f"**{nome}** · {email}")
    with st.form("form_trocar_senha_global"):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirmar nova senha", type="password")
        sub = st.form_submit_button("Salvar nova senha")
    if not obrigatoria_mes:
        if st.button("Cancelar"):
            st.session_state["_troca_senha_ui"] = False
            st.rerun()
    if sub:
        err = validar_forca_senha(nova)
        if err:
            st.error(err)
            return
        if nova != conf:
            st.error("A confirmação não coincide com a nova senha.")
            return
        if not verificar_senha_usuario(email, atual):
            st.error("Senha atual incorreta.")
            return
        atualizar_senha_no_banco(email, nova)
        st.session_state["_troca_senha_ui"] = False
        st.session_state["flash_senha_ok"] = True
        st.rerun()


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
                data_pagamento_realizado TEXT,
                data_ultima_atualizacao TIMESTAMP,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(codigo_cliente, numero_titulo)
            )
        ''')
        cur = conn.execute("PRAGMA table_info(clientes)")
        colunas = [row[1] for row in cur.fetchall()]
        if 'data_pagamento_realizado' not in colunas:
            conn.execute("ALTER TABLE clientes ADD COLUMN data_pagamento_realizado TEXT")
        
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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auditoria_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                usuario TEXT,
                detalhes TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur_u = conn.execute("PRAGMA table_info(usuarios)")
        cols_u = [row[1] for row in cur_u.fetchall()]
        if "ultima_troca_senha" not in cols_u:
            conn.execute("ALTER TABLE usuarios ADD COLUMN ultima_troca_senha TEXT")
            primeiro_mes = datetime.now().strftime("%Y-%m-01")
            conn.execute(
                "UPDATE usuarios SET ultima_troca_senha = ? WHERE ultima_troca_senha IS NULL",
                (primeiro_mes,),
            )
        # Migração de perfil e correção de nome (legado)
        conn.execute("UPDATE usuarios SET perfil = 'supervisor' WHERE perfil = 'admin'")
        conn.execute(
            "UPDATE usuarios SET perfil = 'desenvolvedor' WHERE lower(email) = lower(?)",
            ("wsdataanalyst",),
        )
        conn.execute(
            "UPDATE usuarios SET nome = ? WHERE lower(email) = lower(?)",
            ("Edvanisson Muniz", "edvanison@empresa.com"),
        )
        conn.commit()


def criar_usuarios_iniciais():
    """
    Bootstrap de usuários sem senhas hardcoded.

    Espera configuração via `st.secrets["BOOTSTRAP_USERS_JSON"]` (string JSON)
    ou `st.secrets["BOOTSTRAP_USERS"]` (lista de dicts).

    Exemplo:
      [{"nome":"Admin","email":"admin@empresa.com","senha":"...","perfil":"supervisor"}]
    """
    hoje = datetime.now().strftime("%Y-%m-%d")

    def _load_bootstrap_users():
        try:
            if "BOOTSTRAP_USERS" in st.secrets:
                return list(st.secrets["BOOTSTRAP_USERS"])
            if "BOOTSTRAP_USERS_JSON" in st.secrets:
                return json.loads(st.secrets["BOOTSTRAP_USERS_JSON"])
        except Exception:
            return []
        return []

    usuarios = _load_bootstrap_users()
    if not usuarios:
        # Não cria usuários sem configuração explícita.
        return

    def _truthy(v) -> bool:
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

    # Quando habilitado, sincroniza (atualiza) usuários já existentes com nome/perfil/senha do Secrets.
    # Útil no Streamlit Cloud para "reset" controlado de credenciais.
    sync_existing = False
    try:
        sync_existing = _truthy(st.secrets.get("BOOTSTRAP_SYNC_EXISTING", False))
    except Exception:
        sync_existing = False

    with get_connection() as conn:
        for u in usuarios:
            try:
                nome = (u.get("nome") or "").strip()
                email = (u.get("email") or "").strip().lower()
                senha = (u.get("senha") or "").strip()
                perfil = (u.get("perfil") or "").strip().lower()
            except Exception:
                continue
            if not (nome and email and senha and perfil):
                continue
            if perfil not in PERFIS_LABEL:
                continue
            cur = conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO usuarios (nome, email, senha_hash, perfil, ultima_troca_senha) VALUES (?, ?, ?, ?, ?)",
                    (nome, email, hash_password(senha), perfil, hoje),
                )
            elif sync_existing:
                conn.execute(
                    "UPDATE usuarios SET nome = ?, perfil = ?, senha_hash = ?, ultima_troca_senha = ? WHERE email = ?",
                    (nome, perfil, hash_password(senha), hoje, email),
                )
        conn.commit()


def verificar_login(email, senha):
    em = (email or "").strip().lower()
    if not em:
        return None
    # Rate limit simples por sessão
    now = time.time()
    lock_until = float(st.session_state.get("login_lock_until", 0) or 0)
    if lock_until and now < lock_until:
        restante = int(lock_until - now)
        st.error(f"Muitas tentativas. Aguarde {restante}s e tente novamente.")
        return None
    attempts = st.session_state.get("login_attempts", [])
    attempts = [t for t in attempts if (now - float(t)) <= LOGIN_JANELA_SEG]
    st.session_state["login_attempts"] = attempts

    def _get_user_row(email_key: str):
        with get_connection() as conn:
            return conn.execute(
                "SELECT nome, perfil, senha_hash, email FROM usuarios WHERE email = ?",
                (email_key,),
            ).fetchone()

    row = _get_user_row(em)
    if not row and "@" in em:
        # Aceita login por e-mail corporativo mesmo quando o usuário foi cadastrado sem domínio
        em2 = em.split("@", 1)[0].strip()
        if em2:
            row = _get_user_row(em2)
    if not row:
        return None
    nome, perfil, stored_hash, email_db = row
    ok, migrar = verificar_hash_armazenado(senha, stored_hash)
    if not ok:
        attempts.append(now)
        st.session_state["login_attempts"] = attempts
        if len(attempts) >= LOGIN_MAX_TENTATIVAS:
            st.session_state["login_lock_until"] = now + LOGIN_COOLDOWN_SEG
            registrar_auditoria("login_bloqueado", em, f"tentativas={len(attempts)}; janela={LOGIN_JANELA_SEG}s")
        else:
            registrar_auditoria("login_falha", em, f"tentativas={len(attempts)}; janela={LOGIN_JANELA_SEG}s")
        return None
    if migrar:
        with get_connection() as conn:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ?, ultima_troca_senha = ? WHERE email = ?",
                (hash_password(senha), datetime.now().strftime("%Y-%m-%d"), email_db),
            )
            conn.commit()
        st.cache_data.clear()
    # sucesso: limpa tentativas
    st.session_state["login_attempts"] = []
    st.session_state["login_lock_until"] = 0
    registrar_auditoria("login_ok", em, f"perfil={perfil}")
    return nome, perfil, email_db

def create_backup():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"cobranca_backup_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def create_backup_registrado(usuario=None):
    path = create_backup()
    registrar_auditoria("backup_create", usuario, os.path.basename(path))
    st.session_state["backup_ok_ts"] = time.time()
    return path


def backup_ok_recente() -> bool:
    ts = st.session_state.get("backup_ok_ts")
    if not ts:
        return False
    return (time.time() - float(ts)) <= (BACKUP_OBRIGATORIO_VALIDADE_MIN * 60)


def exigir_backup_supervisor(titulo: str):
    st.warning(
        f"Para segurança dos dados, é obrigatório criar um **backup** antes de usar **{titulo}**."
    )
    st.caption(
        f"Validade do backup para liberar ações: **{BACKUP_OBRIGATORIO_VALIDADE_MIN} min**. "
        "Após isso, o sistema volta a exigir um novo backup."
    )
    if st.button("💾 Criar backup obrigatório agora", use_container_width=True):
        path = create_backup_registrado(st.session_state.get("usuario"))
        st.success("Backup criado. Baixe e guarde este arquivo em local seguro.")
        with open(path, "rb") as f:
            st.download_button("📥 Baixar backup", f, file_name=os.path.basename(path))
        st.rerun()
    st.stop()

def registrar_auditoria(tipo, usuario, detalhes=""):
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO auditoria_eventos (tipo, usuario, detalhes) VALUES (?, ?, ?)",
                (tipo, usuario or "", (detalhes or "")[:8000]),
            )
            conn.commit()
    except Exception:
        pass


def _require_profile(required: set, titulo: str):
    perfil = st.session_state.get("perfil")
    if perfil not in required:
        st.error(f"Ação restrita. Apenas: {', '.join(sorted(required))}.")
        registrar_auditoria("acesso_negado", st.session_state.get("usuario"), f"acao={titulo}; perfil={perfil}")
        st.stop()


def _require_reauth(titulo: str):
    """
    Reautenticação simples: pede senha atual para ações críticas.
    """
    safe_key = re.sub(r"[^a-zA-Z0-9_]+", "_", (titulo or "acao")).strip("_").lower()
    now = time.time()
    ok_ts_key = f"reauth_ok_ts_{safe_key}"
    last_ok = float(st.session_state.get(ok_ts_key, 0) or 0)
    if last_ok and (now - last_ok) <= REAUTH_TTL_SEG:
        return
    st.warning(f"Confirmação necessária: **{titulo}**")
    email = st.session_state.get("email")
    if not email:
        st.error("Sessão inválida. Faça login novamente.")
        st.stop()
    with st.form(f"reauth_{safe_key}"):
        senha = st.text_input("Digite sua senha para confirmar", type="password")
        ok = st.form_submit_button("Confirmar", use_container_width=True)
    if not ok:
        st.stop()
    if not verificar_senha_usuario(email, senha):
        registrar_auditoria("reauth_falha", st.session_state.get("usuario"), f"acao={titulo}")
        st.error("Senha incorreta. Operação cancelada.")
        st.stop()
    st.session_state[ok_ts_key] = now
    registrar_auditoria("reauth_ok", st.session_state.get("usuario"), f"acao={titulo}")


def _uploaded_size_mb(uploaded_file) -> float:
    try:
        sz = getattr(uploaded_file, "size", None)
        if sz is None and hasattr(uploaded_file, "getbuffer"):
            sz = len(uploaded_file.getbuffer())
        if not sz:
            return 0.0
        return float(sz) / (1024 * 1024)
    except Exception:
        return 0.0


def _validate_sqlite_backup_file(uploaded_file) -> tuple[bool, str]:
    """
    Valida se o upload parece um SQLite válido e contém tabelas esperadas.
    """
    required_tables = {"usuarios", "clientes"}
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name
        try:
            con = sqlite3.connect(tmp_path)
            try:
                rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                tables = {r[0] for r in rows}
                missing = required_tables - tables
                if missing:
                    return False, f"Backup inválido: faltam tabelas {', '.join(sorted(missing))}."
                return True, "OK"
            finally:
                con.close()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        return False, "Backup inválido ou corrompido."

def restore_backup(uploaded_file, usuario=None):
    try:
        if _uploaded_size_mb(uploaded_file) > MAX_UPLOAD_MB_DB:
            st.error(f"Arquivo de backup muito grande (limite {MAX_UPLOAD_MB_DB} MB).")
            return False
        ok, msg = _validate_sqlite_backup_file(uploaded_file)
        if not ok:
            st.error(msg)
            return False
        create_backup_registrado(usuario)
        with open(DB_PATH, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        registrar_auditoria("restore_backup", usuario, getattr(uploaded_file, "name", "upload.db"))
        st.cache_data.clear()
        st.cache_resource.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao restaurar backup: {e}")
        return False

def processar_upload_excel(arquivo, modo="atualizar"):
    try:
        if _uploaded_size_mb(arquivo) > MAX_UPLOAD_MB_EXCEL:
            st.error(f"Arquivo Excel muito grande (limite {MAX_UPLOAD_MB_EXCEL} MB).")
            return None
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
    # Proteção básica: limita volume (evita travar o app por planilhas gigantes)
    if len(df) > 200_000:
        st.error("Planilha muito grande (limite: 200.000 linhas).")
        return None
    def normalizar_texto(texto):
        if not isinstance(texto, str): return ""
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
    with get_connection() as conn:
        # Mapa de contexto existente por cliente: assistente atual + status predominante (para novos títulos)
        mapa_cliente = {}
        try:
            base_ctx = pd.read_sql_query(
                "SELECT codigo_cliente, assistente_responsavel, status_tratativa FROM clientes",
                conn,
            )
            if not base_ctx.empty:
                prioridade = {"em_tratativa": 3, "acordo_pendente": 2, "contatado_sem_exito": 1, "pendente": 0, "acordo_finalizado": -1}
                for cod, sub in base_ctx.groupby("codigo_cliente"):
                    ass = sub["assistente_responsavel"].dropna().astype(str).iloc[0] if not sub["assistente_responsavel"].dropna().empty else None
                    sts = sub["status_tratativa"].dropna().astype(str).tolist()
                    # Não propaga "acordo_finalizado" como default para títulos novos
                    sts_valid = [s for s in sts if s in prioridade and s != "acordo_finalizado"]
                    if sts_valid:
                        sts_valid.sort(key=lambda s: prioridade.get(s, 0), reverse=True)
                        stp = sts_valid[0]
                    else:
                        stp = "pendente"
                    mapa_cliente[str(cod).strip()] = {"assistente": ass, "status": stp}
        except Exception:
            mapa_cliente = {}

        if modo == "substituir":
            senha_admin = st.text_input(
                "Digite sua senha de login (Supervisor) para confirmar a substituição total da base:",
                type="password",
            )
            email_adm = st.session_state.get("email")
            if not email_adm or not verificar_senha_usuario(email_adm, senha_admin):
                st.error("Senha incorreta. Operação cancelada.")
                return None
            conn.execute("DELETE FROM clientes")
            conn.execute("DELETE FROM historico_tratativas")
            conn.execute("DELETE FROM solicitacoes_reabertura")
            conn.commit()
            registrar_auditoria("upload_substituir_total", st.session_state.get("usuario"), f"registros_planilha={len(df)}")
            st.warning("Base antiga removida. Inserindo novos dados...")
        total = len(df)
        progress = st.progress(0, f"Processando {total} registros...")
        batch_size = 50
        for i, (_, row) in enumerate(df.iterrows()):
            codigo = str(row['Cliente']).strip()
            titulo = str(row['No. Titulo']).strip()
            if not codigo or not titulo: continue
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
            # Preserva assistente e status do cliente já tratado, quando existir
            if codigo in mapa_cliente and mapa_cliente[codigo].get("assistente"):
                assistente = mapa_cliente[codigo]["assistente"]
            else:
                assistente = 'Jane Xavier' if tempo_atraso <= 30 else 'Renata Kelly'
            status_inicial = mapa_cliente.get(codigo, {}).get("status", "pendente")
            conn.execute('''
                INSERT INTO clientes (
                    codigo_cliente, numero_titulo, razao_social, valor_original, juros, valor_atualizado,
                    tempo_atraso, emissao, vencimento, parcela, tipo_faturamento, vendedor, situacao,
                    historico_contato, canal, assistente_responsavel, status_tratativa, observacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
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
                    data_ultima_atualizacao = CURRENT_TIMESTAMP
            ''', (
                codigo, titulo, razao, valor_original, juros, valor_atualizado,
                tempo_atraso, emissao_str, vencimento_str, parcela, tipo_fat, vendedor, situacao,
                hist_contato, canal, assistente, status_inicial
            ))
            if i % batch_size == 0:
                conn.commit()
                progress.progress((i+1)/total)
        conn.commit()
        progress.empty()
        st.success(f"Upload concluído! {total} registros processados.")
        if modo == "atualizar":
            registrar_auditoria("upload_atualizar", st.session_state.get("usuario"), f"registros={total}; tratativas preservadas nos títulos já existentes")
        st.cache_data.clear()
        return df

def atualizar_status_cliente(cliente_id, novo_status, observacao, assistente, data_pagamento=None, valor_acordo=None, data_pagamento_realizado=None):
    try:
        with get_connection() as conn:
            cur = conn.execute("SELECT status_tratativa FROM clientes WHERE id = ?", (cliente_id,))
            row = cur.fetchone()
            if not row: return False
            status_anterior = row[0]
            set_parts = ["status_tratativa = ?", "observacao = ?", "data_ultima_atualizacao = CURRENT_TIMESTAMP"]
            params = [novo_status, observacao]
            if data_pagamento:
                set_parts.append("data_pagamento_programado = ?")
                params.append(data_pagamento)
            if valor_acordo is not None:
                set_parts.append("valor_acordo = ?")
                params.append(valor_acordo)
            if data_pagamento_realizado:
                set_parts.append("data_pagamento_realizado = ?")
                params.append(data_pagamento_realizado)
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
    if data_vencimento is None or valor_original == 0: return valor_original
    try:
        venc = datetime.strptime(data_vencimento, '%Y-%m-%d')
        fut = datetime.strptime(data_futura, '%Y-%m-%d')
        dias = (fut - venc).days
        if dias <= 0: return valor_original
        if dias < 30: return valor_original * (1 + TAXA_JUROS_DIARIO * dias)
        else:
            meses = dias // 30
            resto_dias = dias % 30
            valor_com_meses = valor_original * ((1 + TAXA_JUROS_MENSAL) ** meses)
            if resto_dias > 0:
                valor_com_meses *= (1 + TAXA_JUROS_DIARIO * resto_dias)
            return valor_com_meses
    except:
        return valor_original

def get_date_range_from_selection(ano, mes):
    if ano is None or ano == "Todos": return None, None
    if mes == "Todos":
        data_inicio = datetime(ano, 1, 1)
        data_fim = datetime(ano, 12, 31)
    else:
        meses_map = {"Janeiro":1, "Fevereiro":2, "Março":3, "Abril":4, "Maio":5, "Junho":6, "Julho":7, "Agosto":8, "Setembro":9, "Outubro":10, "Novembro":11, "Dezembro":12}
        mes_num = meses_map[mes]
        data_inicio = datetime(ano, mes_num, 1)
        if mes_num == 12: data_fim = datetime(ano, 12, 31)
        else: data_fim = datetime(ano, mes_num + 1, 1) - timedelta(days=1)
    return data_inicio, data_fim

def aplicar_filtro_periodo(df, campo_data, data_inicio, data_fim):
    if data_inicio and data_fim and campo_data in df.columns:
        df[campo_data] = pd.to_datetime(df[campo_data], errors='coerce')
        mask = (df[campo_data] >= pd.to_datetime(data_inicio)) & (df[campo_data] <= pd.to_datetime(data_fim))
        return df[mask]
    return df

def is_inadimplente(row):
    return row['tempo_atraso'] > 0 and row['status_tratativa'] != 'acordo_finalizado'

def _get_clientes_colunas(conn) -> set:
    try:
        cur = conn.execute("PRAGMA table_info(clientes)")
        return {row[1] for row in cur.fetchall()}
    except Exception:
        return set()

def _read_clientes_df(conn, data_inicio=None, data_fim=None, campo_filtro="vencimento") -> pd.DataFrame:
    """
    Lê dados de `clientes` garantindo que a coluna `valor_atualizado` exista no DataFrame.
    Isso evita quebra em bases legadas / migrações parciais (ex.: Streamlit Cloud).
    """
    cols = _get_clientes_colunas(conn)
    base_cols = {"tempo_atraso", "vencimento", "emissao", "status_tratativa"}

    if "valor_atualizado" in cols:
        select_cols = ["valor_atualizado", *sorted(base_cols)]
        df = pd.read_sql_query(
            f"SELECT {', '.join(select_cols)} FROM clientes",
            conn,
        )
    else:
        # Base legada: calcula "valor_atualizado" a partir de valor_original + juros (quando existir).
        select_cols = []
        if "valor_original" in cols:
            select_cols.append("valor_original")
        if "juros" in cols:
            select_cols.append("juros")
        # mantém colunas usadas na UI/metricas quando existirem
        for c in sorted(base_cols):
            if c in cols:
                select_cols.append(c)
        if not select_cols:
            df = pd.DataFrame(columns=["valor_atualizado", *sorted(base_cols)])
        else:
            df = pd.read_sql_query(
                f"SELECT {', '.join(select_cols)} FROM clientes",
                conn,
            )
        valor_original = pd.to_numeric(df.get("valor_original", 0), errors="coerce").fillna(0)
        juros = pd.to_numeric(df.get("juros", 0), errors="coerce").fillna(0)
        df["valor_atualizado"] = valor_original + juros

    df = aplicar_filtro_periodo(df, campo_filtro, data_inicio, data_fim)
    return df

@st.cache_data(ttl=300)
def get_dashboard_data(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        df = _read_clientes_df(conn, data_inicio=data_inicio, data_fim=data_fim, campo_filtro=campo_filtro)
    total_titulos = len(df)
    if "valor_atualizado" not in df.columns:
        df["valor_atualizado"] = 0.0
    valor_total = pd.to_numeric(df["valor_atualizado"], errors="coerce").fillna(0).sum()
    df_inad = df[df.apply(is_inadimplente, axis=1)] if not df.empty else df
    valor_inadimplente = pd.to_numeric(df_inad.get("valor_atualizado", 0), errors="coerce").fillna(0).sum()
    return pd.Series({'total_titulos': total_titulos, 'valor_total': valor_total, 'valor_inadimplente': valor_inadimplente, 'df_inad': df_inad})

@st.cache_data(ttl=300)
def get_status_counts(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        df = _read_clientes_df(conn, data_inicio=data_inicio, data_fim=data_fim, campo_filtro=campo_filtro)
    if "status_tratativa" not in df.columns:
        df["status_tratativa"] = "pendente"
    return df.groupby('status_tratativa').agg(qtd=('status_tratativa', 'count'), total=('valor_atualizado', 'sum')).reset_index()

@st.cache_data(ttl=300)
def get_assistente_comparativo(data_inicio=None, data_fim=None, campo_filtro="vencimento"):
    with get_connection() as conn:
        # Lê o mesmo núcleo e traz assistente_responsavel quando existir.
        cols = _get_clientes_colunas(conn)
        if "assistente_responsavel" in cols:
            df = pd.read_sql_query(
                "SELECT assistente_responsavel, tempo_atraso, vencimento, emissao, status_tratativa, "
                + ("valor_atualizado" if "valor_atualizado" in cols else "valor_original, juros")
                + " FROM clientes",
                conn,
            )
            if "valor_atualizado" not in df.columns:
                valor_original = pd.to_numeric(df.get("valor_original", 0), errors="coerce").fillna(0)
                juros = pd.to_numeric(df.get("juros", 0), errors="coerce").fillna(0)
                df["valor_atualizado"] = valor_original + juros
            df = aplicar_filtro_periodo(df, campo_filtro, data_inicio, data_fim)
        else:
            df = _read_clientes_df(conn, data_inicio=data_inicio, data_fim=data_fim, campo_filtro=campo_filtro)
            df["assistente_responsavel"] = "N/D"
    df['inad'] = df.apply(is_inadimplente, axis=1)
    return df.groupby('assistente_responsavel').agg(valor_total=('valor_atualizado', 'sum'), clientes_em_atraso=('inad', 'sum'), clientes_total=('assistente_responsavel', 'count')).reset_index()

@st.cache_data(ttl=300)
def get_acordos_ontem():
    ontem = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total FROM clientes WHERE status_tratativa IN ('acordo_finalizado', 'acordo_pendente') AND DATE(data_ultima_atualizacao) = ?", conn, params=(ontem,))
    if df.empty: return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

@st.cache_data(ttl=300)
def get_acordos_hoje():
    hoje = datetime.now().strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total FROM clientes WHERE data_pagamento_programado = ?", conn, params=(hoje,))
    if df.empty: return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

@st.cache_data(ttl=300)
def get_acordos_futuros():
    hoje = datetime.now().strftime('%Y-%m-%d')
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT COUNT(*) as qtd, COALESCE(SUM(valor_acordo), 0) as total FROM clientes WHERE data_pagamento_programado > ?", conn, params=(hoje,))
    if df.empty: return 0, 0.0
    return int(df.iloc[0]['qtd']), float(df.iloc[0]['total'])

def criar_solicitacao_reabertura(cliente_id, assistente, motivo):
    try:
        cliente_id = int(cliente_id)
    except (ValueError, TypeError):
        st.error("ID do título inválido.")
        return False
    try:
        with get_connection() as conn:
            cur = conn.execute("SELECT id FROM clientes WHERE id = ?", (cliente_id,))
            if cur.fetchone() is None:
                st.error(f"Erro: Título ID {cliente_id} não encontrado na base de dados.")
                return False
            conn.execute('''
                INSERT INTO solicitacoes_reabertura (cliente_id, assistente, motivo, status)
                VALUES (?, ?, ?, 'pendente')
            ''', (cliente_id, assistente, motivo))
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao criar solicitação: {e}")
        return False

def listar_solicitacoes_pendentes():
    with get_connection() as conn:
        df = pd.read_sql_query('''
            SELECT s.id, s.cliente_id, c.codigo_cliente, c.razao_social, s.assistente, s.motivo, 
                   datetime(s.data_solicitacao, 'localtime') as data_solicitacao
            FROM solicitacoes_reabertura s
            JOIN clientes c ON s.cliente_id = c.id
            WHERE s.status = 'pendente'
            ORDER BY s.data_solicitacao DESC
        ''', conn)
    return df

def processar_solicitacao(solicitacao_id, aprovado, admin_nome):
    with get_connection() as conn:
        novo_status = 'aprovada' if aprovado else 'rejeitada'
        conn.execute('''
            UPDATE solicitacoes_reabertura SET status = ?, data_resposta = CURRENT_TIMESTAMP, admin_responsavel = ?
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

def carregar_historico_titulo(cliente_id):
    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT datetime(data_hora, 'localtime') AS data_hora, assistente, acao,
                   status_anterior, status_novo, observacao
            FROM historico_tratativas
            WHERE cliente_id = ?
            ORDER BY data_hora DESC
            LIMIT 200
            """,
            conn,
            params=(int(cliente_id),),
        )

def listar_auditoria_recente(limite=80):
    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT datetime(data_hora, 'localtime') AS data_hora, tipo, usuario, detalhes
            FROM auditoria_eventos
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limite,),
        )

def transferir_cliente(codigo_cliente, nova_assistente, executado_por=None):
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id, assistente_responsavel, status_tratativa FROM clientes WHERE codigo_cliente = ?",
            (codigo_cliente.strip(),),
        )
        rows = cur.fetchall()
        if not rows:
            return False
        conn.execute(
            "UPDATE clientes SET assistente_responsavel = ?, data_ultima_atualizacao = CURRENT_TIMESTAMP WHERE codigo_cliente = ?",
            (nova_assistente, codigo_cliente.strip()),
        )
        quem = executado_por or "Supervisor"
        for cliente_id, assist_ant, status_atual in rows:
            conn.execute(
                """
                INSERT INTO historico_tratativas (cliente_id, assistente, acao, status_anterior, status_novo, observacao)
                VALUES (?, ?, 'transferencia_assistente', ?, ?, ?)
                """,
                (
                    cliente_id,
                    quem,
                    status_atual,
                    status_atual,
                    f"Assistente: {assist_ant} → {nova_assistente}",
                ),
            )
        conn.commit()
    registrar_auditoria(
        "transferencia_cliente",
        executado_por,
        f"codigo={codigo_cliente}; destino={nova_assistente}; titulos={len(rows)}",
    )
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
    st.session_state.email = None
    st.session_state.last_activity = None

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Ajuste de espaçamento apenas na tela de login (evita "corte" pelo header fixo)
        st.markdown(
            """
            <style>
              .main .block-container { padding-top: 5.75rem !important; }
              .login-hero-card { margin-top: 0.75rem !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("""
            <div class="login-hero-card">
                <h1 class="login-title">Dashboard Financeiro</h1>
                <p class="login-subtitle">Cobrança &amp; Resultado — acesse com login e senha.</p>
                <p class="login-subtitle" style="margin-top:-0.75rem;font-size:0.9rem;">
                    Ambiente protegido. Acesso restrito a usuários autorizados.
                </p>
            </div>
        """, unsafe_allow_html=True)
        email = st.text_input("Usuário ou email", key="login_email", placeholder="wsdataanalyst ou nome@empresa.com")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", use_container_width=True):
            user = verificar_login(email, senha)
            if user:
                nome, perfil, email_db = user
                st.session_state.autenticado = True
                st.session_state.usuario = nome
                st.session_state.perfil = perfil
                st.session_state.email = email_db
                st.session_state.last_activity = time.time()
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

# ---------- Sessão (timeout) + feedbacks ----------
agora = time.time()
ult = st.session_state.get("last_activity")
if ult is not None and (agora - ult > SESSAO_TIMEOUT_SEGUNDOS):
    limpar_sessao_auth()
    st.cache_data.clear()
    st.cache_resource.clear()
    st.warning(
        f"Sessão encerrada por inatividade (limite: {SESSAO_TIMEOUT_SEGUNDOS // 60} minutos sem uso). Faça login novamente."
    )
    st.stop()
st.session_state.last_activity = agora

if st.session_state.pop("flash_senha_ok", None):
    st.success("Senha alterada com sucesso.")
if st.session_state.pop("flash_atualizar_dados", None):
    st.success("Caches atualizados — dados recarregados a partir do banco (não foi necessário sair).")

if st.session_state.email and precisa_trocar_senha_mensal(st.session_state.email):
    render_tela_trocar_senha(
        st.session_state.email,
        st.session_state.usuario,
        obrigatoria_mes=True,
    )
    st.stop()

# ========== INTERFACE PRINCIPAL ==========
st.sidebar.title(f"👤 {st.session_state.usuario}")
st.sidebar.write(f"Perfil: **{PERFIS_LABEL.get(st.session_state.perfil, st.session_state.perfil)}**")

# ---------- Layout (responsivo / dispositivos) ----------
if "device_profile" not in st.session_state:
    st.session_state.device_profile = "Auto"
st.sidebar.markdown("---")
st.session_state.device_profile = st.sidebar.selectbox(
    "📱 Layout do dispositivo",
    ["Auto", "Smartphone", "Tablet / iPad", "Notebook / PC"],
    index=["Auto", "Smartphone", "Tablet / iPad", "Notebook / PC"].index(st.session_state.device_profile)
    if st.session_state.device_profile in ["Auto", "Smartphone", "Tablet / iPad", "Notebook / PC"]
    else 0,
    help="Ajusta tamanhos e espaçamentos para melhorar a usabilidade em diferentes dispositivos.",
)
_inject_device_profile_css(st.session_state.device_profile)

# ---------- Desenvolvedor: alternar visões ----------
perfil_real = st.session_state.perfil
modo_visao_dev = "Supervisor"
assistente_alvo = st.session_state.usuario

if perfil_real == "desenvolvedor":
    st.sidebar.markdown("---")
    modo_visao_dev = st.sidebar.radio(
        "Modo de visualização",
        ["Supervisor", "Assistente"],
        index=0,
        help="Como Desenvolvedor, você pode alternar entre visão gerencial (Supervisor) e visão de operação (Assistente).",
    )
    if modo_visao_dev == "Assistente":
        with get_connection() as conn:
            df_assist = pd.read_sql_query(
                "SELECT nome FROM usuarios WHERE perfil = 'assistente' ORDER BY nome",
                conn,
            )
        opcoes = df_assist["nome"].tolist() if not df_assist.empty else []
        if not opcoes:
            st.sidebar.warning("Nenhuma assistente cadastrada para simular a visão.")
        else:
            assistente_alvo = st.sidebar.selectbox("Assistente (visão)", opcoes, index=0)

is_visao_supervisor = (perfil_real in PERFIS_VISAO_GERAL) and (perfil_real != "desenvolvedor" or modo_visao_dev == "Supervisor")
is_visao_assistente = (perfil_real == "assistente") or (perfil_real == "desenvolvedor" and modo_visao_dev == "Assistente")

if st.sidebar.button("🚪 Sair", use_container_width=True):
    limpar_sessao_auth()
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

if st.sidebar.button(
    "🔄 Atualizar dados",
    use_container_width=True,
    help="Limpa o cache do app e relê o SQLite. Use após importar planilha ou restaurar backup, sem precisar sair.",
):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state["flash_atualizar_dados"] = True
    st.rerun()

if st.sidebar.button("🔑 Trocar senha", use_container_width=True):
    st.session_state["_troca_senha_ui"] = True
    st.rerun()

if st.session_state.get("_troca_senha_ui"):
    render_tela_trocar_senha(
        st.session_state.email,
        st.session_state.usuario,
        obrigatoria_mes=False,
    )
    st.stop()

# ---------- FILTRO DE ANO/MÊS ----------
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Filtro por Período")
with get_connection() as conn:
    anos_df = pd.read_sql_query("SELECT DISTINCT strftime('%Y', vencimento) as ano FROM clientes ORDER BY ano DESC", conn)
    anos_disponiveis = anos_df['ano'].tolist() if not anos_df.empty else [str(datetime.now().year)]
anos_opcoes = ["Todos"] + anos_disponiveis
ano_selecionado = st.sidebar.selectbox("Ano", anos_opcoes, index=0 if "Todos" in anos_opcoes else 0)

if ano_selecionado != "Todos":
    mes_opcoes = ["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_selecionado = st.sidebar.selectbox("Mês", mes_opcoes, index=0)
else:
    mes_selecionado = "Todos"

if ano_selecionado == "Todos":
    data_inicio = None
    data_fim = None
else:
    data_inicio, data_fim = get_date_range_from_selection(int(ano_selecionado) if ano_selecionado != "Todos" else None, mes_selecionado)
campo_db = "vencimento"

if is_visao_assistente:
    st.sidebar.markdown("---")
    restringir_fila_periodo = st.sidebar.checkbox(
        "Restringir minha fila ao período (vencimento)",
        value=False,
        help="Desligado (recomendado para operação): todos os títulos atribuídos entram na fila por atraso/status. Ligado: apenas títulos com vencimento no ano/mês escolhidos.",
        key="restr_periodo_fila",
    )
else:
    restringir_fila_periodo = True

data_inicio_fila_assistente = data_inicio if restringir_fila_periodo else None
data_fim_fila_assistente = data_fim if restringir_fila_periodo else None

# Menu com contagem textual
if is_visao_supervisor:
    with get_connection() as conn:
        pendentes = pd.read_sql_query("SELECT COUNT(*) as qtd FROM solicitacoes_reabertura WHERE status = 'pendente'", conn)
        qtd_pendentes = pendentes.iloc[0]['qtd'] if not pendentes.empty else 0
    menu_opcoes = ["📤 Upload", "📊 Dashboard Geral", "📥 Exportar Dados", "🔄 Transferir Cliente", "💾 Backup/Restore"]
    if qtd_pendentes > 0:
        menu_opcoes.insert(2, f"🔄 Solicitações de Reabertura ({qtd_pendentes})")
    else:
        menu_opcoes.insert(2, "🔄 Solicitações de Reabertura")
    menu = st.sidebar.radio("Menu", menu_opcoes, index=0)
else:
    menu = st.sidebar.radio("Menu", ["📋 Meus Clientes", "📊 Meu Dashboard"])

# ========== SUPERVISOR ==========
if is_visao_supervisor:
    if menu.startswith("📤"):
        st.header("Upload da Planilha")
        _require_profile({"supervisor", "desenvolvedor"}, "Upload da Planilha")
        _require_reauth("Upload da Planilha")
        if not backup_ok_recente():
            exigir_backup_supervisor("Upload da Planilha")
        st.info("Backup verificado. Você pode prosseguir com segurança.")
        modo_upload = st.radio("Modo de upload:", ["Atualizar base (recomendado)", "Substituir base (apaga tudo)"])
        arquivo = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls"])
        if arquivo:
            modo = "atualizar" if "Atualizar" in modo_upload else "substituir"
            if modo == "substituir":
                st.error("🚨 **MODO DE SUBSTITUIÇÃO TOTAL** 🚨")
            df = processar_upload_excel(arquivo, modo=modo)
            if df is not None:
                st.cache_data.clear()

    elif menu.startswith("📊"):
        st.header("Dashboard Gerencial")
        metricas = get_dashboard_data(data_inicio, data_fim, campo_db)
        total_clientes = int(metricas['total_titulos'])
        total_valor = float(metricas['valor_total'])
        inad_valor = float(metricas['valor_inadimplente'])
        percent_inad = (inad_valor / total_valor * 100) if total_valor else 0
        tone_inad = "ok" if percent_inad <= 3 else ("warn" if percent_inad <= 6 else "danger")
        badge_inad = "Dentro da meta (≤ 3%)" if percent_inad <= 3 else f"Acima da meta (+{percent_inad-3:.2f} p.p.)"
        kpis = [
            render_kpi_card("Total de títulos", _fmt_int(total_clientes), "Base no período selecionado", icon="🧾", tone="default"),
            render_kpi_card("Valor em aberto", _fmt_brl(total_valor), "Soma do valor atualizado", icon="💰", tone="default"),
            render_kpi_card("Inadimplência", f"{percent_inad:.2f}%", "Percentual do valor em atraso", icon="📉", badge=badge_inad, tone=tone_inad),
            render_kpi_card("Valor inadimplente", _fmt_brl(inad_valor), "Somente títulos em atraso", icon="🚨", tone=tone_inad),
        ]
        st.markdown(render_kpi_grid(kpis), unsafe_allow_html=True)

        st.subheader("📅 Acordos")
        qtd_ontem, val_ontem = get_acordos_ontem()
        qtd_hoje, val_hoje = get_acordos_hoje()
        qtd_fut, val_fut = get_acordos_futuros()
        kpis_acordos = [
            render_kpi_card("Acordos ontem", _fmt_int(qtd_ontem), _fmt_brl(val_ontem), icon="✅", tone="ok"),
            render_kpi_card("Acordos hoje", _fmt_int(qtd_hoje), _fmt_brl(val_hoje), icon="📅", tone="warn" if qtd_hoje else "default"),
            render_kpi_card("Acordos futuros", _fmt_int(qtd_fut), _fmt_brl(val_fut), icon="⏭️", tone="default"),
            render_kpi_card("Ação sugerida", "Revisar hoje", "Se houver acordos para hoje, priorize tratativas", icon="🧭", tone="default"),
        ]
        st.markdown(render_kpi_grid(kpis_acordos), unsafe_allow_html=True)

        st.subheader("📈 Status das Tratativas (Global)")
        df_status = get_status_counts(data_inicio, data_fim, campo_db)
        if df_status is None or df_status.empty:
            st.info("Sem dados de status para o período selecionado.")
        else:
            cards_status = []
            for _, row in df_status.iterrows():
                status = row['status_tratativa']
                label = STATUS_MAP.get(status, status)
                cards_status.append(
                    render_kpi_card(
                        label,
                        _fmt_int(row["qtd"]),
                        _fmt_brl(row["total"]),
                        icon="📌",
                        tone="default",
                    )
                )
            st.markdown(render_kpi_grid(cards_status), unsafe_allow_html=True)

        st.subheader("📊 Análise Comparativa por Assistente")
        df_ass = get_assistente_comparativo(data_inicio, data_fim, campo_db)
        if not df_ass.empty:
            df_ass['Taxa_Inadimplencia'] = (df_ass['clientes_em_atraso'] / df_ass['clientes_total'] * 100).fillna(0)
            fig = px.bar(
                df_ass,
                x='assistente_responsavel',
                y='valor_total',
                text='clientes_em_atraso',
                color='Taxa_Inadimplencia',
                color_continuous_scale=['#99f6e4', '#a5b4fc', '#c4b5fd', '#f0abfc', '#fb7185'],
                labels={
                    'assistente_responsavel': 'Assistente',
                    'valor_total': 'Valor em aberto (R$)',
                    'Taxa_Inadimplencia': 'Taxa inadimplência (%)',
                    'clientes_em_atraso': 'Clientes em atraso',
                },
                title='Valor em aberto por assistente (cor = taxa de inadimplência)',
            )
            aplicar_tema_plotly(fig, altura=420)
            fig.update_traces(textposition='outside', texttemplate='%{text}', marker_line_width=0, textfont_color='#f1f5f9')
            fig.update_coloraxes(colorbar=dict(title=dict(text='% inad.', font=dict(color='#94a3b8')), tickfont=dict(color='#94a3b8')))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("🔴 Top 10 Inadimplentes")
        with get_connection() as conn:
            top_inad = pd.read_sql_query('''
                SELECT razao_social, valor_atualizado, tempo_atraso, assistente_responsavel
                FROM clientes WHERE tempo_atraso > 0 AND status_tratativa != 'acordo_finalizado'
                ORDER BY valor_atualizado DESC LIMIT 10
            ''', conn)
        st.dataframe(top_inad, use_container_width=True)

    elif menu.startswith("🔄 Solicitações"):
        st.header("Solicitações de Reabertura")
        df_solic = listar_solicitacoes_pendentes()
        if df_solic.empty:
            st.info("Nenhuma solicitação pendente.")
        else:
            # BOTÃO APROVAR TODAS (ADICIONADO AQUI)
            if st.button("✅ Aprovar Todas as Solicitações"):
                for _, row in df_solic.iterrows():
                    processar_solicitacao(row['id'], True, st.session_state.usuario)
                st.success(f"{len(df_solic)} solicitações aprovadas!")
                st.rerun()
            st.markdown("---")
            for _, row in df_solic.iterrows():
                with st.expander(f"Cliente {row['codigo_cliente']} - {row['razao_social']} (Solicitado por {row['assistente']})"):
                    st.write(f"**Motivo:** {row['motivo']}")
                    st.write(f"**Data:** {row['data_solicitacao']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"✅ Aprovar", key=f"apr_{row['id']}"):
                            processar_solicitacao(row['id'], True, st.session_state.usuario)
                            st.success("Aprovada!"); st.rerun()
                    with col2:
                        if st.button(f"❌ Rejeitar", key=f"rej_{row['id']}"):
                            processar_solicitacao(row['id'], False, st.session_state.usuario)
                            st.success("Rejeitada."); st.rerun()

    elif menu.startswith("📥"):
        st.header("Exportar Base Completa")
        _require_profile({"supervisor", "desenvolvedor"}, "Exportar Base Completa")
        _require_reauth("Exportar Base Completa")
        if not backup_ok_recente():
            exigir_backup_supervisor("Exportar Base Completa")
        with get_connection() as conn:
            df_export = pd.read_sql_query("SELECT * FROM clientes ORDER BY assistente_responsavel, status_tratativa", conn)
        if df_export.empty:
            st.warning("Sem dados.")
        else:
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Clientes')
            st.download_button("📥 Baixar Excel", data=output.getvalue(), file_name=f"base_cobranca_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")

    elif menu.startswith("🔄 Transferir"):
        st.header("Transferir Cliente entre Assistentes")
        _require_profile({"supervisor", "desenvolvedor"}, "Transferir Cliente")
        _require_reauth("Transferir Cliente")
        if not backup_ok_recente():
            exigir_backup_supervisor("Transferir Cliente")
        codigo = st.text_input("Código do Cliente")
        nova = st.selectbox("Nova Assistente", ["Jane Xavier", "Renata Kelly"])
        if st.button("Transferir"):
            if codigo:
                if transferir_cliente(codigo, nova, st.session_state.usuario):
                    st.success(f"Cliente {codigo} transferido para {nova}.")
                else:
                    st.warning("Código não encontrado.")
            else:
                st.warning("Informe o código.")

    elif menu.startswith("💾"):
        st.header("Gerenciamento de Backup")
        _require_profile({"supervisor", "desenvolvedor"}, "Backup/Restore")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Criar backup agora"):
                _require_reauth("Criar backup")
                path = create_backup_registrado(st.session_state.get("usuario"))
                st.success(f"Backup: {path}")
                with open(path, "rb") as f: st.download_button("📥 Baixar", f, file_name=os.path.basename(path))
        with col2:
            uploaded = st.file_uploader("Restaurar backup (.db)", type=["db"])
            if uploaded and st.button("Restaurar"):
                _require_reauth("Restaurar backup")
                if restore_backup(uploaded, st.session_state.usuario):
                    st.success("Restaurado!"); st.rerun()
        st.markdown("---")
        st.subheader("📜 Auditoria recente")
        df_aud = listar_auditoria_recente(100)
        if df_aud.empty:
            st.caption("Nenhum evento registrado ainda.")
        else:
            st.dataframe(df_aud, use_container_width=True, hide_index=True)

# ========== ASSISTENTE ==========
else:
    st.sidebar.subheader("🔍 Consulta Manual")
    codigo_manual = st.sidebar.text_input("Código do Cliente")
    if st.sidebar.button("Buscar"):
        if codigo_manual:
            with get_connection() as conn:
                df_manual = pd.read_sql_query("SELECT * FROM clientes WHERE codigo_cliente = ?", conn, params=(codigo_manual,))
            if not df_manual.empty:
                st.sidebar.success(f"Cliente: {df_manual.iloc[0]['razao_social']}")
                st.session_state.cliente_selecionado = codigo_manual
                st.rerun()
            else:
                st.sidebar.warning("Código não encontrado.")

    df_clientes_total = carregar_clientes_assistente(assistente_alvo)

    if menu == "📋 Meus Clientes":
        st.header(f"Clientes de {assistente_alvo}")
        if st.session_state.pop("flash_reabertura", None):
            st.success(
                "Solicitação de reabertura **registrada com sucesso**. "
                "Ela aparecerá na fila do Supervisor para análise."
            )
        if df_clientes_total.empty:
            st.info("Nenhum título atribuído.")
            st.stop()

        df_clientes_filtrado = aplicar_filtro_periodo(
            df_clientes_total.copy(), campo_db, data_inicio_fila_assistente, data_fim_fila_assistente
        )

        st.subheader("📊 Status das Tratativas (Período)" if restringir_fila_periodo else "📊 Status das Tratativas (todos os vencimentos)")
        status_list = list(STATUS_MAP.keys())
        cols = st.columns(len(status_list))
        if 'filtro_status' not in st.session_state: st.session_state.filtro_status = None

        for i, status in enumerate(status_list):
            df_status = df_clientes_filtrado[df_clientes_filtrado['status_tratativa'] == status]
            qtd = len(df_status)
            valor = df_status['valor_atualizado'].sum()
            with cols[i]:
                st.markdown(render_status_card(status, qtd, valor), unsafe_allow_html=True)
                if st.button("Filtrar", key=f"card_{status}"):
                    st.session_state.filtro_status = status
                    st.rerun()

        if st.session_state.filtro_status:
            st.info(f"Filtrando por: {STATUS_MAP[st.session_state.filtro_status]}")
            if st.button("❌ Limpar filtro"): st.session_state.filtro_status = None; st.rerun()
            df_filtrado = df_clientes_filtrado[df_clientes_filtrado['status_tratativa'] == st.session_state.filtro_status]
        else:
            df_filtrado = df_clientes_filtrado

        st.subheader("📋 Lista de Clientes (ordenada por maior atraso)")
        if not df_filtrado.empty:
            st.markdown('<div class="panel-card"><div class="panel-title">📌 Seleção e títulos</div><div class="panel-subtitle">Escolha um cliente, selecione títulos e aplique a tratativa em lote.</div>', unsafe_allow_html=True)
            df_ordenado = df_filtrado.sort_values('tempo_atraso', ascending=False)
            codigos = df_ordenado['codigo_cliente'].unique().tolist()
            if 'cliente_selecionado' in st.session_state and st.session_state.cliente_selecionado in codigos:
                default_idx = codigos.index(st.session_state.cliente_selecionado)
            else:
                default_idx = 0
            codigo_sel = st.selectbox("Selecione um cliente:", codigos, index=default_idx,
                format_func=lambda c: f"{c} - {df_ordenado[df_ordenado['codigo_cliente']==c]['razao_social'].iloc[0]} (Atraso: {df_ordenado[df_ordenado['codigo_cliente']==c]['tempo_atraso'].iloc[0]} dias)")

            if codigo_sel:
                with get_connection() as conn:
                    titulos_df = pd.read_sql_query(
                        "SELECT * FROM clientes WHERE codigo_cliente = ? AND assistente_responsavel = ?",
                        conn,
                        params=(codigo_sel, assistente_alvo),
                    )
                if titulos_df.empty:
                    st.error("Cliente não encontrado.")
                else:
                    cliente_nome = titulos_df.iloc[0]['razao_social']
                    st.write(f"**{cliente_nome}** possui {len(titulos_df)} título(s).")
                    titulos_df['Selecionar'] = False
                    edited_df = st.data_editor(
                        titulos_df[['Selecionar', 'numero_titulo', 'vencimento', 'valor_atualizado', 'status_tratativa', 'observacao']],
                        column_config={"Selecionar": st.column_config.CheckboxColumn("Selecionar")},
                        hide_index=True, use_container_width=True, key=f"editor_{codigo_sel}")
                    ids_selecionados = titulos_df[edited_df['Selecionar'] == True]['id'].tolist()

                    if ids_selecionados:
                        st.write(f"{len(ids_selecionados)} título(s) selecionado(s).")
                        ids_validos = [tid for tid in ids_selecionados if titulos_df[titulos_df['id']==tid]['status_tratativa'].iloc[0] != 'acordo_finalizado']
                        if len(ids_validos) < len(ids_selecionados): st.warning("Títulos 'Acordo Finalizado' ignorados.")
                        if ids_validos:
                            st.markdown('<div class="panel-card"><div class="panel-title">⚡ Tratativa em lote</div><div class="panel-subtitle">Atualize status, motivo e observações para os títulos selecionados.</div>', unsafe_allow_html=True)
                            with st.form("form_tratativa_lote"):
                                novo_status = st.selectbox("Novo Status", options=list(STATUS_MAP.keys()), format_func=lambda x: STATUS_MAP[x])
                                motivo = st.selectbox("Motivo (opcional)", ['','Vencimento fim de semana','Repasse de verba','Problemas financeiros','Erro de programação','Mudança de Pessoal','Contato não atende!'])
                                obs = st.text_area("Observações")
                                data_pag = st.date_input("Data de Pagamento Programado (opcional)", value=None, min_value=datetime.today())
                                valor_acordo = None
                                data_pag_realizado = None
                                if novo_status == 'acordo_finalizado':
                                    data_pag_realizado = st.date_input("Data de Pagamento Realizado em:", value=datetime.today(), max_value=datetime.today())
                                if data_pag:
                                    ex = titulos_df[titulos_df['id'] == ids_validos[0]].iloc[0]
                                    valor_proj = calcular_juros_projetado(ex['valor_original'], ex['vencimento'], data_pag.strftime('%Y-%m-%d'))
                                    st.write(f"💡 Valor projetado (exemplo): R$ {valor_proj:,.2f}")
                                    valor_acordo = st.number_input("Valor do Acordo (R$)", value=float(valor_proj), step=0.01)
                                if st.form_submit_button("Aplicar aos selecionados"):
                                    obs_completa = f"{motivo}: {obs}" if motivo else obs
                                    data_str = data_pag.strftime('%Y-%m-%d') if data_pag else None
                                    data_real_str = data_pag_realizado.strftime('%Y-%m-%d') if data_pag_realizado else None
                                    for tid in ids_validos:
                                        atualizar_status_cliente(tid, novo_status, obs_completa, st.session_state.usuario, data_str, valor_acordo, data_real_str)
                                    st.success(f"{len(ids_validos)} título(s) atualizado(s)!")
                                    st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)

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
                                if titulo['data_pagamento_programado']: st.write(f"**Pagamento Programado:** {titulo['data_pagamento_programado']}")
                                if titulo['data_pagamento_realizado']: st.write(f"**Pagamento Realizado:** {titulo['data_pagamento_realizado']}")

                            hist_df = carregar_historico_titulo(titulo['id'])
                            if not hist_df.empty:
                                st.markdown("**Histórico de interações neste título**")
                                st.dataframe(hist_df, use_container_width=True, hide_index=True)

                            status_atual = titulo['status_tratativa']
                            if status_atual != 'acordo_finalizado':
                                with st.form(f"form_edit_{titulo['id']}"):
                                    novo_status = st.selectbox("Alterar para:", options=list(STATUS_MAP.keys()), format_func=lambda x: STATUS_MAP[x], key=f"status_{titulo['id']}")
                                    motivo = st.selectbox("Motivo (opcional)", ['','Vencimento fim de semana','Repasse de verba','Problemas financeiros','Erro de programação','Mudança de Pessoal','Contato não atende!'], key=f"motivo_{titulo['id']}")
                                    obs = st.text_area("Observações", key=f"obs_{titulo['id']}")
                                    data_pag = st.date_input("Data de Pagamento Programado (opcional)", value=None, min_value=datetime.today(), key=f"data_{titulo['id']}")
                                    valor_acordo = None
                                    data_pag_realizado = None
                                    if novo_status == 'acordo_finalizado':
                                        data_pag_realizado = st.date_input("Data de Pagamento Realizado em:", value=datetime.today(), max_value=datetime.today(), key=f"real_{titulo['id']}")
                                    if data_pag:
                                        valor_proj = calcular_juros_projetado(titulo['valor_original'], titulo['vencimento'], data_pag.strftime('%Y-%m-%d'))
                                        st.write(f"💡 Valor projetado: R$ {valor_proj:,.2f}")
                                        valor_acordo = st.number_input("Valor do Acordo (R$)", value=float(valor_proj), step=0.01, key=f"valor_{titulo['id']}")
                                    if st.form_submit_button("Atualizar"):
                                        obs_completa = f"{motivo}: {obs}" if motivo else obs
                                        data_str = data_pag.strftime('%Y-%m-%d') if data_pag else None
                                        data_real_str = data_pag_realizado.strftime('%Y-%m-%d') if data_pag_realizado else None
                                        if atualizar_status_cliente(titulo['id'], novo_status, obs_completa, st.session_state.usuario, data_str, valor_acordo, data_real_str):
                                            st.success("Título atualizado!"); st.rerun()
                            else:
                                st.warning("Títulos com 'Acordo Finalizado' não podem ser alterados diretamente.")
                                with st.form(f"form_reabertura_{titulo['id']}"):
                                    motivo_reab = st.text_area("Justificativa para reabertura")
                                    if st.form_submit_button("📩 Solicitar Reabertura"):
                                        if motivo_reab.strip():
                                            if criar_solicitacao_reabertura(titulo['id'], st.session_state.usuario, motivo_reab):
                                                st.session_state["flash_reabertura"] = True
                                                try:
                                                    st.toast("Solicitação registrada!", icon="✅")
                                                except Exception:
                                                    pass
                                                st.rerun()
                                            else:
                                                st.error("Erro ao enviar solicitação.")
                                        else:
                                            st.error("Descreva o motivo.")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Nenhum cliente com este status.")

    elif menu == "📊 Meu Dashboard":
        st.header("Meu Desempenho")
        if df_clientes_total.empty:
            st.info("Sem dados."); st.stop()
        df_clientes_filtrado = aplicar_filtro_periodo(
            df_clientes_total.copy(), campo_db, data_inicio_fila_assistente, data_fim_fila_assistente
        )
        metricas_global = get_dashboard_data(data_inicio, data_fim, campo_db)
        total_global = float(metricas_global['valor_total'])
        inad_global = float(metricas_global['valor_inadimplente'])
        percent_global = (inad_global / total_global * 100) if total_global else 0
        tone_global = "ok" if percent_global <= 3 else ("warn" if percent_global <= 6 else "danger")
        badge_global = "Meta ≤3%" if percent_global <= 3 else "Acima da meta"
        total_ind = df_clientes_filtrado['valor_atualizado'].sum()
        df_inad_ind = df_clientes_filtrado[df_clientes_filtrado.apply(is_inadimplente, axis=1)]
        inad_ind = df_inad_ind['valor_atualizado'].sum()
        percent_ind = (inad_ind / total_ind * 100) if total_ind else 0
        qtd_inad = len(df_inad_ind)
        clientes_unicos_filtrado = df_clientes_filtrado['codigo_cliente'].nunique()
        total_boletos_filtrado = len(df_clientes_filtrado)
        tone_ind = "ok" if percent_ind <= 3 else ("warn" if percent_ind <= 6 else "danger")
        kpi_ass = [
            render_kpi_card("Inadimplência global", f"{percent_global:.2f}%", _fmt_brl(inad_global), icon="🌍", badge=badge_global, tone=tone_global),
            render_kpi_card("Meu valor em aberto", _fmt_brl(total_ind), "No período selecionado", icon="💼", tone="default"),
            render_kpi_card("Minha inadimplência", f"{percent_ind:.2f}%", _fmt_brl(inad_ind), icon="📉", tone=tone_ind),
            render_kpi_card("Títulos em atraso", _fmt_int(qtd_inad), "Qtde de títulos inadimplentes", icon="⏳", tone=tone_ind),
            render_kpi_card("Clientes únicos", _fmt_int(clientes_unicos_filtrado), "Na sua carteira (período)", icon="👥", tone="default"),
            render_kpi_card("Total de boletos", _fmt_int(total_boletos_filtrado), "Títulos carregados no período", icon="🧾", tone="default"),
        ]
        st.markdown(render_kpi_grid(kpi_ass), unsafe_allow_html=True)

        qtd_hoje, val_hoje = get_acordos_hoje()
        if qtd_hoje > 0: st.warning(f"🔔 **Fique atento!** Você tem **{qtd_hoje}** acordo(s) programado(s) para hoje, totalizando **R$ {val_hoje:,.2f}**.")

        st.subheader("📅 Meus Acordos")
        col_a, col_b, col_c = st.columns(3)
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        hoje_str = hoje.strftime('%Y-%m-%d')
        ontem_str = ontem.strftime('%Y-%m-%d')
        df_ass = df_clientes_filtrado
        qtd_ontem = len(df_ass[(df_ass['status_tratativa'].isin(['acordo_finalizado','acordo_pendente'])) & (pd.to_datetime(df_ass['data_ultima_atualizacao']).dt.date == ontem)])
        val_ontem = df_ass[(df_ass['status_tratativa'].isin(['acordo_finalizado','acordo_pendente'])) & (pd.to_datetime(df_ass['data_ultima_atualizacao']).dt.date == ontem)]['valor_acordo'].sum()
        with col_a: st.metric("Acordos Fechados Ontem", f"{qtd_ontem} títulos", f"R$ {val_ontem:,.2f}")
        df_hoje = df_ass[df_ass['data_pagamento_programado'] == hoje_str]
        with col_b: st.metric("Acordos Programados Hoje", f"{len(df_hoje)} títulos", f"R$ {df_hoje['valor_acordo'].sum():,.2f}")
        df_fut = df_ass[df_ass['data_pagamento_programado'] > hoje_str]
        with col_c: st.metric("Acordos Programados Futuros", f"{len(df_fut)} títulos", f"R$ {df_fut['valor_acordo'].sum():,.2f}")

        df_pendentes = df_ass[df_ass['status_tratativa'] == 'acordo_pendente']
        if not df_pendentes.empty:
            valor_pendente = df_pendentes['valor_atualizado'].sum()
            nova_inad = inad_ind - valor_pendente
            nova_taxa = (nova_inad / total_ind * 100) if total_ind else 0
            st.subheader("🔮 Projeção")
            st.write(f"Se todos os **acordos pendentes** (R$ {valor_pendente:,.2f}) forem finalizados, sua inadimplência cairá para **{nova_taxa:.2f}%**.")

        if percent_ind > 3:
            valor_necessario = inad_ind - (0.03 * total_ind)
            st.subheader("🎯 Meta para 3%")
            st.write(f"Para atingir **3%** de inadimplência, você precisa recuperar **R$ {valor_necessario:,.2f}**.")
            if qtd_inad > 0:
                valor_medio = inad_ind / qtd_inad
                qtd_necessaria = int(valor_necessario / valor_medio) + 1
                st.write(f"Isso equivale a aproximadamente **{qtd_necessaria}** títulos.")

        st.subheader("📊 Status das Minhas Tratativas")
        status_list = list(STATUS_MAP.keys())
        cols = st.columns(len(status_list))
        for i, status in enumerate(status_list):
            df_status = df_ass[df_ass['status_tratativa'] == status]
            with cols[i]:
                st.markdown(render_status_card(status, len(df_status), df_status['valor_atualizado'].sum()), unsafe_allow_html=True)

        st.subheader("Distribuição")
        status_counts = df_ass['status_tratativa'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Quantidade']
        status_counts['Status'] = status_counts['Status'].map(STATUS_MAP)
        fig = px.pie(
            status_counts,
            names='Status',
            values='Quantidade',
            hole=0.48,
            title='Distribuição das tratativas',
            color_discrete_sequence=['#64748b', '#6366f1', '#f87171', '#14b8a6', '#f59e0b'],
        )
        aplicar_tema_plotly(fig, altura=440)
        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            textfont_size=12,
            marker=dict(line=dict(color='rgba(11,15,20,0.85)', width=2)),
        )
        fig.update_layout(showlegend=False, margin=dict(t=56, b=32, l=32, r=32))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🔴 Meus Top 5 Inadimplentes")
        top5 = df_inad_ind.nlargest(5, 'valor_atualizado')[['razao_social', 'valor_atualizado', 'tempo_atraso']]
        st.dataframe(top5, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption(f"Dashboard v13.0 · Sessão: {SESSAO_TIMEOUT_SEGUNDOS // 60} min inativo")