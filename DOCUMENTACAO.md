# Documentação — Portal RH & Triagem IA (Grupo DDM)

> Última atualização: 2026-09-10
> Status: protótipo funcional (não pronto para produção)

---

## 1. Visão Geral

Plataforma interna de RH do Grupo DDM para automatizar a triagem de currículos:

1. A equipe de RH cadastra uma vaga (colando a URL do anúncio em Sólides/Gupy/Catho/LinkedIn, ou via texto direto).
2. O sistema extrai os requisitos da vaga (obrigatórios, desejáveis, experiência, competências).
3. Currículos (PDF/DOCX) são enviados para aquela vaga.
4. Um motor de matching (IA generativa, quando configurada, ou um motor de regras determinístico como fallback) calcula um score de aderência de 0–100% por candidato, com evidências auditáveis (quais trechos do currículo sustentam cada critério).
5. A equipe convoca os candidatos aprovados via WhatsApp (atualmente simulado — ver seção 8).

Existe um único documento de referência de produto na raiz do projeto: `Arquitetura_Plataforma_Recrutamento_IA_DDM.pdf` (não analisado neste documento, mas é a fonte original de especificação).

---

## 2. Arquitetura

Arquitetura simples de 3 camadas, tudo rodando como um processo único local:

```
┌─────────────────────────────┐
│  index.html (frontend)      │  HTML + Tailwind (CDN) + JS vanilla inline
│  servido estaticamente      │  Sem build step, sem framework
└──────────────┬───────────────┘
               │ fetch() → /api/v1/*
┌──────────────▼───────────────┐
│  FastAPI (backend)           │  backend/app/main.py
│  Routers REST                │  jobs, resumes, screenings, messages, settings
└──────────────┬───────────────┘
               │
     ┌─────────┼──────────────────────────┐
     ▼         ▼                          ▼
 SQLAlchemy  Serviços de domínio      APIs externas
 + SQLite    (parsing, matching,      (Gemini / OpenAI / Groq,
             whatsapp mock)           via urllib puro)
```

