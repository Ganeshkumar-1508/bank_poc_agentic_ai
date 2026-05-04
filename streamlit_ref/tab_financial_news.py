# tab_financial_news.py  —  Financial News Tab for Fixed Deposit Advisor
import os
import requests as _nd_requests
import streamlit as st


def render_financial_news_tab():
    """Render the Financial News tab."""
    st.markdown("## Financial News")
    st.markdown(
        "Latest financial and business news for your region, powered by NewsData.io."
    )

    _NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

    def _country_to_newsdata_code(country_code: str) -> str:
        """Map country code to newsdata.io 2-letter ISO code."""
        if not country_code or country_code.upper() in ("WW", "WORLDWIDE"):
            return "us"
        return country_code.lower()[:2]

    def fetch_financial_news(country_code: str) -> dict:
        nd_country = _country_to_newsdata_code(country_code)
        # /market endpoint returns only financial, stock market, and business news natively
        url = "https://newsdata.io/api/1/market"
        params = {
            "apikey": _NEWSDATA_API_KEY,
            "country": nd_country,
            "language": "en",
            "removeduplicate": 1,
        }
        try:
            resp = _nd_requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    _region_info = st.session_state.user_region
    _country_code = _region_info.get("country_code", "WW")
    _country_name = _region_info.get("country_name", "Worldwide")

    col_news_hdr, col_news_refresh = st.columns([4, 1])
    with col_news_hdr:
        st.caption(
            f"Showing news for: {_country_name}  |  country code: {_country_code.lower()[:2]}"
        )
    with col_news_refresh:
        _refresh_news = st.button("Refresh", key="news_refresh_btn")

    if not _NEWSDATA_API_KEY:
        st.warning(
            "NEWSDATA_API_KEY is not set in your .env file. "
            "Add NEWSDATA_API_KEY=your_key_here to .env and restart the app."
        )
    else:
        _news_cache_key = f"news_data_{_country_code}"
        if _news_cache_key not in st.session_state or _refresh_news:
            with st.spinner("Fetching latest news..."):
                st.session_state[_news_cache_key] = fetch_financial_news(_country_code)

        _news_data = st.session_state.get(_news_cache_key, {})

        if _news_data.get("status") == "error":
            st.error(
                f"Failed to fetch news: {_news_data.get('message', 'Unknown error')}"
            )
        elif _news_data.get("status") == "success":
            _articles = _news_data.get("results", [])
            if not _articles:
                st.info("No articles found for your region right now. Try refreshing.")
            else:
                st.markdown(f"**{len(_articles)} articles found**")
                st.markdown("---")
                for _article in _articles:
                    _title = _article.get("title") or "Untitled"
                    _desc = _article.get("description") or ""
                    _source = (
                        _article.get("source_name")
                        or _article.get("source_id")
                        or "Unknown"
                    )
                    _pub_date = _article.get("pubDate") or ""
                    _link = _article.get("link") or ""
                    _image = _article.get("image_url") or ""
                    _category = (
                        ", ".join(_article.get("category") or []).title() or "General"
                    )

                    with st.container():
                        if _image:
                            img_col, txt_col = st.columns([1, 3])
                            with img_col:
                                try:
                                    st.image(_image, use_container_width=True)
                                except Exception:
                                    pass
                            with txt_col:
                                st.markdown(f"### {_title}")
                                if _desc:
                                    st.markdown(
                                        _desc[:300]
                                        + ("..." if len(_desc) > 300 else "")
                                    )
                                m1, m2, m3 = st.columns(3)
                                m1.caption(f"Source: {_source}")
                                m2.caption(
                                    f"Date: {_pub_date[:10] if _pub_date else 'N/A'}"
                                )
                                m3.caption(f"Category: {_category}")
                                if _link:
                                    st.markdown(f"[Read full article]({_link})")
                        else:
                            st.markdown(f"### {_title}")
                            if _desc:
                                st.markdown(
                                    _desc[:300] + ("..." if len(_desc) > 300 else "")
                                )
                            m1, m2, m3 = st.columns(3)
                            m1.caption(f"Source: {_source}")
                            m2.caption(
                                f"Date: {_pub_date[:10] if _pub_date else 'N/A'}"
                            )
                            m3.caption(f"Category: {_category}")
                            if _link:
                                st.markdown(f"[Read full article]({_link})")
                        st.markdown("---")
        else:
            st.info("Press Refresh to load the latest financial news.")
