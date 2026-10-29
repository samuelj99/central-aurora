"""
Cálculo único e compartilhado de comportamento de pagamento por cliente.

Usado por build_central.py (Hoje), build_risco.py (Risco por cliente) e
build_previsao.py (Previsão de caixa). As três telas falam do mesmo cliente
usando os MESMOS números de atraso médio, dispersão, sazonalidade e mudança
de comportamento -- calculados uma única vez, aqui.

Se uma tela precisar de algo que este módulo não calcula, o conserto é aqui
dentro (e todas as telas que já existem herdam o conserto), nunca uma conta
paralela dentro do script de uma tela.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import openpyxl

# ---------------------------------------------------------------------------
# Parâmetros do comportamento (compartilhados pelas três telas)
# ---------------------------------------------------------------------------
JANELA_TENDENCIA_DIAS = 90        # janela "recente" para detectar mudança de comportamento
AMOSTRA_MINIMA_TENDENCIA = 3      # mínimo de títulos pagos em cada janela (recente/antiga)
LIMIAR_ABS_FORTE = 8              # dias -- piora "forte" precisa ser pelo menos isso
LIMIAR_REL_FORTE = 1.0            # ... E pelo menos 1x o desvio histórico do próprio cliente

LIMIAR_SAZONALIDADE_MIN = 5       # dias de elevação mínima p/ considerar um mês-calendário "quente"
LIMIAR_SAZONALIDADE_REL = 0.75    # ... ou 0.75x o desvio geral do cliente, o que for maior
MIN_ANOS_SAZONALIDADE = 2         # só é "padrão de calendário" se repetir em >=2 anos distintos

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}
NOME_MES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def ler_data_referencia(xlsx_path: Path) -> pd.Timestamp:
    """Lê a frase 'DATA DE REFERÊNCIA' na aba Leia-me. Nunca o relógio do computador."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Leia-me"]
    valores = [c for row in ws.iter_rows(values_only=True) for c in row if c is not None]
    for i, v in enumerate(valores):
        if isinstance(v, str) and v.strip().upper() == "DATA DE REFERÊNCIA":
            texto = str(valores[i + 1])
            m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto, re.IGNORECASE)
            if not m:
                raise ValueError(f"Não consegui entender a data de referência: {texto!r}")
            dia, mes_nome, ano = m.groups()
            return pd.Timestamp(year=int(ano), month=MESES_PT[mes_nome.lower()], day=int(dia))
    raise ValueError("Não encontrei 'DATA DE REFERÊNCIA' na aba Leia-me.")


def fmt_reais(centavos) -> str:
    """Real mais próximo (meio real arredonda para cima). É a MESMA regra do
    fmtReais() das telas -- truncar aqui fazia o Relatório mostrar R$ 1 a
    menos que a tela para o mesmo número."""
    c = int(round(centavos))
    reais = (abs(c) + 50) // 100
    return ("-" if c < 0 and reais else "") + f"{reais:,}".replace(",", ".")


def plural(n, singular, pl):
    return singular if n == 1 else pl


def fmt_dec(valor, casas=1) -> str:
    """Número com vírgula decimal, como se escreve em português."""
    return f"{valor:.{casas}f}".replace(".", ",")


def fmt_dias(n) -> str:
    return f"{n} {plural(abs(n), 'dia', 'dias')}"


def fmt_atraso(dias) -> str:
    """Atraso de pagamento em relação ao vencimento, em português: negativo
    é pagamento ADIANTADO, não 'pagou em -3 dias'."""
    if dias < 0:
        return f"{fmt_dias(-dias)} antes do vencimento"
    if dias == 0:
        return "no dia do vencimento"
    return f"{fmt_dias(dias)} depois do vencimento"


