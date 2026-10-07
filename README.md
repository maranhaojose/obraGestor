# Controle de Obra

Sistema de gestão financeira de obras (MVP v1). Sem dependências: só Python 3.8+.

## Executar
    python3 server.py        # http://localhost:8000  (outra porta: python3 server.py 8080)

O banco SQLite `data/obra.db` é criado vazio no primeiro uso. Comece pela aba **Obra**.

## Estrutura
    server.py                  servidor HTTP + API REST + SQLite
    data/obra.db               banco de dados (gerado automaticamente)
    public/index.html          estrutura da página
    public/css/style.css       estilos
    public/js/app.js           interface, painel, histórico e importação de CSV
    docs/documentacao.pdf      documentação completa
    exemplo_importacao.csv     exemplo para importar

## Importar dados
Aba **Importar**: escolha um CSV (obrigatórias: item, quantidade, valor unitário; opcionais: data, categoria, comportamento, unidade, observação). O mapeamento de colunas pode ser ajustado antes de confirmar.
