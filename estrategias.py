# estrategias.py (Versão Final 2.9 - Com Estratégia de Tabela)

# --- FUNÇÕES AUXILIARES ---

def _get_nome_corrigido(nome_time_api, contexto):
    """
    Busca o nome de time correspondente no mapa de nomes (master_team_list).
    """
    mapa_de_nomes = contexto.get('mapa_de_nomes', {})
    nome_correspondente = mapa_de_nomes.get(nome_time_api)
    return nome_correspondente

def _encontrar_odd_especifica(jogo, mercado):
    """Encontra a odd de um mercado específico (Home, Away, Draw)."""
    bookmakers = jogo.get('bookmakers', [])
    if not bookmakers: return None
    for bookmaker in bookmakers:
        for market in bookmaker.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == mercado:
                        return outcome.get('price')
    return None

# --- NOVAS ESTRATÉGIAS ---

def analisar_confronto_de_opostos(jogo, contexto, debug=False):
    """
    Analisa jogos entre times de ponta e times do fundo da tabela.
    Usa os dados de classificação da The Rundown.
    """
    tabelas = contexto.get('tabelas_ligas', {})
    tabela_do_jogo = tabelas.get(jogo['league_id'])

    if not tabela_do_jogo:
        if debug: return "Tabela de classificação não disponível para esta liga."
        return None

    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    
    # Tentamos encontrar os nomes dos times na tabela que carregamos
    nome_casa_na_tabela = None
    nome_fora_na_tabela = None
    
    # A correspondência de nomes pode ser um desafio entre APIs.
    # Esta é uma abordagem simples. Poderia ser melhorada com o master_team_list se necessário.
    for nome_tabela in tabela_do_jogo.keys():
        if time_casa_api.lower() in nome_tabela.lower() or nome_tabela.lower() in time_casa_api.lower():
            nome_casa_na_tabela = nome_tabela
        if time_fora_api.lower() in nome_tabela.lower() or nome_tabela.lower() in time_fora_api.lower():
            nome_fora_na_tabela = nome_tabela

    if not nome_casa_na_tabela or not nome_fora_na_tabela:
        if debug: return "Time sem correspondência na tabela de classificação."
        return None
        
    stats_casa = tabela_do_jogo.get(nome_casa_na_tabela)
    stats_fora = tabela_do_jogo.get(nome_fora_na_tabela)

    if not stats_casa or not stats_fora:
        if debug: return "Stats não encontrados para um dos times na tabela."
        return None
        
    posicao_casa = stats_casa.get('rank', 99)
    posicao_fora = stats_fora.get('rank', 99)

    # Regra: Um time no G4 (top 4) contra um time nos últimos 4 (posição >= 16 para ligas de 20)
    if posicao_casa <= 4 and posicao_fora >= 16:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Confronto de Opostos (Casa Fav)', 'mercado': 'Casa para Vencer', 'emoji': '🥇'}
    
    if posicao_fora <= 4 and posicao_casa >= 16:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Confronto de Opostos (Fora Fav)', 'mercado': 'Visitante para Vencer', 'emoji': '🥇'}

    if debug: return f"Não é um confronto de opostos (Posições: {posicao_casa}º vs {posicao_fora}º)."
    return None

# --- ESTRATÉGIAS EXISTENTES ---

def analisar_favorito_forte_fora(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)
    if not nome_casa or not nome_fora: return "Time sem correspondência no histórico." if debug else None
    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]
    if (stats_fora.get('perc_vitorias_fora', 0) > 70 and stats_casa.get('perc_derrotas_casa', 0) > 70):
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Favorito Forte Fora', 'mercado': 'Visitante para Vencer', 'emoji': '🚀'}
    return "Critérios de favoritismo extremo do visitante não atendidos." if debug else None

def analisar_valor_mandante_azarao(jogo, contexto, debug=False):
    time_casa_api = jogo['home_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    if not nome_casa: return "Time da casa sem correspondência no histórico." if debug else None
    stats_casa = contexto['stats_individuais'][nome_casa]
    odd_casa = _encontrar_odd_especifica(jogo, 'Home')
    if not odd_casa: return "Odd do mandante não encontrada." if debug else None
    if (odd_casa > 2.0 and stats_casa.get('perc_vitorias_casa', 0) > 45):
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Valor no Mandante Azarão', 'mercado': 'Casa para Vencer', 'emoji': '💎'}
    return "Critérios de valor para o mandante azarão não atendidos." if debug else None

def analisar_valor_visitante_azarao(jogo, contexto, debug=False):
    time_fora_api = jogo['away_team']
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)
    if not nome_fora: return "Time visitante sem correspondência no histórico." if debug else None
    stats_fora = contexto['stats_individuais'][nome_fora]
    odd_visitante = _encontrar_odd_especifica(jogo, 'Away')
    if not odd_visitante: return "Odd do visitante não encontrada." if debug else None
    if (odd_visitante > 2.2 and stats_fora.get('perc_vitorias_fora', 0) > 40):
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Valor no Visitante Azarão', 'mercado': 'Visitante para Vencer', 'emoji': '💎'}
    return "Critérios de valor para o visitante azarão não atendidos." if debug else None

def analisar_empate_valorizado(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)
    if not nome_casa or not nome_fora: return "Time sem correspondência no histórico." if debug else None
    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]
    if (stats_casa.get('perc_empates_casa', 0) > 30 and stats_fora.get('perc_empates_fora', 0) > 30):
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Empate Valorizado', 'mercado': 'Empate', 'emoji': '🤝'}
    return "Critérios para tendência de empate não atendidos." if debug else None

def analisar_forma_recente_casa(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)
    if not nome_casa or not nome_fora: return "Time sem correspondência no histórico." if debug else None
    forma = contexto.get('forma_recente', {}); forma_casa = forma.get(nome_casa, []); forma_fora = forma.get(nome_fora, [])
    if len(forma_casa) < 5 or len(forma_fora) < 5: return "Times com menos de 5 jogos recentes." if debug else None
    if forma_casa.count('V') >= 3 and forma_fora.count('D') >= 3:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Forma Recente (Casa Forte)', 'mercado': 'Casa para Vencer', 'emoji': '🔥'}
    return f"Reprovado. Vitórias Recentes Casa: {forma_casa.count('V')}, Derrotas Recentes Fora: {forma_fora.count('D')}" if debug else None

def analisar_forma_recente_fora(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)
    if not nome_casa or not nome_fora: return "Time sem correspondência no histórico." if debug else None
    forma = contexto.get('forma_recente', {}); forma_casa = forma.get(nome_casa, []); forma_fora = forma.get(nome_fora, [])
    if len(forma_casa) < 5 or len(forma_fora) < 5: return "Times com menos de 5 jogos recentes." if debug else None
    if forma_casa.count('D') >= 3 and forma_fora.count('V') >= 3:
        return {'type': 'pre_aprovado', 'nome_estrategia': 'Forma Recente (Visitante Forte)', 'mercado': 'Visitante para Vencer', 'emoji': '🔥'}
    return f"Reprovado. Derrotas Recentes Casa: {forma_casa.count('D')}, Vitórias Recentes Fora: {forma_fora.count('V')}" if debug else None