def carregar_base(xlsx_path: Path):
    """Lê Clientes, Títulos e Cobranças, com valores já em centavos (inteiro)."""
    clientes = pd.read_excel(xlsx_path, sheet_name="Clientes")
    titulos = pd.read_excel(xlsx_path, sheet_name="Títulos")
    cobrancas = pd.read_excel(xlsx_path, sheet_name="Cobranças")

    titulos["valor_centavos"] = (titulos["Valor do título"] * 100).round().astype("int64")
    clientes["limite_centavos"] = (clientes["Limite de crédito"] * 100).round().astype("int64")
    cobrancas["valor_centavos"] = (cobrancas["Valor cobrado"] * 100).round().astype("int64")
    return clientes, titulos, cobrancas


def calcular_comportamento_clientes(clientes: pd.DataFrame, titulos: pd.DataFrame, data_base: pd.Timestamp) -> dict:
    """
    Para cada cliente, calcula o comportamento de pagamento a partir do histórico de
    títulos PAGOS: nível de atraso, dispersão, sazonalidade e mudança de comportamento.

    Retorna um dict {codigo_cliente: {...}}. Esta é a ÚNICA função que calcula essas
    coisas -- Hoje, Risco e Previsão leem daqui, nunca recalculam por conta própria.
    """
    pagos = titulos[titulos["Data de pagamento"].notna()].copy()
    pagos["atraso"] = (pagos["Data de pagamento"] - pagos["Data de vencimento"]).dt.days
    pagos["mes_cal"] = pagos["Data de vencimento"].dt.month
    pagos["ano_cal"] = pagos["Data de vencimento"].dt.year

    corte = data_base - pd.Timedelta(days=JANELA_TENDENCIA_DIAS)
    out = {}

    for cod in sorted(clientes["Código do cliente"].unique()):
        g_full = pagos[pagos["Código do cliente"] == cod].copy()
        n_pagos = len(g_full)

        # --- sazonalidade: mês-calendário com atraso bem acima da média, repetido em >=2 anos ---
        meses_sazonais = []
        media_atraso_sazonal = {}
        if n_pagos >= 2:
            media_geral = g_full["atraso"].mean()
            desvio_geral = g_full["atraso"].std()
            limiar = max(LIMIAR_SAZONALIDADE_MIN, LIMIAR_SAZONALIDADE_REL * (desvio_geral or 0))
            piv = g_full.groupby(["mes_cal", "ano_cal"])["atraso"].mean().reset_index()
            elevados = {}
            for _, row in piv.iterrows():
                if row["atraso"] - media_geral >= limiar:
                    elevados.setdefault(int(row["mes_cal"]), set()).add(int(row["ano_cal"]))
            meses_sazonais = sorted(m for m, anos in elevados.items() if len(anos) >= MIN_ANOS_SAZONALIDADE)
            for m in meses_sazonais:
                media_atraso_sazonal[m] = float(g_full[g_full["mes_cal"] == m]["atraso"].mean())

        g = g_full[~g_full["mes_cal"].isin(meses_sazonais)].sort_values("Data de vencimento")
        n_pagos_uteis = len(g)

        if n_pagos_uteis >= 2:
            media_atraso = float(g["atraso"].mean())
            desvio_atraso = float(g["atraso"].std())
            min_atraso = int(g["atraso"].min())
            max_atraso = int(g["atraso"].max())
        elif n_pagos_uteis == 1:
            media_atraso = float(g["atraso"].iloc[0])
            desvio_atraso = None
            min_atraso = max_atraso = int(g["atraso"].iloc[0])
        else:
            media_atraso = desvio_atraso = min_atraso = max_atraso = None

        # --- mudança de comportamento: sinal FORTE (gatilho -- grande em dias E grande p/ o próprio cliente) ---
        mudou_forte = False
        media_antiga = media_recente = delta_forte = None
        min_atraso_recente = max_atraso_recente = None
        recente = g[g["Data de vencimento"] >= corte]
        antiga = g[g["Data de vencimento"] < corte]
        if len(recente) >= AMOSTRA_MINIMA_TENDENCIA and len(antiga) >= AMOSTRA_MINIMA_TENDENCIA and desvio_atraso:
            media_recente = float(recente["atraso"].mean())
            media_antiga = float(antiga["atraso"].mean())
            delta_forte = media_recente - media_antiga
            if delta_forte >= LIMIAR_ABS_FORTE and delta_forte >= LIMIAR_REL_FORTE * desvio_atraso:
                mudou_forte = True
        if len(recente) >= AMOSTRA_MINIMA_TENDENCIA:
            min_atraso_recente = int(recente["atraso"].min())
            max_atraso_recente = int(recente["atraso"].max())

        # --- sinal leve: mesmo mês, ano a ano, sem gatilho (só informativo) ---
        leve_delta = None
        leve_n_meses = 0
        if n_pagos_uteis >= 6:
            mensal = g.groupby(g["Data de vencimento"].dt.to_period("M"))["atraso"].mean()
            deltas = []
            for periodo, valor in mensal.items():
                anterior = periodo - 12
                if anterior in mensal.index:
                    deltas.append(valor - mensal[anterior])
            if len(deltas) >= 4:
                leve_delta = float(np.mean(deltas))
                leve_n_meses = len(deltas)

        # série mensal (p/ gráficos) -- inclui meses sazonais, marcados à parte
        serie_mensal = []
        if n_pagos > 0:
            mensal_full = g_full.groupby(g_full["Data de vencimento"].dt.to_period("M")).agg(
                media=("atraso", "mean"), n=("atraso", "size")
            )
            for periodo, row in mensal_full.iterrows():
                serie_mensal.append({
                    "mes": str(periodo),
                    "media": round(float(row["media"]), 1),
                    "n": int(row["n"]),
                    "sazonal": int(periodo.month) in meses_sazonais,
                    "fora_padrao": bool(mudou_forte and periodo >= corte.to_period("M")),
                })

        out[int(cod)] = {
            "n_titulos_pagos": n_pagos,
            "n_titulos_pagos_uteis": n_pagos_uteis,
            "meses_sazonais": meses_sazonais,
            "media_atraso_sazonal": media_atraso_sazonal,
            "media_atraso": media_atraso,
            "desvio_atraso": desvio_atraso,
            "min_atraso": min_atraso,
            "max_atraso": max_atraso,
            "mudou_forte": mudou_forte,
            "media_antiga": media_antiga,
            "media_recente": media_recente,
            "delta_forte": delta_forte,
            "min_atraso_recente": min_atraso_recente,
            "max_atraso_recente": max_atraso_recente,
            "leve_delta": leve_delta,
            "leve_n_meses": leve_n_meses,
            "corte_tendencia": corte,
            "serie_mensal": serie_mensal,
        }
    return out


