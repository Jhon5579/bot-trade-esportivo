# --- gestao_banca.py ---
# Este script contém todas as funções para gerir a nossa banca.

import json

# O nome do nosso ficheiro de banca fica definido aqui
ARQUIVO_GESTAO_BANCA = 'gestao_banca.json'

def carregar_banca():
    """
    Carrega os dados da gestão de banca do ficheiro JSON.
    Se o ficheiro não existir ou estiver inválido, cria um novo com valores padrão.
    """
    try:
        with open(ARQUIVO_GESTAO_BANCA, 'r', encoding='utf-8') as f:
            banca = json.load(f)
        # Garante que o ficheiro tem a estrutura mínima
        if "banca_atual" not in banca:
            raise json.JSONDecodeError("Estrutura do JSON inválida", "", 0)
        return banca
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"  -> ⚠️ AVISO: Ficheiro '{ARQUIVO_GESTAO_BANCA}' não encontrado ou inválido. A criar um novo.")
        banca_padrao = {
            "banca_inicial": 100.0,
            "banca_atual": 100.0,
            "stake_padrao_percentual": 5.0,
            "perda_a_recuperar": 0.0
        }
        # Salva o ficheiro padrão para garantir que ele exista na próxima vez
        salvar_banca(banca_padrao)
        return banca_padrao

def salvar_banca(dados_banca):
    """
    Salva os dados atualizados da gestão de banca no ficheiro JSON.
    """
    with open(ARQUIVO_GESTAO_BANCA, 'w', encoding='utf-8') as f:
        json.dump(dados_banca, f, indent=4, ensure_ascii=False)
    print("  -> 💾 Banca salva com sucesso!")

def calcular_stake(dados_banca):
    """
    Calcula o valor da aposta (stake) com base na percentagem definida.
    """
    percentual = dados_banca.get('stake_padrao_percentual', 5.0) / 100
    stake = dados_banca.get('banca_atual', 0) * percentual
    return round(stake, 2)

def registrar_resultado(aposta, resultado_final, placar_casa, placar_fora):
    """
    Atualiza a banca com base no resultado de uma aposta ('GREEN' ou 'RED')
    e retorna a mensagem formatada para o Telegram.
    """
    banca = carregar_banca()
    lucro_ou_prejuizo = 0
    stake_aposta = aposta.get('stake', 0)
    odd_aposta = aposta.get('odd', 0)

    if resultado_final == "GREEN":
        lucro = stake_aposta * (odd_aposta - 1)
        lucro_ou_prejuizo = lucro
        banca['banca_atual'] += lucro
        banca['perda_a_recuperar'] = 0.0
    else: # RED
        prejuizo = stake_aposta
        lucro_ou_prejuizo = -prejuizo
        banca['banca_atual'] -= prejuizo
        banca['perda_a_recuperar'] += prejuizo

    # Arredonda os valores para evitar problemas com casas decimais
    banca['banca_atual'] = round(banca['banca_atual'], 2)
    banca['perda_a_recuperar'] = round(banca['perda_a_recuperar'], 2)

    salvar_banca(banca)
    print(f"  -> Banca atualizada: Saldo R$ {banca['banca_atual']:.2f}, A recuperar R$ {banca['perda_a_recuperar']:.2f}")

    emoji_resultado = "✅" if resultado_final == "GREEN" else "🔴"
    sinal_lucro = "+" if lucro_ou_prejuizo >= 0 else ""

    linhas_mensagem = [
        f"{emoji_resultado} *RESULTADO DA APOSTA* {emoji_resultado}",
        "",
        f"*⚽ Jogo:* {aposta['nome_jogo']}",
        f"*📈 Mercado:* {aposta['mercado']}",
        f"*🏁 Placar Final:* {placar_casa} x {placar_fora}",
        f"*Resultado:* {resultado_final}",
        "",
        f"*💰 Stake:* R$ {stake_aposta:.2f}",
        f"*📊 Lucro/Prejuízo:* {sinal_lucro}R$ {lucro_ou_prejuizo:.2f}",
        f"*🏦 Saldo Atual:* R$ {banca['banca_atual']:.2f}"
    ]
    return "\n".join(linhas_mensagem)

