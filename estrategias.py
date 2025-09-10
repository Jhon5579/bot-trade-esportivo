# estrategias.py

"""
Este arquivo contém todas as funções de análise (estratégias) do Robô Falcão.
Cada função recebe os dados de um jogo e o contexto (estatísticas históricas),
e retorna um dicionário de oportunidade se os critérios forem atendidos, ou uma
string com o motivo da falha se o modo de depuração estiver ativo.
"""

# --- FUNÇÃO AUXILIAR PARA BUSCAR ODDS ---

def _encontrar_odd_especifica(jogo, mercado_alvo, resultado_alvo, casa_alvo='pinnacle'):
    """
    Função auxiliar para encontrar uma odd específica dentro dos dados do jogo.
    Exemplo de uso: _encontrar_odd_especifica(jogo, 'Match Winner', 'Home')
    Exemplo de uso: _encontrar_odd_especifica(jogo, 'Over/Under', 'Over')
    """
    for bookmaker in jogo.get('bookmakers', []):
        if bookmaker.get('key') == casa_alvo:
            for market in bookmaker.get('markets', []):
                if market.get('key') == mercado_alvo:
                    for outcome in market.get('outcomes', []):
                        if outcome.get('name') == resultado_alvo:
                            return outcome.get('price'), market.get('last_update')
    return None, None

# --- ESTRATÉGIAS DE ANÁLISE ---

def analisar_visitante_fraco(jogo, contexto, debug=False):
    """
    Estratégia: Busca jogos onde um time da casa forte enfrenta um visitante que
    costuma ter um desempenho muito ruim fora de casa.
    Mercado Alvo: Casa para Vencer (Match Winner - Home)
    """
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_individuais = contexto["stats_individuais"]
    
    stats_casa = stats_individuais.get(time_casa, {})
    stats_fora = stats_individuais.get(time_fora, {})

    if not stats_casa or not stats_fora:
        if debug: return "Time sem dados históricos suficientes."
        return None

    # --- CRITÉRIOS DA ESTRATÉGIA ---
    # 1. Time da casa tem um bom percentual de vitória em casa (ex: > 60%)
    # 2. Time visitante tem um alto percentual de derrota fora de casa (ex: > 60%)
    perc_vitorias_casa = stats_casa.get('perc_vitorias_casa', 0)
    perc_derrotas_fora = stats_fora.get('perc_derrotas_fora', 0)

    if perc_vitorias_casa >= 60 and perc_derrotas_fora >= 60:
        # SUCESSO! Critérios atendidos.
        motivo = f"Casa vence {perc_vitorias_casa:.1f}% dos jogos em casa e o Visitante perde {perc_derrotas_fora:.1f}% dos jogos fora."
        
        odd_casa, _ = _encontrar_odd_especifica(jogo, 'h2h', 'Home')

        oportunidade = {
            'type': 'aposta', 'nome_estrategia': 'Visitante Fraco',
            'emoji': ' fortress', 'motivo': motivo,
            'mercado': 'Casa para Vencer', 'odd': odd_casa
        }
        return oportunidade
    else:
        # FALHA! Critérios não atendidos. Retorna o motivo.
        if debug:
            return f"Reprovado. Vitórias Casa: {perc_vitorias_casa:.1f}% (Req: >=60%), Derrotas Fora: {perc_derrotas_fora:.1f}% (Req: >=60%)"
        return None


