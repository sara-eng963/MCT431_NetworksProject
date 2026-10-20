
#include "serial_link.h"

#include <stdbool.h>

#include "driver/uart.h"
#include "atr.h"
#include "slip.h"

#define SERIAL_UART UART_NUM_0
#define SERIAL_BAUD 115200

#define RX_BUFFER_SIZE 1024
#define TX_BUFFER_SIZE 512

#define MAX_ATR_SIZE \
    (ATR_HEADER_SIZE + SERIAL_LINK_MAX_PAYLOAD + ATR_CRC_SIZE)

#define MAX_SLIP_SIZE (2 * MAX_ATR_SIZE + 2)

static bool initialized = false;

esp_err_t serial_link_init(void)
{
    if (initialized) {
        return ESP_OK;
    }

    uart_config_t config = {
        .baud_rate = SERIAL_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT
    };

    esp_err_t err = uart_driver_install(
        SERIAL_UART,
        RX_BUFFER_SIZE,
        TX_BUFFER_SIZE,
        0, NULL, 0
    );

    if (err != ESP_OK) {
        return err;
    }

    err = uart_param_config(SERIAL_UART, &config);

    if (err == ESP_OK) {
        err = uart_set_pin(
            SERIAL_UART,
            1, 3,
            UART_PIN_NO_CHANGE,
            UART_PIN_NO_CHANGE
        );
    }

    if (err != ESP_OK) {
        uart_driver_delete(SERIAL_UART);
        return err;
    }

    initialized = true;
    return ESP_OK;
}

esp_err_t serial_link_send_atr(
    uint16_t test_id,
    uint32_t seq,
    const uint8_t *payload,
    uint16_t payload_len)
{
    if (!initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (payload_len > SERIAL_LINK_MAX_PAYLOAD) {
        return ESP_ERR_INVALID_SIZE;
    }

    if (payload_len > 0 && payload == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t atr_buffer[MAX_ATR_SIZE];
    uint8_t slip_buffer[MAX_SLIP_SIZE];

    size_t atr_len = 0;
    size_t slip_len = 0;

    if (!atr_encode(
            test_id, seq, payload, payload_len,
            atr_buffer, sizeof(atr_buffer), &atr_len)) {
        return ESP_FAIL;
    }

    if (!slip_encode(
            atr_buffer, atr_len,
            slip_buffer, sizeof(slip_buffer), &slip_len)) {
        return ESP_FAIL;
    }

    int written = uart_write_bytes(
        SERIAL_UART,
        slip_buffer,
        slip_len
    );

    return written == (int)slip_len ? ESP_OK : ESP_FAIL;
}
