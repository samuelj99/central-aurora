function fmtReais(centavos) {
  // arredonda para o real mais próximo (estimativa não tem centavo) -- mesma regra de aurora_calc.fmt_reais
  const reais = Math.round(Math.abs(centavos) / 100);
  return (centavos < 0 && reais > 0 ? "−" : "") + "R$ " + reais.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}
function plural(n, s, p) { return n === 1 ? s : p; }

/* ======================================================================
   MOTOR DE REDAÇÃO -- único ponto que transforma números em texto.
   Hoje é tudo gerado aqui, por regra. No dia de trocar por um modelo de
   IA, é aqui (e só aqui) que se troca: a função gerarTexto(cliente, tom,
   canal) é o único contrato que o resto da tela usa.
   ====================================================================== */

function listaTitulosLinhas(cliente) {
  return cliente.titulos_vencidos.map(t =>
    `- ${t.numero}: ${fmtReais(t.valor_centavos)}, venceu em ${t.vencimento} (${t.dias_vencido} ${plural(t.dias_vencido,'dia','dias')} de atraso)`
  ).join("\n");
}

function dias(n) { return n + " " + plural(Math.abs(n), "dia", "dias"); }
function piorTitulo(c) { return c.titulos_vencidos[0]; }   // vem ordenado do mais atrasado para o menos
function atrasoAtualInedito(c) { const p = piorTitulo(c); return !!p && c.max_atraso != null && p.dias_vencido > c.max_atraso; }
function ritmoHabitual(c) { return `costumam pagar por volta de ${dias(Math.round(c.media_atraso))} depois do vencimento`; }
function blocoTitulos(c) {
  const n = c.titulos_vencidos.length;
  return `${listaTitulosLinhas(c)}${n > 1 ? `\n\nTotal: ${fmtReais(c.valor_vencido_centavos)}.` : ""}`;
}

/* Cada tom só afirma o que os números do cliente sustentam: quando o tom é
   trocado na mão para um cliente que não se encaixa nele, a frase muda em vez
   de afirmar uma coisa falsa ("bem mais que o seu ritmo", "maiores parceiros"). */

function corpoComercialAntesFinanceiro(c) {
  const gap = c.gap_tipico_dias ? Math.round(c.gap_tipico_dias) : null;
  let txt;
  if (gap && c.dias_desde_pedido > gap * 1.5) {
    txt = `Faz ${dias(c.dias_desde_pedido)} que não chega um pedido seu aqui, bem mais que o seu ritmo normal de pedir a cada ${dias(gap)}. Antes de falar de boleto, queria entender se está tudo bem do seu lado e se ainda faz sentido a gente continuar junto. Se for só uma fase corrida, sem problema nenhum — só queria saber.`;
  } else if (c.queda_compra_pct != null && c.queda_compra_pct >= 20) {
    txt = `Reparei que os seus pedidos diminuíram nos últimos meses (uns ${Math.round(c.queda_compra_pct)}% a menos que antes). Antes de falar de boleto, queria entender se está tudo bem do seu lado.`;
  } else {
    txt = `Queria saber como andam as coisas por aí e se a Aurora está atendendo bem vocês.`;
  }
  txt += ` E se tiver algo que a gente pode ajustar (prazo, forma de entrega, o que for), me conta — prefiro resolver isso do que só mandar cobrança.`;
  if (c.valor_vencido_centavos > 0) {
    const n = c.titulos_vencidos.length;
    txt += `\n\nSeparado disso, ${n === 1 ? "ficou um título em aberto" : "ficaram alguns títulos em aberto"}:\n${blocoTitulos(c)}\n\nIsso a gente acerta com calma, depois dessa conversa.`;
  }
  return txt;
}

function corpoLembreteLevePrazo(c) {
  const n = c.titulos_vencidos.length;
  let txt = `Passando só para lembrar que ${n === 1 ? "tem 1 título" : `tem ${n} títulos`} em aberto com a gente:\n${blocoTitulos(c)}`;
  if (atrasoAtualInedito(c)) {
    txt += `\n\nVocês ${ritmoHabitual(c)}, e ${n === 1 ? "esse já passou" : "o mais antigo já passou"} disso — por isso estou lembrando.`;
  } else {
    txt += `\n\nSei que vocês ${ritmoHabitual(c)} — então isso provavelmente já está nos seus planos, é só um lembrete mesmo.`;
  }
  if (c.casos_especiais.includes("falso_positivo_cronico")) {
    txt += `\n\nAproveito para jogar uma ideia: como esse já é o seu jeito de pagar há bastante tempo, talvez valha a gente ajustar o prazo combinado no contrato (hoje está em ${dias(c.prazo_contratado_dias)}) para bater com o que acontece de verdade. Assim ninguém perde tempo cobrando, nem sendo cobrado, à toa. Topa conversar sobre isso?`;
  }
  return txt;
}

