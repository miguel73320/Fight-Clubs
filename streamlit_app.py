import streamlit as st
import sqlite3
import pandas as pd
import os

# --- CONFIGURACIÓN ---
# Usamos nuestra base de datos 'batallas.db'
DB_PATH = os.path.join(os.path.dirname(__file__), "batallas.db")
TIKTOK_PROFILE_URL = "https://tiktok.com/@"

# ========= FUNCIONES DE BASE DE DATOS (ADAPTADAS A 'resultados') ========= #

def get_conn():
    """Se conecta a nuestra base de datos 'batallas.db'."""
    if not os.path.exists(DB_PATH):
        st.error("Error: No se encuentra el archivo 'batallas.db'. Ejecuta la simulación 'juego.py' primero.")
        st.stop()
    return sqlite3.connect(DB_PATH)

@st.cache_data(ttl=300)
def get_available_dates():
    """Obtiene los días ('dia') de nuestra tabla 'resultados'."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT dia FROM resultados ORDER BY dia DESC")
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ["All Time"] + dates 

@st.cache_data(ttl=300)
def get_daily_summary(day_num):
    """Obtiene el ganador y el número de jugadores para un día."""
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
def get_players(day_filter):
    """Obtiene los jugadores ('usuario') de nuestra tabla 'resultados'."""
    conn = get_conn()
    cursor = conn.cursor()
    if day_filter == "All Time":
        cursor.execute("SELECT DISTINCT usuario FROM resultados ORDER BY usuario ASC")
    else:
        cursor.execute("SELECT usuario FROM resultados WHERE dia = ? ORDER BY usuario ASC", (day_filter,))
    players = [row[0] for row in cursor.fetchall()]
    conn.close()
    return players

@st.cache_data(ttl=300)
def get_top_players(day_filter, stat="kills", limit=10):
    """Obtiene los mejores jugadores según 'kills', 'colisiones', o 'tiempo_s'."""
    conn = get_conn()
    
    valid_stats = {"kills": "kills", "colisiones": "colisiones", "tiempo": "tiempo_s"}
    stat_col = valid_stats.get(stat, "kills") # Default a kills por seguridad

    if day_filter == "All Time":
        query = f"""
            SELECT usuario, SUM({stat_col}) as total_stat
            FROM resultados
            GROUP BY usuario
            ORDER BY total_stat DESC
            LIMIT ?
        """
        params = (limit,)
    else:
        query = f"""
            SELECT usuario, {stat_col} as total_stat
            FROM resultados
            WHERE dia = ?
            ORDER BY total_stat DESC
            LIMIT ?
        """
        params = (day_filter, limit)
    
    df = pd.read_sql_query(query, conn, params=params)
    df.columns = ["Jugador", stat.capitalize()] # Renombra columnas
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_player_stats(day_filter, player):
    """Obtiene las estadísticas de un jugador desde nuestra tabla 'resultados'."""
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
            FROM resultados
            WHERE usuario = ?
        """, (player,))
        row = cursor.fetchone()
        conn.close()
        if row and row['total_kills'] is not None:
            return dict(row)
    else:
        cursor.execute("""
            SELECT kills, ranking, tiempo_s, colisiones, muerto_por
            FROM resultados
            WHERE dia = ? AND usuario = ?
        """, (day_filter, player))
        row = cursor.fetchone()
        conn.close()
        if row:
            stats = dict(row)
            stats['deaths'] = 1 if stats['ranking'] > 1 else 0
            stats['nemesis'] = stats['muerto_por'] # Asignamos 'muerto_por' a 'nemesis'
            return stats
    return None

@st.cache_data(ttl=300)
def get_all_winners():
    """Obtiene todos los ganadores ('usuario') de nuestra tabla 'resultados'."""
    conn = get_conn()
    df = pd.read_sql_query("SELECT dia, usuario FROM resultados WHERE ranking = 1 ORDER BY dia DESC", conn)
    df.columns = ["Día", "Ganador"] # Renombramos para la tabla
    conn.close()
    return df

