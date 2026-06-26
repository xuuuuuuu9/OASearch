import os

import reflex as rx


config = rx.Config(
    app_name="frontend",
    app_module_import="frontend.app",
    api_url=os.getenv("NP_OA_API_URL", "http://127.0.0.1:8000"),
    plugins=[
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(
                appearance="light",
                accent_color="green",
                gray_color="sage",
                radius="small",
                scaling="100%",
            ),
        )
    ],
    disable_plugins=[rx.plugins.SitemapPlugin],
)
