"""
Calcula a tela "Previsão de caixa" a partir de Base_bruta.xlsx (a tela é montada por build_app.py).

Projeta as próximas 4 semanas da carteira que já existe (nenhuma venda nova).
Usa o MESMO comportamento de pagamento de aurora_calc.py (média/desvio/mudança
de comportamento) que a tela Hoje e a tela Risco usam -- não existe uma conta
paralela aqui. O índice de risco por cliente vem de dados_risco.json, exportado
pelo build_risco.py (rode build_risco.py antes deste script).

Para cada título em aberto:
  1. data prevista de pagamento = vencimento + atraso que o cliente pratica
     (comportamento RECENTE se ele mudou de verdade; histórico completo, sem
     os meses sazonais, caso contrário).
  2. cenário otimista/conservador = mesma conta, usando o dia bom / dia ruim
     (mínimo/máximo de atraso já visto nessa mesma janela).
  3. uma probabilidade de entrada, que cai com o tempo decorrido E com o
     índice de risco do cliente.

O número central da tela é a comparação entre a soma ingênua por vencimento
(o que a planilha mostraria) e a soma esperada lendo o comportamento de cada
cliente.

Uso:
    python build_risco.py        (gera dados_risco.json, se ainda não existir)
    python build_previsao.py
"""

import json
import math
from pathlib import Path

import pandas as pd

import aurora_calc as ac

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
RISCO_JSON_PATH = Path(__file__).parent / "dados_risco.json"
JSON_EXPORT_PATH = Path(__file__).parent / "dados_previsao.json"

# ---------------------------------------------------------------------------
# Parâmetros específicos desta tela (decisões assumidas -- ver relatório)
# ---------------------------------------------------------------------------
N_SEMANAS = 4
DIAS_POR_SEMANA = 7

P_BASE = 0.98              # chance de entrada de um título que vence hoje, cliente sem risco
DECAIMENTO_DIAS = 100       # "meia-vida" aproximada: quanto mais os dias de espera se aproximam
                             # disso, mais a chance cai (decaimento exponencial)
HAIRCUT_MAX_RISCO = 0.5     # um cliente com índice de risco 100 tem sua chance multiplicada por (1-0.5)
P_MIN, P_MAX = 0.05, 0.99


def probabilidade(dias_espera: float, indice_risco: int) -> float:
    dias_espera = max(0.0, dias_espera)
    p_idade = P_BASE * math.exp(-dias_espera / DECAIMENTO_DIAS)
    fator_risco = 1 - (indice_risco / 100) * HAIRCUT_MAX_RISCO
    p = p_idade * fator_risco
    return max(P_MIN, min(P_MAX, p))


def semana_da_data(data: pd.Timestamp, data_base: pd.Timestamp) -> int:
    """1-4 para dentro do horizonte, 0 se já devia ter sido hoje (projeção no passado,
    empurrada para a semana 1), 5 se cai depois das 4 semanas."""
    dias = (data - data_base).days
    if dias <= 0:
        return 1
    semana = (dias - 1) // DIAS_POR_SEMANA + 1
    return semana if semana <= N_SEMANAS else 5


