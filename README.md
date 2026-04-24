# Dashboard Financeiro Interno (Streamlit)

App Streamlit para cobrança & financeiro com SQLite.

## Rodar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy no Streamlit Cloud (GitHub)

1. Suba este repositório no GitHub.
2. Acesse o Streamlit Cloud e crie um novo app apontando para:
   - **Repository**: seu repo
   - **Branch**: `main` (ou a sua)
   - **Main file path**: `app.py`
3. Em **Settings → Secrets**, configure pelo menos:
   - `STREAMLIT_SESSION_TIMEOUT` (ex.: `"1800"`)

### Importante sobre o banco de dados

O app usa **SQLite** (`DB_PATH`). No **Streamlit Cloud**, o filesystem é **efêmero** (pode reiniciar/atualizar e perder o arquivo `.db`).

Para produção, o recomendado é:
- **Usar um banco externo** (Postgres/Supabase, etc.), ou
- **Hospedar você mesmo** (VM/Docker) com volume persistente.

Enquanto o app estiver em SQLite e rodando em Cloud efêmera, trate como **ambiente de demonstração**.

## Configurações

- **Python**: definido em `runtime.txt`
- **Streamlit**: `.streamlit/config.toml`
- **Exemplo de secrets**: `.streamlit/secrets.toml.example`

