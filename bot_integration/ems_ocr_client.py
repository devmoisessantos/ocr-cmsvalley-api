"""
Módulo pra COLAR dentro do repositório do cmsvalley-bot já existente
(ex: em bot/services/ems_ocr_client.py ou onde ficam os helpers do bot).

Isso NÃO cria um bot novo — é só uma função HTTP que o cog responsável
pela chamada de verificação/plantão médico vai importar e chamar.

Uso dentro de um cog existente:

    from services.ems_ocr_client import enviar_print_ems

    @app_commands.command(name="chamada_ems")
    async def chamada_ems(self, interaction: discord.Interaction, print_ems: discord.Attachment):
        await interaction.response.defer()
        try:
            resultado = await enviar_print_ems(print_ems)
        except EmsOcrError as e:
            await interaction.followup.send(f"Erro ao ler o print: {e}")
            return

        # resultado["medicos"] -> [{"id": 9, "nome": "Tuco Palacio"}, ...]
        # aqui entra a comparação com quem está com toggle ligado no Discord
"""

import os
import aiohttp
import discord

API_URL = os.getenv("EMS_OCR_API_URL", "http://localhost:8000/ocr/ems")
TIMEOUT_SEGUNDOS = 20


class EmsOcrError(Exception):
    """Erro ao chamar o serviço de OCR do EMS."""


async def enviar_print_ems(anexo: discord.Attachment) -> dict:
    """
    Recebe o discord.Attachment do print do comando /ems, envia pra API
    de OCR e devolve o JSON já parseado:

        {
          "total_detectado": 8,
          "medicos": [{"id": 9, "nome": "Tuco Palacio"}, ...],
          "aviso": None | str
        }
    """
    if not anexo.content_type or not anexo.content_type.startswith("image/"):
        raise EmsOcrError("O arquivo enviado não é uma imagem.")

    imagem_bytes = await anexo.read()

    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEGUNDOS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            imagem_bytes,
            filename=anexo.filename,
            content_type=anexo.content_type,
        )

        try:
            async with session.post(API_URL, data=form) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise EmsOcrError(data.get("erro", "erro desconhecido na API de OCR"))
                return data
        except aiohttp.ClientError as e:
            raise EmsOcrError(f"não foi possível conectar na API de OCR ({e})")
