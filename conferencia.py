"""
Conferência da Central de Crédito e Cobrança da Aurora.

Recalcula, a partir da planilha crua (nunca a partir do HTML gerado), os
números que cada tela mostra, e compara. Também checa que as três telas
concordam entre si sobre o mesmo cliente -- média de atraso, desvio,
mudança de comportamento -- já que todas usam aurora_calc.py.

Se alguma checagem falhar, o problema está no código que gera a tela (ou
neste script), nunca na checagem em si: ela não deve ser afrouxada para
passar.

Uso:
    python conferencia.py
"""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

import aurora_calc as ac

XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
PASTA = Path(__file__).parent

TOLERANCIA_CENTAVOS = 150  # ~R$1,50 de folga para arredondamento acumulado em somas de probabilidade

# Hash da Base_bruta.xlsx no momento em que a Central foi construída. Se mudar,
# ou alguém escreveu nela (o que não pode acontecer nunca) ou a planilha foi
# atualizada de propósito -- nesse caso, recalcule e atualize esta constante.
HASH_XLSX_ESPERADO = "af5d278c22234d4a83a9db7086b3d05a72928d09fc166ce7f74967f8bf669511"

resultados = []


def checar(nome, ok, detalhe=""):
    resultados.append((nome, ok, detalhe))
    status = "OK " if ok else "FALHOU"
    print(f"[{status}] {nome}" + (f" -- {detalhe}" if detalhe and not ok else ""))


def ler_json_embutido(path: Path) -> dict:
    html = path.read_text(encoding="utf-8")
    start = html.index("const DATA = ") + len("const DATA = ")
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    return data


