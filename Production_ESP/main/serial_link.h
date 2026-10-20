
#ifndef SERIAL_LINK_H
#define SERIAL_LINK_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

// Maximum payload supported by this implementation.
#define SERIAL_LINK_MAX_PAYLOAD 128U

esp_err_t serial_link_init(void);

esp_err_t serial_link_send_atr(
    uint16_t test_id,
    uint32_t seq,
    const uint8_t *payload,
    uint16_t payload_len
);

#endif
