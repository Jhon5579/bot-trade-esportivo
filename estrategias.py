# estrategias.py
from thefuzz import process

# --- FUNÇÕES AUXILIARES ---

def _get_nome_corrigido(nome_time_api, contexto):
    """
    Função inteligente que busca o nome de time mais parecido no nosso banco de dados.
    Usa um cache simples para não repetir a busca para o mesmo time na mesma execução.
    Retorna o nome corrigido do time como encontrado no arquivo histórico.
    """
    if 'cache_nomes' not in contexto:
        contexto['cache_nomes'] = {}
        contexto['lista_nomes_historico'] = list(contexto.get('stats_individuais', {}).keys())

    if nome_time_api in contexto['cache_nomes']:
        return contexto['cache_nomes'][nome_time_api]

    if not contexto['lista_nomes_historico']:
        return None

    melhor_match = process.extractOne(nome_time_api, contexto['lista_nomes_historico'], score_cutoff=85)

    if melhor_match:
        nome_correspondente = melhor_match[0]
        contexto['cache_nomes'][nome_time_api] = nome_correspondente
        return nome_correspondente
    else:
        contexto['cache_nomes'][nome_time_api] = None
        return None

def _encontrar_odd_especifica(jogo, mercado):
    """Encontra a odd de um mercado específico (Home, Away, Draw)."""
    bookmakers = jogo.get('bookmakers', [])
    if not bookmakers: return None

    for market in bookmakers[0].get('markets', []):
        if market.get('key') == 'h2h':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == mercado:
                    return outcome.get('price')
    return None

# --- ESTRATÉGIAS DE ANÁLISE ---