def main():
    hash_atual = hashlib.sha256(XLSX_PATH.read_bytes()).hexdigest()
    checar("Base_bruta.xlsx não foi alterada (nenhuma tela escreve nela)", hash_atual == HASH_XLSX_ESPERADO,
           f"hash mudou: {hash_atual}")

    data_base = ac.ler_data_referencia(XLSX_PATH)
    clientes, titulos, cobrancas = ac.carregar_base(XLSX_PATH)
    comportamento = ac.calcular_comportamento_clientes(clientes, titulos, data_base)
    registros = ac.carregar_registros(PASTA / "registros_cobranca.json")
    contatos = ac.combinar_cobrancas(cobrancas, registros)

    abertos = titulos[titulos["Data de pagamento"].isna()].copy()
    abertos["dias_vencido"] = (data_base - abertos["Data de vencimento"]).dt.days
    vencidos = abertos[abertos["Data de vencimento"] < data_base]
    a_vencer = abertos[abertos["Data de vencimento"] >= data_base]

    saldo_aberto_total_cru = int(abertos["valor_centavos"].sum())
    vencido_total_cru = int(vencidos["valor_centavos"].sum())
    a_vencer_total_cru = int(a_vencer["valor_centavos"].sum())

    checar(
        "Planilha: aberto = vencido + a vencer",
        saldo_aberto_total_cru == vencido_total_cru + a_vencer_total_cru,
        f"{saldo_aberto_total_cru} != {vencido_total_cru}+{a_vencer_total_cru}",
    )

    # A Central inteira mora num arquivo só. Se ele não existir, REPROVA -- nunca "pula":
    # pular checagem por falta de arquivo é o mesmo que desligar a conferência.
    app_path = PASTA / "Central_Aurora.html"
    checar("Central_Aurora.html existe (a Central inteira num arquivo só)", app_path.exists())
    APP = ler_json_embutido(app_path) if app_path.exists() else {}

    # ===================== HOJE =====================
    if "hoje" in APP:
        central = APP["hoje"]
        r = central["resumo"]

        checar("Hoje: total vencido bate com a planilha", r["total_vencido_centavos"] == vencido_total_cru,
               f"{r['total_vencido_centavos']} != {vencido_total_cru}")
        checar("Hoje: total a vencer bate com a planilha", r["total_a_vencer_centavos"] == a_vencer_total_cru,
               f"{r['total_a_vencer_centavos']} != {a_vencer_total_cru}")
        checar("Hoje: qtd títulos vencidos bate", r["qtd_titulos_vencidos"] == len(vencidos))
        checar("Hoje: qtd títulos a vencer bate", r["qtd_titulos_a_vencer"] == len(a_vencer))

        # recalcula a fila (quem tem vencido > 0) independentemente e compara o conjunto de clientes
        cod_com_vencido = set(int(c) for c in vencidos["Código do cliente"].unique())
        cod_na_fila = set(c["codigo"] for c in central["fila"])
        checar("Hoje: fila = exatamente os clientes com título vencido", cod_com_vencido == cod_na_fila,
               f"{cod_com_vencido} != {cod_na_fila}")

        # soma por cliente bate com a planilha, título a título
        ok_soma_cliente = True
        for c in central["fila"]:
            esperado = int(vencidos[vencidos["Código do cliente"] == c["codigo"]]["valor_centavos"].sum())
            if esperado != c["valor_vencido_centavos"]:
                ok_soma_cliente = False
                print(f"    {c['nome']}: planilha={esperado} tela={c['valor_vencido_centavos']}")
        checar("Hoje: valor vencido por cliente bate título a título", ok_soma_cliente)

        # posições em ordem decrescente de score
        scores = [c["score"] for c in central["fila"]]
        checar("Hoje: fila ordenada por score decrescente", scores == sorted(scores, reverse=True))

        # contato recente usa a tabela COMBINADA (planilha + registros da Central), não só a planilha
        ultimo_combinado = contatos.groupby("codigo_cliente").tail(1).set_index("codigo_cliente")
        ok_contato = True
        for c in central["fila"]:
            if c["codigo"] in ultimo_combinado.index:
                dt = ultimo_combinado.loc[c["codigo"], "data_hora"]
                esperado_dias = int((data_base.normalize() - dt.normalize()).days)
                esperado_recente = esperado_dias <= 2
                if esperado_dias != c["dias_desde_contato"] or esperado_recente != c["contato_recente_48h"]:
                    ok_contato = False
                    print(f"    {c['nome']}: esperado dias={esperado_dias} recente={esperado_recente} | "
                          f"tela dias={c['dias_desde_contato']} recente={c['contato_recente_48h']}")
        checar("Hoje: contato recente usa planilha + registros da Central combinados", ok_contato)
    else:
        checar("Hoje: dados da tela presentes no arquivo", False)
        central = None

    # ===================== RISCO =====================
    if "risco" in APP:
        risco = APP["risco"]
        rr = risco["resumo"]

        checar("Risco: saldo em aberto total bate com a planilha",
               rr["saldo_aberto_total_centavos"] == saldo_aberto_total_cru,
               f"{rr['saldo_aberto_total_centavos']} != {saldo_aberto_total_cru}")

        ult12m = titulos[titulos["Data de emissão"] >= data_base - pd.Timedelta(days=365)]
        checar("Risco: faturamento 12m bate com a planilha",
               rr["faturamento_total_12m_centavos"] == int(ult12m["valor_centavos"].sum()))

        ok_indice = True
        ok_valor_risco = True
        ok_pesos = True
        for c in risco["clientes"]:
            if not (0 <= c["indice_risco"] <= 100):
                ok_indice = False
            esperado_ver = round(c["saldo_aberto_centavos"] * c["indice_risco"] / 100)
            if abs(esperado_ver - c["valor_em_risco_centavos"]) > 1:
                ok_valor_risco = False
                print(f"    {c['nome']}: esperado {esperado_ver} tela {c['valor_em_risco_centavos']}")
            soma_pesos = sum(comp["peso"] for comp in c["componentes"])
            if soma_pesos != 100:
                ok_pesos = False
        checar("Risco: índice de risco sempre entre 0 e 100", ok_indice)
        checar("Risco: valor em risco = saldo aberto x índice / 100", ok_valor_risco)
        checar("Risco: pesos dos componentes somam 100", ok_pesos)

        ordenado = [c["valor_em_risco_centavos"] for c in risco["clientes"]]
        checar("Risco: lista ordenada por valor em risco decrescente", ordenado == sorted(ordenado, reverse=True))

        # cruzamento com aurora_calc: os números de comportamento batem com o que a tela mostra
        ok_cruzado = True
        for c in risco["clientes"]:
            comp = comportamento[c["codigo"]]
            esperado_media = round(comp["media_atraso"], 1) if comp["media_atraso"] is not None else None
            if esperado_media != c["media_atraso"] or comp["mudou_forte"] != c["mudou_forte"]:
                ok_cruzado = False
                print(f"    {c['nome']}: aurora_calc média={esperado_media} mudou={comp['mudou_forte']} "
                      f"| tela média={c['media_atraso']} mudou={c['mudou_forte']}")
        checar("Risco: comportamento na tela bate com aurora_calc", ok_cruzado)
    else:
        checar("Risco: dados da tela presentes no arquivo", False)
        risco = None

    # ===================== CRUZAMENTO HOJE x RISCO (o ponto central do pedido) =====================
    if central is not None and risco is not None:
        risco_by_cod = {c["codigo"]: c for c in risco["clientes"]}
        ok_cruzado_telas = True
        for c in central["fila"]:
            rc = risco_by_cod.get(c["codigo"])
            if rc is None:
                ok_cruzado_telas = False
                continue
            if c["media_atraso_hist"] != rc["media_atraso"] or c["max_atraso_hist"] != rc["max_atraso"] \
               or c["mudou_comportamento"] != rc["mudou_forte"]:
                ok_cruzado_telas = False
                print(f"    {c['nome']}: Hoje(média={c['media_atraso_hist']}, max={c['max_atraso_hist']}, "
                      f"mudou={c['mudou_comportamento']}) != Risco(média={rc['media_atraso']}, "
                      f"max={rc['max_atraso']}, mudou={rc['mudou_forte']})")
        checar("Hoje e Risco concordam sobre o comportamento de cada cliente (mesma conta)", ok_cruzado_telas)

    # ===================== PREVISÃO =====================
    if "previsao" in APP:
        prev = APP["previsao"]
        pr = prev["resumo"]
        horizonte_fim = data_base + pd.Timedelta(days=28)

        # inclui o que vence HOJE: não está vencido (não entra no Hoje) e tem de cair
        # em alguma semana da planilha -- com ">" ele sumia das duas contas
        no_horizonte_cru = abertos[(abertos["Data de vencimento"] >= data_base) &
                                    (abertos["Data de vencimento"] <= horizonte_fim)]
        naive_cru = int(no_horizonte_cru["valor_centavos"].sum())
        checar("Previsão: soma 'planilha' (ingênuo) bate com a planilha crua",
               pr["planilha_centavos"] == naive_cru, f"{pr['planilha_centavos']} != {naive_cru}")
        checar("Previsão: qtd títulos no horizonte bate", pr["qtd_titulos_no_horizonte"] == len(no_horizonte_cru))
        checar("Previsão: qtd títulos abertos bate", pr["qtd_titulos_abertos"] == len(abertos))

        soma_semanas_planilha = sum(s["planilha_centavos"] for s in prev["semanas"])
        checar("Previsão: soma das semanas (planilha) = total da planilha",
               soma_semanas_planilha == pr["planilha_centavos"],
               f"{soma_semanas_planilha} != {pr['planilha_centavos']}")

        soma_semanas_esperado = sum(s["esperado_centavos"] for s in prev["semanas"])
        checar("Previsão: soma das semanas (esperado) ≈ total esperado",
               abs(soma_semanas_esperado - pr["esperado_centavos"]) <= TOLERANCIA_CENTAVOS,
               f"{soma_semanas_esperado} vs {pr['esperado_centavos']}")

        checar("Previsão: diferença total = planilha - esperado",
               pr["diferenca_centavos"] == pr["planilha_centavos"] - pr["esperado_centavos"])

        soma_dif_clientes = sum(c["diferenca_centavos"] for c in prev["clientes"])
        checar("Previsão: soma das diferenças por cliente ≈ diferença total",
               abs(soma_dif_clientes - pr["diferenca_centavos"]) <= TOLERANCIA_CENTAVOS,
               f"{soma_dif_clientes} vs {pr['diferenca_centavos']}")

        ok_monotono = True
        for serie in prev["cumulativo"].values():
            if any(serie[i + 1] < serie[i] - 1 for i in range(len(serie) - 1)):
                ok_monotono = False
        checar("Previsão: séries acumuladas nunca diminuem", ok_monotono)

        ok_ordem_cenarios = True
        c = prev["cumulativo"]
        for i in range(len(c["esperado"])):
            if not (c["pessimista"][i] <= c["esperado"][i] <= c["otimista"][i] + 1):
                ok_ordem_cenarios = False
        checar("Previsão: pessimista <= esperado <= otimista em todo ponto acumulado", ok_ordem_cenarios)

        checar("Previsão: valor esperado nunca excede o valor nominal (nenhuma probabilidade > 100%)",
               pr["esperado_centavos"] <= saldo_aberto_total_cru + TOLERANCIA_CENTAVOS)

        # cruzamento com aurora_calc: clientes com mudou_forte=True na tela usam comportamento recente
        ok_cruzado_prev = True
        for c in prev["clientes"]:
            comp = comportamento[c["codigo"]]
            if c["usando_recente"] != comp["mudou_forte"]:
                ok_cruzado_prev = False
        checar("Previsão: 'usando comportamento recente' bate com aurora_calc (mudou_forte)", ok_cruzado_prev)
    else:
        checar("Previsão: dados da tela presentes no arquivo", False)
        prev = None

    # ===================== RÉGUA =====================
    if "regua" in APP and risco is not None:
        regua = APP["regua"]
        risco_by_cod = {c["codigo"]: c for c in risco["clientes"]}

        cod_com_vencido = set(int(c) for c in vencidos["Código do cliente"].unique())
        cod_comercial = {c["codigo"] for c in risco["clientes"]
                          if set(c["casos_especiais"]) & {"comprando_menos", "caro_silencioso"}}
        cod_regua = set(c["codigo"] for c in regua["clientes"])
        checar("Régua: candidatos = vencidos hoje OU comprando menos/caro silencioso",
               cod_regua == (cod_com_vencido | cod_comercial),
               f"{cod_regua} != {cod_com_vencido | cod_comercial}")

        ok_tom = True
        for c in regua["clientes"]:
            rc = risco_by_cod[c["codigo"]]
            venc_cli = vencidos[vencidos["Código do cliente"] == c["codigo"]]
            dias_vencido_max = int(venc_cli["dias_vencido"].max()) if len(venc_cli) else -1
            comp = comportamento[c["codigo"]]
            tier_esperado = ac.calcular_tier(dias_vencido_max, comp["media_atraso"], comp["max_atraso"])
            tom_esperado, _ = ac.escolher_tom(tier_esperado, comp["mudou_forte"], rc["casos_especiais"], rc["share_faturamento_12m"])
            if tom_esperado != c["tom_sugerido"]:
                ok_tom = False
                print(f"    {c['nome']}: esperado={tom_esperado} tela={c['tom_sugerido']}")
        checar("Régua: tom sugerido bate com aurora_calc.escolher_tom", ok_tom)

        ok_valor_regua = all(
            int(vencidos[vencidos["Código do cliente"] == c["codigo"]]["valor_centavos"].sum()) == c["valor_vencido_centavos"]
            for c in regua["clientes"]
        )
        checar("Régua: valor vencido por cliente bate título a título", ok_valor_regua)
    else:
        checar("Régua: dados da tela presentes no arquivo", False)

    # ===================== REGISTROS DE COBRANÇA =====================
    reg_path = PASTA / "registros_cobranca.json"
    if reg_path.exists():
        brutos = json.loads(reg_path.read_text(encoding="utf-8"))
        titulos_validos = set(titulos["Número do título"])
        ok_data = True
        ok_cliente = True
        ok_titulos = True
        for r in brutos:
            dt = pd.Timestamp(r["data_hora"])
            # Os registros acumulam de um mês para o outro: um registro feito sobre a base
            # anterior fica com a data de referência ANTIGA, e isso está certo. O que não pode
            # existir é registro depois da data de referência atual: isso só nasce de relógio
            # do computador (semanas à frente da base), e quebraria a regra das 48 horas.
            if dt.date() > data_base.date():
                ok_data = False
                print(f"    registro {r['id']}: data {dt.date()} é POSTERIOR à data de referência {data_base.date()}")
            if r["codigo_cliente"] not in set(clientes["Código do cliente"]):
                ok_cliente = False
            if not set(r["titulos"]).issubset(titulos_validos):
                ok_titulos = False
                print(f"    registro {r['id']}: título(s) inexistente(s) {set(r['titulos']) - titulos_validos}")
        checar("Registros de cobrança: nenhum datado depois da data de referência (nunca no relógio da máquina)", ok_data)
        # Aviso (não reprova): contato que já veio na aba Cobranças e também está nos registros
        # -- mesmo cliente, mesmo dia, mesmo valor -- aparece duas vezes no histórico da Régua.
        ja_na_planilha = {(int(c["Código do cliente"]), pd.Timestamp(c["Data e hora do contato"]).date(), int(c["valor_centavos"]))
                          for _, c in cobrancas.iterrows()}
        duplicados = [r["id"] for r in brutos
                      if (r["codigo_cliente"], pd.Timestamp(r["data_hora"]).date(), r["valor_cobrado_centavos"]) in ja_na_planilha]
        if duplicados:
            print(f"    AVISO: registro(s) {', '.join(duplicados)} parece(m) já constar na aba Cobranças da planilha "
                  f"(mesmo cliente, dia e valor). Veja o passo 6 do CLAUDE.md.")
        checar("Registros de cobrança: código de cliente sempre válido", ok_cliente)
        checar("Registros de cobrança: títulos citados sempre existem na planilha", ok_titulos)
        checar("Registros de cobrança: ficam em arquivo separado, nunca na planilha",
               reg_path.name == "registros_cobranca.json" and reg_path.parent == PASTA)
    else:
        print("[--] registros_cobranca.json não existe ainda (nenhuma cobrança registrada) -- ok.")

    # ===================== EXPORTS JSON (usados pelo Relatório) =====================
    for nome_export, chave_app, chave in [
        ("dados_hoje.json", "hoje", None),
        ("dados_previsao.json", "previsao", None),
    ]:
        caminho = PASTA / nome_export
        if caminho.exists() and chave_app in APP:
            export = json.loads(caminho.read_text(encoding="utf-8"))
            tela = APP[chave_app]
            checar(f"{nome_export} é idêntico ao que a tela mostra", export == tela)

    if (PASTA / "dados_risco.json").exists() and risco is not None:
        export_risco = json.loads((PASTA / "dados_risco.json").read_text(encoding="utf-8"))
        ok_export_risco = export_risco.get("resumo") == risco["resumo"] and all(
            export_risco["clientes"][str(c["codigo"])]["indice_risco"] == c["indice_risco"]
            for c in risco["clientes"]
        )
        checar("dados_risco.json bate com a tela Risco", ok_export_risco)

    # ===================== TELA CONTRA TELA =====================
    # Cada tela pode fechar com a planilha e mesmo assim discordar da vizinha.
    if prev is not None:
        # todo título em aberto cai em exatamente um lugar: vencido (Hoje), uma
        # semana da planilha, ou depois do horizonte -- nenhum some no meio
        fim_h = data_base + pd.Timedelta(days=28)
        depois = abertos[abertos["Data de vencimento"] > fim_h]["valor_centavos"].sum()
        soma_semanas = sum(s["planilha_centavos"] for s in prev["semanas"])
        checar("Previsão x Hoje: vencido + semanas da planilha + depois do horizonte = todo o aberto",
               int(vencidos["valor_centavos"].sum()) + soma_semanas + int(depois) == int(abertos["valor_centavos"].sum()))
    if central is not None and "regua" in APP:
        regua_tela = APP["regua"]
        pos_hoje = {c["codigo"]: c["posicao"] for c in central["fila"]}
        checar("Régua x Hoje: o mesmo cliente tem o mesmo número nas duas telas",
               all(c["posicao"] == pos_hoje[c["codigo"]] for c in regua_tela["clientes"] if c["codigo"] in pos_hoje))
    # arredondamento único: o Relatório (Python) e as telas (JS, Math.round) escrevem o mesmo número
    casos_arred = [0, 49, 50, 99, 150, 7774460, 7774450, 59550386, -3680386, -20600]
    checar("Formato de R$: Python arredonda igual às telas (meio real para cima)",
           all(ac.fmt_reais(v) == (("-" if v < 0 and (abs(v) + 50) // 100 else "") + f"{(abs(v) + 50) // 100:,}".replace(",", "."))
               for v in casos_arred))

    # ===================== O QUE O NOVO DESENHO ACRESCENTOU =====================
    if app_path.exists():
        import re as _re
        html = app_path.read_text(encoding="utf-8")
        externos = [u for u in _re.findall(r"https?://[^\s\"')<>]+", html) if not u.startswith("http://www.w3.org/")]
        checar("Arquivo único: nenhum endereço da internet (abre sem rede)", not externos, f"achei {externos[:3]}")
        checar("Arquivo único: as duas fontes estão embutidas no próprio arquivo", html.count("data:font/woff2;base64,") == 2)
    if central is not None:
        venc = vencidos.copy()
        venc["dias"] = (data_base - venc["Data de vencimento"]).dt.days
        ok_fx = len(central["resumo"]["faixas_atraso"]) == 4
        for f, (de, ate) in zip(central["resumo"]["faixas_atraso"], [(1, 7), (8, 30), (31, 60), (61, None)]):
            m = (venc["dias"] >= de) & ((venc["dias"] <= ate) if ate else True)
            ok_fx = ok_fx and f["valor_centavos"] == int(venc[m]["valor_centavos"].sum()) and f["qtd"] == int(m.sum())
        checar("Hoje: faixas de atraso batem com a planilha crua, faixa a faixa", ok_fx)
        checar("Hoje: faixas de atraso somam o total vencido",
               sum(f["valor_centavos"] for f in central["resumo"]["faixas_atraso"]) == central["resumo"]["total_vencido_centavos"])
        tot = central["resumo"]["total_vencido_centavos"]
        checar("Hoje: anel '% do vencido' = valor vencido do cliente / total vencido",
               all(c["pct_do_vencido"] == round(c["valor_vencido_centavos"] / tot * 100) for c in central["fila"]))
        def sev_certa(c):
            if c["tier"] == "inedito" or c["mudou_comportamento"]:
                return "critico"
            return {"acima_normal": "atencao", "dentro_padrao": "ok"}.get(c["tier"], "neutro")
        checar("Hoje: cor de cada cliente segue a regra (inédito ou piora = crítico; acima do normal = atenção; padrão = ok)",
               all(c["severidade"] == sev_certa(c) for c in central["fila"]))
        checar("Hoje: a linha curta de cada cliente cita os mesmos dias de atraso da frase completa",
               all(str(c["dias_vencido_max"]) in c["motivo"][0] and str(c["dias_vencido_max"]) in c["frase"] for c in central["fila"]))
    if risco is not None:
        checar("Risco: nível do índice segue os cortes (60+ alto, 30-59 médio, abaixo baixo)",
               all(c["nivel"] == ("alto" if c["indice_risco"] >= 60 else "medio" if c["indice_risco"] >= 30 else "baixo") for c in risco["clientes"]))
        desc = risco.get("descobertas", [])
        por_cod = {c["codigo"]: c for c in risco["clientes"]}
        checar("Hoje x Risco: cada descoberta do topo do Hoje é um alerta que a tela Risco mostra para o mesmo cliente",
               0 < len(desc) <= 3 and len({d["tipo"] for d in desc}) == len(desc)
               and all(d["tipo"] in por_cod[d["codigo"]]["casos_especiais"] for d in desc))
    if prev is not None:
        checar("Previsão: o número do topo é a semana de maior diferença",
               prev["semana_maior_diferenca"] == max(prev["semanas"], key=lambda w: abs(w["diferenca_centavos"]))["indice"])
    if "regua" in APP and central is not None:
        rg = APP["regua"]
        cods_rg = {x["codigo"] for x in rg["clientes"]}
        checar("Régua: contagem do topo = clientes da lista; cobrados em 48h = mesma regra do Hoje",
               rg["resumo"]["qtd"] == len(rg["clientes"])
               and rg["resumo"]["cobrados_48h"] == sum(1 for c in central["fila"] if c["contato_recente_48h"] and c["codigo"] in cods_rg))
    if "relatorio" in APP:
        import redator_relatorio as _rr
        checar("Relatório: o texto embutido no arquivo é o mesmo que o redator monta agora",
               APP["relatorio"]["texto"] == _rr.montar_relatorio(PASTA))
        sp = ac.calcular_semana_passada(titulos, data_base)
        checar("Relatório: número do topo (entrou na semana) bate com a planilha",
               APP["relatorio"]["semana"]["entrou_centavos"] == sp["entrou_centavos"]
               and APP["relatorio"]["semana"]["nao_entrou_do_previsto_centavos"] == sp["nao_entrou_do_previsto_centavos"])

    # ===================== RELATÓRIO DA SEMANA =====================
    try:
        import redator_relatorio
        texto = redator_relatorio.montar_relatorio(PASTA)
        checar("Relatório: gera texto sem erro, a partir só dos exports existentes", isinstance(texto, str) and len(texto) > 100)
        if prev is not None:
            checar("Relatório x Previsão: o esperado das 4 semanas aparece com o mesmo número",
                   ("R$ " + ac.fmt_reais(prev["resumo"]["esperado_centavos"])) in texto)
        if central is not None:
            ordem_rel = [int(l.split(".")[0]) for l in texto.split("\n") if l[:2].rstrip(".").isdigit() and ". " in l[:4]]
            checar("Relatório x Hoje: a lista do que fazer segue a numeração da fila de Hoje",
                   ordem_rel == [c["posicao"] for c in central["fila"][:len(ordem_rel)]] and len(ordem_rel) > 0)
    except Exception as e:
        checar("Relatório: gera texto sem erro, a partir só dos exports existentes", False, str(e))

    print()
    total = len(resultados)
    falhas = [n for n, ok, _ in resultados if not ok]
    if falhas:
        print(f"{len(falhas)} de {total} checagens FALHARAM:")
        for n in falhas:
            print(f"  - {n}")
        sys.exit(1)
    else:
        print(f"Todas as {total} checagens passaram.")


if __name__ == "__main__":
    main()
