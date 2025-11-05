import streamlit as st
import sqlite3
import pandas as pd
import os

# --- CONFIGURACIÓN --- # <-- MODIFICADO
# Apunta a la nueva base de datos del proyecto
DB_PATH = os.path.join(os.path.dirname(__file__), "data/daily_stats.db")
TIKTOK_PROFILE_URL = "https://tiktok.com/@" # Puedes cambiar esto por Instagram si quieres

st.set_page_config(page_title="Arena Stats", layout="wide")

# --- CUSTOM CSS para el Sidebar en móvil ---
st.markdown("""
<style>
/* 1. ESTILO PARA EL BOTÓN DE LA BARRA LATERAL (HAMBURGUESA) */
[data-testid="stHeader"] button:first-child {
    background-color: #555555; /* Gris un poco más claro */
    border: 1px solid #555555; /* Borde del mismo color */
    border-radius: 5px;
    padding: 5px;
}
/* 2. COLOR DEL ICONO SVG DENTRO DEL BOTÓN DE LA BARRA LATERAL */
[data-testid="stHeader"] button:first-child svg {
    color: #FFFFFF; /* Icono blanco para la hamburguesa */
}
/* 3. RESTAURAR LOS OTROS BOTONES DE LA CABECERA A SU ESTILO NORMAL */
[data-testid="stHeader"] button:not(:first-child) {
    background-color: transparent !important; /* Fondo transparente */
    border: none !important; /* Sin borde */
    color: inherit !important; /* Heredar color de texto/icono */
    padding: 5px !important; /* Ajustar padding */
}
[data-testid="stHeader"] button:not(:first-child) svg {
    color: inherit !important; /* Heredar color de icono */
}
/* 4. AJUSTE PARA EL CONTENEDOR DE LA CABECERA */
.stApp > header {
    background-color: transparent;
    box-shadow: none;
}
</style>
""", unsafe_allow_html=True)

# ========= FUNCIONES DE BASE DE DATOS (Adaptadas) ========= #

# <-- MODIFICADO: get_conn -->
# Ahora busca la nueva DB
def get_conn():
    if not os.path.exists(DB_PATH):
        st.error("Error: No se encuentra el archivo 'daily_stats.db'. Ejecuta log_manager.py primero.")
        st.stop()
    return sqlite3.connect(DB_PATH)

# <-- MODIFICADO: get_available_dates -->
# Lee la tabla 'daily_summary' que usa fechas de texto (ej: "2025-11-04")
@st.cache_data(ttl=300)
def get_available_dates():
    conn = get_conn()
    cursor = conn.cursor()
    # La nueva tabla 'daily_summary' usa 'date' como PK
    cursor.execute("SELECT date FROM daily_summary ORDER BY date DESC")
    # Las fechas ya no son números, son texto
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ["All Time"] + dates 

# <-- MODIFICADO: get_all_players -->
# Lee la tabla 'player_stats'
@st.cache_data(ttl=300)
def get_all_players():
    conn = get_conn()
    cursor = conn.cursor()
    # La nueva tabla usa 'player'
    cursor.execute("SELECT DISTINCT player FROM player_stats ORDER BY player ASC")
    players = [row[0] for row in cursor.fetchall()]
    conn.close()
    return players

