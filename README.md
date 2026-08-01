---
title: EMS OCR CMS Valley
emoji: 🚑
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# EMS OCR Service — CMS Valley

Serviço separado (API + site de teste) que recebe o print do comando **EMS**
in-game e devolve, em JSON, a lista `ID: Nome` dos médicos com toggle ligado.

**Isto NÃO é um bot novo.** É um microsserviço HTTP que o `cmsvalley-bot`
(o bot Discord já existente) vai chamar quando o Doutor pedir a chamada de
verificação. O bot continua sendo um só; este serviço só faz o trabalho pesado
de OCR e devolve o resultado pronto.

```
ems-ocr-service/
├── api/                    → FastAPI: recebe a imagem, roda o OCR, devolve JSON
│   ├── main.py             → endpoints da API
│   ├── ocr.py              → chama o Space DeepSeek-OCR (gradio_client) + parsing
│   └── models.py           → schemas de request/response (Pydantic)
├── site/                   → painel de teste, servido pela própria API em `/`
│   ├── index.html
│   └── style.css
├── bot_integration/
│   └── ems_ocr_client.py   → módulo pronto pra COLAR dentro do cmsvalley-bot existente
├── requirements.txt
├── Dockerfile              → deploy de API + painel em qualquer host de container
├── render.yaml             → deploy da API no Render
├── vercel.json             → deploy do painel estático no Vercel
└── .gitignore
```

## Como isso se encaixa no cmsvalley-bot

1. Este serviço (`api/`) sobe sozinho, com sua própria URL
   (ex: `https://ems-ocr.onrender.com`) — ver "Deploy" abaixo.
2. Dentro do repositório do **cmsvalley-bot já existente**, você copia o arquivo
   `bot_integration/ems_ocr_client.py` pra dentro da pasta de utils/services do bot.
3. No cog que já cuida da chamada de verificação/plantão médico, você importa
   `enviar_print_ems()` e chama essa função passando o `discord.Attachment`
   da imagem enviada pelo Doutor. Ela faz o POST pra API e devolve a lista
   `[{id, nome}]` já parseada, pronta pra comparar com quem está com toggle
   ligado no Discord.
4. Nenhum outro bot é criado — o bot continua único, só ganha uma chamada de
   rede a mais.

## Rodando localmente

```bash
cd api
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000
```

Teste rápido:

```bash
curl -X POST http://localhost:8000/ocr/ems -F "file=@print_ems.png"
```

O painel em `site/index.html` pode ser aberto direto no navegador — ele busca
a lista de rotas em `GET /routes` sozinho, usando o endereço do campo "URL da
API" no rodapé do menu (troque pra `http://127.0.0.1:8000` ao testar local).
A própria API também serve esse mesmo painel em `/`, caso você não queira um
deploy separado do estático.

## Deploy

Hoje a API roda no Render (`render.yaml`) e o painel no Vercel (`vercel.json`
+ `.vercelignore`), apontando pro endereço fixo no campo "URL da API" do
`site/index.html`.

Como o OCR pesado foi terceirizado pro Space do DeepSeek, as dependências
cabem em qualquer free tier — e, como a API também serve o painel em `/`, dá
pra usar um deploy só. Outras opções:

- **Hugging Face Spaces** (free, sem cartão) — crie um Space com **SDK:
  Docker**, gere um token em https://huggingface.co/settings/tokens e rode
  `git remote add space https://<usuario>:<token>@huggingface.co/spaces/<usuario>/<space>`
  seguido de `git push space main`. O bloco YAML no topo deste README é a
  configuração lida pelo HF (`sdk: docker`, `app_port: 7860`) — não remova.
- **Qualquer host de container** (VPS, Koyeb, Oracle Cloud):
  `docker build -t ems-ocr . && docker run -p 7860:7860 ems-ocr`.

Depois do deploy, coloque a URL pública na env var `API_URL` do `cmsvalley-bot`.

## Motor de OCR: OCR.space (padrão), com Spaces do HF como alternativa

`OCR_PROVIDER` escolhe o motor, sem precisar editar código:

