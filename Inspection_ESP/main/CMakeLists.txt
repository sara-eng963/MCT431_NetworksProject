idf_component_register(SRCS "main.c" "inspection.c" INCLUDE_DIRS "."
    PRIV_REQUIRES esp_timer esp_hw_support esp_driver_uart esp_wifi esp_event
    esp_netif nvs_flash lwip json)