def main():
    data_base = ac.ler_data_referencia(XLSX_PATH)
    clientes, titulos, _cobrancas = ac.carregar_base(XLSX_PATH)
    comportamento = ac.calcular_comportamento_clientes(clientes, titulos, data_base)

    if not RISCO_JSON_PATH.exists():
        raise SystemExit(
            f"Não encontrei {RISCO_JSON_PATH}. Rode 'python build_risco.py' primeiro -- "
            f"a Previsão lê o índice de risco de lá em vez de recalcular."
        )
    dados_risco = json.loads(RISCO_JSON_PATH.read_text(encoding="utf-8"))["clientes"]

    nomes = clientes.set_index("Código do cliente")["Nome do cliente"].to_dict()
    media_geral_carteira = pd.Series(
        [c["media_atraso"] for c in comportamento.values() if c["media_atraso"] is not None]
    ).mean()

    abertos = titulos[titulos["Data de pagamento"].isna()].copy()
    horizonte_fim = data_base + pd.Timedelta(days=N_SEMANAS * DIAS_POR_SEMANA)

    # A semana 1 começa HOJE: título que vence na própria data de referência
    # ainda não está vencido (não entra no "vencido" da tela Hoje) e precisa
    # cair em alguma semana da planilha -- antes ele não caía em nenhuma, mas
    # entrava no esperado, e a comparação ficava torta.
    limites_semana = []
    for k in range(N_SEMANAS):
        ini = data_base + pd.Timedelta(days=k * DIAS_POR_SEMANA + (0 if k == 0 else 1))
        fim = data_base + pd.Timedelta(days=(k + 1) * DIAS_POR_SEMANA)
        limites_semana.append((ini, fim))

    linhas = []
    for _, t in abertos.iterrows():
        cod = int(t["Código do cliente"])
        comp = comportamento[cod]
        indice_risco = dados_risco[str(cod)]["indice_risco"]
        vencimento = t["Data de vencimento"]
        valor = int(t["valor_centavos"])
        dias_vencido_hoje = (data_base - vencimento).days

        dias_esp, dia_bom, dia_ruim, origem = ac.atraso_esperado(comp)
        usando_sazonal = False
        if dias_esp is None:
            dias_esp, dia_bom, dia_ruim = media_geral_carteira, media_geral_carteira, media_geral_carteira
            origem = "fallback_carteira"
        elif (not comp["mudou_forte"]) and vencimento.month in comp["meses_sazonais"]:
            dias_esp = comp["media_atraso_sazonal"][vencimento.month]
            usando_sazonal = True
        dia_bom = min(dia_bom, dias_esp) if dia_bom is not None else dias_esp
        dia_ruim = max(dia_ruim, dias_esp) if dia_ruim is not None else dias_esp

        cenarios = {}
        for nome_cen, dia in (("central", dias_esp), ("otimista", dia_bom), ("pessimista", dia_ruim)):
            data_prevista = vencimento + pd.Timedelta(days=round(dia))
            data_prevista_clampeada = max(data_prevista, data_base + pd.Timedelta(days=1))
            dias_base_prob = max(dia, dias_vencido_hoje, 0)
            p = probabilidade(dias_base_prob, indice_risco)
            cenarios[nome_cen] = {
                "data_prevista": data_prevista_clampeada,
                "semana": semana_da_data(data_prevista_clampeada, data_base),
                "probabilidade": p,
                "valor_esperado_centavos": valor * p,
            }

        linhas.append({
            "codigo": cod, "nome": nomes[cod], "numero": t["Número do título"],
            "valor_centavos": valor, "vencimento": vencimento, "dias_vencido_hoje": dias_vencido_hoje,
            "origem_atraso": origem, "usando_sazonal": usando_sazonal, "dias_esperado": dias_esp,
            "cenarios": cenarios,
            "vence_no_horizonte": data_base <= vencimento <= horizonte_fim,
        })

    df = pd.DataFrame(linhas)

    # ---- (a) ingênuo: planilha somando só por data de vencimento, valor cheio, sem probabilidade ----
    naive_total = int(df.loc[df["vence_no_horizonte"], "valor_centavos"].sum())
    naive_por_semana = []
    for k, (ini, fim) in enumerate(limites_semana, start=1):
        mask = (df["vencimento"] >= ini) & (df["vencimento"] <= fim)
        naive_por_semana.append(int(df.loc[mask, "valor_centavos"].sum()))

    # ---- (b) realista: soma esperada (valor x probabilidade), por data PREVISTA, por cenário ----
    def soma_cenario(nome_cen, semana_filtro=None):
        vals = df["cenarios"].apply(lambda c: c[nome_cen])
        semanas = vals.apply(lambda v: v["semana"])
        esperado = vals.apply(lambda v: v["valor_esperado_centavos"])
        if semana_filtro is None:
            mask = semanas <= N_SEMANAS
        else:
            mask = semanas == semana_filtro
        return float(esperado[mask].sum())

    central_por_semana = [soma_cenario("central", k) for k in range(1, N_SEMANAS + 1)]
    otimista_por_semana = [soma_cenario("otimista", k) for k in range(1, N_SEMANAS + 1)]
    pessimista_por_semana = [soma_cenario("pessimista", k) for k in range(1, N_SEMANAS + 1)]

    central_total = sum(central_por_semana)
    otimista_total = sum(otimista_por_semana)
    pessimista_total = sum(pessimista_por_semana)

    # cumulativo (semana 0 = hoje, valor 0)
    def acumula(serie):
        acc, out = 0.0, [0.0]
        for v in serie:
            acc += v
            out.append(acc)
        return out

    naive_acc = acumula(naive_por_semana)
    central_acc = acumula(central_por_semana)
    otimista_acc = acumula(otimista_por_semana)
    pessimista_acc = acumula(pessimista_por_semana)

    diferenca_total = naive_total - round(central_total)

    # ---- detalhe por cliente, dentro do horizonte (por data prevista central) ----
    clientes_detalhe = []
    for cod in sorted(df["codigo"].unique()):
        sub = df[df["codigo"] == cod]
        naive_cli = int(sub.loc[sub["vence_no_horizonte"], "valor_centavos"].sum())
        esperado_cli = sum(
            c["central"]["valor_esperado_centavos"]
            for c in sub["cenarios"] if c["central"]["semana"] <= N_SEMANAS
        )
        if naive_cli == 0 and esperado_cli == 0:
            continue
        comp = comportamento[cod]
        clientes_detalhe.append({
            "codigo": int(cod), "nome": nomes[cod],
            "naive_centavos": naive_cli,
            "esperado_centavos": round(esperado_cli),
            "diferenca_centavos": naive_cli - round(esperado_cli),
            "indice_risco": dados_risco[str(cod)]["indice_risco"],
            "usando_recente": bool(comp["mudou_forte"]),
            "media_atraso": round(comp["media_atraso"], 1) if comp["media_atraso"] is not None else None,
            "media_recente": round(comp["media_recente"], 1) if comp["media_recente"] is not None else None,
        })
    # "quem puxa a diferença" = quem mais diverge, para um lado ou para o outro
    clientes_detalhe.sort(key=lambda c: abs(c["diferenca_centavos"]), reverse=True)

    semanas_out = []
    for k, (ini, fim) in enumerate(limites_semana):
        semanas_out.append({
            "indice": k + 1,
            "inicio": ini.strftime("%d/%m"),
            "fim": fim.strftime("%d/%m"),
            "planilha_centavos": naive_por_semana[k],
            "esperado_centavos": round(central_por_semana[k]),
            "diferenca_centavos": naive_por_semana[k] - round(central_por_semana[k]),
        })

    payload = {
        "resumo": {
            "data_base": data_base.strftime("%d/%m/%Y"),
            "horizonte_fim": horizonte_fim.strftime("%d/%m/%Y"),
            "planilha_centavos": naive_total,
            "esperado_centavos": round(central_total),
            "otimista_centavos": round(otimista_total),
            "pessimista_centavos": round(pessimista_total),
            "diferenca_centavos": diferenca_total,
            "diferenca_pct": round(diferenca_total / naive_total * 100, 1) if naive_total else None,
            "qtd_titulos_abertos": int(len(df)),
            "qtd_titulos_no_horizonte": int(df["vence_no_horizonte"].sum()),
        },
        "semanas": semanas_out,
        "semana_maior_diferenca": max(semanas_out, key=lambda w: abs(w["diferenca_centavos"]))["indice"],
        "cumulativo": {
            "planilha": [round(v) for v in naive_acc],
            "esperado": [round(v) for v in central_acc],
            "otimista": [round(v) for v in otimista_acc],
            "pessimista": [round(v) for v in pessimista_acc],
        },
        "clientes": clientes_detalhe,
    }


    # Exporta um resumo limpo para o Relatório da semana ler (não recalcular).
    JSON_EXPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK -- {JSON_EXPORT_PATH.name} gerado (Previsão).")
    print(f"  Planilha (ingênuo, 4 semanas):  R$ {naive_total/100:,.0f}")
    print(f"  Esperado (comportamento, 4 semanas): R$ {central_total/100:,.0f}")
    print(f"  Diferença: R$ {diferenca_total/100:,.0f}  ({payload['resumo']['diferenca_pct']}%)")
    print(f"  Cenário otimista: R$ {otimista_total/100:,.0f}  |  pessimista: R$ {pessimista_total/100:,.0f}")
    return payload


if __name__ == "__main__":
    main()