def analisar_classico_de_gols(jogo, contexto, debug=False):
    """
    Estratégia: Identifica clássicos ou confrontos diretos (H2H) que historicamente
    têm uma alta média de gols.
    Mercado Alvo: Mais de 2.5 Gols (Over/Under 2.5 - Over)
    """
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_h2h = contexto["stats_h2h"]
    
    h2h_key = '|'.join(sorted([time_casa, time_fora]))
    confronto = stats_h2h.get(h2h_key, {})

    if not confronto:
        if debug: return "Sem histórico de confrontos diretos (H2H)."
        return None

    # --- CRITÉRIOS DA ESTRATÉGIA ---
    # 1. Média de gols nos confrontos diretos é alta (ex: > 3.0)
    # 2. Houve um número mínimo de confrontos para a estatística ser relevante (ex: >= 3)
    avg_gols_h2h = confronto.get('avg_gols_h2h', 0)
    total_jogos_h2h = confronto.get('total_jogos_h2h', 0)

    if avg_gols_h2h > 3.0 and total_jogos_h2h >= 3:
        # SUCESSO! Critérios atendidos.
        motivo = f"A média de gols nos últimos {total_jogos_h2h} confrontos diretos é de {avg_gols_h2h:.2f}."
        
        odd_over, _ = _encontrar_odd_especifica(jogo, 'totals', 'Over')

        oportunidade = {
            'type': 'aposta', 'nome_estrategia': 'Clássico de Gols',
            'emoji': '⚽', 'motivo': motivo,
            'mercado': 'Mais de 2.5 Gols', 'odd': odd_over
        }
        return oportunidade
    else:
        # FALHA! Critérios não atendidos. Retorna o motivo.
        if debug:
            return f"Reprovado. Média Gols H2H: {avg_gols_h2h:.2f} (Req: >3.0), Jogos H2H: {total_jogos_h2h} (Req: >=3)"
        return None


def analisar_reacao_gigante(jogo, contexto, debug=False):
    """
    Estratégia: Procura por um time considerado "gigante" (com alto percentual
    de vitórias geral) jogando em casa contra um time nitidamente mais fraco.
    A ideia é apostar na reação ou confirmação do favoritismo do time grande.
    Mercado Alvo: Casa para Vencer (Match Winner - Home)
    """
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_individuais = contexto["stats_individuais"]
    
    stats_casa = stats_individuais.get(time_casa, {})
    stats_fora = stats_individuais.get(time_fora, {})

    if not stats_casa or not stats_fora:
        if debug: return "Time sem dados históricos suficientes."
        return None

    # --- CRITÉRIOS DA ESTRATÉGIA ---
    # 1. Time da casa é um "gigante", com alto % de vitórias geral (ex: > 65%)
    # 2. Time visitante é "azarão", com baixo % de vitórias geral (ex: < 35%)
    # 3. Time da casa tem um bom ataque em casa (ex: média de gols > 1.8)
    vitorias_geral_casa = (stats_casa.get('vitorias_casa', 0) + stats_casa.get('vitorias_fora', 0))
    total_jogos_casa = (stats_casa.get('total_jogos_casa', 0) + stats_casa.get('total_jogos_fora', 0))
    perc_vitorias_geral_casa = (vitorias_geral_casa / total_jogos_casa * 100) if total_jogos_casa > 0 else 0
    
    vitorias_geral_fora = (stats_fora.get('vitorias_casa', 0) + stats_fora.get('vitorias_fora', 0))
    total_jogos_fora = (stats_fora.get('total_jogos_casa', 0) + stats_fora.get('total_jogos_fora', 0))
    perc_vitorias_geral_fora = (vitorias_geral_fora / total_jogos_fora * 100) if total_jogos_fora > 0 else 0
    
    avg_gols_marcados_casa = stats_casa.get('avg_gols_marcados_casa', 0)

    if perc_vitorias_geral_casa > 65 and perc_vitorias_geral_fora < 35 and avg_gols_marcados_casa > 1.8:
        # SUCESSO! Critérios atendidos.
        motivo = f"Gigante ({perc_vitorias_geral_casa:.1f}% vitórias) enfrenta azarão ({perc_vitorias_geral_fora:.1f}% vitórias) e tem média de {avg_gols_marcados_casa:.2f} gols em casa."

        odd_casa, _ = _encontrar_odd_especifica(jogo, 'h2h', 'Home')
        
        oportunidade = {
            'type': 'aposta', 'nome_estrategia': 'Reação do Gigante',
            'emoji': '🦁', 'motivo': motivo,
            'mercado': 'Casa para Vencer', 'odd': odd_casa
        }
        return oportunidade
    else:
        # FALHA! Critérios não atendidos. Retorna o motivo.
        if debug:
            return f"Reprovado. % Vit Geral Casa: {perc_vitorias_geral_casa:.1f}% (Req: >65%), % Vit Geral Fora: {perc_vitorias_geral_fora:.1f}% (Req: <35%), Média Gols Casa: {avg_gols_marcados_casa:.2f} (Req: >1.8)"
        return None