# <-- MODIFICADO: get_all_time_winners -->
# Lee la tabla 'daily_summary'
@st.cache_data(ttl=300)
def get_all_time_winners():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # La nueva tabla 'daily_summary' tiene al ganador
    cursor.execute("SELECT date, winner FROM daily_summary ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()
    if rows:
        df = pd.DataFrame(rows, columns=["Fecha", "Ganador"]) # Cambiado 'Día' a 'Fecha'
        return df
    return pd.DataFrame(columns=["Fecha", "Ganador"])

# <-- MODIFICADO: get_daily_summary -->
# Lee la tabla 'daily_summary'
@st.cache_data(ttl=300)
def get_daily_summary(date_str): # Renombrado de day_num a date_str
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Esta tabla ya tiene los datos pre-calculados
    cursor.execute("SELECT num_players, winner FROM daily_summary WHERE date = ?", (date_str,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"num_players": 0, "winner": "N/A"}

# <-- MODIFICADO: get_top_players -->
# Lee la tabla 'player_stats'
@st.cache_data(ttl=300)
def get_top_players(day_filter, stat="kills", limit=10):
    conn = get_conn()
    # La nueva DB solo soporta 'kills' y 'deaths' para esta query
    valid_stats = {"kills": "kills", "deaths": "deaths"} 
    stat_col = valid_stats.get(stat, "kills")
    
    if day_filter == "All Time":
        query = f"""
            SELECT player, SUM({stat_col}) as total_stat
            FROM player_stats GROUP BY player ORDER BY total_stat DESC LIMIT ?
        """
        params = (limit,)
    else:
        query = f"""
            SELECT player, {stat_col} as total_stat
            FROM player_stats WHERE date = ? ORDER BY total_stat DESC LIMIT ?
        """
        params = (day_filter, limit)
        
    df = pd.read_sql_query(query, conn, params=params)
    df.columns = ["Jugador", stat.capitalize()]
    conn.close()
    return df

# <-- MODIFICADO: get_player_stats (La función más cambiada) -->
# Ahora lee de TRES tablas (player_stats, ranking, daily_summary)
@st.cache_data(ttl=300)
def get_player_stats(day_filter, player):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if day_filter == "All Time":
        # Query 1: Obtener kills y muertes de player_stats
        cursor.execute("""
            SELECT 
                SUM(kills) as total_kills,
                SUM(deaths) as total_deaths
            FROM player_stats WHERE player = ?
        """, (player,))
        stats_row = cursor.fetchone()
        
        # Query 2: Obtener victorias de daily_summary
        cursor.execute("SELECT COUNT(*) as total_wins FROM daily_summary WHERE winner = ?", (player,))
        wins_row = cursor.fetchone()
        
        conn.close()
        
        if stats_row and stats_row['total_kills'] is not None:
            stats = dict(stats_row)
            stats['total_wins'] = wins_row['total_wins'] if wins_row else 0
            return stats
        return None
    else:
        # Query para un día específico, uniendo 'player_stats' y 'ranking'
        cursor.execute("""
            SELECT 
                ps.kills, ps.deaths, ps.nemesis,
                r.rank, r.time
            FROM player_stats as ps
            LEFT JOIN ranking as r ON ps.date = r.date AND ps.player = r.player
            WHERE ps.date = ? AND ps.player = ?
        """, (day_filter, player))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            stats = dict(row)
            # Renombramos las claves para que coincidan con el UI antiguo
            stats['ranking'] = stats.pop('rank')
            stats['tiempo_s'] = stats.pop('time')
            # 'nemesis' ya se llama igual que lo que esperábamos ('muerto_por')
            return stats
    return None

# ========= APP (Interfaz Rediseñada con Pestañas) ========= #

st.title("⚔️ FIGTH club: fight or unfollow")

available_dates = get_available_dates()
if not available_dates or len(available_dates) <= 1:
    st.error("No hay datos en la base de datos. Ejecuta log_manager.py al menos una vez.")
    st.stop()

all_players = get_all_players()
if not all_players:
    st.error("No se han encontrado jugadores en la base de datos.")
    st.stop()

# --- BARRA LATERAL (Sidebar) ---
all_time_label = "Historial Completo"
placeholder_label = "Escribe o selecciona tu nombre..."

st.sidebar.header("Filtros de Búsqueda")

# <-- MODIFICADO: Filtro de Fecha -->
# Ya no añade "Día ", solo usa las fechas de texto de la DB
available_dates_with_all_time = [all_time_label] + [d for d in available_dates if d != "All Time"]
selected_day_filter = st.sidebar.selectbox(
    "Seleccionar Fecha:", 
    available_dates_with_all_time
)

# Filtro de Jugador
player_list_with_placeholder = [placeholder_label] + all_players
username_input = st.sidebar.selectbox(
    "Buscar Jugador:", 
    player_list_with_placeholder
)

# Filtro de Estadísticas del Leaderboard
st.sidebar.markdown("---")
st.sidebar.subheader("Ver Leaderboard por:")
stat_to_show = st.sidebar.radio(
    "Estadística del Leaderboard:", 
    ("Kills", "Ganadores"), 
    label_visibility="collapsed"
)

# <-- MODIFICADO: LÓGICA DE TRADUCCIÓN DE FECHA -->
# Ahora es más simple: solo revisa si es "All Time"
day_to_query = "All Time"
if selected_day_filter != all_time_label:
    day_to_query = selected_day_filter # Ej: "2025-11-04"

# --- PESTAÑAS PRINCIPALES ---
tab_leaderboard, tab_stats = st.tabs(["🏆 Leaderboard", "📊 Estadísticas de Jugador"])

# --- Pestaña 1: Leaderboard ---
with tab_leaderboard:
    st.header(f"Leaderboard: {selected_day_filter}")
    
    if stat_to_show == "Kills":
        st.subheader("Top 10 - Kills")
        top_kills_df = get_top_players(day_to_query, "kills", limit=10)
        
        if not top_kills_df.empty:
            st.dataframe(top_kills_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No hay datos de Kills para {selected_day_filter}.")

    elif stat_to_show == "Ganadores":
        st.subheader("Ganadores")
        
        if day_to_query == "All Time":
            winners_df = get_all_time_winners()
            if not winners_df.empty:
                st.dataframe(winners_df, use_container_width=True, hide_index=True)
            else:
                st.info("No hay ganadores registrados.")
        else:
            summary = get_daily_summary(day_to_query)
            winner_name = summary.get('winner', 'N/A')
            if winner_name != 'N/A':
                # El UI ahora muestra la fecha completa, ej: "Ganador del Día 2025-11-04"
                st.metric(f"Ganador del Día {day_to_query}", winner_name, "👑")
            else:
                st.warning(f"No se encontró un ganador para el Día {day_to_query}.")

# --- Pestaña 2: Estadísticas de Jugador ---
with tab_stats:
    if username_input and username_input != placeholder_label:
        username = username_input
        st.header(f"Estadísticas para [{username}]({TIKTOK_PROFILE_URL}{username})")
        st.subheader(f"Filtro: {selected_day_filter}")
        
        stats = get_player_stats(day_to_query, username)
        
        if not stats:
            st.warning(f"No se encontraron estadísticas para **{username}** en **{selected_day_filter}**.")
        else:
            cols_metrics = st.columns(3)
            
            if day_to_query == "All Time":
                cols_metrics[0].metric("🏆 Victorias Totales", stats.get("total_wins", 0))
                cols_metrics[1].metric("🔪 Kills Totales", stats.get("total_kills", 0))
                cols_metrics[2].metric("☠️ Muertes Totales", stats.get("total_deaths", 0))
            
            else:
                rank = stats.get("ranking")
                # El nuevo 'ranking' del ganador es 0, no 1
                rank_display = "1º 👑" if rank == 0 else str(rank)
                cols_metrics[0].metric("📊 Ranking", rank_display)
                cols_metrics[1].metric("🔪 Kills", stats.get("kills", 0))
                
                # Manejamos el tiempo (puede ser None)
                tiempo = stats.get('tiempo_s')
                if tiempo is not None:
                    cols_metrics[2].metric("⏱️ Tiempo", f"{tiempo:.2f} s")
                else:
                    cols_metrics[2].metric("⏱️ Tiempo", "N/A")
                
                # El rank 0 es el ganador
                if rank is not None and rank != 0 and stats.get("nemesis"):
                    nemesis = stats["nemesis"]
                    if nemesis: # El nuevo 'nemesis' puede ser None
                        st.markdown(f"**Te eliminó:** [{nemesis}]({TIKTOK_PROFILE_URL}{nemesis})")
    
    else:
        st.info("Selecciona un jugador en la barra lateral para ver sus estadísticas.")