def atraso_esperado(comp: dict) -> tuple:
    """
    Dado o dict de comportamento de UM cliente (saída de calcular_comportamento_clientes),
    devolve (dias_esperado, dia_bom, dia_ruim, origem) a usar para projetar pagamento:

    - Cliente em mudança forte (piorou de verdade, recente): usa o comportamento RECENTE
      (média/min/max dos últimos JANELA_TENDENCIA_DIAS dias), não a média de 2 anos --
      senão projeta um cliente que não existe mais.
    - Caso contrário: usa o histórico completo (sem os meses sazonais).

    dia_bom = mais rápido que ele já pagou nessa janela; dia_ruim = mais devagar.
    """
    if comp["mudou_forte"] and comp["media_recente"] is not None:
        dias = comp["media_recente"]
        bom = comp["min_atraso_recente"] if comp["min_atraso_recente"] is not None else comp["min_atraso"]
        ruim = comp["max_atraso_recente"] if comp["max_atraso_recente"] is not None else comp["max_atraso"]
        origem = "recente"
    else:
        dias = comp["media_atraso"]
        bom = comp["min_atraso"]
        ruim = comp["max_atraso"]
        origem = "historico"
    return dias, bom, ruim, origem


def calcular_tier(dias_vencido_max, media_atraso, max_atraso) -> str:
    """Mesma classificação usada na tela Hoje: 'inedito' (nunca atrasou tanto),
    'acima_normal' (acima da média dele, mas já visto), 'dentro_padrao' ou
    'sem_historico'. Compartilhado para Hoje e Régua nunca divergirem."""
    if media_atraso is None:
        return "sem_historico"
    if dias_vencido_max > max_atraso:
        return "inedito"
    if dias_vencido_max > media_atraso:
        return "acima_normal"
    return "dentro_padrao"