function corpoConversaNaoAmeaca(c) {
  const n = c.titulos_vencidos.length;
  const abertura = (c.mudou_forte && c.media_antiga != null && c.media_recente != null)
    ? `Reparei que o jeito de pagar de vocês mudou nos últimos meses: até pouco tempo atrás vocês pagavam, em média, ${dias(Math.round(c.media_antiga))} depois do vencimento, e os títulos mais recentes estão levando perto de ${dias(Math.round(c.media_recente))}.`
    : `Reparei que ${n === 1 ? "esse título está levando" : "esses títulos estão levando"} mais tempo que o normal para vocês (vocês ${ritmoHabitual(c)}).`;
  return `${abertura} Hoje ${n === 1 ? "está" : "estão"} em aberto:\n${blocoTitulos(c)}\n\nIsso aqui não é uma cobrança, é uma pergunta mesmo: está passando por alguma dificuldade? Prefiro saber agora e ver como ajudar — um prazo diferente para regularizar, outra solução, o que fizer sentido — do que deixar crescer sem conversar. Me chama quando puder.`;
}

function corpoAlertaCuidadosoGrande(c) {
  const pior = piorTitulo(c);
  const fato = atrasoAtualInedito(c)
    ? `e isso nunca tinha acontecido com vocês (o atraso mais longo até hoje tinha sido de ${dias(c.max_atraso)})`
    : `e isso foge do ritmo de vocês (vocês ${ritmoHabitual(c)})`;
  const relacao = c.share_faturamento_12m >= 10
    ? "Como vocês são um dos nossos maiores parceiros, preferi falar direto com você antes de qualquer outra coisa."
    : "Preferi falar direto com você antes de qualquer outra coisa.";
  return `A gente percebeu algo fora do comum: o título ${pior.numero}, de ${fmtReais(pior.valor_centavos)}, está há ${dias(pior.dias_vencido)} sem pagamento, ${fato}.${c.titulos_vencidos.length > 1 ? `\n\nTambém estão em aberto:\n${blocoTitulos(c)}` : ""}\n\n${relacao} Pode ser um esquecimento, pode ser algo pontual — só queria entender e já resolver junto. Me avisa o que está rolando?`;
}

function corpoAtrasoInedito(c) {
  const n = c.titulos_vencidos.length;
  const abertura = n === 1 ? "O título abaixo está" : "Os títulos abaixo estão";
  const sujeito = n === 1 ? "ele" : "o mais antigo";
  const fato = atrasoAtualInedito(c)
    ? `e ${sujeito} já passou do que costuma acontecer com vocês (o atraso mais longo até hoje tinha sido de ${dias(c.max_atraso)})`
    : `e ${sujeito} já passou do prazo (vocês ${ritmoHabitual(c)})`;
  return `${abertura} em aberto, ${fato}:\n${blocoTitulos(c)}\n\nPode me confirmar se já está encaminhado, ou se precisa de alguma coisa da nossa parte para fechar isso?`;
}

function corpoCobrancaPadrao(c) {
  return `Passando para lembrar que ${c.titulos_vencidos.length === 1 ? "está" : "estão"} em aberto:\n${blocoTitulos(c)}\n\nPode confirmar o pagamento ou me dizer se precisa de algo para regularizar?`;
}

const CORPO_POR_TOM = {
  comercial_antes_financeiro: corpoComercialAntesFinanceiro,
  lembrete_leve_prazo: corpoLembreteLevePrazo,
  conversa_nao_ameaca: corpoConversaNaoAmeaca,
  alerta_cuidadoso_grande: corpoAlertaCuidadosoGrande,
  atraso_inedito: corpoAtrasoInedito,
  cobranca_padrao: corpoCobrancaPadrao,
};

function formatarPorCanal(corpo, cliente, canal) {
  const nome = cliente.contato_primeiro_nome;
  if (canal === "E-mail") {
    const assunto = `Assunto: Aurora · ${cliente.nome} — ${cliente.titulos_vencidos.length > 0 ? 'títulos em aberto' : 'contato'}`;
    return `${assunto}\n\nOi ${nome}, tudo bem?\n\n${corpo}\n\nAbraço,\nTime Aurora`;
  }
  if (canal === "Telefone") {
    const pontos = corpo.split("\n\n").map(p => {
      const linhas = p.split("\n");
      return `• ${linhas[0]}` + linhas.slice(1).map(l => `\n   ${l}`).join("");
    }).join("\n\n");
    return `Roteiro da ligação para ${nome}:\n\n${pontos}\n\n(fale com suas palavras — isto é um guia, não um texto para ler)`;
  }
  // WhatsApp (padrão)
  return `Oi ${nome}, tudo bem?\n\n${corpo}`;
}

function gerarTexto(cliente, tom, canal) {
  const corpo = CORPO_POR_TOM[tom](cliente);
  return formatarPorCanal(corpo, cliente, canal);
}

/* ====================== fim do motor de redação ====================== */

const CANAL_PADRAO_POR_TOM = {
  comercial_antes_financeiro: "Telefone",
  lembrete_leve_prazo: "WhatsApp",
  conversa_nao_ameaca: "WhatsApp",
  alerta_cuidadoso_grande: "Telefone",
  atraso_inedito: "E-mail",
  cobranca_padrao: "WhatsApp",
};

const TAG_CASO = {
  falso_positivo_cronico: "Aparece vencido, não é risco",
  deteriorou: "Piorou de verdade",
  sazonal: "Padrão sazonal",
  comprando_menos: "Comprando menos",
  caro_silencioso: "Caro e silencioso",
};
