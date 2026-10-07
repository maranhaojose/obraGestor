# Publicar na Vercel (produção)

Arquitetura: `public/` (HTML, CSS, JS) é servido como site estático; `api/index.py` roda como função serverless e grava em **PostgreSQL** (Neon). O SQLite não é usado na Vercel porque o disco das funções não persiste.

## Passo a passo
1. **Código no GitHub:** envie esta pasta inteira (na raiz do repositório devem estar `api/`, `public/`, `vercel.json` e `requirements.txt`).
2. **Importar na Vercel:** Add New > Project > escolha o repositório. Framework Preset: **Other**. Não precisa de Build Command.
3. **Banco de dados:** no projeto, aba **Storage** > Create Database > **Neon (Postgres)** > conectar ao projeto. Isso cria a variável `DATABASE_URL` automaticamente. As tabelas e as 8 categorias iniciais são criadas no primeiro acesso.
4. **Variáveis de ambiente** (Settings > Environment Variables):
   - `APP_PASSWORD`: senha de acesso ao sistema (obrigatória em produção)
   - `APP_SECRET`: texto aleatório longo para assinar a sessão (recomendada)
5. **Redeploy:** Deployments > ... > Redeploy (as variáveis só valem em novos deploys). Abra o endereço, entre com a senha e crie a obra.

## Sem a senha ou o banco configurados
A API responde 503 com a mensagem do que falta, em vez de funcionar sem proteção ou perder dados.

## Rodar localmente
`python3 server.py` (SQLite em `data/obra.db`, sem senha, só em localhost). Para testar com o Postgres, defina `DATABASE_URL` e instale `pip install "psycopg[binary]"`.

## Observações
- Backup: aba Importar > Exportar histórico (CSV). O Neon também mantém restauração pontual no plano gratuito.
- A sessão dura 7 dias (cookie HttpOnly). Para trocar a senha, altere `APP_PASSWORD` e faça redeploy.
