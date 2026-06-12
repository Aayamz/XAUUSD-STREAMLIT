"""Reusable pagination for any list-based view."""

import math
import streamlit as st


def paginate(items: list, page_size: int = 15, key: str = "page_num"):
    """
    Returns (page_slice, page_number, total_pages).
    Uses st.session_state[key] to track the current page.
    """
    if key not in st.session_state:
        st.session_state[key] = 1

    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(st.session_state[key], total_pages))
    st.session_state[key] = page

    start = (page - 1) * page_size
    return items[start:start + page_size], page, total_pages


def render_pagination(page: int, total_pages: int, total_items: int,
                      page_size: int, key: str) -> None:
    """Renders Previous / page info / Next below a paginated list."""
    if total_pages <= 1:
        return

    start_item = (page - 1) * page_size + 1
    end_item = min(page * page_size, total_items)

    c_info, c_prev, c_next = st.columns([4, 1, 1])

    with c_info:
        st.markdown(
            f'<div class="tb-pager-info">'
            f'Showing {start_item}\u2013{end_item} of {total_items}</div>',
            unsafe_allow_html=True,
        )
    with c_prev:
        if st.button("\u2190 Prev", key=f"{key}_prev", disabled=(page <= 1),
                     width="stretch"):
            st.session_state[key] = page - 1
            st.rerun()
    with c_next:
        if st.button("Next \u2192", key=f"{key}_next", disabled=(page >= total_pages),
                     width="stretch"):
            st.session_state[key] = page + 1
            st.rerun()