- O próprio FastAPI serve o `index.html` na rota `/` ([main.py:35-38](backend/app/main.py#L35)) — não há servidor de frontend separado.
- Não há build step (webpack/vite/etc): o frontend é um único arquivo HTML de ~770 linhas com Tailwind carregado via `<script>` de CDN e todo o JavaScript inline no final do arquivo.
- Banco de dados: SQLite local (`rh_database.db`), criado automaticamente na primeira execução (`Base.metadata.create_all` em [main.py:16](backend/app/main.py#L16)).
- Não há autenticação, gateway de API, cache ou fila de processamento — é uma arquitetura monolítica de protótipo.

---

## 3. Tecnologias e Linguagens

| Camada | Tecnologia |
|---|---|
| Frontend | HTML5, Tailwind CSS (via CDN, sem build), JavaScript vanilla (ES2017+), Google Fonts (Inter) |
| Backend | Python 3 (testado em 3.14), FastAPI, Uvicorn (ASGI) |
| ORM / Banco | SQLAlchemy 2.x, SQLite |
| Validação | Pydantic v2 |
| Parsing de currículo | PyMuPDF (`fitz`) para PDF, `python-docx` para Word |
| IA / LLM | Integração direta via `urllib` (sem SDK) com Google Gemini, OpenAI ou Groq — a chave configurada define qual provedor é usado |
| Mensageria | Serviço próprio simulado (mock), preparado para plugar Z-API / Evolution API / Twilio |
| Testes | Pytest (1 arquivo de teste, cobre só o motor de matching determinístico) |

Não há: bundler de frontend, linter/formatter configurado, CI/CD, containerização (Docker), gerenciador de dependências além de `requirements.txt` (sem lockfile).

---

## 4. Estrutura de Pastas

```
RH/
├── index.html                          # Frontend único (SPA simples de abas)
├── .env / .env.example                 # Chaves de API (não versionado) / template
├── rh_database.db                      # Banco SQLite (não versionado)
├── Arquitetura_Plataforma_...DDM.pdf   # Documento de especificação original
├── test_cvs/                           # Currículos de exemplo para teste manual
└── backend/
    ├── app/
    │   ├── main.py                     # Bootstrap FastAPI + serve o index.html
    │   ├── core/
    │   │   ├── config.py                # Settings (DATABASE_URL, UPLOAD_DIR)
    │   │   └── database.py              # Engine SQLAlchemy + sessão
    │   ├── models/domain.py             # Tabelas ORM
    │   ├── schemas/domain.py            # Schemas Pydantic (request/response)
    │   ├── api/
    │   │   ├── jobs.py                  # CRUD de vagas + criação via URL/texto
    │   │   ├── resumes.py               # Upload/exclusão de currículos
    │   │   ├── screenings.py            # Cálculo do ranking de matching
    │   │   ├── messages.py              # Envio/histórico de WhatsApp
    │   │   └── settings.py              # Status e configuração da chave de IA
    │   └── services/
    │       ├── job_parser.py            # Extrai texto de URL de vaga + estrutura requisitos
    │       ├── resume_parser.py         # Extração de texto de PDF/DOCX
    │       ├── matching_service.py      # Motor determinístico de matching (sem IA)
    │       ├── llm_service.py           # Integração com Gemini/OpenAI/Groq
    │       └── whatsapp_service.py      # Mock de envio de WhatsApp
    ├── tests/test_matching.py           # 2 testes do motor determinístico
    └── requirements.txt
```

---

## 5. Telas e Abas (Frontend)

Interface de página única com navegação por abas no topo (`switchTab()` em [index.html](index.html)):

| Aba | Estado | Descrição |
|---|---|---|
| **Início** | Funcional (dashboard mínimo) | KPIs agregados no client: total de vagas, currículos processados e alta aderência (soma client-side de `/jobs` + `/jobs/{id}/screenings` de cada vaga — não há endpoint agregado no backend) |
| **Triagem IA (Vagas)** | Funcional — núcleo do produto | Cadastro de vaga por URL, upload de currículos, tabela de ranking com score/status/evidências, modal de ficha do candidato com relatório auditável, ação de convocar via WhatsApp |
| **Cadastro & Vagas** | Placeholder / em construção | Hoje só redireciona para a aba Triagem IA (cadastro avançado por formulário não foi implementado) |
| **Convocação WhatsApp** | Funcional (mock) | Log em tempo real das convocações disparadas na sessão atual |

Componentes globais: modal de configuração de chave de IA (Gemini/OpenAI/Groq), modal de ficha do candidato, toast de notificação.

O botão **"Sair"** no header está desabilitado propositalmente — não existe sistema de autenticação/login implementado (ver seção 7).

---

## 6. Modelo de Dados

Tabelas definidas em [models/domain.py](backend/app/models/domain.py):

| Tabela | Papel |
|---|---|
| `companies` | Empresa (multi-tenant no schema, mas não aplicado na prática — ver seção 9) |
| `users` | Usuários (schema existe, **sem nenhuma rota de API** — não há login/cadastro de usuário) |
| `jobs` | Vagas |
| `job_requirements` | Requisitos da vaga (categoria: `mandatory` / `desirable` / `experience` / `competency`) |
| `candidates` | Candidatos (criados automaticamente a partir do nome do arquivo no upload) |
| `resumes` | Currículos enviados (texto extraído + arquivo físico em `backend/uploads/`) |
| `screenings` / `screening_results` | **Schema existe mas não é usado** — o ranking é recalculado a cada requisição, nunca persistido (ver seção 9, gargalo #1) |
| `messages` | Histórico de mensagens de WhatsApp enviadas |
| `audit_logs` | **Schema existe mas não é usado em nenhum lugar do código** — nenhuma ação gera log de auditoria hoje |

---

## 7. Segurança

### O que já está certo
- `.env` (chaves de API) e dados sensíveis de candidatos (`uploads/`, `test_cvs/`, `*.pdf`, `*.docx`, `*.db`) estão corretamente listados no `.gitignore` — não vazam para o Git.
- SQLAlchemy ORM com queries parametrizadas em todo o código — sem risco de SQL injection.
- `.env.example` versionado como template, sem segredos reais.

### Gargalos e riscos identificados
| Risco | Onde | Impacto |
|---|---|---|
| **Sem autenticação/autorização** | Toda a API (`/api/v1/*`) | Qualquer pessoa com acesso de rede ao backend pode ler, criar, editar e excluir vagas, currículos e disparar mensagens de WhatsApp. Não há verificação de identidade em nenhuma rota. |
| **Endpoint de configuração de IA sem proteção** | [settings.py](backend/app/api/settings.py) `POST /settings/ai-key` | Qualquer requisição pode sobrescrever a chave de API de IA da empresa, gravando diretamente no `.env` do servidor. |
| **Upload de arquivo sem sanitização de nome** | [resumes.py:22](backend/app/api/resumes.py#L22) — `os.path.join(UPLOAD_DIR, file.filename)` | Nome de arquivo vindo do cliente não é sanitizado. Um nome como `../../algum_lugar/arquivo` pode escrever fora da pasta de uploads (path traversal). Também não há validação de extensão/tamanho no servidor (o `accept=".pdf,.docx"` do HTML é só uma dica de UI, não uma barreira real). |
| **SSRF potencial na criação de vaga por URL** | [job_parser.py:20](backend/app/services/job_parser.py#L20) `extract_text_from_url` | O backend faz uma requisição HTTP para qualquer URL informada pelo usuário, sem allowlist de domínio. Uma URL apontando para um endereço interno (ex: metadados de nuvem, serviços internos) faria o servidor requisitar esse recurso. |
| **Tabela de auditoria não utilizada** | `AuditLog` em models, nunca referenciada na API | Nenhuma ação (exclusão de vaga, de currículo, envio de mensagem, alteração de chave de IA) fica registrada — dificulta rastreabilidade em caso de incidente. |
| **Dados de candidatos (LGPD)** | `resumes.extracted_text`, `candidates` | Currículos contêm dados pessoais (e às vezes sensíveis). Não há política de retenção, criptografia em repouso, nem consentimento registrado. A exclusão (`DELETE /resumes/{id}`) remove o arquivo físico e o registro, o que atende ao direito de exclusão, mas não há trilha de auditoria de quem excluiu e quando. |
| **Sem HTTPS/TLS configurado** | Ambiente de execução (`uvicorn.run`) | Hoje roda em HTTP puro em `127.0.0.1`. Se for exposto além do localhost, chaves de API e dados de candidatos trafegam sem criptografia. |
| **Modo debug/reload em produção** | [main.py:42](backend/app/main.py#L42) `reload=True` | Adequado para desenvolvimento; não deve ir para produção. |

---

## 8. Motor de Matching

Dois caminhos, escolhidos automaticamente conforme há ou não chave de IA configurada ([screenings.py:26-31](backend/app/api/screenings.py#L26)):

1. **Com IA** ([llm_service.py](backend/app/services/llm_service.py)): envia vaga + currículo num prompt estruturado para Gemini/OpenAI/Groq, pedindo JSON com score e evidências. Mais preciso semanticamente, mas depende de custo/latência por chamada e de disponibilidade do provedor externo.
2. **Sem IA — motor local determinístico** ([matching_service.py](backend/app/services/matching_service.py)): matching por regras de domínio + palavras-chave (busca de substring, sem NLP real). Pontuação: 60% obrigatórios + 20% desejáveis + 10% experiência + 10% competências. Foi reescrito nesta sessão (de um dicionário de sinônimos genérico `SYNONYMS` para `DOMAIN_RULES`, mais específico por domínio: DP, formação superior, Excel/sistemas, competências comportamentais) — **mudança ainda não commitada no Git**.

Limitação conhecida do motor local: é baseado em substring matching, então é sensível a "keyword stuffing" (um currículo que apenas lista termos da vaga sem contexto real pode pontuar bem) e não entende sinônimos fora da lista pré-cadastrada.

**Convocação via WhatsApp** ([whatsapp_service.py](backend/app/services/whatsapp_service.py)) é 100% simulada — gera um link de agendamento fake e retorna uma mensagem, sem integração real com nenhum provedor (Z-API, Evolution API, Twilio, etc). O código já está desacoplado para receber uma integração real sem mudar as regras de negócio.

---

## 9. Gargalos Técnicos

1. **Screenings recalculados a cada requisição, nunca persistidos.** As tabelas `screenings`/`screening_results` existem no schema mas [screenings.py](backend/app/api/screenings.py) nunca grava nelas — todo `GET /jobs/{id}/screenings` reprocessa **todos os currículos da vaga do zero**, inclusive rechamando a API de IA por currículo se houver chave configurada. Isso significa: custo de IA proporcional ao número de vezes que a tela é aberta/atualizada (não ao número de currículos novos), latência crescente com o volume de candidatos, e resultados potencialmente inconsistentes entre uma chamada e outra (a IA pode variar a resposta).
2. **Multi-tenancy não aplicado.** O schema tem `companies` e `company_id` em várias tabelas, mas o código sempre pega "a primeira empresa" (`db.query(Company).first()`) — não há isolamento real entre empresas, e não há sistema de usuário/login para associar quem está operando.
3. **SQLite em produção.** Adequado para prototipagem e uso single-user, mas não escala bem para acesso concorrente real (lock de arquivo) nem para múltiplas instâncias do backend.
4. **Processamento síncrono.** Upload + parsing + (opcionalmente) chamada de IA acontecem dentro do próprio request HTTP — upload de muitos currículos de uma vez pode travar a requisição por um tempo longo, sem fila de background nem feedback de progresso granular.
5. **Sem paginação** em `/jobs` nem em `/jobs/{id}/screenings` — não escala com muitas vagas ou muitos candidatos por vaga.
6. **Cobertura de testes mínima.** Só 2 testes, cobrindo apenas o motor de matching determinístico. Sem testes de API, sem testes do fluxo de upload, sem CI configurado.
7. **Frontend em arquivo único sem framework.** Funciona hoje (770 linhas), mas qualquer nova tela tende a tornar o arquivo mais difícil de manter; não há componentização nem gerenciamento de estado.

---

## 10. O que foi feito (histórico desta fase de trabalho)

- Diagnóstico inicial da plataforma: nenhum servidor rodando, frontend estático solto, backend FastAPI estruturado mas não iniciado.
- Revisão e melhoria de design do `index.html`:
  - Troca do CDN do Tailwind (estava apontando para uma URL de artefato de desenvolvimento interno do Google, risco de quebra sem aviso) pelo CDN oficial.
  - Aba "Início" transformada em dashboard mínimo real (KPIs agregados).
  - Aba "Cadastro" com hierarquia visual melhor para o estado "em construção".
  - Estado vazio tratado no seletor de vagas.
  - Estados de loading/disabled em todas as ações assíncronas (evita cliques duplicados disparando requisições repetidas).
  - `aria-label` em botões só-ícone.
  - Botão "Sair" corrigido de link morto para estado desabilitado honesto (sem sistema de auth para sustentar um logout real).
  - Todas as chamadas `fetch` que não tratavam resposta de erro do backend (`res.ok === false`) passaram a exibir a mensagem real do erro via toast.
- Backend testado localmente de ponta a ponta: subida do servidor, upload de currículos reais (pasta `test_cvs/`), execução do motor de matching (incluindo a mudança em `matching_service.py`, ainda não commitada) e verificação da resposta da API.
- Investigação de uma suspeita de bug de encoding (caracteres acentuados corrompidos) — **descartada**: era um artefato de exibição do terminal usado nesta sessão (Windows/Git Bash), não um problema real. Confirmado por inspeção de bytes crus da resposta HTTP (UTF-8 correto de ponta a ponta).

### Pendências não commitadas no Git (no momento deste documento)
- `backend/app/services/matching_service.py` — refatoração de `SYNONYMS` para `DOMAIN_RULES`.
- `index.html` — todas as melhorias de design e tratamento de erro listadas acima.

---

## 11. Próximos Passos Recomendados

Em ordem sugerida de prioridade:

1. **Autenticação e autorização.** Sem isso, a plataforma não deve ser exposta além de `localhost`. Mínimo viável: login de usuário (a tabela `users` já existe) + proteção das rotas de escrita/exclusão.
2. **Corrigir upload de arquivo** — sanitizar `file.filename` (usar um nome gerado no servidor, ex: UUID + extensão original) e validar extensão/tamanho no backend, não só no HTML.
3. **Restringir `extract_text_from_url`** a uma allowlist de domínios conhecidos (Sólides, Gupy, Catho, LinkedIn) para eliminar o risco de SSRF.
4. **Persistir os resultados de screening** nas tabelas já existentes (`screenings`/`screening_results`) em vez de recalcular a cada requisição — reduz custo de IA, latência e dá histórico real.
5. **Proteger o endpoint de configuração de chave de IA** — hoje qualquer requisição pode reescrever a chave de API da empresa.
6. **Usar a tabela `audit_logs`** para registrar ações sensíveis (exclusão de vaga/currículo, alteração de chave de IA, envio de convocação).
7. **Definição de política de retenção de dados de candidatos** (LGPD) — por quanto tempo currículos ficam armazenados, e um processo formal de exclusão.
8. **Completar a aba "Cadastro & Vagas"** com formulário próprio (hoje só redireciona).
9. **Integração real de WhatsApp** (Z-API, Evolution API ou Twilio) — o serviço já está desacoplado para isso.
10. **Testes de API e CI** — cobrir upload, criação de vaga, exclusão e o fluxo de screening; configurar pipeline de CI para rodar os testes automaticamente.
11. Avaliar migração de SQLite para Postgres/MySQL se o uso crescer para múltiplos usuários simultâneos.
12. Avaliar paginação nas listagens antes que o volume de vagas/candidatos cresça.

---

## 12. Como Rodar Localmente

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Acesse http://127.0.0.1:8000/ — o próprio FastAPI serve o index.html
```

Configurar `.env` na raiz do projeto (copiar de `.env.example`) com pelo menos uma chave de IA (`GEMINI_API_KEY`, `OPENAI_API_KEY` ou `GROQ_API_KEY`) para habilitar o motor de matching por IA. Sem nenhuma chave, o sistema usa automaticamente o motor determinístico local.
