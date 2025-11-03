import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime # Para mostrar la fecha actual

# --- CONFIGURACIÓN ---
DB_PATH = os.path.join(os.path.dirname(__file__), "batallas.db")

# --- FUNCIONES AUXILIARES PARA LA BASE DE DATOS (con caché de Streamlit) ---
# (@st.cache_data decora las funciones para que Streamlit guarde los resultados y no consulte la DB innecesariamente)

def get_conn():
    """Establece conexión con la base de datos SQLite."""
    return sqlite3.connect(DB_PATH)

@st.cache_data(ttl=300) # Guarda el resultado por 5 minutos (300 segundos)
def get_available_days():
    """Obtiene la lista de días disponibles en la base de datos."""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT dia FROM resultados ORDER BY dia DESC")
        # Extrae el primer elemento de cada tupla (el número del día)
        days = [row[0] for row in cursor.fetchall()]
        conn.close()
        # Devuelve "All Time" más la lista de días
        return ["All Time"] + days
    except sqlite3.Error as e:
        st.error(f"Error al obtener días disponibles: {e}")
        return ["All Time"] # Devuelve solo All Time si hay error

@st.cache_data(ttl=300)
def get_players(day_filter):
    """Obtiene la lista de jugadores para un día específico o todos."""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        if day_filter == "All Time":
            # DISTINCT asegura que cada jugador aparezca solo una vez
            cursor.execute("SELECT DISTINCT usuario FROM resultados ORDER BY usuario ASC")
        else:
            cursor.execute("SELECT usuario FROM resultados WHERE dia = ? ORDER BY usuario ASC", (day_filter,))
        players = [row[0] for row in cursor.fetchall()]
        conn.close()
        return players
    except sqlite3.Error as e:
        st.error(f"Error al obtener lista de jugadores: {e}")
        return []

@st.cache_data(ttl=300)
def get_player_stats(day_filter, player):
    """Obtiene las estadísticas detalladas de un jugador para un día o en total."""
    try:
        conn = get_conn()
        conn.row_factory = sqlite3.Row # Para acceder a columnas por nombre
        cursor = conn.cursor()

        if day_filter == "All Time":
            # Calcula estadísticas agregadas (SUMA de kills, etc.)
            cursor.execute("""
                SELECT 
                    SUM(kills) as total_kills, 
                    SUM(CASE WHEN ranking > 1 THEN 1 ELSE 0 END) as total_deaths,
                    COUNT(CASE WHEN ranking = 1 THEN 1 END) as total_wins,
                    AVG(tiempo_s) as avg_time,
                    AVG(colisiones) as avg_collisions
                FROM resultados
                WHERE usuario = ?
            """, (player,))
            row = cursor.fetchone()
            conn.close()
            if row and row['total_kills'] is not None : # Verifica si se encontró al jugador
                 return {
                    "kills": row['total_kills'],
                    "deaths": row['total_deaths'],
                    "wins": row['total_wins'],
                    "avg_time": round(row['avg_time'], 2) if row['avg_time'] else 0,
                    "avg_collisions": round(row['avg_collisions']) if row['avg_collisions'] else 0,
                    "ranking": None, # No aplica para All Time
                    "nemesis": None, # Podríamos calcularlo, pero lo omitimos por simplicidad
                    "victim": None   # Podríamos calcularlo, pero lo omitimos por simplicidad
                }
            else:
                return None # Jugador no encontrado en All Time
        else:
            # Obtiene estadísticas para un día específico
            cursor.execute("""
                SELECT kills, CASE WHEN ranking > 1 THEN 1 ELSE 0 END as deaths, ranking, tiempo_s, colisiones, muerto_por 
                FROM resultados
                WHERE dia = ? AND usuario = ?
            """, (day_filter, player))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "kills": row['kills'],
                    "deaths": row['deaths'],
                    "ranking": row['ranking'],
                    "time": row['tiempo_s'],
                    "collisions": row['colisiones'],
                    "victim": row['muerto_por'] if row['ranking'] > 1 else "GANADOR", # Muestra GANADOR si rank=1
                    "nemesis": None # No tenemos esta info directamente
                }
            else:
                return None # Jugador no encontrado para ese día
    except sqlite3.Error as e:
        st.error(f"Error al obtener estadísticas del jugador: {e}")
        return None

