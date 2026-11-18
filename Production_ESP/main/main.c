#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_err.h"
#include "controller.h"
#include "serial_link.h"

static controller_t controller;
static uint32_t tx_seq;
static void send_payload(const uint8_t *payload, size_t len, void *context)
{
    (void)context;
    if (serial_link_send_atr(0, tx_seq, payload, (uint16_t)len) == ESP_OK) tx_seq++;
}
void app_main(void)
{
    ESP_ERROR_CHECK(serial_link_init());
    uint32_t boot_id;
    do { boot_id = esp_random(); } while (!boot_id);
    controller_init(&controller, boot_id, send_payload, NULL);
    TickType_t wake = xTaskGetTickCount();
    while (1) {
        uint8_t buffer[138];
        atr_record_t record;
        for (unsigned i=0; i<8 && serial_link_receive_atr(buffer,sizeof(buffer),&record); i++) {
            if (record.test_id==0)
                controller_receive(&controller,record.payload,record.payload_len,esp_timer_get_time());
        }
        controller_tick(&controller,esp_timer_get_time());
        vTaskDelayUntil(&wake,pdMS_TO_TICKS(10));
    }
}
