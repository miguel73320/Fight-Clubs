import streamlit as st
import sqlite3
import pandas as pd
import os

# --- CONFIGURACIÓN ---
DB_PATH = os.path.join(os.path.dirname(__file__), "batallas.db")
TIKTOK_PROFILE_URL = "https://tiktok.com/@"

st.set_page_config(page_title="Arena Stats", layout="wide")

# ========= FUNCIONES DE BASE DE DATOS (Adaptadas) ========= #

def get_conn():
    if not os.path.exists(DB_PATH):
        st.error("Error: No se encuentra el archivo 'batallas.db'. Ejecuta la simulación 'juego.py' primero.")
        st.stop()
    return sqlite3.connect(DB_PATH)

@st.cache_data(ttl=300)
def get_available_dates():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT dia FROM resultados ORDER BY dia DESC")
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ["All Time"] + dates 

@st.cache_data(ttl=300)
def get_daily_summary(day_num):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT usuario as winner FROM resultados WHERE dia = ? AND ranking = 1", (day_num,))
    winner_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(usuario) as num_players FROM resultados WHERE dia = ?", (day_num,))
    players_row = cursor.fetchone()
    conn.close()
    return {
        "num_players": players_row['num_players'] if players_row else 0,
        "winner": winner_row['winner'] if winner_row else "N/A"
    }

@st.cache_data(ttl=300)
def get_top_players(day_filter, stat="kills", limit=20):
    conn = get_conn()
    valid_stats = {"kills": "kills", "colisiones": "colisiones", "tiempo": "tiempo_s"}
    stat_col = valid_stats.get(stat, "kills")
    if day_filter == "All Time":
        query = f"""
            SELECT usuario, SUM({stat_col}) as total_stat
            FROM resultados GROUP BY usuario ORDER BY total_stat DESC LIMIT ?
        """
        params = (limit,)
    else:
        query = f"""
            SELECT usuario, {stat_col} as total_stat
            FROM resultados WHERE dia = ? ORDER BY total_stat DESC LIMIT ?
        """
        params = (day_filter, limit)
    df = pd.read_sql_query(query, conn, params=params)
    df.columns = ["Jugador", stat.capitalize()]
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_player_stats(day_filter, player):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if day_filter == "All Time":
        cursor.execute("""
            SELECT 
                SUM(kills) as total_kills,
                SUM(CASE WHEN ranking > 1 THEN 1 ELSE 0 END) as total_deaths,
                SUM(CASE WHEN ranking = 1 THEN 1 ELSE 0 END) as total_wins,
                AVG(tiempo_s) as avg_time,
                AVG(colisiones) as avg_collisions
            FROM resultados WHERE usuario = ?
        """, (player,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row and row['total_kills'] is not None else None
    else:
        cursor.execute("""
            SELECT kills, ranking, tiempo_s, colisiones, muerto_por
            FROM resultados WHERE dia = ? AND usuario = ?
        """, (day_filter, player))
        row = cursor.fetchone()
        conn.close()
        if row:
            stats = dict(row)
            stats['deaths'] = 1 if stats['ranking'] > 1 else 0
            stats['nemesis'] = stats['muerto_por']
            return stats
    return None

# ========= APP (Interfaz Rediseñada) ========= #

st.title("⚔️ fIGth club: fight or unfollow")

available_dates = get_available_dates()
if not available_dates or len(available_dates) <= 1:
    st.error("No hay datos en la base de datos. Ejecuta la simulación 'juego.py' al menos una vez.")
    st.stop()

# --- BARRA LATERAL (Sidebar) ---
st.sidebar.header("Buscar Jugador")
username_input = st.sidebar.text_input("Ingresa tu nombre de usuario:")
all_time_label = "Historial Completo"
available_dates_with_all_time = [all_time_label] + [f"Día {d}" for d in available_dates if d != "All Time"]
selected_day_filter = st.sidebar.selectbox("Filtrar por Día:", available_dates_with_all_time)

# --- LÓGICA DE BÚSQUEDA DE JUGADOR ---
if username_input:
    username = username_input.strip()
    st.header(f"📊 Estadísticas para [{username}]({TIKTOK_PROFILE_URL}{username})")
    
    # Obtenemos el día seleccionado (o "All Time")
    day_to_query = selected_day_filter
    if "Día " in selected_day_filter:
        day_to_query = int(selected_day_filter.replace("Día ", ""))
    
    stats = get_player_stats(day_to_query, username)
    
    if not stats:
        st.warning(f"No se encontraron estadísticas para **{username}** en **{selected_day_filter}**.")
    else:
        # Mostramos las estadísticas encontradas
        cols_metrics = st.columns(3)
        if day_to_query == all_time_label:
            cols_metrics[0].metric("🏆 Victorias Totales", stats.get("total_wins", 0))
            cols_metrics[1].metric("🔪 Kills Totales", stats.get("total_kills", 0))
            cols_metrics[2].metric("☠️ Muertes Totales", stats.get("total_deaths", 0))
        else:
            rank = stats.get("ranking")
            rank_display = "1º 👑" if rank == 1 else str(rank)
            cols_metrics[0].metric("📊 Ranking", rank_display)
            cols_metrics[1].metric("🔪 Kills", stats.get("kills", 0))
            cols_metrics[2].metric("⏱️ Tiempo", f"{stats.get('tiempo_s', 0):.2f} s")
            if rank != 1 and stats.get("nemesis"):
                nemesis = stats["nemesis"]
                if nemesis and nemesis not in ["Nadie", "GANADOR"]:
                    st.markdown(f"**Te eliminó:** [{nemesis}]({TIKTOK_PROFILE_URL}{nemesis})")

# --- PÁGINA PRINCIPAL (Leaderboard del Último Día) ---
else:
    # Si no se está buscando un jugador, muestra el leaderboard
    st.markdown("---")
    
    # Obtiene el día más reciente (el primero en la lista después de "All Time")
    last_day = available_dates[1] 
    summary = get_daily_summary(last_day)
    
    st.header(f"🏆 Clasificación: Última Batalla (Día {last_day})")
    
    cols_summary = st.columns(2)
    cols_summary[0].metric("Jugadores Totales", summary['num_players'])
    cols_summary[1].metric("Ganador del Día", summary['winner'])
    
    st.subheader("Mejores Kills de la Partida")
    top_kills_df = get_top_players(last_day, "kills", limit=20)
    if not top_kills_df.empty:
        st.dataframe(top_kills_df, use_container_width=True, hide_index=True)
    else:
        st.write("No hay datos de kills para este día.")

    with st.expander("Ver clasificación de otros días"):
        # Permite seleccionar un día diferente para el leaderboard
        selected_leaderboard_day = st.selectbox("Selecciona un Día para la Clasificación", available_dates)
        if selected_leaderboard_day:
            day_to_query = selected_leaderboard_day
            if "Día " in selected_leaderboard_day:
                day_to_query = int(selected_leaderboard_day.replace("Día ", ""))
            
            st.subheader(f"Clasificación por Kills ({selected_leaderboard_day})")
            top_df = get_top_players(day_to_query, "kills", limit=20)
            st.dataframe(top_df, use_container_width=True, hide_index=True)
            