@st.cache_data(ttl=300)
def get_top_players(day_filter, stat="kills", limit=10):
    """Obtiene los mejores jugadores según una estadística (kills por defecto)."""
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # Aseguramos que la columna 'stat' sea válida para evitar inyección SQL
        valid_stats = ["kills", "colisiones", "tiempo_s"]
        if stat not in valid_stats:
            stat = "kills" # Valor por defecto seguro

        if day_filter == "All Time":
            # Agrupa por jugador y suma la estadística
            query = f"""
                SELECT usuario, SUM({stat}) as total_stat
                FROM resultados
                GROUP BY usuario
                ORDER BY total_stat DESC
                LIMIT ?
            """
            params = (limit,)
        else:
            # Ordena por la estadística en un día específico
            query = f"""
                SELECT usuario, {stat} as total_stat
                FROM resultados
                WHERE dia = ?
                ORDER BY total_stat DESC
                LIMIT ?
            """
            params = (day_filter, limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        # Usamos Pandas para crear un DataFrame que Streamlit muestra como tabla bonita
        return pd.DataFrame(rows, columns=["Jugador", stat.replace('_',' ').capitalize()])
    except sqlite3.Error as e:
        st.error(f"Error al obtener top players: {e}")
        return pd.DataFrame() # Devuelve tabla vacía en caso de error

@st.cache_data(ttl=300)
def get_all_winners():
    """Obtiene todos los ganadores por día."""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT dia, usuario FROM resultados WHERE ranking = 1 ORDER BY dia DESC")
        rows = cursor.fetchall()
        conn.close()
        return pd.DataFrame(rows, columns=["Día", "Ganador"])
    except sqlite3.Error as e:
        st.error(f"Error al obtener ganadores: {e}")
        return pd.DataFrame()

# ========= INICIO DE LA APLICACIÓN STREAMLIT ========= #

st.set_page_config(page_title="Arena Stats", layout="wide") # Configura título y ancho de página
st.title("📊 Estadísticas - Arena de Batalla TikTok")

# --- BARRA LATERAL (Sidebar) ---
st.sidebar.header("Filtros")
available_days = get_available_days()

if not available_days or len(available_days) <= 1: # Si solo está "All Time"
    st.error("No hay datos en la base de datos. Ejecuta la simulación primero.")
    st.stop() # Detiene la ejecución si no hay datos

selected_day = st.sidebar.selectbox("Selecciona el Día", available_days)

players = get_players(selected_day)
if not players:
    st.warning(f"No se encontraron jugadores para el día {selected_day}.")
    st.stop()

# Intenta mantener al jugador seleccionado si cambia el día, si no, selecciona el primero
if 'selected_player' not in st.session_state or st.session_state.selected_player not in players:
    st.session_state.selected_player = players[0]

selected_player = st.sidebar.selectbox(
    "Selecciona un Jugador",
    players,
    index=players.index(st.session_state.selected_player),
    key='selected_player' # Mantiene la selección entre recargas
)

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["🏆 Leaderboard", "👤 Estadísticas del Jugador"])

with tab1:
    st.subheader(f"🏆 Leaderboard - Día: {selected_day}")

    # Opciones para el leaderboard
    stat_options = {"Kills": "kills", "Colisiones": "colisiones", "Tiempo Sobrevivido": "tiempo_s"}
    chosen_stat_label = st.radio("Ordenar por:", list(stat_options.keys()), horizontal=True)
    chosen_stat_col = stat_options[chosen_stat_label]

    # Mostramos la tabla de los mejores jugadores
    top_df = get_top_players(selected_day, chosen_stat_col, limit=20) # Top 20
    if not top_df.empty:
        st.dataframe(top_df, use_container_width=True, hide_index=True)
    else:
        st.write("No hay datos suficientes para este leaderboard.")

    # Mostramos la lista de ganadores si se selecciona "All Time"
    if selected_day == "All Time":
         st.subheader("🥇 Historial de Ganadores")
         winners_df = get_all_winners()
         if not winners_df.empty:
             st.dataframe(winners_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader(f"👤 Estadísticas para **{selected_player}** - Día: {selected_day}")

    stats = get_player_stats(selected_day, selected_player)

    if not stats:
        st.warning("No se encontraron estadísticas para este jugador en el día seleccionado.")
    else:
        # Mostramos las estadísticas en columnas usando st.metric
        col1, col2, col3 = st.columns(3)
        col1.metric("🔪 Kills", stats.get("kills", 0))
        col2.metric("☠️ Muertes", stats.get("deaths", 0))
        if stats.get("wins") is not None: # Solo para All Time
             col3.metric("🏆 Victorias", stats.get("wins", 0))

        col4, col5, col6 = st.columns(3)
        if stats.get("ranking") is not None: # Solo para días específicos
             rank_display = "🏆 1º" if stats["ranking"] == 1 else str(stats["ranking"])
             col4.metric("📊 Ranking", rank_display)
        if stats.get("time") is not None:
            col5.metric("⏱️ Tiempo", f"{stats['time']:.2f} s")
        elif stats.get("avg_time") is not None:
            col5.metric("⏱️ Tiempo Prom.", f"{stats['avg_time']:.2f} s")

        if stats.get("collisions") is not None:
             col6.metric("💥 Colisiones", stats["collisions"])
        elif stats.get("avg_collisions") is not None:
             col6.metric("💥 Colisiones Prom.", f"{stats['avg_collisions']:.1f}")

        # Mostramos Némesis/Víctima solo para días específicos
        if selected_day != "All Time" and stats.get("ranking") != 1:
            st.markdown("---") # Separador
            col_victim, col_placeholder = st.columns(2) # Usamos 2 columnas
            with col_victim:
                st.markdown("##### Eliminado por:")
                victim = stats.get("victim", "N/A")
                if victim and victim != "Nadie" and victim != "GANADOR":
                     st.markdown(f"**{victim}**") # Link a TikTok si quieres: [{victim}](https://tiktok.com/@{victim})
                else:
                     st.markdown(f"_{victim}_")

# --- PIE DE PÁGINA (Opcional) ---
st.sidebar.markdown("---")
st.sidebar.info(f"Datos actualizados hasta el Día {available_days[1] if len(available_days)>1 else 'N/A'}.")