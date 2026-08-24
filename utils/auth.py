import streamlit as st

def require_edit_access():
    if st.session_state.get("edit_unlocked"):
        return True

    st.subheader("🔒 Edit access required")
    pw = st.text_input("Password", type="password")
    if st.button("Unlock"):
        if pw == st.secrets["edit_password"]:
            st.session_state["edit_unlocked"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False