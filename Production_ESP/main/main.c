
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_timer.h"
#include "esp_err.h"

#include "production.h"
#include "serial_link.h"
#include "app_protocol.h"

#define STATUS_INTERVAL_US 2000000LL

static production_t production;

void app_main(void)
{
    production_init(&production);
    ESP_ERROR_CHECK(serial_link_init());

    uint32_t tx_seq = 0;
    int64_t next_status_us = esp_timer_get_time();

    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(10);

    while (1) {
        int64_t now_us = esp_timer_get_time();
        production_event_t event;

        // Update production logic
        (void)production_update(
            &production,
            now_us,
            &event
        );

        // Send periodic STATUS messages
        if (now_us >= next_status_us) {

            uint8_t payload[APP_STATUS_SIZE];

            app_encode_status(
                payload,
                production.state,
                production.produced_parts
            );

            esp_err_t err = serial_link_send_atr(
                APP_ATR_ID,
                tx_seq,
                payload,
                (uint16_t)sizeof(payload)
            );

            if (err == ESP_OK) {
                tx_seq++;
            }

            next_status_us = now_us + STATUS_INTERVAL_US;
        }

        vTaskDelayUntil(&last_wake_time, period);
    }
}
