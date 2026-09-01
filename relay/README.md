# Relay local — reconciliação de payments

O Streamlit Community Cloud é bloqueado (HTTP 403) pelo WAF na frente do
Reprtoir — provavelmente por rodar em IPs de datacenter compartilhados. Este
relay roda na sua máquina (IP que funciona), fala com o Reprtoir daqui, e
fica exposto pra internet via túnel — a página do Lyra Cloud chama ele em
vez do Reprtoir direto.

**Só precisa estar rodando enquanto você usa a página "Reconciliação de
pagamentos" no Lyra.** Fora isso, pode ficar desligado.

## Configuração (uma vez)

1. **Instalar dependências** (num venv, pode ser o mesmo do Lyra):
   ```
   pip install -r relay/requirements.txt
   ```

2. **Criar `relay/.env`** a partir de `relay/.env.example`, preenchendo:
   - `REPRTOIR_EMAIL` / `REPRTOIR_PASSWORD` — mesmas credenciais de sempre
   - `RELAY_TOKEN` — um valor aleatório só seu:
     ```
     python -c "import secrets; print(secrets.token_urlsafe(32))"
     ```

3. **Instalar o ngrok**: baixe em https://ngrok.com/download, crie uma conta
   grátis, e configure o authtoken (`ngrok config add-authtoken <seu-token>`,
   disponível no dashboard da conta).

4. **Domínio fixo grátis**: toda conta ngrok já vem com um "dev domain"
   gratuito e fixo (tipo `algo-gerado.ngrok-free.dev`) — veja em
   https://dashboard.ngrok.com/domains. Sem ele, a URL muda toda vez que
   reiniciar o ngrok, e você teria que atualizar os secrets do Lyra Cloud
   toda vez. (Escolher um nome customizado exige plano pago — o dev domain
   gerado automaticamente já resolve.)

5. **Nos secrets do app no Streamlit Cloud**, adicione:
   ```toml
   RELAY_URL = "https://algo-gerado.ngrok-free.dev"
   RELAY_TOKEN = "<o mesmo valor do relay/.env>"
   ```
   (E pode remover `REPRTOIR_EMAIL`/`REPRTOIR_PASSWORD` de lá — não são mais
   usados pelo Lyra Cloud, só pelo relay local.)

## Uso (toda vez)

Dois terminais, rodando a partir da **raiz do repo** (não de dentro de `relay/`):

```
# Terminal 1
python -m uvicorn relay.server:app --port 8000

# Terminal 2
ngrok http --url=algo-gerado.ngrok-free.dev 8000
```

Deixe os dois abertos enquanto usa a página no Lyra. Pode fechar os dois
depois.

## Diagnóstico

- `GET /health` (sem token) — confirma que o relay está de pé:
  `curl https://algo-gerado.ngrok-free.dev/health`
- Se a página no Lyra disser "Não consegui alcançar o relay": confira se os
  dois terminais estão rodando e se a URL nos secrets bate com a do ngrok.
- Se disser "Relay recusou o token": `RELAY_TOKEN` diferente entre
  `relay/.env` e os secrets do Lyra Cloud.
