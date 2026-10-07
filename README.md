# Controle de Obra
Gestão financeira de obras (MVP v1).

- **Produção (Vercel + Postgres + login):** veja `DEPLOY.md`
- **Local:** `python3 server.py` → http://localhost:8000 (SQLite em `data/obra.db`)

## Estrutura
    api/index.py         função serverless da Vercel (rota /api/*)
    api/_core.py         regras de negócio, banco (Postgres/SQLite) e autenticação
    server.py            servidor local
    public/              index.html, css/style.css, js/app.js
    vercel.json          configuração da Vercel
    requirements.txt     dependência de produção (psycopg)
    docs/documentacao.pdf  documentação completa
    exemplo_importacao.csv exemplo para a aba Importar