@st.cache_data(ttl=300)
def get_wins(player):
    """Cuenta las victorias (ranking = 1) de un jugador."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM resultados WHERE ranking = 1 AND usuario = ?", (player,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ========= APP ========= #

st.set_page_config(page_title="Arena Stats", layout="wide")
# 1. Título (se mantiene en inglés como pediste)
st.title("⚔️ fIGth club: fight or unfollow")

# 2. Barra Lateral (Sidebar)
available_dates = get_available_dates()
if not available_dates or len(available_dates) <= 1:
    st.error("No hay datos en la base de datos. Ejecuta la simulación 'juego.py' al menos una vez.")
    st.stop()

# --- TRADUCCIONES ---
selected_date_label = "Selecciona el Día"
all_time_label = "All Time"
available_dates[0] = all_time_label # Reemplaza "All Time"
selected_date = st.sidebar.selectbox(selected_date_label, available_dates)

players = get_players(selected_date)
if not players:
    st.warning(f"No se encontraron jugadores para {selected_date}")
    st.stop()

if "selected_player" not in st.session_state:
    st.session_state.selected_player = players[0]

if st.session_state.selected_player not in players:
    st.sidebar.warning(f"No hay datos para **{st.session_state.selected_player}** en {selected_date}")

selected_player = st.sidebar.selectbox(
    "Selecciona un Jugador",
    players,
    index=players.index(st.session_state.selected_player) if st.session_state.selected_player in players else 0,
    key="selected_player"
)

# 3. Pestañas (Tabs)
tab1, tab2 = st.tabs(["🏆 Clasificación", "📊 Estadísticas del Jugador"])

with tab1:
    summary = get_daily_summary(selected_date) if selected_date != all_time_label else None
    n_players = summary['num_players'] if summary else len(players)
    
    st.subheader(f"🏆 Clasificación para {selected_date} — {n_players} jugadores")
    
    stat_choice_label = st.sidebar.radio("Estadística de Clasificación", ["Ganadores", "Kills", "Colisiones", "Tiempo"])
    
    top_df = pd.DataFrame()
    if stat_choice_label == "Ganadores":
        if selected_date == all_time_label:
            top_df = get_all_winners()
        else: 
            winner = summary['winner'] if summary else "N/A"
            st.markdown(f"🏅 El ganador para {selected_date} es **[{winner}]({TIKTOK_PROFILE_URL}{winner})**!")
    else:
        stat_map = {"Kills": "kills", "Colisiones": "colisiones", "Tiempo": "tiempo_s"}
        top_df = get_top_players(selected_date, stat_map[stat_choice_label], limit=10)
    
    if not top_df.empty:
        st.dataframe(top_df, use_container_width=True, hide_index=True)

with tab2:
    st.header(f"📊 Estadísticas para [{selected_player}]({TIKTOK_PROFILE_URL}{selected_player})")

    stats = get_player_stats(selected_date, selected_player)
    if not stats:
        st.write("No hay estadísticas disponibles para este jugador en la fecha seleccionada.")
    else:
        cols = st.columns(2)
        with cols[0]:
            st.metric("🔪 Kills", stats["kills"])
        with cols[1]:
            st.metric("☠️ Muertes", stats["deaths"])

        # Fila 2
        cols2 = st.columns(2)
        if selected_date == all_time_label:
            with cols2[0]:
                st.metric("🏅 Victorias", stats["total_wins"])
            with cols2[1]:
                 st.metric("⏱️ Tiempo Prom.", f"{stats['avg_time']:.2f} s")
        else:
            rank = stats.get("ranking")
            if rank == 1:
                with cols2[0]:
                    st.metric("Ranking", "1º 👑")
            elif rank is not None:
                with cols2[0]:
                    st.metric("Ranking", rank)
            
            time = stats.get("time")
            if time is not None:
                with cols2[1]:
                    st.metric("⏱️ Tiempo", f"{time:.2f} s")

        # Némesis (quién te eliminó)
        if selected_date != all_time_label and stats.get("nemesis"):
            st.markdown("---")
            st.markdown("### Némesis (Te eliminó)")
            nemesis = stats["nemesis"]
            if nemesis and nemesis not in ["Nadie", "GANADOR"]:
                st.markdown(f"**[{nemesis}]({TIKTOK_PROFILE_URL}{nemesis})**")
            else:
                st.write("Nadie (o ganaste).")
st.sidebar.info(f"Datos actualizados hasta el Día {available_days[1] if len(available_days)>1 else 'N/A'}.")