# ---------------------------------------------------------------------------
# Registro de cobranças feito na Central (nunca escrito na Base_bruta.xlsx)
# ---------------------------------------------------------------------------
REGISTROS_SCHEMA_COLS = [
    "codigo_cliente", "nome_cliente", "data_hora", "canal", "tom", "tom_label",
    "titulos", "valor_cobrado_centavos", "texto",
]


def agora_na_base(data_base: pd.Timestamp) -> pd.Timestamp:
    """'Agora', mas na linha do tempo da planilha: a data é sempre a data de
    referência (a base está congelada nela); só a hora:minuto:segundo vem do
    relógio real, para registros no mesmo dia ficarem em ordem entre si.
    Nunca use pd.Timestamp.now() sozinho para registrar algo nesta Central --
    isso nasceria semanas depois da data de referência e quebraria a regra
    das 48 horas."""
    agora_real = pd.Timestamp.now()
    return pd.Timestamp(
        year=data_base.year, month=data_base.month, day=data_base.day,
        hour=agora_real.hour, minute=agora_real.minute, second=agora_real.second,
    )


def carregar_registros(path: Path) -> pd.DataFrame:
    """Lê registros_cobranca.json (histórico de cobranças feitas pela Central).
    Se o arquivo ainda não existe, devolve uma tabela vazia com as colunas certas."""
    import json
    if not path.exists():
        return pd.DataFrame(columns=REGISTROS_SCHEMA_COLS)
    registros = json.loads(path.read_text(encoding="utf-8"))
    if not registros:
        return pd.DataFrame(columns=REGISTROS_SCHEMA_COLS)
    df = pd.DataFrame(registros)
    df["data_hora"] = pd.to_datetime(df["data_hora"])
    return df


def combinar_cobrancas(cobrancas_xlsx: pd.DataFrame, registros: pd.DataFrame) -> pd.DataFrame:
    """Uma única tabela de contatos, juntando o que veio da Base_bruta.xlsx (aba
    Cobranças, 'origem'='planilha') com o que foi registrado na Central
    ('origem'='central'). É essa tabela -- nunca só a da planilha -- que decide
    quem foi cobrado nas últimas 48h."""
    a = cobrancas_xlsx[["Código do cliente", "Data e hora do contato", "Canal", "Tom usado", "valor_centavos"]].copy()
    a = a.rename(columns={
        "Código do cliente": "codigo_cliente", "Data e hora do contato": "data_hora",
        "Canal": "canal", "Tom usado": "tom_label", "valor_centavos": "valor_cobrado_centavos",
    })
    a["origem"] = "planilha"
    a["texto"] = None
    a["titulos"] = None

    if len(registros):
        b = registros[["codigo_cliente", "data_hora", "canal", "tom_label", "valor_cobrado_centavos", "texto", "titulos"]].copy()
        b["origem"] = "central"
    else:
        b = pd.DataFrame(columns=list(a.columns))

    out = pd.concat([a, b], ignore_index=True)
    return out.sort_values("data_hora")


