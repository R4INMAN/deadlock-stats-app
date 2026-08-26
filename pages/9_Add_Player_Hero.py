import streamlit as st
from utils import data_io, ui
from utils.auth import require_edit_access

if not require_edit_access():
    st.stop()
    
st.set_page_config(page_title="Add Player / Hero", page_icon="assets/ui/puddle_punch.png", layout="wide")
ui.page_header("Add Player / Hero", "Register someone new before their first game.")

players = data_io.load_players()
heroes = data_io.load_heroes()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Add a player")
    with st.form("add_player_form", clear_on_submit=True):
        name = st.text_input("Player name")
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Add player")
        if submitted:
            if not name.strip():
                st.error("Name can't be empty.")
            elif name in players:
                st.error(f"{name} already exists.")
            else:
                data_io.add_player(name.strip(), notes.strip())
                st.success(f"Added player {name}.")
                st.rerun()

    st.markdown(f"**Current players ({len(players)}):**")
    st.dataframe(sorted(players.keys()), use_container_width=True, hide_index=True)

with col2:
    st.subheader("Add a hero")
    with st.form("add_hero_form", clear_on_submit=True):
        hero_name = st.text_input("Hero name")
        submitted_h = st.form_submit_button("Add hero")
        if submitted_h:
            if not hero_name.strip():
                st.error("Name can't be empty.")
            elif hero_name in heroes:
                st.error(f"{hero_name} already exists.")
            else:
                data_io.add_hero(hero_name.strip())
                st.success(f"Added hero {hero_name}.")
                st.rerun()

    st.markdown(f"**Current heroes ({len(heroes)}):**")
    st.dataframe(sorted(heroes), use_container_width=True, hide_index=True)

ui.brand_footer()
