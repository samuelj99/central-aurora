"""
Calcula a fila "Hoje" a partir de Base_bruta.xlsx (a tela é montada por build_app.py).

Lê a planilha, calcula a fila de cobrança ("Hoje") e grava um único arquivo
HTML autocontido (sem bibliotecas externas, sem internet, sem instalação).
Todo número que aparece na tela vem de uma conta feita aqui em cima dos
dados da planilha -- nada é digitado à mão no template.

O comportamento de pagamento de cada cliente (média de atraso, desvio, se
mudou de comportamento) vem de aurora_calc.py -- o mesmo cálculo usado pela
tela Risco por cliente e pela Previsão de caixa. Não existe uma segunda
conta aqui: só a leitura da fila e a frase, que são específicas desta tela.

Uso:
    python build_central.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

import aurora_calc as ac

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
REGISTROS_PATH = Path(__file__).parent / "registros_cobranca.json"
JSON_EXPORT_PATH = Path(__file__).parent / "dados_hoje.json"

# ---------------------------------------------------------------------------
# Parâmetros da regra de priorização (decisões assumidas -- ver relatório)
# ---------------------------------------------------------------------------
BONUS_TENDENCIA = 0.35          # acréscimo no fator de risco se o comportamento mudou (sinal forte)
FATOR_TIER = {
    "inedito": 1.6,         # atraso atual supera o pior atraso que o cliente já teve
    "acima_normal": 1.25,   # atraso atual acima da média do cliente, mas já visto antes
    "dentro_padrao": 0.85,  # atraso atual dentro (ou abaixo) da média histórica do cliente
    "sem_historico": 1.1,   # cliente sem título pago na base -- risco não verificável
}
PENALIDADE_CONTATO_48H = 0.45   # multiplicador aplicado a quem foi cobrado nas últimas 48h
JANELA_CONTATO_DIAS = 2         # "48 horas" tratado em granularidade de dia corrido


def severidade(tier: str, mudou: bool) -> str:
    """Como a tela pinta o cliente (sempre acompanhada de texto): 'critico' = atraso inédito
    ou piora real; 'atencao' = acima do normal dele; 'ok' = dentro do padrão dele."""
    if tier == "inedito" or mudou:
        return "critico"
    if tier == "acima_normal":
        return "atencao"
    if tier == "dentro_padrao":
        return "ok"
    return "neutro"


def motivo_curto(r: dict) -> list:
    """Duas ou três linhas curtas com o porquê da posição na fila -- os mesmos números da frase completa."""
    dias = r["dias_vencido_max"]
    media, maximo = r["media_atraso_hist"], r["max_atraso_hist"]
    atraso = f"{ac.fmt_dias(dias)} de atraso"
    if r["tier"] == "inedito":
        l1 = f"{atraso}: nunca passou de {ac.fmt_dias(maximo)} (média de {media:.0f})."
    elif r["tier"] == "acima_normal":
        l1 = f"{atraso}, acima da média dele ({media:.0f}); já chegou a {ac.fmt_dias(maximo)}."
    elif r["tier"] == "dentro_padrao":
        l1 = f"{atraso}, dentro do padrão dele (paga em torno de {media:.0f})."
    else:
        l1 = f"{atraso}. Sem título pago para comparar."
    linhas = [l1]
    if r["mudou_comportamento"]:
        linhas.append(f"Piorou: pagava em {r['media_antiga']:.0f} dias e agora leva {r['media_recente']:.0f}.")
    d = r["dias_desde_contato"]
    if r["contato_recente_48h"]:
        quando = "hoje" if d == 0 else f"há {ac.fmt_dias(d)}"
        linhas.append(f"Cobrado {quando} ({r['canal_ultimo_contato']}): desceu na fila.")
    elif d is not None:
        linhas.append(f"Último contato há {ac.fmt_dias(d)} ({r['canal_ultimo_contato']}).")
    return linhas


FAIXAS_ATRASO = [(1, 7, "1 a 7 dias"), (8, 30, "8 a 30 dias"), (31, 60, "31 a 60 dias"), (61, None, "mais de 60 dias")]


def main():
    if not XLSX_PATH.exists():
        print(f"Não encontrei {XLSX_PATH}", file=sys.stderr)
        sys.exit(1)

    data_base = ac.ler_data_referencia(XLSX_PATH)
    clientes, titulos, cobrancas = ac.carregar_base(XLSX_PATH)
    comportamento = ac.calcular_comportamento_clientes(clientes, titulos, data_base)

    abertos = titulos[titulos["Data de pagamento"].isna()].copy()
    abertos["dias_vencido"] = (data_base - abertos["Data de vencimento"]).dt.days
    vencidos = abertos[abertos["Data de vencimento"] < data_base].copy()
    a_vencer = abertos[abertos["Data de vencimento"] >= data_base].copy()

    nomes = clientes.set_index("Código do cliente")["Nome do cliente"].to_dict()
    categorias = clientes.set_index("Código do cliente")["Categoria"].to_dict()
    regioes = clientes.set_index("Código do cliente")["Região"].to_dict()
    contatos_cliente = clientes.set_index("Código do cliente")["Contato"].to_dict()

    registros = ac.carregar_registros(REGISTROS_PATH)
    contatos = ac.combinar_cobrancas(cobrancas, registros)
    ultimo_contato = contatos.groupby("codigo_cliente").tail(1).set_index("codigo_cliente")

    fila = []
    for cod in sorted(clientes["Código do cliente"].unique()):
        venc_cli = vencidos[vencidos["Código do cliente"] == cod]
        valor_vencido = int(venc_cli["valor_centavos"].sum())
        if valor_vencido <= 0:
            continue  # só entra na fila quem tem título vencido hoje

        qtd_vencidos = int(len(venc_cli))
        dias_vencido_max = int(venc_cli["dias_vencido"].max())

        comp = comportamento[cod]
        n_pagos = comp["n_titulos_pagos"]
        media_atraso = comp["media_atraso"]
        max_atraso = comp["max_atraso"]
        mudou = comp["mudou_forte"]
        media_antiga = comp["media_antiga"]
        media_recente = comp["media_recente"]

        if media_atraso is None:
            tier = "sem_historico"
        elif dias_vencido_max > max_atraso:
            tier = "inedito"
        elif dias_vencido_max > media_atraso:
            tier = "acima_normal"
        else:
            tier = "dentro_padrao"

        # Contato recente (últimas 48h, em granularidade de dia corrido).
        dias_desde_contato = None
        contato_recente = False
        canal = tom = None
        if cod in ultimo_contato.index:
            dt_contato = ultimo_contato.loc[cod, "data_hora"]
            dias_desde_contato = int((data_base.normalize() - dt_contato.normalize()).days)
            contato_recente = dias_desde_contato <= JANELA_CONTATO_DIAS
            canal = str(ultimo_contato.loc[cod, "canal"])
            tom = str(ultimo_contato.loc[cod, "tom_label"])

        fator_risco = FATOR_TIER[tier] + (BONUS_TENDENCIA if mudou else 0.0)
        fator_contato = PENALIDADE_CONTATO_48H if contato_recente else 1.0
        score = valor_vencido * fator_risco * fator_contato

        # --- frase explicativa, montada a partir dos números acima ---
        frase = (
            f"Tem R$ {ac.fmt_reais(valor_vencido)} vencidos em "
            f"{qtd_vencidos} {ac.plural(qtd_vencidos, 'título', 'títulos')}, "
            f"o mais antigo já com {dias_vencido_max} "
            f"{ac.plural(dias_vencido_max, 'dia', 'dias')} de atraso."
        )
        if tier == "sem_historico":
            frase += " Esse cliente ainda não tem título pago na base, então não há histórico para comparar o risco."
        elif tier == "inedito":
            frase += (
                f" Esse atraso já é o maior que esse cliente já teve: o histórico dele nunca passou de "
                f"{max_atraso} {ac.plural(max_atraso, 'dia', 'dias')}, com média de {media_atraso:.0f} dias."
            )
        elif tier == "acima_normal":
            frase += (
                f" Já está acima do que ele costuma fazer (média de {media_atraso:.0f} dias), "
                f"mas não é inédito — o atraso mais longo dele já chegou a {max_atraso} dias."
            )
        else:  # dentro_padrao
            frase += (
                f" Isso está dentro do padrão normal dele: historicamente paga em média "
                f"{media_atraso:.0f} dias depois do vencimento, então não chega a ser um alerta novo."
            )
        if mudou:
            frase += (
                f" Além disso, o atraso médio dele vinha subindo nos títulos mais recentes: de "
                f"{media_antiga:.0f} para {media_recente:.0f} dias — um sinal de mudança de comportamento."
            )
        if contato_recente:
            quando = "hoje" if dias_desde_contato == 0 else f"há {ac.fmt_dias(dias_desde_contato)}"
            frase += (
                f" Foi cobrado {quando} ({canal}, tom: {tom.lower()}), "
                f"por isso desceu posições na fila para não repetir contato tão em cima."
            )
        elif dias_desde_contato is not None:
            frase += (
                f" O último contato foi há {ac.fmt_dias(dias_desde_contato)} ({canal}), "
                f"tempo suficiente para cobrar de novo sem parecer repetitivo."
            )

        titulos_detalhe = [
            {
                "numero": r["Número do título"],
                "valor_centavos": int(r["valor_centavos"]),
                "vencimento": r["Data de vencimento"].strftime("%d/%m/%Y"),
                "dias_vencido": int(r["dias_vencido"]),
            }
            for _, r in venc_cli.sort_values("dias_vencido", ascending=False).iterrows()
        ]

        fila.append(
            {
                "codigo": int(cod),
                "nome": nomes[cod],
                "categoria": categorias[cod],
                "regiao": regioes[cod],
                "contato_nome": contatos_cliente[cod],
                "valor_vencido_centavos": valor_vencido,
                "qtd_vencidos": qtd_vencidos,
                "dias_vencido_max": dias_vencido_max,
                "tier": tier,
                "media_atraso_hist": round(media_atraso, 1) if media_atraso is not None else None,
                "max_atraso_hist": max_atraso,
                "n_titulos_pagos_hist": n_pagos,
                "mudou_comportamento": mudou,
                "media_antiga": round(media_antiga, 1) if media_antiga is not None else None,
                "media_recente": round(media_recente, 1) if media_recente is not None else None,
                "contato_recente_48h": contato_recente,
                "dias_desde_contato": dias_desde_contato,
                "canal_ultimo_contato": canal,
                "tom_ultimo_contato": tom,
                "score": score,
                "frase": frase,
                "titulos": titulos_detalhe,
            }
        )

    fila.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(fila, start=1):
        r["posicao"] = i

    # ---- camada de apresentação: nada aqui é conta nova de negócio; são os mesmos números
    # da "frase" completa, reescritos em linhas curtas para bater o olho (a frase completa
    # continua no cartão, atrás do clique "detalhes").
    total_vencido = int(vencidos["valor_centavos"].sum())
    for r in fila:
        r["pct_do_vencido"] = round(r["valor_vencido_centavos"] / total_vencido * 100) if total_vencido else 0
        r["severidade"] = severidade(r["tier"], r["mudou_comportamento"])
        r["motivo"] = motivo_curto(r)

    resumo = {
        "data_base": data_base.strftime("%d/%m/%Y"),
        "total_clientes_base": int(clientes["Código do cliente"].nunique()),
        "total_titulos_base": int(len(titulos)),
        "clientes_na_fila": len(fila),
        "total_vencido_centavos": int(vencidos["valor_centavos"].sum()),
        "qtd_titulos_vencidos": int(len(vencidos)),
        "total_a_vencer_centavos": int(a_vencer["valor_centavos"].sum()),
        "qtd_titulos_a_vencer": int(len(a_vencer)),
        "faixas_atraso": [
            {
                "rotulo": rot,
                "valor_centavos": int(vencidos[(vencidos["dias_vencido"] >= de) & ((vencidos["dias_vencido"] <= ate) if ate else True)]["valor_centavos"].sum()),
                "qtd": int(((vencidos["dias_vencido"] >= de) & ((vencidos["dias_vencido"] <= ate) if ate else True)).sum()),
            }
            for de, ate, rot in FAIXAS_ATRASO
        ],
    }

    payload = {"resumo": resumo, "fila": fila}

    # Exporta um resumo limpo para o Relatório da semana ler (não recalcular).
    JSON_EXPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK -- {JSON_EXPORT_PATH.name} gerado. {len(fila)} cliente(s) na fila de hoje.")
    return payload


if __name__ == "__main__":
    main()
