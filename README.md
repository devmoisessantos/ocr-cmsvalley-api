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
│   ├── ocr.py              → pipeline de OCR (OpenCV + EasyOCR + parsing)
│   └── models.py           → schemas de request/response (Pydantic)
├── site/                   → página simples pra testar o OCR manualmente (upload → resultado)
│   ├── index.html
│   └── style.css
├── bot_integration/
│   └── ems_ocr_client.py   → módulo pronto pra COLAR dentro do cmsvalley-bot existente
├── requirements.txt
├── render.yaml             → deploy da API no Render
├── vercel.json             → deploy do site estático no Vercel
└── .gitignore
```

## Como isso se encaixa no cmsvalley-bot

1. Este serviço (`api/`) sobe sozinho no Render, com sua própria URL
   (ex: `https://ems-ocr.onrender.com`).
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

O site em `site/index.html` pode ser aberto direto no navegador — ele busca
a lista de rotas em `GET /routes` sozinho. Tem um campo "URL da API" no
canto inferior do menu caso a API não esteja em `http://127.0.0.1:8000`.

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

## Variáveis de ambiente

- `API_URL` (usado pelo bot em `ems_ocr_client.py`) — URL pública da API depois do deploy.
- `OCR_LANGS` (opcional, default `pt`) — idiomas carregados pelo EasyOCR.
