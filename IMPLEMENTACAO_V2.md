# DDM Pessoas — versão 2

## O que mudou

- Interface responsiva em laranja, grafite e branco, inspirada no site do Grupo DDM. Arquivos locais, sem depender do Tailwind CDN.
- Login real do RH, senha derivada com scrypt, sessão revogável de 8 horas em cookie HttpOnly e proteção de operações privadas.
- Cadastro de vagas e extração de URL pública HTTPS, com revisão de requisitos e quantidade de posições. Falhas de leitura são explícitas. Sem quantidade identificada, o RH precisa informar antes de convocar.
- Análises persistidas: GET apenas consulta, POST executa. Mudanças nos requisitos/currículos invalidam o ranking anterior para novas convocações.
- OpenAI com saída estruturada, validação de evidências literais e pontuação calculada no servidor. Modo local conservador e identificado; sem chave não simula IA. Erro da OpenAI não vira análise local silenciosamente.
- Ranking, escolha dos melhores limitada à quantidade de posições, revisão humana e fila de mensagens sem duplicidade por candidato/vaga.
- Perguntas e mensagem personalizadas por vaga; aceite SIM, perguntas sequenciais, histórico e interrupção SAIR no webhook.
- Portal `/interno`: lista apenas vagas internas publicadas; recebe dados e PDF/DOCX; código privado para atualizações; banco e candidaturas visíveis exclusivamente ao RH.
- Agenda interna com prevenção de sobreposição e reserva única por conversa. Conector Outlook/Microsoft Graph para leitura de disponibilidade.
- Modelos compatíveis com MySQL/MariaDB, conexão com verificação de saúde e adaptador Passenger para cPanel Python.

## Uso local

Python 3.11 ou superior. Na raiz do projeto:

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
python backend/create_admin.py
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Configure `COOKIE_SECURE=false` apenas para localhost HTTP. Em produção use `true` com HTTPS. Não existe senha padrão. `create_admin.py` solicita nome, e-mail e senha de pelo menos 12 caracteres. O usuário criado administra este workspace de uma única empresa; não é uma implementação multiempresa.

Acesse `/` para RH e `/interno` para colaboradores. Não abra index.html como arquivo: a aplicação precisa do servidor. Os bancos SQLite existentes não foram convertidos nem apagados. A versão anterior da interface foi preservada em `backups/index-before-redesign.html`.

## Sequência de operação

1. RH cadastra/importa uma vaga, revisa cada requisito e confirma a quantidade de posições. Para publicar internamente, marca os dois campos de vaga interna e publicação.
2. Inclui currículos e executa a análise. Após alterações, executa novamente. Notas são apoio à decisão, não reprovação automática.
3. Confere as evidências, nomes e telefones (nomes de arquivos são somente sugestões); seleciona até o número de posições e prepara mensagens.
4. Na aba WhatsApp, revisa e envia cada item da fila após a integração estar homologada. A triagem avança pelos eventos do fornecedor; as próximas mensagens ficam na fila para envio pelo operador nesta versão.
5. Com a triagem concluída, combina o horário com o candidato e reserva na agenda. A reserva é interna: o conector atual consulta o Outlook, mas não cria eventos ou convites automaticamente.
6. Colaboradores usam o portal interno. Devem guardar o código de atualização; quem possui esse código pode atualizar o cadastro. O RH deve validar a matrícula. Não há autenticação Microsoft dos colaboradores nesta versão.

## OpenAI

No ambiente do servidor: `OPENAI_API_KEY` e `OPENAI_MODEL` (padrão `gpt-4o-mini`, alterável conforme acesso da conta). A chave nunca é devolvida ao navegador. Trechos do currículo são enviados ao provedor somente quando a análise é executada; contatos reconhecidos são removidos, mas isso não constitui anonimização completa. A revisão de tratamento de dados e a política corporativa devem ser concluídas antes do uso com candidatos reais.