- **`ocrspace`** (default) — [OCR.space](https://ocr.space/OCRAPI), serviço
  dedicado de OCR com API key própria. É o mais estável dos três: cota
  mensal documentada (25.000 conversões/mês grátis no Engine 1/2, 2.500 no
  Engine 3), sem depender de Space de terceiro sem SLA. Precisa da env var
  `OCRSPACE_API_KEY` — **nunca cole a chave real no `render.yaml` nem em
  qualquer arquivo do repositório**, configure direto no painel do Render
  (`sync: false` já deixa isso marcado no blueprint).
- **`deepseek`** — Space da comunidade `khang119966/DeepSeek-OCR-DEMO`,
  grátis mas sujeito a fila/cota compartilhada e pode sair do ar.
- **`unlimited`** — Space oficial `baidu/Unlimited-OCR`. **Atenção:** o
  adaptador desse aqui (`_rodar_unlimited` em `ocr.py`) ainda não foi
  testado contra a API real — antes de usar em produção, confirma os nomes
  dos parâmetros na página "Use via API" do Space.

Pra trocar de motor: muda a env var `OCR_PROVIDER` no Render (`ocrspace`,
`deepseek` ou `unlimited`) e reinicia o serviço — nenhum código muda.

Histórico: já testamos EasyOCR + OpenCV local (funcionava, mas exigia a
fonte pesada de dependências) e `baidu/Unlimited-OCR` rodando localmente via
`transformers` (descartado — estourava memória no Render).

## IDs suspeitos: a API não descarta, ela sinaliza

A API sabe que IDs FiveM desse servidor vão de 1 a 200000 — mas em vez de
jogar fora quem foge disso (podia ser um erro de OCR corrigível), ela manda
a entrada mesmo assim, com `"suspeito": true` e um `"motivo_suspeita"`.
Só é descartado de verdade quem **não bate com nenhum padrão `ID: Nome`**
(vai pro campo `aviso`, contado à parte).

Quem decide o que fazer com uma entrada suspeita é o **bot**, porque só ele
tem acesso à lista real de membros do servidor pra cruzar e corrigir — ver
`bot_integration/validacao_ids.py`. A estratégia usada lá:

1. ID bate direto com um membro conhecido → confirmado.
2. Não bate, mas bate depois de trocar 1 dígito confundível pela fonte do
   HUD (ex: `710515` → `110515`, porque "7" e "1" se parecem nessa fonte)
   → corrigido por dígito.
3. Ainda não bate → tenta achar por nome (fuzzy match) entre os membros
   conhecidos e usa o ID real de lá.
4. Não bate de nenhuma forma → provavelmente é médico de outro hospital
   (ex: Hospital Norte), igual já era tratado no fluxo de chamada de
   verificação.

O site também reflete isso: entradas suspeitas aparecem destacadas em
vermelho na lista, com a tag "⚠ confira", em vez de somem calada.

## Painel do site (pensado pra crescer)

O `site/` não é mais uma página fixa só de upload — é um painel com menu
lateral montado **dinamicamente** a partir do que a API expõe em `GET /routes`
(`api/main.py`, variável `ROUTES_INFO`). Isso significa que, quando o projeto
crescer (ex: comparar com o toggle do Discord, ver histórico de chamadas),
o processo é:

1. Criar o endpoint novo normalmente em `api/main.py`.
2. Adicionar uma entrada em `ROUTES_INFO` com um `tipo`:
   - `status` — botão "Testar", mostra o JSON puro (bom pra healthchecks).
   - `upload_imagem` — área de drag-and-drop de imagem (usado hoje pelo OCR do EMS).
   - `acao_simples` — botão "Executar" pra rotas sem parâmetro.
3. Pronto — o painel já mostra a nova rota no menu, sem tocar em HTML/JS.

Se um tipo novo de ação não se encaixar nesses três (ex: um formulário com
campos de texto), aí sim vale estender o JS do `site/index.html` com um novo
`tipo`.

## Vercel tentando rodar a API (não faça isso)

A Vercel detecta automaticamente qualquer pasta `api/` com arquivos `.py`
e tenta rodar como Serverless Function — isso acontece **antes** de olhar
pro `vercel.json`, então mesmo com `outputDirectory: "site"` configurado
ela ainda tentava invocar `api/main.py`, e crashava
(`FUNCTION_INVOCATION_FAILED`), já que o `requirements.txt` fica na raiz,
não dentro de `api/`, e a API nunca foi feita pra rodar como função
serverless mesmo.

O `.vercelignore` na raiz resolve isso, excluindo `api/`, `bot_integration/`,
`requirements.txt` e `render.yaml` do que a Vercel enxerga — ela passa a
servir só o `site/` estático, como sempre foi o plano. A API continua
rodando exclusivamente no Render.

## Variáveis de ambiente

- `API_URL` (usado pelo bot em `ems_ocr_client.py`) — URL pública da API depois do deploy.
- `OCR_PROVIDER` (opcional, default `ocrspace`) — qual motor usar: `ocrspace`, `deepseek` ou `unlimited`.
- `OCRSPACE_API_KEY` — **obrigatória** se `OCR_PROVIDER=ocrspace`. Cole a chave real só no painel do Render, nunca em arquivo do repositório.
- `OCRSPACE_LANGUAGE` (opcional, default `por`) / `OCRSPACE_ENGINE` (opcional, default `2`).
- `DEEPSEEK_OCR_SPACE` / `DEEPSEEK_OCR_MODEL_SIZE` — usados só se `OCR_PROVIDER=deepseek`.
- `UNLIMITED_OCR_SPACE` / `UNLIMITED_OCR_MODE` — usados só se `OCR_PROVIDER=unlimited`.
- `PORT` (opcional, default `7860`) — porta que o uvicorn escuta no container.
