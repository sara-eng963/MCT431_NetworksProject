
idf_component_register(
    SRCS
        "main.c"
        "production.c"
        "atr.c"
        "slip.c"
        "serial_link.c"
        "controller.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        esp_timer
        esp_driver_uart
        esp_hw_support
)