A saída estruturada segue a [documentação oficial](https://developers.openai.com/api/docs/guides/structured-outputs). O sistema valida citações literais para evidências; a coerência semântica ainda exige revisão. Falhas, recusas ou respostas incompletas geram erro. PDFs digitalizados sem texto precisam de OCR externo; o upload informa que não pôde extrair texto.

## WhatsApp — contrato para o fornecedor

Por padrão não envia. Ativar somente após validar o contrato:

- `WHATSAPP_API_URL`: endpoint HTTPS de envio.
- `WHATSAPP_API_TOKEN`: autenticação Bearer.
- `WHATSAPP_ENABLED=true`: habilita envio manual pela fila.
- `WHATSAPP_WEBHOOK_TOKEN`: segredo independente para autenticar entradas.

Envio POST JSON: `{"to":"5521999991234","text":"mensagem","client_reference":"123"}`. Cabeçalho `Idempotency-Key: 123`. Resposta obrigatória `{"message_id":"id-no-provedor"}`. Essa é uma interface genérica, não uma suposição de compatibilidade com a API ainda não recebida. Será necessário adaptar nomes, autenticação e templates conforme o fornecedor.

Entrada POST `/api/v1/webhooks/whatsapp`, cabeçalho `X-Webhook-Token`, corpo:

```json
{"event_id":"evento-unico","conversation_id":1,"phone":"5521999991234","text":"SIM"}
```

Eventos repetidos não avançam perguntas. O telefone deve corresponder à conversa. O integrador deve resolver a conversa correta por destinatário/contexto e nunca confiar em um identificador livre enviado pelo candidato. SAIR cancela mensagens pendentes. Falhas de envio ficam como `uncertain`, sem repetição cega. O operador deve conciliar com o fornecedor. `accepted` significa aceito pelo provedor, não entregue/lido. Webhooks de entrega, assinatura específica do fornecedor, templates aprovados ainda dependem da API e homologação. Para envio automático após aprovação do RH, ative `WHATSAPP_AUTO_SEND=true` e configure o cPanel para executar periodicamente `python -m app.worker` a partir de backend (usando o Python do ambiente virtual). O processador pega até 50 mensagens pendentes por execução; a transição atômica evita dois workers enviarem a mesma mensagem. Sem processador agendado, as respostas permanecem na fila. Não repete mensagens de resultado incerto.

## Outlook / Microsoft 365

Prepare um aplicativo de organização no Microsoft Entra com fluxo client credentials. Configure:

- `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.
- `MS_RH_MAILBOX`: caixa principal do RH.
- `MS_ALLOWED_MAILBOXES`: caixas autorizadas separadas por vírgula; padrão é somente a caixa principal.

Permissão de aplicativo mínima documentada para `getSchedule`: `Calendars.ReadBasic`, com consentimento administrativo. O administrador deve restringir o aplicativo às caixas necessárias usando os controles Microsoft disponíveis na organização. Não são criadas permissões pelo projeto.

O conector chama `getSchedule` ao disponibilizar um horário e novamente ao reservar. Horário ocupado, acesso negado ou erro bloqueia a operação. Quando sem credenciais, a interface identifica que apenas a agenda interna está ativa. A consulta não mantém um bloqueio remoto no Outlook; compromissos criados depois ainda podem gerar conflito. Esta versão não escreve convites e não implementa sincronização contínua. Fontes: [getSchedule](https://learn.microsoft.com/en-us/graph/api/calendar-getschedule?view=graph-rest-1.0), [client credentials](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow).

## Publicação no cPanel

Não basta copiar os arquivos para public_html: este projeto tem backend Python. O provedor precisa oferecer Application Manager / Setup Python App com Passenger, Python compatível e instalação de dependências. Referência: [cPanel Python WSGI](https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/).

1. Crie um banco MySQL/MariaDB e usuário de acesso restrito ao banco, com charset `utf8mb4`.
2. Mantenha a raiz da aplicação fora de `public_html`, por exemplo `/home/USUARIO/ddm-rh`. Não publique `.env`, bancos `.db`, uploads, testes, backups ou o arquivo backend.zip antigo.
3. Crie um subdomínio próprio e configure o Python App apontando à raiz da aplicação. Startup file: `passenger_wsgi.py`; entry point: `application`.
4. Instale `backend/requirements.txt` no ambiente virtual da aplicação.
5. Configure variáveis no painel: `DATABASE_URL=mysql+pymysql://USUARIO:SENHA@localhost/BANCO?charset=utf8mb4`, `COOKIE_SECURE=true` e integrações. Caracteres especiais da senha precisam de URL encoding. Use segredo apenas no servidor.
6. Execute `python backend/create_admin.py` no ambiente virtual para criar as tabelas e a conta RH. Tabelas novas são criadas sem apagar tabelas existentes; `create_all` não substitui migrações futuras de esquema.
7. Ative HTTPS, reinicie a aplicação e teste `/health`, login, `/interno`, upload e restrição de acesso sem login.
8. Ajuste o tempo limite do Passenger para análises de lotes; cada currículo gera uma chamada síncrona. Lotes grandes podem exceder o tempo do provedor. A migração para processamento em fila é indicada antes de aumentar o volume.
9. Configure backup do banco e dos arquivos de currículo, limites de upload e requisições no proxy/WAF. O login possui limitação básica por processo; em múltiplos workers use limitação centralizada no proxy.

O esquema foi preparado para MySQL/MariaDB; um teste com servidor real do provedor continua necessário. O banco SQLite não é automaticamente migrado: faça backup e planeje importação preservando IDs, relacionamentos e caminhos dos currículos antes de trocar o ambiente com dados reais.

## Validação e limites

Execute `python -m pytest backend/tests -q` com `PYTHONPATH=backend`. Testes isolados cobrem acesso privado, persistência/invalidação das análises, seleção, upload, portal interno, idempotência de webhook, horários e compilação SQL MySQL. Os testes não fazem chamadas às APIs reais.

Ainda requerem homologação: OpenAI com a chave da empresa e um conjunto de currículos autorizados; contrato e entregas do WhatsApp; permissões Microsoft 365; MySQL/MariaDB e Passenger no cPanel do provedor. Antes da publicação, defina política de retenção, recuperação de acesso/código e atendimento às solicitações de exclusão com o RH. Não há recuperação automática de senha/código nem painel de exclusão nesta versão.
