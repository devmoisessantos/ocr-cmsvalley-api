import re
import os
from typing import List, Tuple

import cv2
import numpy as np
import easyocr

# Idiomas configuráveis por env var (default português + inglês)
_LANGS = os.getenv("OCR_LANGS", "pt,en").split(",")

# EasyOCR é pesado pra inicializar — carrega uma vez só, no import do módulo,
# e reaproveita em todas as requisições.
_reader = easyocr.Reader(_LANGS, gpu=False)

# Restringe o alfabeto possível que o EasyOCR tenta reconhecer — reduz muito
# a confusão de caracteres em fontes de HUD de jogo (esse foi o ajuste que
# resolveu o reconhecimento).
_ALLOWLIST = (
    "0123456789:.- "
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ÀÁÂÃÉÊÍÓÔÕÚÇàáâãéêíóôõúç"
)

# Usa .search (não .match) e não ancora no fim da linha — assim casa mesmo
# quando o EasyOCR gruda algum caractere estranho antes/depois do ID:Nome.
# 1 a 7 dígitos aqui é só o alcance do regex; o intervalo real de IDs válidos
# é validado depois (ID_MINIMO / ID_MAXIMO), porque IDs muito longos quase
# sempre são dígito(s) confundido(s) pelo OCR, não um ID real.
_LINE_PATTERN = re.compile(r"(\d{1,7})\s*[:.\-]\s*(.+)")

# Intervalo esperado de IDs FiveM válidos nesse servidor — nunca existe ID 0,
# negativo, ou acima de 200000. A API NÃO descarta quem cai fora disso — ela
# só marca a entrada como "suspeita" e manda pro bot mesmo assim. Quem decide
# o que fazer com isso (tentar corrigir, cruzar com o Discord, etc.) é o
# bot, não a API — ver validacao_ids.py em bot_integration/.
ID_MINIMO = 1
ID_MAXIMO = 200_000


def _preprocess(image_bytes: bytes) -> np.ndarray:
    """Prepara a imagem do print do EMS pra melhorar a leitura do OCR.

    Importante: SEM binarização (adaptiveThreshold) e SEM denoise agressivo —
    isso destruía o texto fino da fonte do HUD. Só upscale grande com
    interpolação Lanczos + contraste local (CLAHE) é o que funcionou.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Não foi possível decodificar a imagem enviada.")

    img = cv2.resize(img, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contraste = clahe.apply(gray)
    return contraste


def _parse_lines(raw_lines: List[str]) -> Tuple[List[dict], List[str]]:
    """Separa linhas em: reconhecidas (válidas ou suspeitas) e sem padrão 'ID: Nome'.

    Uma linha só é descartada de verdade quando o regex não acha NENHUM
    'número : nome' nela — nesse caso não tem o que mandar pro bot. Se o
    padrão bate mas o número foge do intervalo esperado, a entrada é
    marcada como "suspeito" e enviada mesmo assim: quem decide se corrige,
    descarta ou pede confirmação manual é o bot (que tem acesso à lista
    real de membros do Discord pra cruzar e tentar corrigir).
    """
    medicos = []
    sem_padrao = []
    for line in raw_lines:
        match = _LINE_PATTERN.search(line.strip())
        if not match:
            sem_padrao.append(line)
            continue

        id_str, nome = match.groups()
        id_num = int(id_str)
        suspeito = not (ID_MINIMO <= id_num <= ID_MAXIMO)

        entrada = {"id": id_num, "nome": nome.strip(), "suspeito": suspeito}
        if suspeito:
            entrada["motivo_suspeita"] = (
                f"ID fora do intervalo esperado ({ID_MINIMO}-{ID_MAXIMO})"
            )
        medicos.append(entrada)

    return medicos, sem_padrao


def extrair_medicos_do_print(image_bytes: bytes) -> dict:
    """Recebe os bytes da imagem do print do EMS e devolve a lista ID/Nome."""
    processed = _preprocess(image_bytes)

    resultados = _reader.readtext(
        processed,
        detail=0,
        paragraph=False,
        allowlist=_ALLOWLIST,
        mag_ratio=2.0,
    )

    medicos, sem_padrao = _parse_lines(resultados)

    total_suspeitos = sum(1 for m in medicos if m["suspeito"])

    aviso = None
    if sem_padrao:
        aviso = f"{len(sem_padrao)} linha(s) não bateram com o padrão 'ID: Nome' e foram ignoradas."

    return {
        "total_detectado": len(medicos),
        "total_suspeitos": total_suspeitos,
        "medicos": medicos,
        "aviso": aviso,
    }