def analisar_mandante_forte_vs_visitante_fraco(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    perc_vitorias_casa = stats_casa.get('perc_vitorias_casa', 0)
    perc_derrotas_fora = stats_fora.get('perc_derrotas_fora', 0)

    if perc_vitorias_casa >= 60.0 and perc_derrotas_fora >= 60.0:
        motivo = f"Casa vence {perc_vitorias_casa:.1f}% em casa / Visitante perde {perc_derrotas_fora:.1f}% fora."
        odd = _encontrar_odd_especifica(jogo, 'Home')
        return {'type': 'aposta', 'nome_estrategia': 'Mandante Forte vs Visitante Fraco', 'mercado': 'Casa para Vencer', 'motivo': motivo, 'odd': odd}
    else:
        if debug: return f"Reprovado. Vitórias Casa: {perc_vitorias_casa:.1f}%, Derrotas Fora: {perc_derrotas_fora:.1f}%"
        return None

def analisar_visitante_forte_vs_mandante_fraco(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    perc_derrotas_casa = 100 - stats_casa.get('perc_vitorias_casa', 100)
    perc_vitorias_fora = 100 - stats_fora.get('perc_derrotas_fora', 100)

    if perc_vitorias_fora >= 60.0 and perc_derrotas_casa >= 60.0:
        motivo = f"Visitante vence {perc_vitorias_fora:.1f}% fora / Mandante perde {perc_derrotas_casa:.1f}% em casa."
        odd = _encontrar_odd_especifica(jogo, 'Away')
        return {'type': 'aposta', 'nome_estrategia': 'Visitante Forte vs Mandante Fraco', 'mercado': 'Visitante para Vencer', 'motivo': motivo, 'odd': odd}
    else:
        if debug: return f"Reprovado. Vitórias Fora: {perc_vitorias_fora:.1f}%, Derrotas Casa: {perc_derrotas_casa:.1f}%"
        return None

def analisar_classico_de_gols(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico para H2H."
        return None

    h2h_key = '|'.join(sorted([nome_casa, nome_fora]))
    confronto = contexto.get('stats_h2h', {}).get(h2h_key)

    if not confronto:
        if debug: return "Sem histórico H2H."
        return None

    avg_gols_h2h = confronto.get('avg_gols_h2h', 0)
    total_jogos_h2h = confronto.get('total_jogos_h2h', 0)

    if avg_gols_h2h > 3.0 and total_jogos_h2h >= 3:
        motivo = f"Média de {avg_gols_h2h:.2f} gols nos últimos {total_jogos_h2h} confrontos."
        return {'type': 'aposta', 'nome_estrategia': 'Clássico de Gols (Over 2.5)', 'mercado': 'Mais de 2.5 Gols', 'motivo': motivo, 'odd': 1.85}
    else:
        if debug: return f"Reprovado. Média Gols H2H: {avg_gols_h2h:.2f}, Jogos H2H: {total_jogos_h2h}"
        return None

def analisar_forma_recente_casa(jogo, contexto, debug=False):
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

    vitorias_casa = forma_casa.count('V')
    derrotas_fora = forma_fora.count('D')

    if vitorias_casa >= 3 and derrotas_fora >= 3:
        motivo = f"Forma Recente: Casa com {vitorias_casa}V/5j vs Visitante com {derrotas_fora}D/5j."
        odd = _encontrar_odd_especifica(jogo, 'Home')
        return {'type': 'aposta', 'nome_estrategia': 'Forma Recente (Casa Forte)', 'mercado': 'Casa para Vencer', 'motivo': motivo, 'odd': odd}
    else:
        if debug: return f"Reprovado. Vitórias Recentes Casa: {vitorias_casa}, Derrotas Recentes Fora: {derrotas_fora}"
        return None

def analisar_forma_recente_fora(jogo, contexto, debug=False):
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

    derrotas_casa = forma_casa.count('D')
    vitorias_fora = forma_fora.count('V')

    if derrotas_casa >= 3 and vitorias_fora >= 3:
        motivo = f"Forma Recente: Visitante com {vitorias_fora}V/5j vs Mandante com {derrotas_casa}D/5j."
        odd = _encontrar_odd_especifica(jogo, 'Away')
        return {'type': 'aposta', 'nome_estrategia': 'Forma Recente (Visitante Forte)', 'mercado': 'Visitante para Vencer', 'motivo': motivo, 'odd': odd}
    else:
        if debug: return f"Reprovado. Derrotas Recentes Casa: {derrotas_casa}, Vitórias Recentes Fora: {vitorias_fora}"
        return None

def analisar_ambas_marcam(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    if (stats_casa.get('avg_gols_marcados_casa', 0) > 1.4 and
        stats_casa.get('avg_gols_sofridos_casa', 0) > 0.8 and
        stats_fora.get('avg_gols_marcados_fora', 0) > 1.2 and
        stats_fora.get('avg_gols_sofridos_fora', 0) > 0.8):

        motivo = "Ambos os times possuem ataques fortes e defesas que costumam sofrer gols."
        return {'type': 'aposta', 'nome_estrategia': 'Ambas Marcam', 'mercado': 'Ambas Marcam - Sim', 'motivo': motivo, 'odd': 1.80}
    else:
        if debug: return "Times não se encaixam no padrão de ataque forte e defesa vulnerável."
        return None

def analisar_empate(jogo, contexto, debug=False):
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    perc_vitorias_geral_casa = stats_casa.get('perc_vitorias_geral', 0)
    perc_vitorias_geral_fora = stats_fora.get('perc_vitorias_geral', 0)
    diff_forca = abs(perc_vitorias_geral_casa - perc_vitorias_geral_fora)
    media_gols_jogo = (stats_casa.get('avg_gols_marcados_casa', 0) + stats_fora.get('avg_gols_marcados_fora', 0)) / 2

    if diff_forca < 10 and media_gols_jogo < 1.3:
        motivo = f"Equipes com forças equivalentes ({diff_forca:.1f}% de dif.) e tendência a poucos gols (média {media_gols_jogo:.2f})."
        odd = _encontrar_odd_especifica(jogo, 'Draw')
        return {'type': 'aposta', 'nome_estrategia': 'Tendência de Empate', 'mercado': 'Empate', 'motivo': motivo, 'odd': odd}
    else:
        if debug: return f"Dif. de força ({diff_forca:.1f}%) ou média de gols ({media_gols_jogo:.2f}) fora do padrão."
        return None