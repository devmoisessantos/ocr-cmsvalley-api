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

O site em `site/index.html` pode ser aberto direto no navegador (ajuste a
constante `API_URL` no topo do arquivo pra apontar pro seu endpoint) pra
testar o upload sem precisar do Discord.

## Variáveis de ambiente

- `API_URL` (usado pelo bot em `ems_ocr_client.py`) — URL pública da API depois do deploy.
- `OCR_LANGS` (opcional, default `pt`) — idiomas carregados pelo EasyOCR.
