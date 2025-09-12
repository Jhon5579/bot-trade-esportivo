# estrategias.py (Versão 2.6 - Com Mapa de Nomes Exato)

# --- FUNÇÕES AUXILIARES ---

def _get_nome_corrigido(nome_time_api, contexto):
    """
    Busca o nome de time correspondente no mapa de nomes (master_team_list).
    Esta versão é exata e muito mais rápida que a busca por similaridade.
    """
    # Pega o mapa de nomes que foi carregado no main.py
    mapa_de_nomes = contexto.get('mapa_de_nomes', {})
    
    # Faz a busca direta no dicionário. Retorna o nome correspondente ou None se não encontrar.
    nome_correspondente = mapa_de_nomes.get(nome_time_api)
    
    return nome_correspondente

def _encontrar_odd_especifica(jogo, mercado):
    """Encontra a odd de um mercado específico (Home, Away, Draw)."""
    bookmakers = jogo.get('bookmakers', [])
    if not bookmakers: return None

    # Itera pelas casas de apostas para encontrar a melhor odd (ou a primeira)
    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == mercado:
                        return outcome.get('price')
    return None

# --- ESTRATÉGIAS ---

def analisar_favorito_forte_fora(jogo, contexto, debug=False):
    """Visitante com alto favoritismo estatístico."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    if (stats_fora.get('perc_vitorias_fora', 0) > 70 and
        stats_casa.get('perc_derrotas_casa', 0) > 70 and
        stats_fora.get('avg_gols_marcados_fora', 0) > 1.8 and
        stats_casa.get('avg_gols_sofridos_casa', 0) > 1.5):

        return {'type': 'pre_aprovado', 'nome_estrategia': 'Favorito Forte Fora', 'mercado': 'Visitante para Vencer', 'emoji': '🚀'}
    else:
        if debug: return "Critérios de favoritismo extremo do visitante não atendidos."
        return None

def analisar_valor_mandante_azarao(jogo, contexto, debug=False):
    """Mandante com status de azarão nas odds, mas com bom histórico em casa."""
    time_casa_api = jogo['home_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)

    if not nome_casa:
        if debug: return "Time da casa sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    odd_casa = _encontrar_odd_especifica(jogo, 'Home')

    if not odd_casa:
        if debug: return "Odd do mandante não encontrada para análise de valor."
        return None

    if (odd_casa > 2.0 and
        stats_casa.get('perc_vitorias_casa', 0) > 45 and
        stats_casa.get('avg_gols_marcados_casa', 0) > 1.5):

        return {'type': 'pre_aprovado', 'nome_estrategia': 'Valor no Mandante Azarão', 'mercado': 'Casa para Vencer', 'emoji': '💎'}
    else:
        if debug: return "Critérios de valor para o mandante azarão não atendidos."
        return None

def analisar_valor_visitante_azarao(jogo, contexto, debug=False):
    """Visitante com status de azarão nas odds, mas com bom histórico fora."""
    time_fora_api = jogo['away_team']
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_fora:
        if debug: return "Time visitante sem correspondência no histórico."
        return None

    stats_fora = contexto['stats_individuais'][nome_fora]
    odd_visitante = _encontrar_odd_especifica(jogo, 'Away')

    if not odd_visitante:
        if debug: return "Odd do visitante não encontrada para análise de valor."
        return None

    if (odd_visitante > 2.2 and
        stats_fora.get('perc_vitorias_fora', 0) > 40 and
        stats_fora.get('avg_gols_marcados_fora', 0) > 1.4):

        return {'type': 'pre_aprovado', 'nome_estrategia': 'Valor no Visitante Azarão', 'mercado': 'Visitante para Vencer', 'emoji': '💎'}
    else:
        if debug: return "Critérios de valor para o visitante azarão não atendidos."
        return None

def analisar_empate_valorizado(jogo, contexto, debug=False):
    """Busca jogos com alta probabilidade de empate com base no histórico."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    if (stats_casa.get('perc_empates_casa', 0) > 30 and
        stats_fora.get('perc_empates_fora', 0) > 30 and
        abs(stats_casa.get('avg_gols_marcados_casa', 0) - stats_fora.get('avg_gols_marcados_fora', 0)) < 0.5):

        return {'type': 'pre_aprovado', 'nome_estrategia': 'Empate Valorizado', 'mercado': 'Empate', 'emoji': '🤝'}
    else:
        if debug: return "Critérios para tendência de empate não atendidos."
        return None

def analisar_forma_recente_casa(jogo, contexto, debug=False):
    """Casa em boa forma recente contra visitante em má forma."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    forma = contexto.get('forma_recente', {})
    forma_casa = forma.get(nome_casa, [])
    forma_fora = forma.get(nome_fora, [])

    if len(forma_casa) < 5 or len(forma_fora) < 5:
        if debug: return "Times com menos de 5 jogos recentes."
        return None

    if forma_casa.count('V') >= 3 and forma_fora.count('D') >= 3:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Forma Recente (Casa Forte)', 'mercado': 'Casa para Vencer', 'emoji': '🔥'}
    else:
        if debug: return f"Reprovado. Vitórias Recentes Casa: {forma_casa.count('V')}, Derrotas Recentes Fora: {forma_fora.count('D')}"
        return None

def analisar_forma_recente_fora(jogo, contexto, debug=False):
    """VERSÃO SIMÉTRICA: Visitante em boa forma recente contra mandante em má forma."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    forma = contexto.get('forma_recente', {})
    forma_casa = forma.get(nome_casa, [])
    forma_fora = forma.get(nome_fora, [])

    if len(forma_casa) < 5 or len(forma_fora) < 5:
        if debug: return "Times com menos de 5 jogos recentes."
        return None

    if forma_casa.count('D') >= 3 and forma_fora.count('V') >= 3:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Forma Recente (Visitante Forte)', 'mercado': 'Visitante para Vencer', 'emoji': '🔥'}
    else:
        if debug: return f"Reprovado. Derrotas Recentes Casa: {forma_casa.count('D')}, Vitórias Recentes Fora: {forma_fora.count('V')}"
        return None