# ---------------------------------------------------------------------------
# Última semana (retrospectivo, antes da data de referência) -- usado pelo
# Relatório da semana. Não existia em nenhuma tela; mora aqui para quem mais
# precisar reusar sem recalcular.
# ---------------------------------------------------------------------------
def calcular_semana_passada(titulos: pd.DataFrame, data_base: pd.Timestamp) -> dict:
    """Janela de 7 dias ANTES da data de referência: de data_base-7 até
    data_base-1 (o próprio dia de referência fica de fora). 'fim' é o último
    dia incluído, para o texto não anunciar um dia que a conta não usa."""
    inicio = data_base - pd.Timedelta(days=7)
    venceu_na_semana = titulos[(titulos["Data de vencimento"] >= inicio) & (titulos["Data de vencimento"] < data_base)]
    previsto = int(venceu_na_semana["valor_centavos"].sum())

    pago_na_semana = titulos[(titulos["Data de pagamento"] >= inicio) & (titulos["Data de pagamento"] < data_base)]
    entrou = int(pago_na_semana["valor_centavos"].sum())

    venceu_e_nao_pagou = venceu_na_semana[venceu_na_semana["Data de pagamento"].isna()]
    nao_entrou_do_previsto = int(venceu_e_nao_pagou["valor_centavos"].sum())

    return {
        "inicio": inicio, "fim": data_base - pd.Timedelta(days=1),
        "previsto_centavos": previsto,
        "entrou_centavos": entrou,
        "nao_entrou_do_previsto_centavos": nao_entrou_do_previsto,
        "qtd_previsto": int(len(venceu_na_semana)),
        "qtd_pago": int(len(pago_na_semana)),
    }


# ---------------------------------------------------------------------------
# Tons da Régua de cobrança -- a ESCOLHA do tom é um número como outro
# qualquer (sai daqui, determinística, auditável). A REDAÇÃO do texto a
# partir do tom escolhido é isolada à parte (motor de redação, em JS na
# Régua e em redator_relatorio.py no Relatório) -- é o ponto único a trocar
# no dia em que um modelo de IA assumir a redação.
# ---------------------------------------------------------------------------
TONS = {
    "comercial_antes_financeiro": "Comercial, antes do financeiro",
    "lembrete_leve_prazo": "Lembrete leve + ajuste de prazo",
    "conversa_nao_ameaca": "Conversa, não ameaça",
    "alerta_cuidadoso_grande": "Alerta cuidadoso (cliente grande)",
    "atraso_inedito": "Atraso inédito",
    "cobranca_padrao": "Cobrança padrão",
}


def escolher_tom(tier: str, mudou_forte: bool, casos_especiais: list, share_faturamento_12m: float) -> tuple:
    """Decide o tom a partir dos números -- nunca da opinião de quem está lendo.
    Devolve (tom_id, justificativa). Ordem de prioridade: parar de comprar >
    atraso crônico confiável > piora real > atraso inédito em cliente grande >
    atraso inédito > padrão."""
    if "comprando_menos" in casos_especiais or "caro_silencioso" in casos_especiais:
        return "comercial_antes_financeiro", (
            "O sinal mais forte aqui não é o atraso, é a compra caindo (ou parada). "
            "Cobrar título agora sem entender o motivo comercial coloca a conversa errada na frente."
        )
    if "falso_positivo_cronico" in casos_especiais:
        return "lembrete_leve_prazo", (
            "Esse cliente paga sempre com o mesmo atraso, há muito tempo, sem exceção. "
            "Cobrar como se fosse um problema novo seria cobrar à toa dos dois lados."
        )
    if mudou_forte:
        return "conversa_nao_ameaca", (
            "O comportamento dele mudou de verdade e recentemente. Isso pede uma conversa para entender "
            "o motivo, não uma régua de cobrança padrão."
        )
    if tier == "inedito" and share_faturamento_12m >= 10:
        return "alerta_cuidadoso_grande", (
            f"O atraso é inédito para esse cliente, e ele representa {fmt_dec(share_faturamento_12m)}% do "
            f"faturamento da Aurora — vale o cuidado extra de uma relação grande."
        )
    if tier == "inedito":
        return "atraso_inedito", "Esse atraso nunca tinha acontecido com esse cliente antes."
    return "cobranca_padrao", "Atraso dentro do que já aconteceu com esse cliente antes — cobrança direta, sem drama."
